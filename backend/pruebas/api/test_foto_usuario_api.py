"""Foto de las personas del equipo: propia, de otro con permiso, del
profesional por su ficha, y aislamiento entre clínicas."""

from __future__ import annotations

import struct
import uuid
import zlib

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.fotos import FotoUsuario
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


def _trozo(tipo: bytes, contenido: bytes) -> bytes:
    cuerpo = tipo + contenido
    return struct.pack(">I", len(contenido)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))


def _png() -> bytes:
    cabecera = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _trozo(b"IHDR", cabecera)
        + _trozo(b"IDAT", zlib.compress(b"\x00\x21\x43\x65\xff"))
        + _trozo(b"IEND", b"")
    )


async def _otro_usuario(sesion: AsyncSession, clinica: Clinica) -> Usuario:
    otro = Usuario(
        clinica_id=clinica.id,
        correo=f"otro.{uuid.uuid4().hex[:8]}@example.invalid",
        hash_contrasena="x",
        nombre="Otra",
        apellido="Persona",
    )
    sesion.add(otro)
    await sesion.flush()
    return otro


async def test_cada_persona_cambia_su_foto_y_el_equipo_la_ve(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    sin_foto = await cliente.get(f"{api}/usuarios/{usuario.id}/foto", headers=cabeceras)
    assert sin_foto.status_code == 204

    for _ in range(2):
        subida = await cliente.put(
            f"{api}/usuarios/{usuario.id}/foto",
            headers=cabeceras,
            files={"archivo": ("yo.png", _png(), "image/png")},
        )
        assert subida.status_code == 200, subida.text
    vigentes = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                FotoUsuario.usuario_id == usuario.id, FotoUsuario.vigente.is_(True)
            )
        )
    ).scalar_one()
    historico = (
        await sesion.execute(sa.select(sa.func.count()).where(FotoUsuario.usuario_id == usuario.id))
    ).scalar_one()
    assert (vigentes, historico) == (1, 2)

    foto = await cliente.get(f"{api}/usuarios/{usuario.id}/foto", headers=cabeceras)
    assert foto.status_code == 200
    assert foto.headers["content-type"] == "image/png"
    assert foto.headers["cache-control"] == "private, no-store"
    assert foto.content == _png()

    # La ficha del profesional muestra la foto de su usuario.
    profesional.usuario_id = usuario.id
    await sesion.flush()
    del_profesional = await cliente.get(
        f"{api}/profesionales/{profesional.id}/foto", headers=cabeceras
    )
    assert del_profesional.status_code == 200

    # Sin `usuario.editar` no se cambia la foto de otra persona.
    otro = await _otro_usuario(sesion, clinica)
    ajena = await cliente.put(
        f"{api}/usuarios/{otro.id}/foto",
        headers=cabeceras,
        files={"archivo": ("x.png", _png(), "image/png")},
    )
    assert ajena.status_code == 403


async def test_administracion_cambia_la_foto_de_otro_y_no_cruza_clinicas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "usuario.editar", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    otro = await _otro_usuario(sesion, clinica)
    respuesta = await cliente.put(
        f"{api}/usuarios/{otro.id}/foto",
        headers=cabeceras,
        files={"archivo": ("x.png", _png(), "image/png")},
    )
    assert respuesta.status_code == 200, respuesta.text

    ajena = Clinica(nombre="Clínica ajena sintética", identificacion_fiscal=uuid.uuid4().hex[:12])
    sesion.add(ajena)
    await sesion.flush()
    de_otra_clinica = await _otro_usuario(sesion, ajena)
    assert (
        await cliente.get(f"{api}/usuarios/{de_otra_clinica.id}/foto", headers=cabeceras)
    ).status_code == 404
    html = await cliente.put(
        f"{api}/usuarios/{otro.id}/foto",
        headers=cabeceras,
        files={"archivo": ("x.png", b"<html>no</html>", "image/png")},
    )
    assert html.status_code == 415
    assert (await cliente.get(f"{api}/usuarios/{otro.id}/foto")).status_code == 401
