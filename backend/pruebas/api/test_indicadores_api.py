"""Indicadores del panel: cada bloque solo con el permiso de su módulo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


def _rango() -> dict[str, str]:
    inicio = datetime(2026, 10, 5, 5, 0, tzinfo=UTC)
    return {"desde": inicio.isoformat(), "hasta": (inicio + timedelta(days=1)).isoformat()}


async def test_sin_autenticacion_no_responde(cliente: AsyncClient, api: str) -> None:
    respuesta = await cliente.get(f"{api}/dashboard/indicadores", params=_rango())
    assert respuesta.status_code == 401


async def test_solo_devuelve_los_bloques_que_el_rol_alcanza(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "agenda.leer",
        "paciente.leer_administrativo",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(
        f"{api}/dashboard/indicadores", params=_rango(), headers=cabeceras
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["agenda"] is not None
    assert cuerpo["pacientes"]["total"] >= 1
    # Sin esos permisos, esos módulos no aparecen ni como ceros.
    for bloque in ("pagos", "usuarios", "promociones", "conocimiento", "mensajes", "clinico"):
        assert cuerpo[bloque] is None, bloque
    # Solo conteos: ningún dato identificable.
    assert "nombre" not in respuesta.text
    assert (paciente.numero_documento or "sin-documento") not in respuesta.text


async def test_administracion_ve_pagos_usuarios_y_campanas(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "pago.leer",
        "usuario.leer",
        "promocion.gestionar",
        "conocimiento.leer",
        "conversacion.leer",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    cuerpo = (
        await cliente.get(f"{api}/dashboard/indicadores", params=_rango(), headers=cabeceras)
    ).json()
    assert cuerpo["usuarios"]["activos"] >= 1
    assert cuerpo["pagos"]["confirmado_30_dias"] is not None
    assert cuerpo["promociones"] is not None
    assert cuerpo["conocimiento"] is not None
    assert cuerpo["mensajes"] is not None
    assert cuerpo["agenda"] is None


async def test_rango_invalido(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    rango = _rango()
    respuesta = await cliente.get(
        f"{api}/dashboard/indicadores",
        params={"desde": rango["hasta"], "hasta": rango["desde"]},
        headers=cabeceras,
    )
    assert respuesta.status_code == 422
