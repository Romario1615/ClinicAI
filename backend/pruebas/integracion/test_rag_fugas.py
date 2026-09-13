"""Los casos negativos del RAG: lo que NO se puede recuperar.

Estas son las pruebas que justifican toda la arquitectura de ADR-0013. Cada
una monta un fragmento que **existe**, es parecido a la consulta, y aun asi no
debe aparecer:

* de otra clinica
* de otra sede
* de otra especialidad
* en borrador o en revision
* archivado
* con vigencia caducada o aun no iniciada
* por encima del nivel de sensibilidad del solicitante

Y una prueba de control en cada bloque que comprueba que el caso **permitido
si** devuelve datos. Sin ella, todas las demas pasarian aunque la busqueda
estuviera rota y no devolviera nunca nada -- que es la forma mas facil de
tener una suite verde que no prueba nada.

Sobre los vectores
------------------
Se usa el proveedor simulado (determinista, derivado del texto). No mide
semantica, y para esto da igual: lo que se comprueba es la **ausencia** de un
fragmento, y eso no depende de la calidad del vector. La calidad de la
recuperacion se mide aparte, en el arnes de evaluacion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.nucleo.autorizacion import NivelSensibilidad

pytestmark = [pytest.mark.integracion, pytest.mark.rag, pytest.mark.seguridad, pytest.mark.asyncio]

CONSULTA = "preparacion para el examen de sangre en ayunas"
TEXTO = (
    "Preparacion para el examen de sangre. No comer nada desde las 22:00 de la "
    "noche anterior. Puede beber agua sin limite. Traiga la orden medica."
)


@pytest.fixture
def embeddings() -> EmbeddingsSimulado:
    return EmbeddingsSimulado()


@pytest.fixture
def repositorio(sesion: AsyncSession) -> RepositorioConocimiento:
    return RepositorioConocimiento(sesion)


@pytest_asyncio.fixture
async def otra_sede(sesion: AsyncSession, clinica: Clinica, sufijo: str) -> Sede:
    """Segunda sede de la MISMA clinica.

    Es el caso que un filtro por clinica dejaria pasar: mismo aislamiento de
    nivel superior, distinto alcance.
    """
    registro = Sede(
        clinica_id=clinica.id,
        nombre=f"Otra Sede de Prueba {sufijo}",
        direccion="Avenida Ficticia 456",
    )
    sesion.add(registro)
    await sesion.flush()
    return registro


@pytest_asyncio.fixture
async def sembrar(sesion: AsyncSession, embeddings: EmbeddingsSimulado) -> object:
    """Crea un documento y su fragmento con los metadatos indicados.

    Se crea el documento de verdad y no solo el fragmento: la clave externa lo
    exige, y ademas deja la prueba mas cerca de la realidad. El estado del
    **fragmento** es el que filtra la consulta -- esa es la desnormalizacion de
    ADR-0013 --, y se fija igual que el del documento para que el caso montado
    sea coherente.

    No se pasa por el servicio a proposito: estas pruebas miden **la
    consulta**, y montar cada caso por el ciclo de vida completo las haria
    depender de reglas que se prueban aparte.
    """

    async def _crear(
        *,
        clinic_id: uuid.UUID,
        status: str = EstadoDocumento.PUBLISHED.value,
        branch_id: uuid.UUID | None = None,
        specialty_id: uuid.UUID | None = None,
        sensitivity_level: str = "N1",
        effective_from: datetime | None = None,
        effective_until: datetime | None = None,
        contenido: str = TEXTO,
    ) -> KnowledgeChunk:
        aprobado = status in (
            EstadoDocumento.APPROVED.value,
            EstadoDocumento.PUBLISHED.value,
        )
        documento = KnowledgeDocument(
            clinic_id=clinic_id,
            titulo="Documento de prueba",
            tipo=TipoDocumentoConocimiento.INSTRUCTIVO.value,
            status=status,
            # Los CHECK del motor exigen constancia de la aprobacion y una
            # version ingerida para los estados recuperables. Cumplirlos aqui
            # no es ceremonia: es la misma regla que el servicio aplica.
            version_vigente=1 if aprobado else 0,
            aprobado_por=uuid.uuid4() if aprobado else None,
            aprobado_en=datetime.now(UTC) if aprobado else None,
            archivado_en=(datetime.now(UTC) if status == EstadoDocumento.ARCHIVED.value else None),
            branch_id=branch_id,
            specialty_id=specialty_id,
            sensitivity_level=sensitivity_level,
            effective_from=effective_from,
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
            clinic_id=clinic_id,
            branch_id=branch_id,
            specialty_id=specialty_id,
            status=status,
            effective_from=effective_from,
            effective_until=effective_until,
            sensitivity_level=sensitivity_level,
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
        return fragmento

    return _crear


async def _buscar(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    contexto: ContextoAutorizacion,
) -> list[uuid.UUID]:
    vector = await embeddings.vectorizar_consulta(CONSULTA)
    fragmentos = await repositorio.buscar_conocimiento_autorizado(
        consulta=CONSULTA,
        vector=vector,
        modelo_embeddings=embeddings.nombre_modelo,
        contexto=contexto,
    )
    return [f.chunk_id for f in fragmentos]


def _contexto(
    clinica: Clinica,
    instante: datetime,
    *,
    sedes: frozenset[uuid.UUID] | None = None,
    especialidades: frozenset[uuid.UUID] | None = None,
    nivel: NivelSensibilidad = NivelSensibilidad.CLINICO,
) -> ContextoAutorizacion:
    return ContextoAutorizacion(
        clinica_id=clinica.id,
        sedes=sedes,
        especialidades=especialidades,
        nivel_maximo=nivel,
        ahora=instante,
    )


# ---------------------------------------------------------------------------
#  Control: el caso permitido SI devuelve datos
# ---------------------------------------------------------------------------
async def test_un_fragmento_publicado_y_vigente_se_recupera(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """La prueba de control.

    Sin ella, todas las de ausencia pasarian aunque la busqueda estuviera rota
    y no devolviera nunca nada.
    """
    fragmento = await sembrar(clinic_id=clinica.id)  # type: ignore[operator]
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert fragmento.id in encontrados


# ---------------------------------------------------------------------------
#  Aislamiento entre clinicas
# ---------------------------------------------------------------------------
async def test_no_se_recupera_un_fragmento_de_otra_clinica(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    sesion: AsyncSession,
    clinica: Clinica,
    instante: datetime,
    sufijo: str,
) -> None:
    """El aislamiento que nunca admite excepcion.

    Ni siquiera un administrador de una clinica ve documentos de otra.
    """
    otra = Clinica(
        nombre=f"Otra Clinica {sufijo}",
        identificacion_fiscal=f"OTRA-{sufijo}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(otra)
    await sesion.flush()

    ajeno = await sembrar(clinic_id=otra.id)  # type: ignore[operator]
    propio = await sembrar(clinic_id=clinica.id)  # type: ignore[operator]

    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert propio.id in encontrados
    assert ajeno.id not in encontrados


# ---------------------------------------------------------------------------
#  Estado del documento
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "estado",
    [
        EstadoDocumento.DRAFT.value,
        EstadoDocumento.PENDING_REVIEW.value,
        EstadoDocumento.ARCHIVED.value,
    ],
)
async def test_no_se_recupera_un_documento_no_aprobado(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
    estado: str,
) -> None:
    """RF-M05: solo `APPROVED` y `PUBLISHED` son recuperables.

    El borrador es el caso que mas importa: si fuera recuperable, el agente
    responderia con texto a medio escribir y nadie se enteraria hasta que
    alguien se quejara.
    """
    fragmento = await sembrar(clinic_id=clinica.id, status=estado)  # type: ignore[operator]
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert fragmento.id not in encontrados


@pytest.mark.parametrize(
    "estado", [EstadoDocumento.APPROVED.value, EstadoDocumento.PUBLISHED.value]
)
async def test_los_estados_recuperables_si_aparecen(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
    estado: str,
) -> None:
    fragmento = await sembrar(clinic_id=clinica.id, status=estado)  # type: ignore[operator]
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert fragmento.id in encontrados


# ---------------------------------------------------------------------------
#  Vigencia
# ---------------------------------------------------------------------------
async def test_no_se_recupera_un_documento_vencido(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """Un protocolo caducado es peor que ninguno: parece vigente."""
    fragmento = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id, effective_until=instante - timedelta(days=1)
    )
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert fragmento.id not in encontrados


async def test_no_se_recupera_un_documento_que_aun_no_entra_en_vigor(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """Un tarifario del proximo trimestre no se aplica todavia."""
    fragmento = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id, effective_from=instante + timedelta(days=1)
    )
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert fragmento.id not in encontrados


async def test_un_documento_dentro_de_su_vigencia_se_recupera(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    fragmento = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id,
        effective_from=instante - timedelta(days=1),
        effective_until=instante + timedelta(days=1),
    )
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert fragmento.id in encontrados


async def test_el_mismo_documento_deja_de_recuperarse_al_vencer(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """La vigencia se evalua contra el instante que se pasa, no contra el reloj.

    Es lo que permite comprobar el limite exacto sin esperar (ADR-0010).
    """
    fragmento = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id, effective_until=instante + timedelta(hours=1)
    )
    antes = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    despues = await _buscar(
        repositorio, embeddings, _contexto(clinica, instante + timedelta(hours=2))
    )
    assert fragmento.id in antes
    assert fragmento.id not in despues


# ---------------------------------------------------------------------------
#  Sede
# ---------------------------------------------------------------------------
async def test_no_se_recupera_un_documento_de_otra_sede(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    sesion: AsyncSession,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    instante: datetime,
) -> None:
    propio = await sembrar(clinic_id=clinica.id, branch_id=sede.id)  # type: ignore[operator]
    ajeno = await sembrar(clinic_id=clinica.id, branch_id=otra_sede.id)  # type: ignore[operator]

    encontrados = await _buscar(
        repositorio, embeddings, _contexto(clinica, instante, sedes=frozenset({sede.id}))
    )
    assert propio.id in encontrados
    assert ajeno.id not in encontrados


async def test_un_documento_sin_sede_es_de_alcance_general(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    sede: Sede,
    instante: datetime,
) -> None:
    """Nulo significa «toda la clinica», no «ninguna».

    Un protocolo general no se limita a una sede, y tratarlo como restringido
    lo haria invisible para todos.
    """
    general = await sembrar(clinic_id=clinica.id, branch_id=None)  # type: ignore[operator]
    encontrados = await _buscar(
        repositorio, embeddings, _contexto(clinica, instante, sedes=frozenset({sede.id}))
    )
    assert general.id in encontrados


async def test_un_ambito_de_sedes_vacio_no_recupera_nada(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """Ambito vacio = ningun acceso, igual que en el resto del sistema.

    Ni siquiera los documentos de alcance general, que es el caso que un
    tratamiento descuidado dejaria pasar.
    """
    await sembrar(clinic_id=clinica.id, branch_id=None)  # type: ignore[operator]
    encontrados = await _buscar(
        repositorio, embeddings, _contexto(clinica, instante, sedes=frozenset())
    )
    assert encontrados == []


# ---------------------------------------------------------------------------
#  Especialidad
# ---------------------------------------------------------------------------
async def test_no_se_recupera_un_documento_de_otra_especialidad(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    sesion: AsyncSession,
    clinica: Clinica,
    especialidad: Especialidad,
    instante: datetime,
    sufijo: str,
) -> None:
    otra = Especialidad(clinica_id=clinica.id, nombre=f"Otra Especialidad {sufijo}")
    sesion.add(otra)
    await sesion.flush()

    propio = await sembrar(clinic_id=clinica.id, specialty_id=especialidad.id)  # type: ignore[operator]
    ajeno = await sembrar(clinic_id=clinica.id, specialty_id=otra.id)  # type: ignore[operator]

    encontrados = await _buscar(
        repositorio,
        embeddings,
        _contexto(clinica, instante, especialidades=frozenset({especialidad.id})),
    )
    assert propio.id in encontrados
    assert ajeno.id not in encontrados


async def test_un_ambito_de_especialidades_vacio_no_recupera_nada(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    await sembrar(clinic_id=clinica.id, specialty_id=None)  # type: ignore[operator]
    encontrados = await _buscar(
        repositorio, embeddings, _contexto(clinica, instante, especialidades=frozenset())
    )
    assert encontrados == []


# ---------------------------------------------------------------------------
#  Nivel de sensibilidad
# ---------------------------------------------------------------------------
async def test_no_se_recupera_por_encima_del_nivel_del_solicitante(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """Recepcion no ve un documento clasificado como clinico sensible."""
    sensible = await sembrar(clinic_id=clinica.id, sensitivity_level="N3")  # type: ignore[operator]
    administrativo = await sembrar(clinic_id=clinica.id, sensitivity_level="N1")  # type: ignore[operator]

    encontrados = await _buscar(
        repositorio,
        embeddings,
        _contexto(clinica, instante, nivel=NivelSensibilidad.ADMINISTRATIVO),
    )
    assert administrativo.id in encontrados
    assert sensible.id not in encontrados


async def test_el_nivel_alto_alcanza_a_los_inferiores(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """`cubre` es «alcanza a», no «coincide con».

    Un profesional con nivel clinico ve tambien lo administrativo y lo
    publico; tratarlo como igualdad lo dejaria sin ver casi nada.
    """
    publico = await sembrar(clinic_id=clinica.id, sensitivity_level="N0")  # type: ignore[operator]
    clinico = await sembrar(clinic_id=clinica.id, sensitivity_level="N2")  # type: ignore[operator]

    encontrados = await _buscar(
        repositorio, embeddings, _contexto(clinica, instante, nivel=NivelSensibilidad.CLINICO)
    )
    assert publico.id in encontrados
    assert clinico.id in encontrados


# ---------------------------------------------------------------------------
#  Las dos ramas de la busqueda hibrida filtran igual
# ---------------------------------------------------------------------------
async def test_un_fragmento_no_autorizado_no_entra_por_la_rama_textual(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """El caso que una divergencia entre ramas dejaria pasar.

    El fragmento contiene **literalmente** las palabras de la consulta, asi
    que la rama textual lo puntuaria primero. Si esa rama filtrara distinto de
    la vectorial, aparecerìa. Es el motivo de que las condiciones se
    construyan una sola vez.
    """
    ajeno = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id,
        status=EstadoDocumento.ARCHIVED.value,
        contenido=f"{CONSULTA}. {CONSULTA}. {CONSULTA}.",
    )
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert ajeno.id not in encontrados


async def test_la_busqueda_encuentra_por_coincidencia_textual_exacta(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """La mitad textual existe justo para esto.

    El proveedor simulado no mide semantica, asi que un fragmento con las
    palabras exactas solo puede llegar por la rama textual. Que aparezca
    demuestra que esa rama funciona y que la fusion la tiene en cuenta.
    """
    exacto = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id,
        contenido=(
            "Instrucciones: preparacion para el examen de sangre en ayunas. "
            "Presentarse con doce horas de ayuno."
        ),
    )
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert exacto.id in encontrados


async def test_las_tildes_no_impiden_la_coincidencia_textual(
    repositorio: RepositorioConocimiento,
    embeddings: EmbeddingsSimulado,
    sembrar: object,
    clinica: Clinica,
    instante: datetime,
) -> None:
    """La configuracion `espanol_sin_tildes` aplica `unaccent` antes de derivar.

    Sin ella, «preparación» en el documento y «preparacion» en la consulta no
    coincidirian, y media base de conocimiento seria invisible segun como
    escribiera cada uno.
    """
    con_tildes = await sembrar(  # type: ignore[operator]
        clinic_id=clinica.id,
        contenido=(
            "Preparación para el exámen de sangre en ayunas. Presentarse con doce horas de ayuno."
        ),
    )
    encontrados = await _buscar(repositorio, embeddings, _contexto(clinica, instante))
    assert con_tildes.id in encontrados
