"""Foto de las personas del equipo (cualquier rol) y de los profesionales.

Para qué sirve
--------------
Reconocer a quién se asigna una tarea, quién atiende en la agenda y quién
firmó. Es dato de identificación (N1), no clínico: la ve el personal de la
misma clínica y la cambia la propia persona o quien gestiona usuarios.

Cómo se guarda
--------------
Igual que la foto de un paciente: tipo real por contenido, sin metadatos
EXIF/GPS, cifrada en la aplicación antes del almacén y servida solo por el
API. Cambiar la foto crea una fila nueva y deja la anterior como no vigente:
no se borra nada.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Path, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.almacen import ErrorAlmacen
from app.nucleo.archivos import sanear_imagen
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador
from app.nucleo.dependencias import (
    AlmacenActual,
    Auditor,
    CifradorActual,
    ConfiguracionActual,
    PrincipalActual,
    RelojActual,
    Sesion,
)
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    PermisoDenegado,
    ProveedorExternoNoDisponible,
    RecursoNoEncontrado,
)


class FotoUsuario(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "foto_usuario"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    clave_objeto: Mapped[str] = mapped_column(String(300))
    tipo_mime: Mapped[str] = mapped_column(String(32))
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index(
            "ix_foto_usuario_una_vigente",
            "usuario_id",
            unique=True,
            postgresql_where=text("vigente"),
        ),
    )


class FotoUsuarioSalida(BaseModel):
    usuario_id: uuid.UUID
    tipo_mime: str
    tamano_bytes: int
    actualizada_en: datetime


enrutador = APIRouter(tags=["usuarios"])


def _exigir_personal(principal: Principal) -> uuid.UUID:
    """Solo personal con sesión de una clínica; nunca el agente."""
    if principal.es_agente or principal.clinica_id is None or principal.actor_id is None:
        raise PermisoDenegado("Las fotos del equipo solo las ve el personal de la clínica.")
    return principal.clinica_id


async def _usuario_de_la_clinica(
    sesion: AsyncSession, usuario_id: uuid.UUID, clinica_id: uuid.UUID
) -> Usuario:
    usuario = await sesion.get(Usuario, usuario_id)
    if usuario is None or usuario.clinica_id != clinica_id:
        raise RecursoNoEncontrado("La persona indicada no existe.")
    return usuario


async def _servir(
    sesion: AsyncSession,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    usuario_id: uuid.UUID,
) -> Response:
    foto = (
        await sesion.execute(
            select(FotoUsuario).where(
                FotoUsuario.usuario_id == usuario_id, FotoUsuario.vigente.is_(True)
            )
        )
    ).scalar_one_or_none()
    if foto is None:
        # Sin foto, la interfaz pinta las iniciales.
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    try:
        cifrado = await almacen.leer(foto.clave_objeto)
    except (ErrorAlmacen, OSError) as exc:
        raise ProveedorExternoNoDisponible("La foto no está disponible en este momento.") from exc
    return Response(
        content=cifrador.descifrar_bytes(cifrado, contexto=foto.id.bytes),
        media_type=foto.tipo_mime,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@enrutador.get("/usuarios/{usuario_id}/foto", response_class=Response)
async def ver_foto_usuario(
    principal: PrincipalActual,
    sesion: Sesion,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    usuario_id: Annotated[uuid.UUID, Path()],
) -> Response:
    clinica_id = _exigir_personal(principal)
    await _usuario_de_la_clinica(sesion, usuario_id, clinica_id)
    return await _servir(sesion, almacen, cifrador, usuario_id)


@enrutador.get("/profesionales/{profesional_id}/foto", response_class=Response)
async def ver_foto_profesional(
    principal: PrincipalActual,
    sesion: Sesion,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    profesional_id: Annotated[uuid.UUID, Path()],
) -> Response:
    clinica_id = _exigir_personal(principal)
    profesional = await sesion.get(Profesional, profesional_id)
    if profesional is None or profesional.clinica_id != clinica_id:
        raise RecursoNoEncontrado("El profesional indicado no existe.")
    if profesional.usuario_id is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return await _servir(sesion, almacen, cifrador, profesional.usuario_id)


@enrutador.put("/usuarios/{usuario_id}/foto", response_model=FotoUsuarioSalida)
async def cambiar_foto_usuario(
    principal: PrincipalActual,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    almacen: AlmacenActual,
    cifrador: CifradorActual,
    configuracion: ConfiguracionActual,
    usuario_id: Annotated[uuid.UUID, Path()],
    archivo: Annotated[UploadFile, File()],
) -> FotoUsuarioSalida:
    clinica_id = _exigir_personal(principal)
    usuario = await _usuario_de_la_clinica(sesion, usuario_id, clinica_id)
    propia = usuario.id == principal.actor_id
    if not propia and not principal.tiene_permiso("usuario.editar"):
        raise PermisoDenegado("Solo puede cambiar su propia foto.")

    maximo = configuracion.max_tamano_archivo_mb * 1024 * 1024
    try:
        contenido = await archivo.read(maximo + 1)
    finally:
        await archivo.close()
    if len(contenido) > maximo:
        raise ArchivoDemasiadoGrande("El archivo supera el límite configurado.")
    saneada = await sanear_imagen(contenido, configuracion)

    identificador = uuid.uuid4()
    clave = f"{clinica_id}/usuarios/{usuario_id}/{identificador}"
    await sesion.execute(
        update(FotoUsuario)
        .where(FotoUsuario.usuario_id == usuario_id, FotoUsuario.vigente.is_(True))
        .values(vigente=False)
    )
    await sesion.flush()
    foto = FotoUsuario(
        id=identificador,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        clave_objeto=clave,
        tipo_mime=saneada.tipo_mime,
        tamano_bytes=len(saneada.datos),
        sha256=saneada.sha256,
        creado_por=principal.actor_id,
    )
    sesion.add(foto)
    await sesion.flush()
    try:
        await almacen.guardar(
            clave, cifrador.cifrar_bytes(saneada.datos, contexto=identificador.bytes)
        )
    except (ErrorAlmacen, OSError) as exc:
        await sesion.rollback()
        raise ProveedorExternoNoDisponible(
            "No se pudo guardar la foto. Inténtelo de nuevo en unos minutos."
        ) from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_FOTO_ACTUALIZADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario_id,
                propia=propia,
            )
        ]
    )
    await sesion.commit()
    return FotoUsuarioSalida(
        usuario_id=usuario_id,
        tipo_mime=foto.tipo_mime,
        tamano_bytes=foto.tamano_bytes,
        actualizada_en=reloj.ahora(),
    )


__all__ = ["FotoUsuario", "enrutador"]
