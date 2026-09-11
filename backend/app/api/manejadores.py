"""Traduccion de errores a respuestas HTTP.

Un `ErrorDominio` es un resultado esperado -- turno ocupado, permiso
insuficiente, cita ya cancelada -- y se traduce a su codigo HTTP sin
registrarse como fallo. Solo lo inesperado produce un 500 y una traza.

La forma del cuerpo es siempre la misma:

    {"codigo": "TURNO_NO_DISPONIBLE", "mensaje": "...", "detalles": {...}}

Un cliente puede ramificar por `codigo`, que es estable, en lugar de por el
texto del mensaje, que cambia al reescribirlo.

Que no sale nunca en una respuesta
----------------------------------
Ni la traza, ni el mensaje de PostgreSQL, ni el nombre de la restriccion que
fallo. Un error de base de datos sin filtrar revela nombres de tablas y de
columnas, y con ellos la estructura del esquema. El detalle completo va al
registro con el identificador de correlacion; la respuesta lleva ese
identificador para que soporte pueda encontrarlo.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.nucleo.errores import ErrorDominio, LimiteTasaExcedido
from app.nucleo.errores_bd import traducir
from app.nucleo.registro import obtener_logger

_logger = obtener_logger(__name__)

# Starlette renombro la constante de 422 y marco la antigua como obsoleta; la
# suite trata los avisos como errores, asi que se fija el numero y no el
# nombre. El significado del codigo HTTP no depende de la version de una
# libreria.
CODIGO_DATOS_INVALIDOS = 422
CODIGO_NO_AUTENTICADO = 401


def _cuerpo(
    codigo: str,
    mensaje: str,
    *,
    detalles: dict[str, Any] | None = None,
    correlacion: str | None = None,
) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {"codigo": codigo, "mensaje": mensaje}
    if detalles:
        cuerpo["detalles"] = detalles
    if correlacion:
        cuerpo["correlacion_id"] = correlacion
    return cuerpo


def _correlacion(peticion: Request) -> str | None:
    valor = getattr(peticion.state, "correlacion_id", None)
    return str(valor) if valor else None


async def manejar_error_dominio(peticion: Request, exc: Exception) -> JSONResponse:
    # El estrechamiento de tipo no se hace con `assert`: las aserciones
    # desaparecen con `python -O`, y un manejador de errores que se comporta
    # distinto segun como se arranque el interprete es peor que no tenerlo.
    if not isinstance(exc, ErrorDominio):
        return await manejar_error_no_controlado(peticion, exc)

    cabeceras: dict[str, str] = {}
    if exc.estado_http == CODIGO_NO_AUTENTICADO:
        # RFC 9110: **todo** 401 debe llevar `WWW-Authenticate`, no solo el de
        # "falta la cabecera". Sin ella la respuesta esta incompleta y algunos
        # clientes no reintentan. Se decide por el codigo de estado y no por
        # el tipo de excepcion: asi un error de autenticacion nuevo la lleva
        # sin que nadie tenga que acordarse de anadirlo aqui.
        cabeceras["WWW-Authenticate"] = "Bearer"
    if isinstance(exc, LimiteTasaExcedido):
        cabeceras["Retry-After"] = str(exc.reintentar_en_segundos)

    _logger.info(
        "error.dominio",
        codigo=exc.codigo,
        estado=exc.estado_http,
        ruta=peticion.url.path,
    )
    return JSONResponse(
        status_code=exc.estado_http,
        content=_cuerpo(
            exc.codigo,
            exc.mensaje,
            detalles=exc.detalles,
            correlacion=_correlacion(peticion),
        ),
        headers=cabeceras,
    )


async def manejar_validacion(peticion: Request, exc: Exception) -> JSONResponse:
    """Errores de validacion de Pydantic.

    Se reexpone la lista de campos invalidos, pero **sin el valor recibido**.
    Pydantic lo incluye en `input`, y ese valor puede ser una contrasena o el
    numero de documento de un paciente: devolverlo en la respuesta lo pondria
    tambien en los registros de cualquier proxy intermedio.
    """
    if not isinstance(exc, RequestValidationError):
        return await manejar_error_no_controlado(peticion, exc)

    campos = [
        {
            "campo": ".".join(str(p) for p in error["loc"]),
            "problema": error["msg"],
            "tipo": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=CODIGO_DATOS_INVALIDOS,
        content=_cuerpo(
            "DATOS_INVALIDOS",
            "Los datos enviados no son validos.",
            detalles={"campos": campos},
            correlacion=_correlacion(peticion),
        ),
    )


async def manejar_error_bd(peticion: Request, exc: Exception) -> JSONResponse:
    """Errores de PostgreSQL que llegaron sin traducir.

    La traduccion normal ocurre en el servicio, junto a la operacion que sabe
    que significa cada restriccion. Este manejador es la red de seguridad:
    traduce lo que reconoce y, si no reconoce nada, responde 500 sin filtrar
    el mensaje del motor.
    """
    if not isinstance(exc, DBAPIError):
        return await manejar_error_no_controlado(peticion, exc)

    traducido = traducir(exc)
    if traducido is not None:
        _logger.warning(
            "error.bd.traducido",
            codigo=traducido.codigo,
            ruta=peticion.url.path,
        )
        return await manejar_error_dominio(peticion, traducido)

    _logger.exception("error.bd.no_traducido", ruta=peticion.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_cuerpo(
            "ERROR_INTERNO",
            "No se pudo completar la operacion. El incidente quedo registrado.",
            correlacion=_correlacion(peticion),
        ),
    )


async def manejar_error_no_controlado(peticion: Request, exc: Exception) -> JSONResponse:
    """Cualquier otra excepcion.

    Se registra con traza completa y se responde con un mensaje generico mas
    el identificador de correlacion. Es lo unico que el cliente necesita para
    que soporte encuentre el error exacto.
    """
    _logger.exception(
        "error.no_controlado",
        tipo=type(exc).__name__,
        ruta=peticion.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_cuerpo(
            "ERROR_INTERNO",
            "No se pudo completar la operacion. El incidente quedo registrado.",
            correlacion=_correlacion(peticion),
        ),
    )


def registrar_manejadores(aplicacion: FastAPI) -> None:
    """Engancha los manejadores. El orden de registro no importa: FastAPI
    elige el mas especifico por tipo de excepcion."""
    aplicacion.add_exception_handler(ErrorDominio, manejar_error_dominio)
    aplicacion.add_exception_handler(RequestValidationError, manejar_validacion)
    # `IntegrityError` es subclase de `DBAPIError`; se registra aparte para
    # dejar constancia explicita de que tambien pasa por aqui.
    aplicacion.add_exception_handler(IntegrityError, manejar_error_bd)
    aplicacion.add_exception_handler(DBAPIError, manejar_error_bd)
    aplicacion.add_exception_handler(Exception, manejar_error_no_controlado)


__all__ = [
    "manejar_error_bd",
    "manejar_error_dominio",
    "manejar_error_no_controlado",
    "manejar_validacion",
    "registrar_manejadores",
]
