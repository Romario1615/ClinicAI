from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.modulos.imagenes.adjuntos_modelos import FotoRegistro
from app.modulos.imagenes.adjuntos_servicios import ServicioFotosRegistro
from app.nucleo.almacen import ErrorAlmacen
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad
from app.nucleo.dependencias import (
    AlmacenActual,
    Auditor,
    CifradorActual,
    ConfiguracionActual,
    PrincipalActual,
    RelojActual,
    Sesion,
)
from app.nucleo.errores import ArchivoDemasiadoGrande, DatosInvalidos, ProveedorExternoNoDisponible

MIN_MOTIVO = 8

enrutador = APIRouter(
    prefix="/fotos-registro/{tipo}/{id_registro}", tags=["fotografías de registros"]
)


class FotoRegistroSalida(BaseModel):
    id: uuid.UUID
    tipo_mime: str
    tamano_bytes: int
    descripcion: str | None
    creado_en: datetime


def salida(fila: FotoRegistro) -> FotoRegistroSalida:
    return FotoRegistroSalida(
        id=fila.id,
        tipo_mime=fila.tipo_mime,
        tamano_bytes=fila.tamano_bytes,
        descripcion=fila.descripcion,
        creado_en=fila.creado_en,
    )


async def auditar(
    fila: FotoRegistro,
    accion: AccionAuditada,
    principal: PrincipalActual,
    reloj: RelojActual,
    auditor: Auditor,
) -> None:
    await auditor.registrar(
        [
            construir_entrada(
                accion=accion,
                principal=replace(principal, clinica_id=fila.clinica_id),
                ahora=reloj.ahora(),
                entidad_tipo="foto_registro",
                entidad_id=fila.id,
                paciente_id=fila.paciente_id,
                nivel_sensibilidad=NivelSensibilidad(fila.nivel_sensibilidad),
                tipo_registro=fila.tipo_registro,
            )
        ]
    )


@enrutador.get("", response_model=list[FotoRegistroSalida])
async def listar(
    principal: PrincipalActual,
    tipo: str,
    id_registro: uuid.UUID,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> list[FotoRegistroSalida]:
    servicio = ServicioFotosRegistro(sesion, reloj)
    destino = await servicio.acceso(principal, tipo, id_registro)
    filas = await servicio.repo.listar(
        tipo,
        id_registro,
        servicio.clinica_destino(tipo, destino),
        niveles=servicio.niveles_permitidos(principal, tipo),
    )
    for fila in filas:
        await auditar(fila, AccionAuditada.IMAGEN_CONSULTADA, principal, reloj, auditor)
    await sesion.commit()
    return [salida(f) for f in filas]


@enrutador.post("", response_model=FotoRegistroSalida, status_code=status.HTTP_201_CREATED)
async def subir(
    principal: PrincipalActual,
    tipo: str,
    id_registro: uuid.UUID,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    configuracion: ConfiguracionActual,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    archivo: Annotated[UploadFile, File()],
    clave_idempotencia: Annotated[uuid.UUID, Form()],
    descripcion: Annotated[str | None, Form(max_length=500)] = None,
) -> FotoRegistroSalida:
    maximo = configuracion.max_tamano_archivo_mb * 1024 * 1024
    try:
        contenido = await archivo.read(maximo + 1)
    finally:
        await archivo.close()
    if len(contenido) > maximo:
        raise ArchivoDemasiadoGrande("El archivo supera el límite configurado.")
    servicio = ServicioFotosRegistro(sesion, reloj)
    fila = await servicio.subir(
        principal,
        tipo,
        id_registro,
        clave_idempotencia,
        contenido,
        descripcion,
        configuracion,
        almacen,
        cifrador,
    )
    await auditar(fila, AccionAuditada.IMAGEN_CARGADA, principal, reloj, auditor)
    await sesion.commit()
    return salida(fila)


@enrutador.get("/{id_foto}/contenido", response_class=Response)
async def contenido(
    principal: PrincipalActual,
    tipo: str,
    id_registro: uuid.UUID,
    id_foto: uuid.UUID,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
) -> Response:
    fila = await ServicioFotosRegistro(sesion, reloj).foto(principal, tipo, id_registro, id_foto)
    try:
        cifrado = await almacen.leer(fila.clave_objeto)
        datos = cifrador.descifrar_bytes(cifrado, contexto=fila.id.bytes)
    except (ErrorAlmacen, OSError, ValueError) as exc:
        raise ProveedorExternoNoDisponible("La imagen no está disponible temporalmente.") from exc
    await auditar(fila, AccionAuditada.IMAGEN_CONSULTADA, principal, reloj, auditor)
    await sesion.commit()
    return Response(
        datos,
        media_type=fila.tipo_mime,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


class RetirarFoto(BaseModel):
    motivo: str = Field(min_length=8, max_length=500)


@enrutador.post("/{id_foto}/retirar", status_code=status.HTTP_204_NO_CONTENT)
async def retirar(
    principal: PrincipalActual,
    tipo: str,
    id_registro: uuid.UUID,
    id_foto: uuid.UUID,
    datos: RetirarFoto,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> Response:
    if len(datos.motivo.strip()) < MIN_MOTIVO:
        raise DatosInvalidos("Explique el motivo de retirar la foto.")
    fila = await ServicioFotosRegistro(sesion, reloj).foto(
        principal, tipo, id_registro, id_foto, True
    )
    fila.anulado_en, fila.anulado_por, fila.motivo_anulacion = (
        reloj.ahora(),
        principal.actor_id,
        datos.motivo.strip(),
    )
    await auditar(fila, AccionAuditada.IMAGEN_ANULADA, principal, reloj, auditor)
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
