"""Limite de tasa por ventana deslizante sobre Redis.

Por que ventana deslizante y no contador por minuto
---------------------------------------------------
Un contador que se reinicia cada minuto permite el doble del limite en el
cambio de ventana: 10 intentos a las 10:00:59 y otros 10 a las 10:01:00. Con
un limite de login eso es 20 contrasenas probadas en dos segundos. La ventana
deslizante cuenta los eventos de los ultimos 60 segundos reales, sin ese
salto.

Se implementa con un conjunto ordenado por marca de tiempo, en un unico script
Lua para que contar, podar y anadir ocurran de forma atomica. Sin atomicidad,
dos peticiones simultaneas leen el mismo contador y ambas pasan.

Que ocurre si Redis no responde
-------------------------------
Se distingue por tipo de operacion, y la distincion es deliberada:

* **Autenticacion (`fallar_cerrado=True`): se deniega.** Si Redis cae, el
  limitador de login deja de existir; seguir aceptando intentos convertiria
  una caida de cache en una ventana abierta de fuerza bruta contra las
  cuentas del personal clinico. Es preferible que nadie pueda iniciar sesion
  durante la caida a que cualquiera pueda probar contrasenas sin limite.

* **Resto de la API (`fallar_cerrado=False`): se permite y se registra.**
  Aqui el atacante ya necesita un token valido, y denegar toda la API por una
  caida de cache dejaria la agenda de la clinica inoperativa. El riesgo que
  se acepta -- un cliente autenticado pudiendo hacer mas peticiones de la
  cuenta mientras Redis esta caido -- es menor que el de no poder atender.

La decision queda registrada en `docs/known-limitations.md` para que no se
cambie por inercia.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.nucleo.errores import LimiteTasaExcedido, ProveedorExternoNoDisponible
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

_logger = obtener_logger(__name__)


# Cuenta los eventos vivos de la ventana, elimina los caducados, y solo anade
# el nuevo si aun cabe. Devuelve {1 si se admite, 0 si no}, cuantos quedan y
# los segundos hasta que se libere un hueco.
#
# KEYS[1] = clave del contador
# ARGV[1] = instante actual en milisegundos
# ARGV[2] = tamano de la ventana en milisegundos
# ARGV[3] = limite de eventos por ventana
# ARGV[4] = identificador unico del evento (evita que dos eventos del mismo
#           milisegundo se pisen dentro del conjunto ordenado)
_GUION_VENTANA = """
local clave = KEYS[1]
local ahora = tonumber(ARGV[1])
local ventana = tonumber(ARGV[2])
local limite = tonumber(ARGV[3])
local evento = ARGV[4]

redis.call('ZREMRANGEBYSCORE', clave, '-inf', ahora - ventana)
local usados = redis.call('ZCARD', clave)

if usados >= limite then
    local antiguo = redis.call('ZRANGE', clave, 0, 0, 'WITHSCORES')
    local espera = ventana
    if antiguo[2] then
        espera = (tonumber(antiguo[2]) + ventana) - ahora
    end
    return {0, 0, espera}
end

redis.call('ZADD', clave, ahora, evento)
redis.call('PEXPIRE', clave, ventana)
return {1, limite - usados - 1, 0}
"""


class ClienteRedis(Protocol):
    """Lo minimo que el limitador necesita de Redis.

    Se declara como protocolo y no se importa `redis.asyncio.Redis` para que
    las pruebas puedan pasar un doble sin levantar Redis, y para que este
    modulo no dependa de la version del cliente.
    """

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> list[int]: ...


@dataclass(frozen=True, slots=True)
class ResultadoLimite:
    admitido: bool
    restantes: int
    reintentar_en_segundos: int


class LimitadorTasa:
    """Ventana deslizante por clave."""

    def __init__(
        self,
        cliente: ClienteRedis | None,
        reloj: Reloj,
        *,
        prefijo: str = "tasa",
    ) -> None:
        self._cliente = cliente
        self._reloj = reloj
        self._prefijo = prefijo

    async def consumir(
        self,
        clave: str,
        *,
        limite: int,
        ventana_segundos: int = 60,
        fallar_cerrado: bool = False,
    ) -> ResultadoLimite:
        """Registra un evento y dice si se admite.

        `clave` debe identificar al sujeto limitado, no a la peticion: la IP
        de origen, el identificador de usuario o la combinacion de ambos.
        """
        if self._cliente is None:
            return self._sin_redis(clave, limite, fallar_cerrado, motivo="no configurado")

        ahora_ms = int(self._reloj.ahora().timestamp() * 1000)
        # El identificador del evento incluye el instante y un contador
        # monotono del propio Redis no esta disponible aqui, asi que se usa
        # el instante en microsegundos: dos eventos del mismo milisegundo
        # siguen produciendo miembros distintos del conjunto ordenado.
        evento = f"{int(self._reloj.ahora().timestamp() * 1_000_000)}"

        try:
            respuesta = await self._cliente.eval(
                _GUION_VENTANA,
                1,
                f"{self._prefijo}:{clave}",
                str(ahora_ms),
                str(ventana_segundos * 1000),
                str(limite),
                evento,
            )
        except Exception as exc:
            return self._sin_redis(clave, limite, fallar_cerrado, motivo=type(exc).__name__)

        admitido, restantes, espera_ms = (int(v) for v in respuesta)
        return ResultadoLimite(
            admitido=bool(admitido),
            restantes=restantes,
            reintentar_en_segundos=max(1, math.ceil(espera_ms / 1000)) if not admitido else 0,
        )

    async def exigir(
        self,
        clave: str,
        *,
        limite: int,
        ventana_segundos: int = 60,
        fallar_cerrado: bool = False,
    ) -> ResultadoLimite:
        """Como `consumir`, pero lanza `LimiteTasaExcedido` si no se admite."""
        resultado = await self.consumir(
            clave,
            limite=limite,
            ventana_segundos=ventana_segundos,
            fallar_cerrado=fallar_cerrado,
        )
        if not resultado.admitido:
            raise LimiteTasaExcedido(
                "Demasiadas peticiones. Espere unos segundos antes de reintentar.",
                reintentar_en_segundos=resultado.reintentar_en_segundos,
            )
        return resultado

    def _sin_redis(
        self, clave: str, limite: int, fallar_cerrado: bool, *, motivo: str
    ) -> ResultadoLimite:
        """Decide que hacer cuando el contador no esta disponible.

        Ver la nota del encabezado: la autenticacion falla cerrada y el resto
        de la API falla abierta, y ambas cosas se registran.
        """
        if fallar_cerrado:
            _logger.error(
                "limite_tasa.sin_contador.denegado",
                clave_limite=clave,
                limite=limite,
                motivo=motivo,
            )
            raise ProveedorExternoNoDisponible(
                "El control de intentos no esta disponible en este momento. "
                "Reintente en unos minutos."
            )

        _logger.warning(
            "limite_tasa.sin_contador.permitido",
            clave_limite=clave,
            limite=limite,
            motivo=motivo,
        )
        return ResultadoLimite(admitido=True, restantes=limite, reintentar_en_segundos=0)


__all__ = ["ClienteRedis", "LimitadorTasa", "ResultadoLimite"]
