"""Qué modelo de decisión y qué LLM usa cada clínica.

Cada clínica configura en Integraciones su cuenta de JEV (TypeSafe) y quién
redacta las respuestas del asistente (Anthropic, Ollama local o nadie). Esto
lo traduce a objetos del agente:

* **Decisiones**: si la clínica habilitó JEV con su clave, se usa esa cuenta;
  si no, lo que diga el entorno (`PROVEEDOR_DECISIONES`), que por defecto son
  reglas locales sin red. El umbral de confianza también es de la clínica.
* **Redacción**: Anthropic con la clave de la clínica, Ollama en su red, o el
  proveedor del entorno. Sin ninguno, el agente no redacta: cita.

Las claves se descifran aquí y solo aquí, con el mismo contexto con que se
cifraron; nunca se registran. Los clientes HTTP se reutilizan por clínica y
versión de configuración: cambiar la clave crea un cliente nuevo y cierra el
anterior.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.conversacion import ProveedorConversacional
from app.ia.decisiones import ClasificadorIntencion, ClasificadorJev
from app.ia.proveedor_ollama import ProveedorOllama
from app.ia.seleccion_llm import FabricaConversacional
from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import obtener_logger
from app.nucleo.seguridad import CifradorDatos

logger = obtener_logger(__name__)

UMBRAL_POR_OMISION = 0.85


def contexto_cifrado(clinica_id: uuid.UUID, codigo: str, campo: str) -> bytes:
    """Mismo contexto que al cifrar: una clave no se puede trasladar de clínica."""
    return b"integracion:" + clinica_id.bytes + b":" + codigo.encode() + b":" + campo.encode()


@dataclass(frozen=True, slots=True)
class Integracion:
    habilitada: bool
    ajustes: dict[str, Any]
    secretos_cifrados: dict[str, str]
    version: int


async def leer_integracion(
    sesion: AsyncSession, clinica_id: uuid.UUID, codigo: str
) -> Integracion | None:
    fila = (
        await sesion.execute(
            select(ConfiguracionClinica).where(
                ConfiguracionClinica.clinica_id == clinica_id,
                ConfiguracionClinica.clave == f"integracion.{codigo}",
                ConfiguracionClinica.vigente.is_(True),
            )
        )
    ).scalar_one_or_none()
    if fila is None or not isinstance(fila.valor, dict):
        return None
    valor: dict[str, Any] = fila.valor
    crudo_ajustes = valor.get("ajustes")
    crudo_secretos = valor.get("secretos_cifrados")
    ajustes: dict[str, Any] = dict(crudo_ajustes) if isinstance(crudo_ajustes, dict) else {}
    secretos: dict[str, str] = (
        {str(k): str(v) for k, v in crudo_secretos.items()}
        if isinstance(crudo_secretos, dict)
        else {}
    )
    return Integracion(bool(valor.get("habilitada")), ajustes, secretos, fila.version)


def descifrar(
    cifrador: CifradorDatos, clinica_id: uuid.UUID, codigo: str, campo: str, integ: Integracion
) -> str | None:
    dato = integ.secretos_cifrados.get(campo)
    if not dato:
        return None
    try:
        return cifrador.descifrar(dato, contexto=contexto_cifrado(clinica_id, codigo, campo))
    except ValueError:
        logger.error("integracion.secreto_ilegible", integracion=codigo, campo=campo)
        return None


# ---------------------------------------------------------------------------
#  Decisiones: modelo JEV de la clínica
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DecisionesClinica:
    clasificador: ClasificadorIntencion
    umbral_clinico: float
    umbral_intencion: float
    origen: str  # «jev de la clínica» o el proveedor del entorno


_CLASIFICADORES: dict[tuple[uuid.UUID, int], ClasificadorJev] = {}


def clasificador_jev(
    clinica_id: uuid.UUID, version: int, clave: str, ajustes: dict[str, Any]
) -> ClasificadorJev:
    llave = (clinica_id, version)
    existente = _CLASIFICADORES.get(llave)
    if existente is not None:
        return existente
    for vieja in [k for k in _CLASIFICADORES if k[0] == clinica_id]:
        _CLASIFICADORES.pop(vieja, None)
    nuevo = ClasificadorJev(
        clave=clave,
        modelo=str(ajustes.get("modelo") or "jev-latest"),
        tiempo_limite=float(ajustes.get("tiempo_limite") or 3.0),
    )
    _CLASIFICADORES[llave] = nuevo
    return nuevo


async def decisiones_de_clinica(
    sesion: AsyncSession,
    cifrador: CifradorDatos,
    configuracion: Configuracion,
    clinica_id: uuid.UUID,
    respaldo: ClasificadorIntencion,
) -> DecisionesClinica:
    integ = await leer_integracion(sesion, clinica_id, "typesafe")
    umbral_intencion = configuracion.decisiones_umbral_intencion
    if integ is not None:
        umbral_intencion = float(integ.ajustes.get("umbral_confianza") or umbral_intencion)
    if integ is not None and integ.habilitada:
        clave = descifrar(cifrador, clinica_id, "typesafe", "api_key", integ)
        if clave:
            return DecisionesClinica(
                clasificador_jev(clinica_id, integ.version, clave, integ.ajustes),
                configuracion.decisiones_umbral_clinico,
                umbral_intencion,
                "jev",
            )
    return DecisionesClinica(
        respaldo, configuracion.decisiones_umbral_clinico, umbral_intencion, respaldo.nombre
    )


# ---------------------------------------------------------------------------
#  Redacción: LLM elegido por la clínica
# ---------------------------------------------------------------------------
class _FabricaOllama:
    def __init__(self, url: str, modelo: str) -> None:
        self._cliente = httpx.AsyncClient()
        self._url = url
        self._modelo = modelo

    def __call__(self) -> ProveedorConversacional:
        return ProveedorOllama(self._cliente, url=self._url, modelo=self._modelo)

    async def cerrar(self) -> None:
        await self._cliente.aclose()


_FABRICAS: dict[tuple[uuid.UUID, str], FabricaConversacional] = {}


async def _reemplazar(clinica_id: uuid.UUID, llave: str, nueva: FabricaConversacional) -> None:
    for vieja in [k for k in _FABRICAS if k[0] == clinica_id and k[1] != llave]:
        fabrica = _FABRICAS.pop(vieja)
        await fabrica.cerrar()
    _FABRICAS[(clinica_id, llave)] = nueva


async def fabrica_de_clinica(
    sesion: AsyncSession,
    cifrador: CifradorDatos,
    configuracion: Configuracion,
    clinica_id: uuid.UUID,
    respaldo: FabricaConversacional,
) -> FabricaConversacional:
    integ = await leer_integracion(sesion, clinica_id, "respuestas_ia")
    proveedor = str(integ.ajustes.get("proveedor") or "entorno") if integ else "entorno"
    if integ is None or not integ.habilitada or proveedor in {"entorno", "ninguno"}:
        return respaldo
    if proveedor == "ollama":
        url = str(integ.ajustes.get("ollama_url") or "")
        modelo = str(integ.ajustes.get("ollama_modelo") or "")
        llave = f"ollama:{integ.version}"
        if (clinica_id, llave) not in _FABRICAS:
            await _reemplazar(clinica_id, llave, _FabricaOllama(url, modelo))
        return _FABRICAS[(clinica_id, llave)]
    if proveedor == "anthropic":
        anthropic = await leer_integracion(sesion, clinica_id, "anthropic")
        clave = (
            descifrar(cifrador, clinica_id, "anthropic", "api_key", anthropic)
            if anthropic and anthropic.habilitada
            else None
        )
        if not clave or anthropic is None:
            logger.warning("integracion.anthropic_sin_clave", clinica_id=str(clinica_id))
            return respaldo
        llave = f"anthropic:{integ.version}:{anthropic.version}"
        if (clinica_id, llave) not in _FABRICAS:
            from anthropic import AsyncAnthropic  # noqa: PLC0415

            from app.ia.seleccion_llm import _FabricaClaude  # noqa: PLC0415

            await _reemplazar(
                clinica_id,
                llave,
                _FabricaClaude(
                    AsyncAnthropic(
                        api_key=clave,
                        timeout=float(configuracion.llm_timeout_segundos),
                        max_retries=2,
                    ),
                    modelo=str(anthropic.ajustes.get("modelo") or configuracion.modelo_llm),
                    max_tokens=int(
                        anthropic.ajustes.get("max_tokens") or configuracion.llm_max_tokens
                    ),
                    esfuerzo=configuracion.llm_esfuerzo,
                ),
            )
        return _FABRICAS[(clinica_id, llave)]
    return respaldo


async def cerrar_proveedores_clinica() -> None:
    """Al apagar: cierra los clientes HTTP de todas las clínicas."""
    for fabrica in list(_FABRICAS.values()):
        await fabrica.cerrar()
    _FABRICAS.clear()
    _CLASIFICADORES.clear()


__all__ = [
    "DecisionesClinica",
    "Integracion",
    "cerrar_proveedores_clinica",
    "contexto_cifrado",
    "decisiones_de_clinica",
    "descifrar",
    "fabrica_de_clinica",
    "leer_integracion",
]
