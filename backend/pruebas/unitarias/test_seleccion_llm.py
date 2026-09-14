"""Que proveedor conversacional sale de cada configuracion.

La prueba que mas importa aqui es la del modo no implementado: **no** puede
caer en silencio al proveedor de demostracion. Una clinica que cree tener un
agente conversacional y tiene un guion de cadenas fijas no lo descubre por un
error, lo descubre por las quejas.
"""

from __future__ import annotations

import pytest

from app.ia.conversacion import ProveedorDemostracion
from app.ia.proveedor_claude import ProveedorClaude
from app.ia.seleccion_llm import construir_fabrica_conversacional
from app.nucleo.configuracion import Configuracion

pytestmark = pytest.mark.unitaria

# No es una credencial: el validador de configuracion solo exige que no este
# vacia, y el cliente no llega a usarse porque no se hace ninguna peticion.
CLAVE_FICTICIA = "clave-inexistente-solo-para-la-prueba"


def test_modo_mock_devuelve_el_proveedor_de_demostracion() -> None:
    fabrica = construir_fabrica_conversacional(Configuracion(_env_file=None, proveedor_llm="mock"))
    assert isinstance(fabrica(), ProveedorDemostracion)


@pytest.mark.asyncio
async def test_modo_anthropic_devuelve_el_proveedor_real() -> None:
    fabrica = construir_fabrica_conversacional(
        Configuracion(_env_file=None, proveedor_llm="anthropic", anthropic_api_key=CLAVE_FICTICIA)
    )
    assert isinstance(fabrica(), ProveedorClaude)
    # El proveedor real guarda la transcripcion del turno: compartir una
    # instancia entre dos conversaciones simultaneas las mezclaria.
    assert fabrica() is not fabrica()
    await fabrica.cerrar()


@pytest.mark.asyncio
async def test_la_fabrica_de_demostracion_tambien_se_puede_cerrar() -> None:
    # El apagado llama a `cerrar()` sin mirar que proveedor hay detras.
    fabrica = construir_fabrica_conversacional(Configuracion(_env_file=None, proveedor_llm="mock"))
    await fabrica.cerrar()


def test_modo_no_implementado_falla_en_lugar_de_degradarse() -> None:
    configuracion = Configuracion(_env_file=None, proveedor_llm="ollama")
    with pytest.raises(ValueError, match="no soportado"):
        construir_fabrica_conversacional(configuracion)


def test_anthropic_sin_clave_no_llega_a_construirse() -> None:
    # El corte esta antes, en la configuracion: arrancar sin clave seria
    # arrancar un canal que falla en el primer mensaje de un paciente.
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Configuracion(_env_file=None, proveedor_llm="anthropic", anthropic_api_key="")
