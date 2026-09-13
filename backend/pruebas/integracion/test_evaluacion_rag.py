"""Arnes de evaluacion del RAG (RF-O08).

Que mide, y que no
------------------
Mide **Hit@K y precision sobre un conjunto de casos con respuesta conocida**,
y comprueba que los casos negativos deliberados no se recuperan nunca.

Lo que **no** mide es la calidad semantica real, y conviene ser claro: estas
pruebas usan el proveedor de embeddings simulado, que deriva el vector del
hash del texto y no entiende nada. Eso significa que la mitad vectorial de la
busqueda aporta ruido, y que lo que hace acertar es la **mitad textual**.

Es una medicion util a pesar de eso, por dos motivos:

1. Mide el **suelo**: si la busqueda hibrida encuentra el documento correcto
   incluso con la mitad vectorial ciega, el fallo de un caso nuevo apunta al
   filtro o a la fusion, no al modelo.
2. Los casos negativos -- documento archivado, vencido, de otra sede, de otra
   especialidad -- **no dependen del modelo en absoluto**. Un cero ahi es un
   cero de verdad.

La medicion con el modelo real es otra cosa y esta declarada como pendiente
(limitacion E-9). Cuando exista, el umbral de estas pruebas debe subir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.embeddings import EmbeddingsSimulado
from app.modulos.conocimiento.modelos import (
    EstadoDocumento,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
    TipoDocumentoConocimiento,
)
from app.modulos.conocimiento.repositorio import (
    ContextoAutorizacion,
    RepositorioConocimiento,
)
from app.modulos.organizacion.modelos import Clinica, Sede
from app.nucleo.autorizacion import NivelSensibilidad

pytestmark = [pytest.mark.integracion, pytest.mark.rag, pytest.mark.asyncio]

# Umbrales con el proveedor simulado. Son el **suelo**, no el objetivo.
#
# Medido el 2026-09-12 sobre este corpus: Hit@1 = 80 %, Hit@3 = 100 %,
# Hit@5 = 100 %, con una media de 2,5 resultados por consulta sobre un corpus
# de 5 documentos -- es decir, la busqueda es selectiva y no devuelve todo.
#
# Los umbrales se dejan por debajo de lo medido para que un cambio menor no
# rompa la suite, pero **bajarlos para que pase una prueba seria falsear la
# evaluacion**. Con un modelo de embeddings real deben subir.
UMBRAL_HIT_EN_3 = 0.8
UMBRAL_HIT_EN_1 = 0.7


@dataclass(frozen=True, slots=True)
class CasoEvaluacion:
    """Una pregunta con el documento que deberia responderla."""

    pregunta: str
    # Palabra que identifica el documento correcto en este conjunto.
    clave: str


# Corpus sintetico de una clinica. Cada entrada es (clave, contenido).
#
# Los textos son plausibles y estan escritos como los escribiria una clinica,
# no como los escribiria alguien que quiere que la prueba pase: si fueran
# copias literales de las preguntas, la evaluacion no mediria nada.
CORPUS: dict[str, str] = {
    "ayuno": (
        "Preparacion para examenes de sangre. El paciente debe mantener ayuno "
        "de doce horas antes de la toma de muestra. Puede beber agua. No se "
        "permite cafe, jugos ni chicle durante ese periodo."
    ),
    "ecografia": (
        "Preparacion para ecografia abdominal. Se requiere vejiga llena: beba "
        "un litro de agua una hora antes y no orine hasta finalizar el "
        "procedimiento. Evite bebidas gaseosas el dia previo."
    ),
    "horario": (
        "Horario de atencion de la clinica. Consulta externa de lunes a "
        "viernes de 08:00 a 17:00 y sabados de 08:00 a 12:00. El laboratorio "
        "toma muestras de 07:00 a 11:00 sin cita previa."
    ),
    "cancelacion": (
        "Politica de cancelacion de citas. Las cancelaciones se aceptan hasta "
        "veinticuatro horas antes del horario reservado. Una inasistencia sin "
        "aviso puede afectar la asignacion de turnos futuros."
    ),
    "documentos": (
        "Documentos requeridos para la atencion. Presente su cedula de "
        "identidad, la orden medica cuando corresponda y el carne del seguro "
        "si tiene cobertura vigente."
    ),
}

# Preguntas escritas como las haria un paciente, no copiando el documento.
CASOS: tuple[CasoEvaluacion, ...] = (
    CasoEvaluacion("cuantas horas de ayuno necesito para el examen de sangre", "ayuno"),
    CasoEvaluacion("puedo tomar agua antes del examen de sangre", "ayuno"),
    CasoEvaluacion("como me preparo para la ecografia abdominal", "ecografia"),
    CasoEvaluacion("necesito vejiga llena para la ecografia", "ecografia"),
    CasoEvaluacion("cual es el horario de atencion de la clinica", "horario"),
    CasoEvaluacion("a que hora toman muestras en el laboratorio", "horario"),
    CasoEvaluacion("con cuanta anticipacion puedo cancelar mi cita", "cancelacion"),
    CasoEvaluacion("que documentos debo llevar a la consulta", "documentos"),
    CasoEvaluacion("necesito llevar el carne del seguro", "documentos"),
    CasoEvaluacion("se aceptan cancelaciones el mismo dia", "cancelacion"),
)


@pytest.fixture
def embeddings() -> EmbeddingsSimulado:
    return EmbeddingsSimulado()


@pytest_asyncio.fixture
async def corpus(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
) -> dict[str, uuid.UUID]:
    """Publica el corpus y devuelve la clave de cada documento."""
    indice: dict[str, uuid.UUID] = {}
    for clave, contenido in CORPUS.items():
        documento = await _publicar(sesion, embeddings, clinica, contenido, instante=instante)
        indice[clave] = documento
    return indice


async def _publicar(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    contenido: str,
    *,
    instante: datetime,
    status: str = EstadoDocumento.PUBLISHED.value,
    branch_id: uuid.UUID | None = None,
    specialty_id: uuid.UUID | None = None,
    effective_until: datetime | None = None,
) -> uuid.UUID:
    aprobado = status in (EstadoDocumento.APPROVED.value, EstadoDocumento.PUBLISHED.value)
    documento = KnowledgeDocument(
        clinic_id=clinica.id,
        titulo=contenido[:60],
        tipo=TipoDocumentoConocimiento.PREGUNTA_FRECUENTE.value,
        status=status,
        version_vigente=1 if aprobado else 0,
        aprobado_por=uuid.uuid4() if aprobado else None,
        aprobado_en=instante if aprobado else None,
        archivado_en=instante if status == EstadoDocumento.ARCHIVED.value else None,
        branch_id=branch_id,
        specialty_id=specialty_id,
        effective_until=effective_until,
    )
    sesion.add(documento)
    await sesion.flush()

    fragmento = KnowledgeChunk(
        document_id=documento.id,
        version=1,
        indice_fragmento=0,
        contenido=contenido,
        tokens=len(contenido) // 4,
        clinic_id=clinica.id,
        branch_id=branch_id,
        specialty_id=specialty_id,
        status=status,
        effective_until=effective_until,
        sensitivity_level="N1",
    )
    sesion.add(fragmento)
    await sesion.flush()

    (vector,) = await embeddings.vectorizar([contenido])
    sesion.add(
        KnowledgeEmbedding(
            chunk_id=fragmento.id,
            modelo=embeddings.nombre_modelo,
            dimension=embeddings.dimension,
            embedding=vector,
        )
    )
    await sesion.flush()
    return documento.id


async def _buscar(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    pregunta: str,
    *,
    limite: int = 3,
    sedes: frozenset[uuid.UUID] | None = None,
    especialidades: frozenset[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    repositorio = RepositorioConocimiento(sesion)
    vector = await embeddings.vectorizar_consulta(pregunta)
    fragmentos = await repositorio.buscar_conocimiento_autorizado(
        consulta=pregunta,
        vector=vector,
        modelo_embeddings=embeddings.nombre_modelo,
        contexto=ContextoAutorizacion(
            clinica_id=clinica.id,
            sedes=sedes,
            especialidades=especialidades,
            nivel_maximo=NivelSensibilidad.CLINICO,
            ahora=instante,
        ),
        limite=limite,
    )
    return [f.document_id for f in fragmentos]


# ---------------------------------------------------------------------------
#  Metricas
# ---------------------------------------------------------------------------
async def test_hit_en_3_supera_el_umbral(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
) -> None:
    """Hit@3: en cuantos casos el documento correcto esta entre los tres primeros.

    El umbral es el **suelo** con el proveedor simulado. Si un caso nuevo falla,
    la pregunta es si la busqueda empeoro o si el caso esta mal planteado --
    no si conviene bajar el umbral.
    """
    aciertos = 0
    fallos: list[str] = []

    for caso in CASOS:
        encontrados = await _buscar(sesion, embeddings, clinica, instante, caso.pregunta, limite=3)
        if corpus[caso.clave] in encontrados:
            aciertos += 1
        else:
            fallos.append(caso.pregunta)

    tasa = aciertos / len(CASOS)
    assert tasa >= UMBRAL_HIT_EN_3, (
        f"Hit@3 = {tasa:.0%} (umbral {UMBRAL_HIT_EN_3:.0%}). Casos sin acierto: {fallos}"
    )


async def test_el_documento_correcto_suele_ser_el_primero(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
) -> None:
    """Hit@1, con un umbral mas bajo.

    Importa porque el agente cita las primeras fuentes: un documento correcto
    en tercera posicion puede quedar fuera del contexto si se recorta.
    """
    aciertos = 0
    for caso in CASOS:
        encontrados = await _buscar(sesion, embeddings, clinica, instante, caso.pregunta, limite=1)
        if corpus[caso.clave] in encontrados:
            aciertos += 1
    tasa = aciertos / len(CASOS)
    # Mas bajo que Hit@3: con embeddings simulados, acertar el primero depende
    # casi por completo de la coincidencia textual.
    assert tasa >= UMBRAL_HIT_EN_1, f"Hit@1 = {tasa:.0%} (umbral {UMBRAL_HIT_EN_1:.0%})"


async def test_ninguna_pregunta_devuelve_resultados_de_mas(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
) -> None:
    """El limite se respeta.

    Un contexto mas grande de lo pedido no mejora la respuesta y multiplica el
    coste de cada consulta.
    """
    for caso in CASOS:
        encontrados = await _buscar(sesion, embeddings, clinica, instante, caso.pregunta, limite=2)
        assert len(encontrados) <= 2


# ---------------------------------------------------------------------------
#  Casos negativos deliberados: aqui el resultado NO depende del modelo
# ---------------------------------------------------------------------------
async def test_un_documento_archivado_nunca_aparece_en_la_evaluacion(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
) -> None:
    """Con el texto **exacto** de la pregunta, que es el peor caso.

    Si la busqueda lo devolviera, seria por el filtro y no por el modelo.
    """
    archivado = await _publicar(
        sesion,
        embeddings,
        clinica,
        "cuantas horas de ayuno necesito para el examen de sangre. Son ocho horas.",
        instante=instante,
        status=EstadoDocumento.ARCHIVED.value,
    )
    for caso in CASOS:
        encontrados = await _buscar(sesion, embeddings, clinica, instante, caso.pregunta, limite=5)
        assert archivado not in encontrados


async def test_un_documento_vencido_nunca_aparece(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
) -> None:
    """Un tarifario caducado es peor que ninguno: parece vigente."""
    vencido = await _publicar(
        sesion,
        embeddings,
        clinica,
        "cual es el horario de atencion de la clinica. Abrimos de 06:00 a 22:00.",
        instante=instante,
        effective_until=instante - timedelta(days=1),
    )
    for caso in CASOS:
        encontrados = await _buscar(sesion, embeddings, clinica, instante, caso.pregunta, limite=5)
        assert vencido not in encontrados


async def test_un_documento_de_otra_sede_nunca_aparece(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    sede: Sede,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
    sufijo: str,
) -> None:
    otra = Sede(
        clinica_id=clinica.id,
        nombre=f"Sede Ajena {sufijo}",
        direccion="Calle Ficticia 789",
    )
    sesion.add(otra)
    await sesion.flush()

    ajeno = await _publicar(
        sesion,
        embeddings,
        clinica,
        "que documentos debo llevar a la consulta. Solo la cedula.",
        instante=instante,
        branch_id=otra.id,
    )
    for caso in CASOS:
        encontrados = await _buscar(
            sesion,
            embeddings,
            clinica,
            instante,
            caso.pregunta,
            limite=5,
            sedes=frozenset({sede.id}),
        )
        assert ajeno not in encontrados


async def test_una_pregunta_sin_documentacion_no_inventa_fuentes(
    sesion: AsyncSession,
    embeddings: EmbeddingsSimulado,
    clinica: Clinica,
    instante: datetime,
    corpus: dict[str, uuid.UUID],
) -> None:
    """El caso que lleva a «no tengo informacion aprobada» (RF-O06).

    Esta prueba destapo un fallo real: sin umbral de similitud, la rama
    vectorial devolvia **el corpus entero** para cualquier pregunta, porque
    ordena por distancia y entrega los N primeros por lejos que esten. Eso
    significaba que «no tengo informacion aprobada» no se dispararia casi
    nunca y el agente citaria como fuente el documento menos irrelevante.

    Con el umbral aplicado, esta consulta devuelve **cero** resultados.
    """
    encontrados = await _buscar(
        sesion,
        embeddings,
        clinica,
        instante,
        "cuanto cuesta una resonancia magnetica con contraste",
        limite=5,
    )
    assert encontrados == []
