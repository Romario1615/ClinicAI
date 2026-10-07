"""Centro de ayuda: cada persona recibe el manual de sus roles, y nada mas.

* Sin sesion, 401.
* Un rol del sistema recibe su manual escrito; un rol propio de la clinica,
  uno compuesto con sus permisos.
* El manual sigue a los permisos en vivo: si la clinica retira uno, la
  seccion desaparece en la siguiente consulta.
* Un rol de otra clinica nunca aporta un manual, aunque llegara a estar
  asignado.
* No hay parametros que permitan pedir el manual de otro rol.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    Permiso,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioRol,
)
from app.nucleo.autorizacion import CATALOGO_PERMISOS, PERMISOS_POR_ROL, TipoAmbito
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def _permiso(sesion: AsyncSession, codigo: str) -> Permiso:
    permiso = await sesion.scalar(sa.select(Permiso).where(Permiso.codigo == codigo))
    if permiso is None:
        definicion = next(d for d in CATALOGO_PERMISOS if d.codigo == codigo)
        permiso = Permiso(
            codigo=definicion.codigo,
            descripcion=definicion.descripcion,
            categoria=definicion.categoria,
            requiere_relacion_asistencial=definicion.requiere_relacion_asistencial,
            nivel_sensibilidad=definicion.nivel.value,
        )
        sesion.add(permiso)
        await sesion.flush()
    return permiso


async def _asignar_rol_sistema(sesion: AsyncSession, usuario: Usuario, codigo: str) -> Rol:
    """Asigna el rol base del sistema, creandolo si la base no tiene catalogos."""
    rol = await sesion.scalar(sa.select(Rol).where(Rol.codigo == codigo, Rol.clinica_id.is_(None)))
    if rol is None:
        rol = Rol(clinica_id=None, codigo=codigo, nombre=codigo.capitalize(), es_sistema=True)
        sesion.add(rol)
        await sesion.flush()
    for codigo_permiso in PERMISOS_POR_ROL[codigo]:
        permiso = await _permiso(sesion, codigo_permiso)
        existe = await sesion.scalar(
            sa.select(RolPermiso.rol_id).where(
                RolPermiso.rol_id == rol.id, RolPermiso.permiso_id == permiso.id
            )
        )
        if existe is None:
            sesion.add(RolPermiso(rol_id=rol.id, permiso_id=permiso.id))
    asignacion = UsuarioRol(usuario_id=usuario.id, rol_id=rol.id)
    sesion.add(asignacion)
    await sesion.flush()
    sesion.add(
        AmbitoAsignacion(usuario_rol_id=asignacion.id, tipo=TipoAmbito.SEDE.value, valor_id=None)
    )
    await sesion.flush()
    return rol


async def _manuales(
    cliente: AsyncClient, api: str, cabeceras: dict[str, str], **parametros: str
) -> list[dict[str, object]]:
    respuesta = await cliente.get(f"{api}/ayuda/manuales", headers=cabeceras, params=parametros)
    assert respuesta.status_code == 200, respuesta.text
    manuales: list[dict[str, object]] = respuesta.json()["manuales"]
    return manuales


def _claves(manual: dict[str, object]) -> set[str]:
    secciones = manual["secciones"]
    assert isinstance(secciones, list)
    return {seccion["clave"] for seccion in secciones}


async def test_sin_sesion_no_hay_manual(cliente: AsyncClient, api: str) -> None:
    respuesta = await cliente.get(f"{api}/ayuda/manuales")
    assert respuesta.status_code == 401


async def test_sin_roles_vigentes_la_lista_esta_vacia(
    cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica
) -> None:
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    assert await _manuales(cliente, api, cabeceras) == []


async def test_recepcion_recibe_su_manual_sin_secciones_clinicas(
    cliente: AsyncClient, api: str, sesion: AsyncSession, usuario: Usuario, clinica: Clinica
) -> None:
    await _asignar_rol_sistema(sesion, usuario, "recepcion")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    [manual] = await _manuales(cliente, api, cabeceras)

    assert manual["tipo"] == "SISTEMA"
    assert manual["rol_codigo"] == "recepcion"
    assert manual["titulo"] == "Manual de Recepción"
    claves = _claves(manual)
    assert {"recepcion.reservar", "recepcion.llegada", "recepcion.cobros"} <= claves
    assert all(clave.startswith("recepcion.") for clave in claves)
    rutas = {seccion["ruta"] for seccion in manual["secciones"]}  # type: ignore[union-attr]
    assert "/historia-clinica" not in rutas
    # El manual no expone nada de la cuenta ni del ambito.
    assert set(manual) == {
        "rol_codigo",
        "rol_nombre",
        "tipo",
        "titulo",
        "introduccion",
        "responsabilidades",
        "limites",
        "secciones",
    }


async def test_profesional_recibe_un_manual_distinto_al_de_recepcion(
    cliente: AsyncClient, api: str, sesion: AsyncSession, usuario: Usuario, clinica: Clinica
) -> None:
    await _asignar_rol_sistema(sesion, usuario, "profesional")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    [manual] = await _manuales(cliente, api, cabeceras)

    assert manual["titulo"] == "Manual del Profesional"
    assert {"profesional.recetas", "profesional.notas", "profesional.emergencia"} <= _claves(manual)


async def test_un_rol_propio_recibe_un_manual_compuesto_que_sigue_a_sus_permisos(
    cliente: AsyncClient, api: str, sesion: AsyncSession, usuario: Usuario, clinica: Clinica
) -> None:
    rol = await conceder_permisos(
        sesion, usuario, clinica, "agenda.leer", "cita.crear", "pago.leer", todas_las_sedes=True
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    [manual] = await _manuales(cliente, api, cabeceras)
    assert manual["tipo"] == "PERSONALIZADO"
    assert {"capacidad.agenda", "capacidad.citas", "capacidad.cobros"} <= _claves(manual)
    assert "No consulta el contenido de la historia clínica." in manual["limites"]  # type: ignore[operator]

    # La clinica retira la reserva de citas: la seccion deja de existir.
    permiso = await _permiso(sesion, "cita.crear")
    await sesion.execute(
        sa.delete(RolPermiso).where(
            RolPermiso.rol_id == rol.id, RolPermiso.permiso_id == permiso.id
        )
    )
    await sesion.flush()

    [despues] = await _manuales(cliente, api, cabeceras)
    assert "capacidad.citas" not in _claves(despues)
    assert "No reserva citas nuevas." in despues["limites"]  # type: ignore[operator]


async def test_un_rol_de_otra_clinica_no_aporta_manual(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sufijo: str,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", todas_las_sedes=True)
    otra = Clinica(nombre=f"Clinica ajena {sufijo}")
    sesion.add(otra)
    await sesion.flush()
    ajeno = Rol(clinica_id=otra.id, codigo=f"ajeno_{uuid.uuid4().hex[:6]}", nombre="Rol ajeno")
    sesion.add(ajeno)
    await sesion.flush()
    sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=ajeno.id))
    await sesion.flush()
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    manuales = await _manuales(cliente, api, cabeceras)

    assert [m["rol_nombre"] for m in manuales] == ["Rol de prueba"]


async def test_los_parametros_no_cambian_el_manual(
    cliente: AsyncClient, api: str, sesion: AsyncSession, usuario: Usuario, clinica: Clinica
) -> None:
    """El manual sale de la sesion: pedir el de otro rol por la URL no hace nada."""
    await _asignar_rol_sistema(sesion, usuario, "asistente")
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    normal = await _manuales(cliente, api, cabeceras)
    forzado = await _manuales(
        cliente, api, cabeceras, rol="superadministrador", clinica_id=str(uuid.uuid4())
    )

    assert forzado == normal
    assert [m["rol_codigo"] for m in forzado] == ["asistente"]
