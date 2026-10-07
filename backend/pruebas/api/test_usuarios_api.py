"""Gestión de cuentas y vínculo con perfiles profesionales."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Especialidad
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Permiso, Rol, RolPermiso, Usuario
from app.nucleo.autorizacion import PERMISOS_POR_ROL
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _autorizar_administrador(
    sesion: AsyncSession, usuario: Usuario, clinica: Clinica
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *sorted(PERMISOS_POR_ROL["administrador_clinica"]),
        codigo_rol=f"admin_usuarios_{uuid.uuid4().hex[:8]}",
        todas_las_sedes=True,
    )


async def _rol_profesional(sesion: AsyncSession, clinica: Clinica) -> Rol:
    rol = await sesion.scalar(
        sa.select(Rol).where(
            Rol.codigo == "profesional", Rol.clinica_id.is_(None), Rol.es_sistema.is_(True)
        )
    )
    assert rol is not None, "cargue el rol de sistema profesional antes de probar su asignación"
    return rol


async def _perfil_sin_cuenta(
    sesion: AsyncSession, clinica: Clinica, especialidad: Especialidad, sufijo: str
) -> Profesional:
    perfil = Profesional(
        clinica_id=clinica.id,
        usuario_id=None,
        especialidad_id=especialidad.id,
        nombre="Perfil",
        apellido=f"Disponible {sufijo}",
        numero_registro_profesional=f"LIB-{sufijo}",
    )
    sesion.add(perfil)
    await sesion.flush()
    return perfil


def _datos_usuario(
    correo: str, roles: list[uuid.UUID], profesional_id: uuid.UUID
) -> dict[str, object]:
    return {
        "correo": correo,
        "contrasena_inicial": "Temporal!Seguro1234",
        "nombre": "Cuenta",
        "apellido": "Profesional",
        "roles": [str(rol) for rol in roles],
        "profesional_id": str(profesional_id),
    }


async def test_perfiles_asignables_solo_devuelve_perfiles_libres_de_la_clinica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    especialidad: Especialidad,
    profesional: Profesional,
    sufijo: str,
) -> None:
    await _autorizar_administrador(sesion, usuario, clinica)
    libre = await _perfil_sin_cuenta(sesion, clinica, especialidad, sufijo)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.get(f"{api}/usuarios/profesionales", headers=cabeceras)
    propios = await cliente.get(
        f"{api}/usuarios/profesionales",
        headers=cabeceras,
        params={"usuario_id": str(usuario.id)},
    )

    assert respuesta.status_code == 200, respuesta.text
    assert [item["id"] for item in respuesta.json()] == [str(libre.id)]
    assert propios.status_code == 200, propios.text
    assert {item["id"] for item in propios.json()} == {str(profesional.id), str(libre.id)}


async def test_alta_y_cambio_de_cuenta_vinculan_y_liberan_perfiles(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    especialidad: Especialidad,
    sufijo: str,
) -> None:
    await _autorizar_administrador(sesion, usuario, clinica)
    rol = await _rol_profesional(sesion, clinica)
    primero = await _perfil_sin_cuenta(sesion, clinica, especialidad, f"{sufijo}a")
    segundo = await _perfil_sin_cuenta(sesion, clinica, especialidad, f"{sufijo}b")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    alta = await cliente.post(
        f"{api}/usuarios",
        headers=cabeceras,
        json=_datos_usuario(f"prof-{sufijo}@example.invalid", [rol.id], primero.id),
    )

    assert alta.status_code == 201, alta.text
    cuenta_id = uuid.UUID(alta.json()["id"])
    assert alta.json()["profesional_id"] == str(primero.id)
    assert (
        await sesion.scalar(sa.select(Profesional.usuario_id).where(Profesional.id == primero.id))
        == cuenta_id
    )

    cambio = await cliente.put(
        f"{api}/usuarios/{cuenta_id}/roles",
        headers=cabeceras,
        json={"roles": [str(rol.id)], "profesional_id": str(segundo.id)},
    )

    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["profesional_id"] == str(segundo.id)
    assert (
        await sesion.scalar(sa.select(Profesional.usuario_id).where(Profesional.id == primero.id))
        is None
    )
    assert (
        await sesion.scalar(sa.select(Profesional.usuario_id).where(Profesional.id == segundo.id))
        == cuenta_id
    )


async def test_alta_rechaza_contrasena_que_no_cumple_la_politica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    especialidad: Especialidad,
    sufijo: str,
) -> None:
    await _autorizar_administrador(sesion, usuario, clinica)
    rol = await _rol_profesional(sesion, clinica)
    perfil = await _perfil_sin_cuenta(sesion, clinica, especialidad, sufijo)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    correo = f"politica-{sufijo}@example.invalid"
    contrasena = "todominusculas123"
    cuerpo = _datos_usuario(correo, [rol.id], perfil.id)
    cuerpo["contrasena_inicial"] = contrasena

    respuesta = await cliente.post(f"{api}/usuarios", headers=cabeceras, json=cuerpo)

    assert respuesta.status_code == 422
    assert "mayuscula" in respuesta.text
    assert contrasena not in respuesta.text
    assert await sesion.scalar(sa.select(Usuario.id).where(Usuario.correo == correo)) is None


async def test_no_permite_vincular_un_perfil_que_ya_tiene_cuenta(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    especialidad: Especialidad,
    sufijo: str,
) -> None:
    await _autorizar_administrador(sesion, usuario, clinica)
    rol = await _rol_profesional(sesion, clinica)
    ocupado = await _perfil_sin_cuenta(sesion, clinica, especialidad, sufijo)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    primera = await cliente.post(
        f"{api}/usuarios",
        headers=cabeceras,
        json=_datos_usuario(f"primero-{sufijo}@example.invalid", [rol.id], ocupado.id),
    )
    assert primera.status_code == 201, primera.text

    duplicada = await cliente.post(
        f"{api}/usuarios",
        headers=cabeceras,
        json=_datos_usuario(f"segundo-{sufijo}@example.invalid", [rol.id], ocupado.id),
    )

    assert duplicada.status_code == 409, duplicada.text
    # El gestor de sesión productivo revierte los cambios pendientes al salir
    # de la petición fallida; este fixture conserva la sesión para toda la
    # prueba, así que aquí comprobamos que la vinculación original no cambió.
    assert await sesion.scalar(
        sa.select(Profesional.usuario_id).where(Profesional.id == ocupado.id)
    ) == uuid.UUID(primera.json()["id"])


async def test_rol_profesional_exige_perfil_de_la_misma_clinica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    especialidad: Especialidad,
    sufijo: str,
) -> None:
    await _autorizar_administrador(sesion, usuario, clinica)
    rol = await _rol_profesional(sesion, clinica)
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    sin_perfil = await cliente.post(
        f"{api}/usuarios",
        headers=cabeceras,
        json={
            **_datos_usuario(f"sin-perfil-{sufijo}@example.invalid", [rol.id], uuid.uuid4()),
            "profesional_id": None,
        },
    )
    assert sin_perfil.status_code == 422
    assert "Vincule un profesional" in sin_perfil.json()["mensaje"]

    clinica_ajena = Clinica(
        nombre=f"Otra clínica {sufijo}",
        identificacion_fiscal=f"AJENA-{sufijo}",
        zona_horaria="America/Guayaquil",
    )
    sesion.add(clinica_ajena)
    await sesion.flush()
    especialidad_ajena = Especialidad(clinica_id=clinica_ajena.id, nombre="Especialidad ajena")
    sesion.add(especialidad_ajena)
    await sesion.flush()
    profesional_ajeno = Profesional(
        clinica_id=clinica_ajena.id,
        usuario_id=None,
        especialidad_id=especialidad_ajena.id,
        nombre="Perfil",
        apellido="Otra clínica",
        numero_registro_profesional=f"AJ-{sufijo}",
    )
    sesion.add(profesional_ajeno)
    await sesion.flush()
    cruzado = await cliente.post(
        f"{api}/usuarios",
        headers=cabeceras,
        json=_datos_usuario(f"cruzado-{sufijo}@example.invalid", [rol.id], profesional_ajeno.id),
    )

    assert cruzado.status_code == 404


async def test_no_delega_permisos_operativos_exclusivos_en_un_rol_personalizado(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sufijo: str,
) -> None:
    await _autorizar_administrador(sesion, usuario, clinica)
    permiso = await sesion.scalar(
        sa.select(Permiso).where(Permiso.codigo == "profesional.conectar_calendario")
    )
    assert permiso is not None
    rol = Rol(
        clinica_id=clinica.id,
        codigo=f"calendario_{sufijo}",
        nombre="Calendario de otro profesional",
    )
    sesion.add(rol)
    await sesion.flush()
    sesion.add(RolPermiso(rol_id=rol.id, permiso_id=permiso.id))
    await sesion.flush()
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.post(
        f"{api}/usuarios",
        headers=cabeceras,
        json={
            "correo": f"sin-delegacion-{sufijo}@example.invalid",
            "contrasena_inicial": "Temporal!Seguro1234",
            "nombre": "Usuario",
            "apellido": "Sin delegación",
            "roles": [str(rol.id)],
        },
    )

    assert respuesta.status_code == 422
    assert "permisos que su propia cuenta no tiene" in respuesta.json()["mensaje"]
