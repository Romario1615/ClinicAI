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

from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modulos.conocimiento.modelos import (
    ESTADOS_RECUPERABLES,
    KnowledgeChunk,
    KnowledgeEmbedding,
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

        vectorial = self._ranking_vectorial(vector, modelo_embeddings, condiciones, candidatos)
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
        """
        distancia = KnowledgeEmbedding.embedding.cosine_distance(vector)
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
            .where(and_(*condiciones))
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
        invalida. `plainto_tsquery` ignoraria esos operadores y
        `to_tsquery` fallaria con una excepcion ante cualquier texto libre.

        La mitad textual existe porque la semantica sola falla justo donde mas
        se nota: el nombre exacto de un examen o de un medicamento, que el
        modelo de embeddings no distingue de sus vecinos.
        """
        consulta_ts = func.websearch_to_tsquery("espanol_sin_tildes", consulta)
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


__all__ = [
    "K_RRF",
    "LIMITE_MAXIMO",
    "ContextoAutorizacion",
    "FragmentoRecuperado",
    "RepositorioConocimiento",
]
