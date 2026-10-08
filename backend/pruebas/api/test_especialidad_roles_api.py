"""La identificacion muestra la especialidad real sin mezclar clinicas."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Especialidad
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Rol, Usuario, UsuarioRol
from app.nucleo.autorizacion import PERMISOS_POR_ROL
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _seleccionar_profesional_local(sesion: AsyncSession, usuario: Usuario) -> None:
    await sesion.execute(
        sa.update(Usuario).where(Usuario.apellido.contains("[SINTETICO]")).values(activo=False)
    )
    usuario.activo = True
    usuario.apellido = "Profesional [SINTETICO]"
    rol = await sesion.scalar(
        sa.select(Rol).where(Rol.codigo == "profesional", Rol.es_sistema.is_(True))
    )
    assert rol is not None
    sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    await sesion.flush()


@pytest.mark.parametrize(
    "nombre", ["Odontologia sintetica", "Dermatologia sintetica", "Estetica sintetica"]
)
async def test_acceso_y_sesion_indican_la_especialidad_de_la_misma_cuenta(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    profesional: Profesional,
    especialidad: Especialidad,
    nombre: str,
) -> None:
    await _seleccionar_profesional_local(sesion, usuario)
    especialidad.nombre = nombre
    await sesion.flush()
    accesos = await cliente.get(f"{api}/autenticacion/accesos-locales")
    assert accesos.status_code == 200
    rol = next(r for r in accesos.json()["roles"] if r["codigo"] == "profesional")
    assert rol["especialidad"] == nombre
    assert set(rol) == {"codigo", "nombre", "especialidad"}
    ingreso = await cliente.post(
        f"{api}/autenticacion/sesion-local", json={"codigo_rol": "profesional"}
    )
    assert ingreso.status_code == 200
    identidad = await cliente.get(
        f"{api}/autenticacion/yo",
        headers={"Authorization": f"Bearer {ingreso.json()['token_acceso']}"},
    )
    assert identidad.status_code == 200
    assert identidad.json()["usuario_id"] == str(usuario.id)
    assert identidad.json()["especialidad"] == nombre
    assert identidad.json()["profesional_id"] == str(profesional.id)
    especialidad.nombre = nombre + " actualizada"
    await sesion.flush()
    actualizados = await cliente.get(f"{api}/autenticacion/accesos-locales")
    assert (
        next(r for r in actualizados.json()["roles"] if r["codigo"] == "profesional")[
            "especialidad"
        ]
        == especialidad.nombre
    )


@pytest.mark.parametrize(
    "caso",
    [
        "perfil_inactivo",
        "perfil_anulado",
        "especialidad_inactiva",
        "especialidad_anulada",
        "especialidad_ajena",
        "perfil_ajeno",
    ],
)
async def test_no_presenta_perfiles_no_vigentes_ni_especialidades_ajenas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    profesional: Profesional,
    especialidad: Especialidad,
    reloj: RelojFijo,
    caso: str,
) -> None:
    await _seleccionar_profesional_local(sesion, usuario)
    if caso == "perfil_inactivo":
        profesional.activo = False
    elif caso == "perfil_anulado":
        profesional.anulado_en = reloj.ahora()
    elif caso == "especialidad_inactiva":
        especialidad.activa = False
    elif caso == "especialidad_anulada":
        especialidad.anulado_en = reloj.ahora()
    else:
        otra = Clinica(nombre="Otra clinica sintetica")
        sesion.add(otra)
        await sesion.flush()
        if caso == "especialidad_ajena":
            especialidad.clinica_id = otra.id
        else:
            profesional.clinica_id = otra.id
    await sesion.flush()
    respuesta = await cliente.get(f"{api}/autenticacion/accesos-locales")
    assert respuesta.status_code == 200
    assert (
        next(r for r in respuesta.json()["roles"] if r["codigo"] == "profesional")["especialidad"]
        is None
    )


async def test_personal_y_perfiles_solo_indican_especialidades_de_su_clinica(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    profesional: Profesional,
    especialidad: Especialidad,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        *sorted(PERMISOS_POR_ROL["administrador_clinica"]),
        codigo_rol="admin_especialidades",
        todas_las_sedes=True,
    )
    otra = Clinica(nombre="Clinica ajena sintetica")
    sesion.add(otra)
    await sesion.flush()
    ajena = Especialidad(clinica_id=otra.id, nombre="Especialidad privada ajena")
    sesion.add(ajena)
    await sesion.flush()
    sesion.add(
        Profesional(clinica_id=otra.id, especialidad_id=ajena.id, nombre="Perfil", apellido="Ajeno")
    )
    await sesion.flush()
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    personal = await cliente.get(f"{api}/usuarios", headers=cabeceras)
    perfiles = await cliente.get(
        f"{api}/usuarios/profesionales", headers=cabeceras, params={"usuario_id": str(usuario.id)}
    )
    assert personal.status_code == perfiles.status_code == 200
    assert (
        next(u for u in personal.json() if u["id"] == str(usuario.id))["especialidad"]
        == especialidad.nombre
    )
    assert (
        next(p for p in perfiles.json() if p["id"] == str(profesional.id))["especialidad"]
        == especialidad.nombre
    )
    assert "Especialidad privada ajena" not in personal.text + perfiles.text


async def test_identidad_y_personal_siguen_exigiendo_autenticacion(
    cliente: AsyncClient, api: str
) -> None:
    for ruta in ["/autenticacion/yo", "/usuarios", "/usuarios/profesionales"]:
        assert (await cliente.get(api + ruta)).status_code == 401


@pytest.mark.parametrize(
    "caso", ["valido", "perfil_inactivo", "sin_marcador", "otra_area", "otro_rol"]
)
async def test_ingreso_local_por_especialidad_solo_elige_cuentas_sinteticas_validas(
    cliente,
    api,
    sesion,
    usuario,
    profesional,
    especialidad,
    caso,
):
    await _seleccionar_profesional_local(sesion, usuario)
    especialidad.nombre = "Salud estética sintética"
    especialidad.codigo = "EST"
    if caso == "perfil_inactivo":
        profesional.activo = False
    elif caso == "sin_marcador":
        usuario.apellido = "Cuenta sin marcador"
    await sesion.flush()
    opciones = await cliente.get(f"{api}/autenticacion/accesos-locales")
    areas = opciones.json()["especialidades_profesionales"]
    assert any(e["id"] == str(especialidad.id) for e in areas) == (
        caso not in {"perfil_inactivo", "sin_marcador"}
    )

    seleccion = uuid4() if caso == "otra_area" else especialidad.id
    ingreso = await cliente.post(
        f"{api}/autenticacion/sesion-local",
        json={
            "codigo_rol": "recepcion" if caso == "otro_rol" else "profesional",
            "especialidad_id": str(seleccion),
        },
    )
    assert ingreso.status_code == (200 if caso == "valido" else 404), ingreso.text
    if caso == "valido":
        headers = {"Authorization": f"Bearer {ingreso.json()['token_acceso']}"}
        yo = await cliente.get(f"{api}/autenticacion/yo", headers=headers)
        assert yo.json()["usuario_id"] == str(usuario.id)
        assert yo.json()["profesional_id"] == str(profesional.id)
        areas = await cliente.get(f"{api}/historia/especialidades", headers=headers)
        assert areas.json()[0]["modulos"] == ["faciograma", "imagenes"]
        assert (
            await cliente.get(f"{api}/historia/faciograma/zonas", headers=headers)
        ).status_code == 200
