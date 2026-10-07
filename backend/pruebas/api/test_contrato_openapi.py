"""Puerta de contrato OpenAPI con Schemathesis.

La prueba valida el documento completo generado por FastAPI y ejercita una
ruta sin efectos secundarios mediante el transporte ASGI de las pruebas.
"""

from __future__ import annotations

import pytest
import schemathesis
from fastapi import FastAPI
from httpx import AsyncClient
from hypothesis import Phase, find, settings

# Se ejecuta con la batería API de CI (`-m "integracion or api"`), no solo
# en la corrida de cobertura.
pytestmark = pytest.mark.api


def test_esquema_openapi_completo_es_valido(aplicacion: FastAPI) -> None:
    """Detecta esquemas o referencias que Schemathesis no pueda interpretar."""
    esquema = schemathesis.openapi.from_dict(aplicacion.openapi())

    esquema.validate()

    operaciones = list(esquema.get_all_operations())
    assert len(operaciones) >= 100


async def test_operaciones_cumplen_el_contrato_openapi(
    aplicacion: FastAPI, cliente: AsyncClient
) -> None:
    """Genera un caso por operación y valida la respuesta HTTP del contrato."""
    esquema = schemathesis.openapi.from_dict(aplicacion.openapi())
    operaciones = [resultado.ok() for resultado in esquema.get_all_operations()]
    assert len(operaciones) >= 100

    for operacion in operaciones:
        caso = find(
            esquema.get_case_strategy(operacion),
            lambda _: True,
            settings=settings(
                max_examples=1,
                phases=(Phase.generate,),
                derandomize=True,
                database=None,
            ),
        )
        solicitud = caso.as_transport_kwargs(base_url="http://pruebas.invalid")
        # Los casos son anónimos por diseño para impedir escrituras protegidas;
        # Schemathesis serializa cookies vacías y httpx las marca obsoletas.
        solicitud.pop("cookies", None)
        if isinstance(solicitud.get("data"), bytes):
            # Schemathesis serializa cuerpos JSON nulos en `data`; HTTPX pide
            # `content` para los bytes sin codificar.
            solicitud["content"] = solicitud.pop("data")
        respuesta = await cliente.request(**solicitud)
        await respuesta.aread()
        await respuesta.request.aread()
        caso.validate_response(respuesta)
