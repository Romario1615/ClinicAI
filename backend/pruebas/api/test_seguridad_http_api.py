"""Cabeceras de seguridad y politica CORS de la aplicacion HTTP real."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.api.middleware import CABECERA_CORRELACION, CABECERAS_SEGURIDAD
from app.nucleo.configuracion import Configuracion

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def test_cabeceras_de_seguridad_se_aplican_a_respuestas_y_errores(
    cliente: AsyncClient,
    configuracion: Configuracion,
) -> None:
    origen = configuracion.lista_origenes_cors[0]
    correcta = await cliente.get("/salud/vivo", headers={"Origin": origen})
    error = await cliente.get("/api/v1/ruta-que-no-existe", headers={"Origin": origen})

    assert correcta.status_code == 200
    assert error.status_code == 404
    for respuesta in (correcta, error):
        for nombre, valor in CABECERAS_SEGURIDAD.items():
            assert respuesta.headers[nombre] == valor
        assert respuesta.headers[CABECERA_CORRELACION]
        assert respuesta.headers["access-control-allow-origin"] == origen
        assert respuesta.headers["access-control-allow-credentials"] == "true"


async def test_preflight_cors_permite_origen_metodo_y_cabeceras_configurados(
    cliente: AsyncClient,
    configuracion: Configuracion,
    api: str,
) -> None:
    origen = configuracion.lista_origenes_cors[0]
    respuesta = await cliente.options(
        f"{api}/autenticacion/sesion",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-request-id",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["access-control-allow-origin"] == origen
    assert respuesta.headers["access-control-allow-credentials"] == "true"
    assert "POST" in respuesta.headers["access-control-allow-methods"]
    permitidas = respuesta.headers["access-control-allow-headers"].lower()
    assert {"authorization", "content-type", "x-request-id"} <= set(permitidas.split(", "))


async def test_preflight_cors_rechaza_un_origen_no_configurado(
    cliente: AsyncClient,
    api: str,
) -> None:
    respuesta = await cliente.options(
        f"{api}/autenticacion/sesion",
        headers={
            "Origin": "https://origen-no-autorizado.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert respuesta.status_code == 400
    assert "access-control-allow-origin" not in respuesta.headers
