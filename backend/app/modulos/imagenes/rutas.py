"""Rutas autenticadas para subir, consultar y retirar imágenes de pacientes."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status

from app.modulos.historia.especialidades import exige_modulo
from app.modulos.imagenes.esquemas import AnulacionImagen, ImagenSalida
from app.modulos.imagenes.modelos import ImagenPaciente, TipoImagen
from app.modulos.imagenes.servicios import DatosSubida
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    ServicioDeImagenes,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import ArchivoDemasiadoGrande, DatosInvalidos

enrutador = APIRouter(prefix="/pacientes", tags=["imágenes de pacientes"])
enrutador_imagenes = APIRouter(prefix="/imagenes", tags=["imágenes de pacientes"])
PuedeLeerClinica = Annotated[Principal, Depends(exige_modulo("imagenes", "imagen_clinica.leer"))]
PuedeCargarClinica = Annotated[
    Principal, Depends(exige_modulo("imagenes", "imagen_clinica.cargar"))
]
PuedeLeerPerfil = Annotated[Principal, Depends(exige_permiso("paciente.leer_administrativo"))]
PuedeEditarPaciente = Annotated[Principal, Depends(exige_permiso("paciente.editar"))]
PuedeLeerImagen = Annotated[
    Principal,
    Depends(exige_permiso("imagen_clinica.leer", "paciente.leer_administrativo")),
]
PuedeRetirarImagen = Annotated[
    Principal,
    Depends(exige_permiso("imagen_clinica.cargar", "paciente.editar")),
]


def _salida(imagen: ImagenPaciente) -> ImagenSalida:
    return ImagenSalida(
        id=imagen.id,
        paciente_id=imagen.paciente_id,
        tipo=imagen.tipo,
        piezas=imagen.piezas,
        tomada_en=imagen.tomada_en,
        descripcion=imagen.descripcion,
        procedimiento_id=imagen.procedimiento_id,
        tipo_mime=imagen.tipo_mime,
        tamano_bytes=imagen.tamano_bytes,
        antivirus=imagen.antivirus,
        creado_en=imagen.creado_en,
        url_contenido=f"/api/v1/imagenes/{imagen.id}/contenido",
    )


async def _contenido(archivo: UploadFile, maximo_bytes: int) -> bytes:
    try:
        contenido = await archivo.read(maximo_bytes + 1)
    finally:
        await archivo.close()
    if len(contenido) > maximo_bytes:
        raise ArchivoDemasiadoGrande("El archivo supera el límite configurado.")
    return contenido


@enrutador.get(
    "/{paciente_id}/imagenes",
    response_model=list[ImagenSalida],
    summary="Consultar la galería clínica de un paciente",
)
async def listar_imagenes(
    principal: PuedeLeerClinica,
    sesion: Sesion,
    servicio: ServicioDeImagenes,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    tipo: Annotated[TipoImagen | None, Query()] = None,
    pieza: Annotated[int | None, Query(ge=11, le=85)] = None,
    procedimiento_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[ImagenSalida]:
    if tipo is TipoImagen.PERFIL:
        raise DatosInvalidos("La foto de perfil se consulta por su ruta específica.")
    imagenes, entradas = await servicio.listar_clinicas(
        paciente_id,
        principal=principal,
        tipo=tipo,
        pieza=pieza,
        procedimiento_id=procedimiento_id,
    )
    await auditor.registrar(list(entradas))
    await sesion.commit()
    return [_salida(imagen) for imagen in imagenes]


@enrutador.post(
    "/{paciente_id}/imagenes",
    response_model=ImagenSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar una imagen clínica saneada y cifrada",
)
async def subir_imagen(
    principal: PuedeCargarClinica,
    sesion: Sesion,
    servicio: ServicioDeImagenes,
    auditor: Auditor,
    configuracion: ConfiguracionActual,
    paciente_id: Annotated[uuid.UUID, Path()],
    archivo: Annotated[UploadFile, File()],
    tipo: Annotated[TipoImagen, Form()],
    piezas: Annotated[list[int] | None, Form()] = None,
    tomada_en: Annotated[date | None, Form()] = None,
    descripcion: Annotated[str | None, Form(max_length=500)] = None,
    cita_id: Annotated[uuid.UUID | None, Form()] = None,
    procedimiento_id: Annotated[uuid.UUID | None, Form()] = None,
) -> ImagenSalida:
    # El tamaño se acota antes de pasar los bytes al saneador o al antivirus.
    if not tipo.es_clinica:
        raise DatosInvalidos("Use la ruta de foto de perfil para imágenes de identificación.")
    maximo = configuracion.max_tamano_archivo_mb * 1024 * 1024
    contenido = await _contenido(archivo, maximo)
    imagen, entradas = await servicio.subir(
        DatosSubida(
            paciente_id=paciente_id,
            tipo=tipo,
            contenido=contenido,
            piezas=tuple(piezas or ()),
            tomada_en=tomada_en,
            descripcion=descripcion,
            cita_id=cita_id,
            procedimiento_id=procedimiento_id,
        ),
        principal=principal,
    )
    await auditor.registrar(list(entradas))
    await sesion.commit()
    return _salida(imagen)


@enrutador.get(
    "/{paciente_id}/foto-perfil",
    response_model=ImagenSalida | None,
    summary="Consultar la foto de perfil del paciente",
)
async def foto_perfil(
    principal: PuedeLeerPerfil,
    servicio: ServicioDeImagenes,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> ImagenSalida | None:
    imagen = await servicio.foto_perfil(paciente_id, principal=principal)
    return _salida(imagen) if imagen is not None else None


@enrutador.post(
    "/{paciente_id}/foto-perfil",
    response_model=ImagenSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Actualizar la foto de perfil del paciente",
)
async def subir_foto_perfil(
    principal: PuedeEditarPaciente,
    sesion: Sesion,
    servicio: ServicioDeImagenes,
    auditor: Auditor,
    configuracion: ConfiguracionActual,
    paciente_id: Annotated[uuid.UUID, Path()],
    archivo: Annotated[UploadFile, File()],
) -> ImagenSalida:
    contenido = await _contenido(archivo, configuracion.max_tamano_archivo_mb * 1024 * 1024)
    imagen, entradas = await servicio.subir(
        DatosSubida(paciente_id=paciente_id, tipo=TipoImagen.PERFIL, contenido=contenido),
        principal=principal,
    )
    await auditor.registrar(list(entradas))
    await sesion.commit()
    return _salida(imagen)


@enrutador_imagenes.get(
    "/{imagen_id}/contenido",
    response_class=Response,
    summary="Descargar una imagen autorizada por el paciente real de la fila",
)
async def descargar_imagen(
    principal: PuedeLeerImagen,
    sesion: Sesion,
    servicio: ServicioDeImagenes,
    auditor: Auditor,
    imagen_id: Annotated[uuid.UUID, Path()],
) -> Response:
    descarga, entradas = await servicio.descargar(imagen_id, principal=principal)
    if entradas:
        await auditor.registrar(list(entradas))
        await sesion.commit()
    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[descarga.imagen.tipo_mime]
    return Response(
        content=descarga.datos,
        media_type=descarga.imagen.tipo_mime,
        headers={
            "Content-Disposition": f'inline; filename="{descarga.imagen.id}.{extension}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@enrutador_imagenes.patch(
    "/{imagen_id}/anulacion",
    response_model=ImagenSalida,
    summary="Anular una imagen con motivo, sin borrar el archivo",
)
async def anular_imagen(
    principal: PuedeRetirarImagen,
    sesion: Sesion,
    servicio: ServicioDeImagenes,
    auditor: Auditor,
    imagen_id: Annotated[uuid.UUID, Path()],
    cuerpo: AnulacionImagen,
) -> ImagenSalida:
    imagen, entradas = await servicio.anular(imagen_id, cuerpo.motivo, principal=principal)
    await auditor.registrar(list(entradas))
    await sesion.commit()
    return _salida(imagen)


__all__ = ["enrutador", "enrutador_imagenes"]
