"""Rutas de la base de conocimiento.

Cuatro permisos, y la separacion importa
----------------------------------------
* `conocimiento.leer` — ver y buscar.
* `conocimiento.cargar` — crear documentos y subir versiones.
* `conocimiento.aprobar` — mover a `APPROVED` o `PUBLISHED`, y desbloquear un
  documento marcado como riesgoso.
* `conocimiento.archivar` — retirar de circulacion.

Quien carga no aprueba. Es la separacion que hace que la aprobacion signifique
algo: si el mismo permiso cubriera ambas cosas, aprobar seria un tramite que
hace quien sube el archivo, y RF-M04 -- «quien autorizo que el agente diga
esto» -- tendria siempre la misma respuesta que «quien lo subio».

La busqueda se audita
---------------------
Toda busqueda deja `rag.consulta` con las fuentes que devolvio. No es
ceremonia: ante «por que el agente le dijo esto a un paciente» hay que poder
reconstruir que documentos se usaron, y eso solo existe si se registro en el
momento.

El **texto de la consulta no se guarda**: puede contener el motivo por el que
un paciente pregunta, y eso es informacion de salud. Se registran las fuentes
y el numero de resultados.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status
from sqlalchemy import func, select

from app.ia.embeddings import ProveedorEmbeddings
from app.ia.recuperador import MENSAJE_SIN_FUENTE, Recuperador, contexto_desde_principal
from app.modulos.conocimiento.esquemas import (
    LONGITUD_EXTRACTO,
    PaginaDocumentos,
    RespuestaBusqueda,
    RespuestaDocumento,
    RespuestaIngesta,
    ResultadoBusqueda,
    SolicitudBusqueda,
    SolicitudCambioEstado,
    SolicitudDocumento,
    SolicitudIngesta,
    SolicitudRevision,
)
from app.modulos.conocimiento.modelos import (
    EstadoDocumento,
    KnowledgeDocument,
    KnowledgeVersion,
)
from app.modulos.conocimiento.servicios import ServicioConocimiento
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import PermisoDenegado, RecursoNoEncontrado
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)

enrutador = APIRouter(prefix="/conocimiento", tags=["conocimiento"])

PuedeLeer = Annotated[Principal, Depends(exige_permiso("conocimiento.leer"))]
PuedeCargar = Annotated[Principal, Depends(exige_permiso("conocimiento.cargar"))]
PuedeAprobar = Annotated[Principal, Depends(exige_permiso("conocimiento.aprobar"))]

IdDocumento = Annotated[uuid.UUID, Path(description="Identificador del documento.")]

# Estados cuyo cambio exige el permiso de aprobacion, y no el de carga.
ESTADOS_QUE_EXIGEN_APROBAR = frozenset(
    {EstadoDocumento.APPROVED.value, EstadoDocumento.PUBLISHED.value}
)
ESTADO_QUE_EXIGE_ARCHIVAR = EstadoDocumento.ARCHIVED.value


def _embeddings(peticion: Request) -> ProveedorEmbeddings:
    proveedor: ProveedorEmbeddings = peticion.app.state.embeddings
    return proveedor


def _servicio(
    peticion: Request, sesion: Sesion, reloj: RelojActual, configuracion: ConfiguracionActual
) -> ServicioConocimiento:
    return ServicioConocimiento(
        sesion,
        reloj,
        _embeddings(peticion),
        tamano_fragmento=configuracion.rag_tamano_fragmento,
        solape_fragmento=configuracion.rag_solape_fragmento,
    )


async def _a_respuesta(sesion: Sesion, documento: KnowledgeDocument) -> RespuestaDocumento:
    """Convierte el documento, resolviendo si requiere revision.

    El aviso se calcula aqui y no se guarda en una columna: derivarlo del
    analisis de la version vigente evita una copia mas que mantener
    sincronizada, y esta tabla ya tiene bastantes.
    """
    requiere = False
    if documento.version_vigente > 0:
        version = (
            await sesion.execute(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.document_id == documento.id,
                    KnowledgeVersion.version == documento.version_vigente,
                )
            )
        ).scalar_one_or_none()
        if version is not None:
            analisis = version.resultado_analisis_inyeccion or {}
            requiere = analisis.get("riesgo") == "ALTO" and not analisis.get("revisado_por")

    return RespuestaDocumento(
        id=documento.id,
        titulo=documento.titulo,
        tipo=documento.tipo,
        status=documento.status,
        version_vigente=documento.version_vigente,
        sensitivity_level=documento.sensitivity_level,
        branch_id=documento.branch_id,
        specialty_id=documento.specialty_id,
        service_id=documento.service_id,
        etiquetas=documento.etiquetas,
        effective_from=documento.effective_from,
        effective_until=documento.effective_until,
        aprobado_por=documento.aprobado_por,
        aprobado_en=documento.aprobado_en,
        archivado_en=documento.archivado_en,
        requiere_revision=requiere,
    )


# ---------------------------------------------------------------------------
#  Documentos
# ---------------------------------------------------------------------------
@enrutador.get(
    "/documentos",
    response_model=PaginaDocumentos,
    summary="Listar documentos de la clinica",
    responses={403: {"description": "Sin permiso de lectura de conocimiento"}},
)
async def listar_documentos(
    principal: PuedeLeer,
    sesion: Sesion,
    estado: Annotated[EstadoDocumento | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaDocumentos:
    """Solo los de la clinica del solicitante.

    El filtro va en el `WHERE`, no despues: un documento de otra clinica es
    indistinguible de uno inexistente.
    """
    condiciones = [KnowledgeDocument.clinic_id == principal.clinica_id]
    if estado is not None:
        condiciones.append(KnowledgeDocument.status == estado.value)

    total = await sesion.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(*condiciones)
    )
    filas = (
        (
            await sesion.execute(
                select(KnowledgeDocument)
                .where(*condiciones)
                .order_by(KnowledgeDocument.creado_en.desc())
                .limit(limite)
                .offset(desplazamiento)
            )
        )
        .scalars()
        .all()
    )
    return PaginaDocumentos(
        elementos=[await _a_respuesta(sesion, fila) for fila in filas],
        total=total or 0,
    )


@enrutador.post(
    "/documentos",
    response_model=RespuestaDocumento,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un documento",
    responses={403: {"description": "Sin permiso para cargar documentos"}},
)
async def crear_documento(
    principal: PuedeCargar,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    peticion: Request,
    cuerpo: SolicitudDocumento,
) -> RespuestaDocumento:
    """Nace en `DRAFT`. No hay forma de crear un documento ya aprobado."""
    servicio = _servicio(peticion, sesion, reloj, configuracion)
    documento = await servicio.crear_documento(
        principal=principal,
        titulo=cuerpo.titulo,
        tipo=cuerpo.tipo.value,
        sensibilidad=cuerpo.sensibilidad,
        branch_id=cuerpo.branch_id,
        specialty_id=cuerpo.specialty_id,
        service_id=cuerpo.service_id,
        responsable_id=cuerpo.responsable_id,
        etiquetas=cuerpo.etiquetas,
        effective_from=cuerpo.effective_from,
        effective_until=cuerpo.effective_until,
    )
    respuesta = await _a_respuesta(sesion, documento)
    await sesion.commit()
    return respuesta


@enrutador.post(
    "/documentos/{document_id}/versiones",
    response_model=RespuestaIngesta,
    status_code=status.HTTP_201_CREATED,
    summary="Subir una version nueva",
    responses={404: {"description": "El documento no existe"}},
)
async def ingerir_version(
    principal: PuedeCargar,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    peticion: Request,
    document_id: IdDocumento,
    cuerpo: SolicitudIngesta,
) -> RespuestaIngesta:
    """Fragmenta y vectoriza. **No cambia el estado del documento.**

    Un documento publicado sigue publicado con su version vigente mientras la
    nueva se revisa: subir contenido no puede ser una via para que texto sin
    aprobar llegue al agente.
    """
    servicio = _servicio(peticion, sesion, reloj, configuracion)
    resultado = await servicio.ingerir_texto(
        principal=principal,
        document_id=document_id,
        contenido=cuerpo.contenido,
        nombre_archivo=cuerpo.nombre_archivo,
        notas_cambio=cuerpo.notas_cambio,
    )

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.DOCUMENTO_CARGADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="knowledge_document",
                entidad_id=document_id,
                version=resultado.version,
                fragmentos=resultado.fragmentos,
                riesgo_inyeccion=resultado.riesgo_inyeccion.value,
            )
        ]
    )
    await sesion.commit()
    return RespuestaIngesta(
        document_id=resultado.document_id,
        version=resultado.version,
        fragmentos=resultado.fragmentos,
        embeddings=resultado.embeddings,
        riesgo_inyeccion=resultado.riesgo_inyeccion.value,
        requiere_revision=resultado.requiere_revision,
    )


@enrutador.post(
    "/documentos/{document_id}/estado",
    response_model=RespuestaDocumento,
    summary="Cambiar el estado de un documento",
    responses={
        403: {"description": "Sin el permiso que exige ese estado"},
        404: {"description": "El documento no existe"},
        409: {"description": "Transicion de estado no permitida"},
    },
)
async def cambiar_estado(
    principal: PuedeCargar,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    peticion: Request,
    document_id: IdDocumento,
    cuerpo: SolicitudCambioEstado,
) -> RespuestaDocumento:
    """Aprobar y archivar exigen permisos propios, ademas del de carga.

    La dependencia concede `conocimiento.cargar`; los estados que importan se
    comprueban aqui porque dependen del **cuerpo** de la peticion, y una
    dependencia de FastAPI no lo ve.
    """
    destino = cuerpo.nuevo_estado.value
    if destino in ESTADOS_QUE_EXIGEN_APROBAR and not principal.tiene_permiso(
        "conocimiento.aprobar"
    ):
        raise PermisoDenegado(
            "Aprobar o publicar un documento exige el permiso "
            "`conocimiento.aprobar`. Quien carga no aprueba."
        )
    if destino == ESTADO_QUE_EXIGE_ARCHIVAR and not principal.tiene_permiso(
        "conocimiento.archivar"
    ):
        raise PermisoDenegado("Archivar un documento exige el permiso `conocimiento.archivar`.")

    servicio = _servicio(peticion, sesion, reloj, configuracion)
    documento = await servicio.cambiar_estado(
        principal=principal,
        document_id=document_id,
        nuevo_estado=cuerpo.nuevo_estado,
        motivo=cuerpo.motivo,
    )

    accion = {
        EstadoDocumento.APPROVED.value: AccionAuditada.DOCUMENTO_APROBADO,
        EstadoDocumento.PUBLISHED.value: AccionAuditada.DOCUMENTO_PUBLICADO,
        EstadoDocumento.ARCHIVED.value: AccionAuditada.DOCUMENTO_ARCHIVADO,
        EstadoDocumento.PENDING_REVIEW.value: AccionAuditada.DOCUMENTO_MARCADO_REVISION,
    }.get(destino)
    if accion is not None:
        await auditor.registrar(
            [
                construir_entrada(
                    accion=accion,
                    principal=principal,
                    ahora=reloj.ahora(),
                    entidad_tipo="knowledge_document",
                    entidad_id=document_id,
                    motivo=cuerpo.motivo,
                    estado_nuevo=destino,
                )
            ]
        )

    respuesta = await _a_respuesta(sesion, documento)
    await sesion.commit()
    return respuesta


@enrutador.post(
    "/documentos/{document_id}/revision-de-riesgo",
    response_model=RespuestaDocumento,
    summary="Marcar como revisado un contenido de riesgo",
    responses={
        403: {"description": "Sin permiso de aprobacion"},
        404: {"description": "La version no existe"},
    },
)
async def marcar_revisado(
    principal: PuedeAprobar,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    peticion: Request,
    document_id: IdDocumento,
    cuerpo: SolicitudRevision,
) -> RespuestaDocumento:
    """Desbloquea la aprobacion de un documento marcado por el analisis.

    Exige el permiso de **aprobacion**, no el de carga: quien sube el archivo
    no puede levantar la alerta que su propio archivo provoco.
    """
    servicio = _servicio(peticion, sesion, reloj, configuracion)
    await servicio.marcar_revisado(
        principal=principal,
        document_id=document_id,
        version=cuerpo.version,
        nota=cuerpo.nota,
    )

    documento = (
        await sesion.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.clinic_id == principal.clinica_id,
            )
        )
    ).scalar_one_or_none()
    if documento is None:
        raise RecursoNoEncontrado("El documento no existe.")

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.INYECCION_DETECTADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="knowledge_version",
                entidad_id=document_id,
                motivo=cuerpo.nota,
                version=cuerpo.version,
                accion_tomada="revisado_y_aceptado",
            )
        ]
    )
    respuesta = await _a_respuesta(sesion, documento)
    await sesion.commit()
    return respuesta


# ---------------------------------------------------------------------------
#  Busqueda
# ---------------------------------------------------------------------------
@enrutador.post(
    "/busqueda",
    response_model=RespuestaBusqueda,
    summary="Buscar en la base de conocimiento",
    responses={403: {"description": "Sin permiso de lectura de conocimiento"}},
)
async def buscar(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    peticion: Request,
    cuerpo: SolicitudBusqueda,
) -> RespuestaBusqueda:
    """Busqueda hibrida con el ambito del solicitante.

    Un resultado vacio **no es un error**: significa que no hay documentacion
    aprobada que cubra la consulta, y la respuesta lleva el mensaje que el
    cliente debe mostrar en lugar de improvisar (RF-O06).
    """
    ahora = reloj.ahora()
    recuperador = Recuperador(
        sesion,
        _embeddings(peticion),
        top_k=cuerpo.limite,
        candidatos=configuracion.rag_top_k_candidatos,
        peso_vectorial=configuracion.rag_peso_vectorial,
    )
    resultado = await recuperador.recuperar(
        consulta=cuerpo.consulta,
        contexto=contexto_desde_principal(principal, ahora=ahora),
    )

    # La auditoria registra las FUENTES, no la consulta: el texto puede
    # contener el motivo por el que alguien pregunta, y eso es informacion de
    # salud. Lo que hay que poder reconstruir es que documentos se usaron.
    await auditor.registrar(
        [
            construir_entrada(
                accion=(
                    AccionAuditada.CONSULTA_RAG
                    if resultado.hay_fuente
                    else AccionAuditada.RAG_SIN_FUENTE
                ),
                principal=principal,
                ahora=ahora,
                entidad_tipo="knowledge_document",
                entidad_id=resultado.documentos[0] if resultado.documentos else None,
                fuentes=resultado.referencias,
                resultados=len(resultado.fragmentos),
            )
        ]
    )
    await sesion.commit()

    return RespuestaBusqueda(
        hay_fuente=resultado.hay_fuente,
        mensaje=None if resultado.hay_fuente else MENSAJE_SIN_FUENTE,
        resultados=[
            ResultadoBusqueda(
                document_id=f.document_id,
                version=f.version,
                indice_fragmento=f.indice_fragmento,
                referencia=f.referencia,
                extracto=f.contenido[:LONGITUD_EXTRACTO],
                puntuacion=f.puntuacion,
                posicion_vectorial=f.posicion_vectorial,
                posicion_textual=f.posicion_textual,
            )
            for f in resultado.fragmentos
        ],
        documentos_citados=resultado.documentos,
    )


__all__ = ["enrutador"]
