"""Recuperacion de conocimiento con los filtros dentro del SQL (ADR-0013).

Este modulo tiene **una sola puerta**: `buscar_conocimiento_autorizado`. No
existe otra forma de leer `knowledge_chunks` desde la capa de IA, y hay una
prueba de arquitectura que recorre el arbol de sintaxis del proyecto para
verificarlo.

Por que pre-filtro y no post-filtro
-----------------------------------
El patron habitual en los tutoriales de RAG es recuperar los `k` fragmentos
mas parecidos y descartar despues los no autorizados. Tiene dos fallos, y el
segundo se nota menos que el primero:

1. **Seguridad.** Cualquier olvido en el descarte es una fuga. Y el descarte
   vive en Python, donde una condicion nueva se anade en un sitio y se olvida
   en otro.
2. **Funcional.** Si los `k` mas parecidos pertenecen todos a otra sede, el
   resultado queda **vacio** aunque existiera documentacion valida. El usuario
   ve «no tengo informacion» sobre algo que si esta documentado.

Aqui el motor solo considera fragmentos autorizados, asi que `k` resultados
son `k` resultados utiles.

El detalle que sostiene todo esto
---------------------------------
La busqueda es hibrida: dos rankings, uno vectorial y uno textual, fusionados
con RRF. Eso significa **dos subconsultas**, y si los filtros de una
divergieran de los de la otra aunque fuera en una condicion, la rama mas laxa
seria la fuga.

Por eso las condiciones se construyen **una sola vez**, en `_condiciones`, y
se aplican a las dos. No es una comodidad: es la razon de que la funcion
exista. Hay una prueba que comprueba que ambas ramas filtran igual.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, Text, and_, exists, func, literal, not_, or_, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.modulos.conocimiento.modelos import (
    ESTADOS_RECUPERABLES,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    KnowledgePermission,
    PrincipalConocimiento,
)
from app.nucleo.autorizacion import NivelSensibilidad
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)

# Constante de la fusion RRF. 60 es el valor del articulo original de Cormack
# y compania, y el que usan la mayoria de implementaciones. Su efecto es
# amortiguar la diferencia entre las primeras posiciones: sin ella, el primero
# de una lista aplastaria a los demas.
K_RRF = 60

# Tope de fragmentos que se devuelven aunque se pida mas. Un contexto enorme
# no mejora la respuesta -- el modelo se pierde en el medio -- y multiplica el
# coste de cada consulta.
LIMITE_MAXIMO = 20

# =========================================================================
#  Umbral de similitud de la rama vectorial.
#
#  Sin el, la busqueda vectorial SIEMPRE devuelve candidatos: ordena por
#  distancia y entrega los N primeros, por lejos que esten. Eso significa que
#  «no tengo informacion aprobada» (RF-O06) no se dispararia casi nunca, y el
#  agente citaria como fuente el documento menos irrelevante que encontrase.
#
#  La distancia coseno de pgvector va de 0 (identico) a 2 (opuesto), y la
#  similitud es `1 - distancia`. Un umbral de similitud de 0.35 se traduce en
#  una distancia maxima de 0.65.
#
#  El valor por defecto viene de `RAG_UMBRAL_SIMILITUD` y **se debe recalibrar
#  con el modelo real**: lo que es «parecido» depende del modelo, y el
#  simulado no mide parecido en absoluto.
# =========================================================================
UMBRAL_SIMILITUD_POR_DEFECTO = 0.35


@dataclass(frozen=True, slots=True)
class ContextoAutorizacion:
    """Con que permisos se busca. Es un parametro **obligatorio**.

    No tiene valores por defecto a proposito. Un contexto con defaults
    permisivos seria la forma mas facil de introducir una fuga: bastaria
    olvidar un campo al construirlo.
    """

    clinica_id: uuid.UUID
    # Sedes y especialidades autorizadas. `None` significa «todas» y la lista
    # vacia significa **ninguna**, igual que en el resto del sistema: un
    # ambito vacio no da acceso (docs/security.md).
    sedes: frozenset[uuid.UUID] | None
    especialidades: frozenset[uuid.UUID] | None
    nivel_maximo: NivelSensibilidad
    # Instante con el que se evalua la vigencia. Se pasa en lugar de leer el
    # reloj aqui para que una prueba pueda situarse antes o despues de que un
    # documento venza (ADR-0010).
    ahora: datetime
    # Identidad y roles del personal para evaluar ACL explícitas por documento.
    # Los códigos vienen del principal validado, nunca de la petición.
    actor_id: uuid.UUID | None
    role_ids: frozenset[uuid.UUID]
    # El agente solo puede citar documentos cuyo ACL habilite ambos usos.
    uso_agente: bool


@dataclass(frozen=True, slots=True)
class FragmentoRecuperado:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version: int
    indice_fragmento: int
    contenido: str
    # Posiciones en cada ranking, y la puntuacion fusionada. Se devuelven para
    # que la evaluacion (RF-O08) pueda medir que aporta cada mitad de la
    # busqueda hibrida, en lugar de tratarla como una caja negra.
    posicion_vectorial: int | None
    posicion_textual: int | None
    puntuacion: float

    @property
    def referencia(self) -> str:
        """Cita legible, para acompanar al texto en el prompt (RF-O04)."""
        return f"doc:{self.document_id}#v{self.version}:{self.indice_fragmento}"


def condicion_acl_documento(
    document_id: InstrumentedAttribute[uuid.UUID] | ColumnElement[uuid.UUID],
    contexto: ContextoAutorizacion,
) -> ColumnElement[bool]:
    """Filtra una fila por su ACL opcional y el principal autenticado."""
    acl_documento = select(KnowledgePermission.id).where(
        KnowledgePermission.document_id == document_id
    )
    grants: list[ColumnElement[bool]] = []
    if contexto.role_ids:
        grants.append(
            and_(
                KnowledgePermission.principal_tipo == PrincipalConocimiento.ROL.value,
                KnowledgePermission.principal_id.in_(sorted(contexto.role_ids)),
            )
        )
    if contexto.actor_id is not None:
        grants.append(
            and_(
                KnowledgePermission.principal_tipo == PrincipalConocimiento.USUARIO.value,
                KnowledgePermission.principal_id == contexto.actor_id,
            )
        )
    if contexto.sedes:
        grants.append(
            and_(
                KnowledgePermission.principal_tipo == PrincipalConocimiento.SEDE.value,
                KnowledgePermission.principal_id.in_(sorted(contexto.sedes)),
            )
        )
    if contexto.especialidades:
        grants.append(
            and_(
                KnowledgePermission.principal_tipo == PrincipalConocimiento.ESPECIALIDAD.value,
                KnowledgePermission.principal_id.in_(sorted(contexto.especialidades)),
            )
        )

    principal_coincide = or_(*grants) if grants else literal(False)

    def existe_regla(*filtros: ColumnElement[bool]) -> ColumnElement[bool]:
        return exists(
            select(KnowledgePermission.id).where(
                KnowledgePermission.document_id == document_id,
                principal_coincide,
                *filtros,
            )
        )

    if contexto.uso_agente:
        permiso_efectivo = and_(
            existe_regla(
                KnowledgePermission.puede_leer.is_(True),
                KnowledgePermission.puede_usar_en_agente.is_(True),
            ),
            not_(
                existe_regla(
                    or_(
                        KnowledgePermission.puede_leer.is_(False),
                        KnowledgePermission.puede_usar_en_agente.is_(False),
                    )
                )
            ),
        )
    else:
        permiso_efectivo = and_(
            existe_regla(KnowledgePermission.puede_leer.is_(True)),
            not_(existe_regla(KnowledgePermission.puede_leer.is_(False))),
        )
    return or_(not_(exists(acl_documento)), permiso_efectivo)


def _condiciones(contexto: ContextoAutorizacion) -> list[ColumnElement[bool]]:
    """Las condiciones de autorizacion. Se aplican a **las dos** subconsultas.

    Vive en una funcion y no repetida en cada consulta porque la busqueda
    hibrida tiene dos ramas: si una filtrara distinto de la otra, la mas laxa
    seria la fuga. Anadir una condicion aqui la anade a ambas.
    """
    condiciones: list[ColumnElement[bool]] = [
        # Aislamiento por clinica. Es la primera y la que nunca admite
        # excepcion: un fragmento de otra clinica no es visible ni para un
        # administrador.
        KnowledgeChunk.clinic_id == contexto.clinica_id,
        # Solo aprobados y vigentes (RF-M05).
        KnowledgeChunk.status.in_(sorted(ESTADOS_RECUPERABLES)),
        or_(
            KnowledgeChunk.effective_from.is_(None),
            KnowledgeChunk.effective_from <= contexto.ahora,
        ),
        or_(
            KnowledgeChunk.effective_until.is_(None),
            KnowledgeChunk.effective_until >= contexto.ahora,
        ),
        # Nivel de sensibilidad. Se compara por la lista de niveles que el
        # solicitante cubre, y no con un `<=` sobre la cadena: «N10» ordenaria
        # entre «N1» y «N2» si algun dia se anade un nivel de dos digitos.
        KnowledgeChunk.sensitivity_level.in_(
            sorted(n.value for n in NivelSensibilidad if contexto.nivel_maximo.cubre(n))
        ),
    ]

    condiciones.append(condicion_acl_documento(KnowledgeChunk.document_id, contexto))

    # Sede. Un fragmento sin sede es de alcance general y lo ve quien tenga
    # acceso a la clinica; uno con sede exige que esa sede este autorizada.
    if contexto.sedes is not None:
        if not contexto.sedes:
            # Ambito vacio = ningun acceso. Se expresa como una condicion
            # imposible y no con un `return []` anticipado: asi el filtro
            # sigue siendo una lista de condiciones y no hay un camino de
            # salida distinto que alguien pueda olvidar replicar.
            condiciones.append(literal(False))
        else:
            condiciones.append(
                or_(
                    KnowledgeChunk.branch_id.is_(None),
                    KnowledgeChunk.branch_id.in_(sorted(contexto.sedes)),
                )
            )

    if contexto.especialidades is not None:
        if not contexto.especialidades:
            condiciones.append(literal(False))
        else:
            condiciones.append(
                or_(
                    KnowledgeChunk.specialty_id.is_(None),
                    KnowledgeChunk.specialty_id.in_(sorted(contexto.especialidades)),
                )
            )

    return condiciones


class RepositorioConocimiento:
    """Unica via de consulta a `knowledge_chunks` desde la capa de IA."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def buscar_conocimiento_autorizado(
        self,
        *,
        consulta: str,
        vector: list[float],
        modelo_embeddings: str,
        contexto: ContextoAutorizacion,
        limite: int = 8,
        candidatos: int = 40,
        peso_vectorial: float = 0.6,
        umbral_similitud: float = UMBRAL_SIMILITUD_POR_DEFECTO,
    ) -> list[FragmentoRecuperado]:
        """Busqueda hibrida con los filtros de autorizacion en el `WHERE`.

        `contexto` es obligatorio y no tiene valor por defecto: ver la nota de
        `ContextoAutorizacion`.

        `candidatos` es cuantos se consideran en cada ranking antes de
        fusionar. Debe ser mayor que `limite` porque los dos rankings se
        solapan solo en parte; con `candidatos == limite` la fusion apenas
        tendria margen para reordenar.
        """
        limite = min(max(limite, 1), LIMITE_MAXIMO)
        candidatos = max(candidatos, limite)
        condiciones = _condiciones(contexto)

        vectorial = self._ranking_vectorial(
            vector, modelo_embeddings, condiciones, candidatos, umbral_similitud
        )
        textual = self._ranking_textual(consulta, condiciones, candidatos)

        # Fusion RRF: 1 / (K + posicion) en cada lista, ponderada. Opera sobre
        # las POSICIONES y no sobre las puntuaciones, que es la razon de
        # elegirla: la distancia coseno y `ts_rank_cd` estan en escalas
        # distintas y normalizarlas exigiria calibrarlas con datos.
        v = vectorial.subquery("vectorial")
        x = textual.subquery("textual")

        puntuacion = (
            func.coalesce(peso_vectorial / (K_RRF + v.c.posicion), 0.0)
            + func.coalesce((1.0 - peso_vectorial) / (K_RRF + x.c.posicion), 0.0)
        ).label("puntuacion")

        fusion = (
            select(
                func.coalesce(v.c.chunk_id, x.c.chunk_id).label("chunk_id"),
                v.c.posicion.label("posicion_vectorial"),
                x.c.posicion.label("posicion_textual"),
                puntuacion,
            )
            .select_from(v.join(x, v.c.chunk_id == x.c.chunk_id, full=True, isouter=True))
            .order_by(puntuacion.desc())
            .limit(limite)
        ).subquery("fusion")

        # Se vuelve a unir con `knowledge_chunks` **aplicando otra vez las
        # condiciones**. Es redundante: los candidatos ya salieron filtrados.
        # Se deja porque esta union es la que devuelve el CONTENIDO, y una
        # redundancia barata en el camino por el que sale el texto vale mas
        # que la elegancia de no repetirla.
        final = (
            select(
                KnowledgeChunk.id,
                KnowledgeChunk.document_id,
                KnowledgeChunk.version,
                KnowledgeChunk.indice_fragmento,
                KnowledgeChunk.contenido,
                fusion.c.posicion_vectorial,
                fusion.c.posicion_textual,
                fusion.c.puntuacion,
            )
            .select_from(fusion.join(KnowledgeChunk, KnowledgeChunk.id == fusion.c.chunk_id))
            .where(and_(*condiciones))
            .order_by(fusion.c.puntuacion.desc())
        )

        filas = (await self._sesion.execute(final)).all()
        return [
            FragmentoRecuperado(
                chunk_id=fila[0],
                document_id=fila[1],
                version=fila[2],
                indice_fragmento=fila[3],
                contenido=fila[4],
                posicion_vectorial=fila[5],
                posicion_textual=fila[6],
                puntuacion=float(fila[7]),
            )
            for fila in filas
        ]

    def _ranking_vectorial(
        self,
        vector: list[float],
        modelo: str,
        condiciones: list[ColumnElement[bool]],
        candidatos: int,
        umbral_similitud: float,
    ) -> Select[tuple[uuid.UUID, int]]:
        """Los `n` fragmentos autorizados mas cercanos por coseno.

        El filtro va en el `WHERE` de esta misma consulta, asi que el indice
        HNSW explora solo entre los autorizados. Esa es la diferencia con el
        post-filtro, y tiene un coste conocido: con un filtro muy selectivo,
        HNSW puede necesitar recorrer mas grafo para reunir `n` candidatos
        (ADR-0013).

        Se exige `modelo` en la union: mezclar vectores de dos modelos en la
        misma busqueda da resultados sin sentido que **no fallan**, solo son
        malos.

        Y se aplica el **umbral de similitud**: sin el, esta rama devolveria
        candidatos siempre, por lejanos que fueran, y el sistema nunca podria
        decir que no tiene informacion aprobada.
        """
        distancia = KnowledgeEmbedding.embedding.cosine_distance(vector)
        distancia_maxima = 1.0 - umbral_similitud
        return (
            select(
                KnowledgeChunk.id.label("chunk_id"),
                func.row_number().over(order_by=distancia).label("posicion"),
            )
            .select_from(
                KnowledgeChunk.__table__.join(
                    KnowledgeEmbedding.__table__,
                    and_(
                        KnowledgeEmbedding.chunk_id == KnowledgeChunk.id,
                        KnowledgeEmbedding.modelo == modelo,
                    ),
                )
            )
            .where(and_(*condiciones, distancia <= distancia_maxima))
            .order_by(distancia)
            .limit(candidatos)
        )

    def _ranking_textual(
        self,
        consulta: str,
        condiciones: list[ColumnElement[bool]],
        candidatos: int,
    ) -> Select[tuple[uuid.UUID, int]]:
        """Los `n` fragmentos autorizados con mejor coincidencia textual.

        Usa `websearch_to_tsquery`, que acepta lo que una persona escribe --
        comillas, `or`, `-` para excluir -- sin lanzar ante una sintaxis
        invalida. `plainto_tsquery` ignoraria esos operadores y `to_tsquery`
        fallaria con una excepcion ante cualquier texto libre.

        Y **se reescriben los `&` por `|`**, que es el detalle que hace que
        esta rama sirva de algo. `websearch_to_tsquery` une todos los terminos
        con AND: la pregunta «cuantas horas de ayuno necesito para el examen de
        sangre» solo encontraria un documento que contenga TODAS esas palabras,
        y una pregunta natural casi nunca coincide asi. Con OR, el documento
        aparece si contiene alguna, y `ts_rank_cd` lo ordena por cuantas y con
        que peso -- que es lo que se quiere de un ranking que luego se fusiona.

        La reescritura se hace sobre el `tsquery` YA construido, no sobre el
        texto del usuario: la consulta sigue pasando por
        `websearch_to_tsquery` como parametro enlazado, asi que no hay forma de
        inyectar operadores.

        La mitad textual existe porque la semantica sola falla justo donde mas
        se nota: el nombre exacto de un examen o de un medicamento, que el
        modelo de embeddings no distingue de sus vecinos.
        """
        consulta_ts = func.replace(
            func.websearch_to_tsquery("espanol_sin_tildes", consulta).cast(Text),
            " & ",
            " | ",
        ).cast(TSQUERY)
        relevancia = func.ts_rank_cd(KnowledgeChunk.contenido_tsv, consulta_ts)
        return (
            select(
                KnowledgeChunk.id.label("chunk_id"),
                func.row_number().over(order_by=relevancia.desc()).label("posicion"),
            )
            .where(and_(*condiciones, KnowledgeChunk.contenido_tsv.op("@@")(consulta_ts)))
            .order_by(relevancia.desc())
            .limit(candidatos)
        )


async def contenido_de_version_revisable(
    sesion: AsyncSession, *, documento: KnowledgeDocument, version: int
) -> list[str]:
    """Fragmentos de una versión, en orden, para la revisión de riesgo.

    **No aplica ámbito**: recibe el documento ya resuelto con el mismo filtro
    que el listado (`revision_riesgo._documento_visible`). Por eso exige el
    objeto y no un identificador suelto: no se puede llamar con un id ajeno.
    """
    resultado = await sesion.scalars(
        select(KnowledgeChunk.contenido)
        .where(
            KnowledgeChunk.document_id == documento.id,
            KnowledgeChunk.clinic_id == documento.clinic_id,
            KnowledgeChunk.version == version,
        )
        .order_by(KnowledgeChunk.indice_fragmento)
    )
    return list(resultado.all())


__all__ = [
    "K_RRF",
    "LIMITE_MAXIMO",
    "UMBRAL_SIMILITUD_POR_DEFECTO",
    "ContextoAutorizacion",
    "FragmentoRecuperado",
    "RepositorioConocimiento",
    "condicion_acl_documento",
    "contenido_de_version_revisable",
]
