"""Middleware HTTP.

Tres piezas, cada una con un motivo concreto:

* **Correlacion.** Cada peticion recibe un identificador que viaja por todas
  las lineas de registro y por toda entrada de auditoria que genere. Sin el,
  reconstruir que ocurrio en un incidente obliga a cruzar marcas de tiempo
  entre servicios, y con varias peticiones por segundo eso deja de funcionar.

* **Registro de acceso.** Metodo, ruta, estado y duracion. Nunca el cuerpo:
  un cuerpo de peticion de este sistema puede contener una nota clinica.

* **Cabeceras de seguridad.** La API sirve JSON, no HTML, pero un navegador
  que reciba una respuesta de error interpretable como documento sigue siendo
  una via de XSS reflejado. Las cabeceras cierran esa via y no cuestan nada.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.nucleo.registro import enlazar_contexto, limpiar_contexto, obtener_logger

_logger = obtener_logger("app.acceso")

CABECERA_CORRELACION = "X-Request-Id"

# Rutas que no se registran como acceso: las sondas de salud producen una
# linea por segundo y ahogarian el registro sin aportar nada.
RUTAS_SILENCIOSAS = frozenset({"/salud", "/salud/vivo", "/salud/listo", "/metricas"})

CABECERAS_SEGURIDAD: dict[str, str] = {
    # La API solo devuelve JSON; impedir que el navegador adivine el tipo
    # evita que una respuesta se interprete como HTML o como script.
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # Ninguna respuesta de esta API necesita ejecutar nada en el navegador.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    # Las respuestas pueden contener datos de pacientes: no se guardan en
    # ninguna cache intermedia ni en el disco del navegador.
    "Cache-Control": "no-store",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class MiddlewareCorrelacion(BaseHTTPMiddleware):
    """Asigna un identificador de correlacion y registra el acceso."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Se acepta el identificador que traiga el cliente para poder seguir
        # una peticion a traves del frontend, pero se acota su longitud y su
        # alfabeto: llega sin validar y termina en los registros.
        recibido = request.headers.get(CABECERA_CORRELACION, "")
        correlacion = _sanear_correlacion(recibido) or uuid.uuid4().hex

        request.state.correlacion_id = correlacion
        enlazar_contexto(correlacion_id=correlacion)

        comienzo = time.perf_counter()
        try:
            respuesta = await call_next(request)
        except Exception:
            # El manejador de errores de FastAPI se encarga de la respuesta;
            # aqui solo se garantiza que el acceso quede registrado aunque
            # la peticion termine en excepcion no controlada.
            _logger.exception(
                "acceso.error",
                metodo=request.method,
                ruta=request.url.path,
                duracion_ms=round((time.perf_counter() - comienzo) * 1000, 2),
            )
            limpiar_contexto()
            raise

        duracion_ms = round((time.perf_counter() - comienzo) * 1000, 2)
        respuesta.headers[CABECERA_CORRELACION] = correlacion
        for nombre, valor in CABECERAS_SEGURIDAD.items():
            respuesta.headers.setdefault(nombre, valor)

        if request.url.path not in RUTAS_SILENCIOSAS:
            _logger.info(
                "acceso",
                metodo=request.method,
                ruta=request.url.path,
                estado=respuesta.status_code,
                duracion_ms=duracion_ms,
                # La IP del cliente es un dato personal, pero es necesaria
                # para investigar un acceso indebido. Se registra; la
                # politica de retencion la acota (docs/security.md).
                ip=request.client.host if request.client else None,
            )

        limpiar_contexto()
        return respuesta


def _sanear_correlacion(valor: str) -> str:
    """Acota lo que llega del cliente antes de que entre en los registros.

    Un identificador con saltos de linea permitiria inyectar lineas falsas en
    un registro de texto; uno de un megabyte lo llenaria. Se admite solo
    alfanumerico, guion y guion bajo, hasta 64 caracteres.
    """
    limpio = valor.strip()[:64]
    if not limpio:
        return ""
    if not all(c.isalnum() or c in "-_" for c in limpio):
        return ""
    return limpio


__all__ = [
    "CABECERAS_SEGURIDAD",
    "CABECERA_CORRELACION",
    "RUTAS_SILENCIOSAS",
    "MiddlewareCorrelacion",
]
