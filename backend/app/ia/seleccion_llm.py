"""Que proveedor conversacional se usa, segun la configuracion.

Por que una fabrica y no una instancia
--------------------------------------
El proveedor real guarda la transcripcion del turno (ver `proveedor_claude`),
asi que dos conversaciones simultaneas no pueden compartirlo.  Lo que si se
comparte -- y conviene que se comparta -- es el cliente HTTP: reutiliza
conexiones y concentra en un sitio el tiempo limite y los reintentos.

De ahi la forma: se construye **una** fabrica al arrancar la aplicacion, cada
turno pide su proveedor, y el apagado cierra la fabrica.  `cerrar()` existe
porque el cliente HTTP mantiene conexiones abiertas; sin el, apagar el proceso
las deja colgando y las pruebas lo denuncian como fuga de recursos.

Un modo desconocido falla
-------------------------
No hay caida silenciosa al proveedor de demostracion.  Una clinica que cree
tener un agente conversacional y tiene un guion de cadenas fijas no se entera
por ningun error: se entera porque los pacientes se quejan.  Es el mismo
criterio que en `construir_proveedor_embeddings`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.ia.conversacion import ProveedorConversacional, ProveedorDemostracion
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger

if TYPE_CHECKING:  # pragma: no cover - solo para los tipos
    from anthropic import AsyncAnthropic

logger = obtener_logger(__name__)


class FabricaConversacional(Protocol):
    """Produce el proveedor de un turno y libera lo que comparten todos."""

    def __call__(self) -> ProveedorConversacional: ...

    async def cerrar(self) -> None: ...


class _FabricaDemostracion:
    """Guion reproducible. No tiene nada que cerrar."""

    def __call__(self) -> ProveedorConversacional:
        return ProveedorDemostracion()

    async def cerrar(self) -> None:
        return None


class _FabricaClaude:
    """Un cliente HTTP compartido, un proveedor por turno."""

    def __init__(
        self,
        cliente: AsyncAnthropic,
        *,
        modelo: str,
        max_tokens: int,
        esfuerzo: str,
    ) -> None:
        self._cliente = cliente
        self._modelo = modelo
        self._max_tokens = max_tokens
        self._esfuerzo = esfuerzo

    def __call__(self) -> ProveedorConversacional:
        from app.ia.proveedor_claude import ProveedorClaude  # noqa: PLC0415

        return ProveedorClaude(
            self._cliente,
            modelo=self._modelo,
            max_tokens=self._max_tokens,
            esfuerzo=self._esfuerzo,  # type: ignore[arg-type]
        )

    async def cerrar(self) -> None:
        await self._cliente.close()


def construir_fabrica_conversacional(configuracion: Configuracion) -> FabricaConversacional:
    """Fabrica de proveedores para el bucle del agente.

    `anthropic` es una dependencia opcional (extra `llm`): se importa aqui
    dentro para que un despliegue con `PROVEEDOR_LLM=mock` no la necesite.
    """
    if configuracion.proveedor_llm == "mock":
        logger.info("agente.proveedor", proveedor="mock")
        return _FabricaDemostracion()

    if configuracion.proveedor_llm == "anthropic":
        from anthropic import AsyncAnthropic  # noqa: PLC0415

        logger.info("agente.proveedor", proveedor="anthropic", modelo=configuracion.modelo_llm)
        return _FabricaClaude(
            AsyncAnthropic(
                api_key=configuracion.anthropic_api_key.get_secret_value(),
                timeout=float(configuracion.llm_timeout_segundos),
                # El SDK reintenta 429 y 5xx con espera exponencial. Dos
                # intentos caben en el tiempo limite de un mensaje de WhatsApp.
                max_retries=2,
            ),
            modelo=configuracion.modelo_llm,
            max_tokens=configuracion.llm_max_tokens,
            esfuerzo=configuracion.llm_esfuerzo,
        )

    raise ValueError(
        f"Proveedor conversacional no soportado: {configuracion.proveedor_llm!r}. "
        "Valores implementados: 'anthropic', 'mock'."
    )


__all__ = ["FabricaConversacional", "construir_fabrica_conversacional"]
