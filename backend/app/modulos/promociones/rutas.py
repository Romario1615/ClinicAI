"""Endpoints de campanas de promociones por WhatsApp.

Permisos: `promocion.gestionar` redacta, sube o genera la imagen y consulta
la audiencia; `promocion.aprobar` aprueba, envia y cancela. Todas las
escrituras quedan en auditoria. La audiencia se devuelve como recuento: esta
API no lista pacientes para marketing.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Path, Request, Response, UploadFile, status

from app.ia.imagenes_generativas import GeneradorImagenes
from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox
from app.modulos.outbox.modelos import CanalOutbox
from app.modulos.promociones.esquemas import (
    Audiencia,
    CambiosCampana,
    CampanaNueva,
    CampanaSalida,
    Cancelacion,
    EnviarCampana,
    GenerarImagen,
    Segmento,
)
from app.modulos.promociones.modelos import CampanaPromocion
from app.modulos.promociones.servicios import ServicioPromociones
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    AlmacenActual,
    Auditor,
    CifradorActual,
    ConfiguracionActual,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import ArchivoDemasiadoGrande
from app.tareas.outbox import construir_canales

enrutador = APIRouter(prefix="/promociones", tags=["promociones"])

PuedeGestionar = Annotated[Principal, Depends(exige_permiso("promocion.gestionar"))]
PuedeAprobar = Annotated[Principal, Depends(exige_permiso("promocion.aprobar"))]


def _generador(peticion: Request) -> GeneradorImagenes:
    generador: GeneradorImagenes = peticion.app.state.generador_imagenes
    return generador


def _servicio(
    peticion: Request,
    sesion: Sesion,
    reloj: RelojActual,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    configuracion: ConfiguracionActual,
) -> ServicioPromociones:
    return ServicioPromociones(
        sesion, reloj, almacen, cifrador, configuracion, _generador(peticion)
    )


Servicio = Annotated[ServicioPromociones, Depends(_servicio)]


def _salida(campana: CampanaPromocion) -> CampanaSalida:
    return CampanaSalida(
        id=campana.id,
        nombre=campana.nombre,
        texto=campana.texto,
        plantilla_meta=campana.plantilla_meta,
        estado=campana.estado,
        segmento=Segmento.model_validate(campana.segmento or {}),
        tiene_imagen=campana.imagen_clave is not None,
        imagen_origen=campana.imagen_origen,
        imagen_proveedor=campana.imagen_proveedor,
        imagen_prompt=campana.imagen_prompt,
        aprobada_en=campana.aprobada_en,
        programada_para=campana.programada_para,
        enviada_en=campana.enviada_en,
        encolados=campana.encolados,
        omitidos=campana.omitidos,
        cancelada_en=campana.cancelada_en,
        motivo_cancelacion=campana.motivo_cancelacion,
        creado_en=campana.creado_en,
        vista_previa=ServicioPromociones.vista_previa(campana),
    )


async def _auditar(
    auditor: Auditor,
    principal: Principal,
    reloj: RelojActual,
    accion: AccionAuditada,
    campana: CampanaPromocion,
    **extra: Any,
) -> None:
    await auditor.registrar(
        [
            construir_entrada(
                accion=accion,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="campana_promocion",
                entidad_id=campana.id,
                estado=campana.estado,
                **extra,
            )
        ]
    )


@enrutador.get("/campanas", response_model=list[CampanaSalida], summary="Listar campanas")
async def listar(principal: PuedeGestionar, servicio: Servicio) -> list[CampanaSalida]:
    return [_salida(campana) for campana in await servicio.listar(principal)]


@enrutador.post(
    "/campanas",
    response_model=CampanaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una campana en borrador",
)
async def crear(
    principal: PuedeGestionar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    datos: CampanaNueva,
) -> CampanaSalida:
    campana = await servicio.crear(datos, principal)
    await _auditar(auditor, principal, reloj, AccionAuditada.CAMPANA_CREADA, campana)
    await sesion.commit()
    return _salida(campana)


@enrutador.get("/campanas/{campana_id}", response_model=CampanaSalida)
async def obtener(
    principal: PuedeGestionar,
    servicio: Servicio,
    campana_id: Annotated[uuid.UUID, Path()],
) -> CampanaSalida:
    return _salida(await servicio.obtener(campana_id, principal))


@enrutador.patch("/campanas/{campana_id}", response_model=CampanaSalida)
async def modificar(
    principal: PuedeGestionar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    campana_id: Annotated[uuid.UUID, Path()],
    cambios: CambiosCampana,
) -> CampanaSalida:
    campana = await servicio.modificar(campana_id, cambios, principal)
    await _auditar(auditor, principal, reloj, AccionAuditada.CAMPANA_MODIFICADA, campana)
    await sesion.commit()
    return _salida(campana)


@enrutador.post("/campanas/{campana_id}/imagen", response_model=CampanaSalida)
async def subir_imagen(
    principal: PuedeGestionar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    campana_id: Annotated[uuid.UUID, Path()],
    archivo: Annotated[UploadFile, File()],
) -> CampanaSalida:
    maximo = configuracion.max_tamano_archivo_mb * 1024 * 1024
    try:
        contenido = await archivo.read(maximo + 1)
    finally:
        await archivo.close()
    if len(contenido) > maximo:
        raise ArchivoDemasiadoGrande("La imagen supera el limite configurado.")
    campana = await servicio.subir_imagen(campana_id, contenido, principal)
    await _auditar(
        auditor, principal, reloj, AccionAuditada.CAMPANA_IMAGEN, campana, origen_imagen="SUBIDA"
    )
    await sesion.commit()
    return _salida(campana)


@enrutador.post(
    "/campanas/{campana_id}/imagen-generada",
    response_model=CampanaSalida,
    summary="Proponer una imagen con el modelo de generacion",
)
async def generar_imagen(
    principal: PuedeGestionar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    campana_id: Annotated[uuid.UUID, Path()],
    datos: GenerarImagen,
) -> CampanaSalida:
    campana = await servicio.generar_imagen(campana_id, datos.descripcion, principal)
    await _auditar(
        auditor,
        principal,
        reloj,
        AccionAuditada.CAMPANA_IMAGEN,
        campana,
        origen_imagen="GENERADA",
        proveedor=campana.imagen_proveedor,
    )
    await sesion.commit()
    return _salida(campana)


@enrutador.get("/campanas/{campana_id}/imagen", summary="Imagen de la campana")
async def imagen(
    principal: PuedeGestionar,
    servicio: Servicio,
    campana_id: Annotated[uuid.UUID, Path()],
) -> Response:
    datos, mime = await servicio.leer_imagen(campana_id, principal)
    return Response(
        content=datos,
        media_type=mime,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@enrutador.get("/campanas/{campana_id}/audiencia", response_model=Audiencia)
async def audiencia(
    principal: PuedeGestionar,
    servicio: Servicio,
    campana_id: Annotated[uuid.UUID, Path()],
) -> Audiencia:
    return Audiencia(con_consentimiento=await servicio.contar_audiencia(campana_id, principal))


@enrutador.post("/campanas/{campana_id}/aprobacion", response_model=CampanaSalida)
async def aprobar(
    principal: PuedeAprobar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    campana_id: Annotated[uuid.UUID, Path()],
) -> CampanaSalida:
    campana = await servicio.aprobar(campana_id, principal)
    await _auditar(auditor, principal, reloj, AccionAuditada.CAMPANA_APROBADA, campana)
    await sesion.commit()
    return _salida(campana)


@enrutador.post("/campanas/{campana_id}/envio", response_model=CampanaSalida)
async def enviar(
    principal: PuedeAprobar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    campana_id: Annotated[uuid.UUID, Path()],
    datos: EnviarCampana,
) -> CampanaSalida:
    canales = construir_canales(configuracion)
    adaptador = canales.obtener(CanalOutbox.WHATSAPP.value)
    campana = await servicio.enviar(
        campana_id,
        principal,
        outbox=ServicioOutbox(sesion, reloj, RegistroCanales()),
        subir_medio=getattr(adaptador, "subir_medio", None),
        programada_para=datos.programada_para,
    )
    await _auditar(
        auditor,
        principal,
        reloj,
        AccionAuditada.CAMPANA_ENVIADA,
        campana,
        encolados=campana.encolados,
        omitidos=campana.omitidos,
    )
    await sesion.commit()
    return _salida(campana)


@enrutador.post("/campanas/{campana_id}/cancelacion", response_model=CampanaSalida)
async def cancelar(
    principal: PuedeAprobar,
    servicio: Servicio,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    campana_id: Annotated[uuid.UUID, Path()],
    datos: Cancelacion,
) -> CampanaSalida:
    campana = await servicio.cancelar(campana_id, datos.motivo, principal)
    entrada_motivo = datos.motivo.strip()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CAMPANA_CANCELADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="campana_promocion",
                entidad_id=campana.id,
                motivo=entrada_motivo,
            )
        ]
    )
    await sesion.commit()
    return _salida(campana)


__all__ = ["enrutador"]
