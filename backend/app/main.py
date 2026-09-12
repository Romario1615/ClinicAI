"""Aplicacion FastAPI.

Construye la aplicacion, monta el middleware, engancha la traduccion de
errores y registra los enrutadores de cada modulo.

Se expone una **fabrica** (`crear_aplicacion`) y no una instancia de modulo.
Con una instancia, importar este modulo abriria un motor de base de datos y
reconfiguraria el registro como efecto secundario, y la suite de API no
podria levantar varias aplicaciones aisladas. El servidor se arranca con
`uvicorn app.main:crear_aplicacion --factory`.

Sondas de salud
---------------
Se separan a proposito en dos, porque responden preguntas distintas:

* `/salud/vivo` -- el proceso responde. Si falla, hay que reiniciarlo.
* `/salud/listo` -- ademas, la base de datos responde y tiene las extensiones
  que este sistema necesita. Si falla, hay que sacarlo del balanceador pero
  **no** reiniciarlo: reiniciar un proceso sano porque PostgreSQL esta caido
  solo anade un arranque en frio al incidente.

Un PostgreSQL en pie pero sin `vector` o sin `btree_gist` no esta sano para
este sistema: sin la segunda no existe la garantia contra la doble reserva.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis_async
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.manejadores import registrar_manejadores
from app.api.middleware import MiddlewareCorrelacion
from app.mensajeria import rutas as rutas_whatsapp
from app.modulos.agenda import rutas as rutas_agenda
from app.modulos.historia import rutas as rutas_historia
from app.modulos.organizacion import rutas as rutas_catalogo
from app.modulos.pacientes import rutas as rutas_pacientes
from app.modulos.usuarios import rutas as rutas_usuarios
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.limite_tasa import ClienteRedis, LimitadorTasa
from app.nucleo.registro import configurar_registro, obtener_logger
from app.nucleo.reloj import Reloj, RelojSistema
from app.nucleo.seguridad import CifradorDatos

_logger = obtener_logger(__name__)

PREFIJO_API = "/api/v1"


def _crear_cliente_redis(configuracion: Configuracion) -> ClienteRedis:
    """Cliente de Redis.

    No se conecta aqui: `redis.asyncio` conecta de forma perezosa. Un Redis
    caido al arrancar no debe impedir que el proceso arranque; el limitador
    decide que hacer cuando la operacion falla, y esa decision depende de si
    es autenticacion o no.
    """
    cliente: Any = redis_async.from_url(
        configuracion.url_redis,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    return cliente  # type: ignore[no-any-return]


@asynccontextmanager
async def _ciclo_de_vida(aplicacion: FastAPI) -> AsyncIterator[None]:
    """Abre y cierra los recursos de larga vida.

    Al arrancar se comprueban las extensiones de PostgreSQL y se **avisa** si
    falta alguna, pero no se aborta: en un despliegue, un proceso que no
    arranca es mas dificil de diagnosticar que uno que arranca y declara en
    `/salud/listo` por que no esta listo.
    """
    configuracion: Configuracion = aplicacion.state.configuracion
    gestor: GestorBaseDatos = aplicacion.state.gestor_bd

    try:
        faltantes = await gestor.extensiones_faltantes()
        if faltantes:
            _logger.error(
                "arranque.extensiones_faltantes",
                extensiones=sorted(faltantes),
                consecuencia=(
                    "Sin btree_gist no existe la garantia contra doble reserva; "
                    "sin vector no hay busqueda de conocimiento."
                ),
            )
        else:
            _logger.info("arranque.base_datos_lista", entorno=configuracion.entorno.value)
    except Exception as exc:  # el arranque no debe depender de la base
        _logger.error("arranque.base_datos_inaccesible", motivo=type(exc).__name__)

    yield

    await gestor.cerrar()
    cliente = getattr(aplicacion.state, "redis", None)
    if cliente is not None:
        cerrar = getattr(cliente, "aclose", None) or getattr(cliente, "close", None)
        if cerrar is not None:
            await cerrar()
    _logger.info("apagado.completado")


def crear_aplicacion(
    configuracion: Configuracion | None = None,
    *,
    reloj: Reloj | None = None,
    gestor_bd: GestorBaseDatos | None = None,
    cliente_redis: ClienteRedis | None = None,
    configurar_logs: bool = True,
) -> FastAPI:
    """Construye una aplicacion.

    Todos los recursos son inyectables para que la suite de API pueda pasar
    su propio reloj (fijo), su propia base de datos y un Redis simulado sin
    parchear nada.
    """
    configuracion = configuracion or Configuracion()

    if configurar_logs:
        configurar_registro(
            nivel=configuracion.nivel_log,
            formato=configuracion.formato_log,
            redactar=configuracion.redactar_datos_sensibles,
        )

    aplicacion = FastAPI(
        title="API de gestion clinica",
        version="0.1.0",
        summary="Agenda, pacientes, historia clinica y comunicacion de una clinica.",
        lifespan=_ciclo_de_vida,
        # La documentacion interactiva no se publica en produccion: describe
        # la superficie completa de la API y facilita el reconocimiento.
        docs_url=None if configuracion.entorno.es_produccion else "/documentacion",
        redoc_url=None,
        openapi_url=None if configuracion.entorno.es_produccion else "/openapi.json",
    )

    aplicacion.state.configuracion = configuracion
    aplicacion.state.reloj = reloj or RelojSistema()
    aplicacion.state.gestor_bd = gestor_bd or GestorBaseDatos(
        configuracion.url_base_datos,
        tamano_pool=configuracion.bd_pool_tamano,
        desborde_maximo=configuracion.bd_pool_desborde,
        eco=False,
    )
    aplicacion.state.cifrador = CifradorDatos(configuracion.clave_cifrado_datos.get_secret_value())
    aplicacion.state.redis = (
        cliente_redis if cliente_redis is not None else _crear_cliente_redis(configuracion)
    )
    aplicacion.state.limitador = LimitadorTasa(aplicacion.state.redis, aplicacion.state.reloj)

    # --- Middleware ---
    #
    # El orden importa: se ejecutan del ultimo registrado al primero. CORS se
    # anade despues para que sea el mas externo y sus cabeceras lleguen
    # tambien en las respuestas de error.
    aplicacion.add_middleware(MiddlewareCorrelacion)
    aplicacion.add_middleware(
        CORSMiddleware,
        # Lista explicita, nunca comodin: con credenciales, un comodin
        # permitiria a cualquier sitio leer respuestas con datos de
        # pacientes. La configuracion lo valida ademas en produccion.
        allow_origins=configuracion.lista_origenes_cors,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id", "Idempotency-Key"],
        expose_headers=["X-Request-Id", "Retry-After"],
        max_age=600,
    )

    registrar_manejadores(aplicacion)
    _registrar_rutas(aplicacion)
    return aplicacion


def _registrar_rutas(aplicacion: FastAPI) -> None:
    aplicacion.include_router(rutas_usuarios.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_agenda.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_catalogo.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_pacientes.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_historia.enrutador, prefix=PREFIJO_API)
    # El webhook no lleva autenticacion: lo protege la firma HMAC, no un
    # token. Ver el encabezado de app/mensajeria/rutas.py.
    aplicacion.include_router(rutas_whatsapp.enrutador, prefix=PREFIJO_API)

    @aplicacion.get("/salud/vivo", tags=["salud"], summary="El proceso responde")
    async def vivo() -> dict[str, str]:
        return {"estado": "vivo"}

    @aplicacion.get(
        "/salud/listo",
        tags=["salud"],
        summary="El proceso puede atender peticiones",
        responses={503: {"description": "Dependencias no disponibles"}},
    )
    async def listo() -> JSONResponse:
        gestor: GestorBaseDatos = aplicacion.state.gestor_bd
        try:
            faltantes = sorted(await gestor.extensiones_faltantes())
        except Exception as exc:  # la sonda nunca debe lanzar
            _logger.warning("salud.base_datos_inaccesible", motivo=type(exc).__name__)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"estado": "no_listo", "motivo": "base_de_datos_inaccesible"},
            )

        if faltantes:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "estado": "no_listo",
                    "motivo": "extensiones_faltantes",
                    "extensiones": faltantes,
                },
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"estado": "listo"})


# No se crea una instancia a nivel de modulo a proposito.
#
# Hacerlo abriria un motor de base de datos y reconfiguraria el registro como
# efecto de *importar* este modulo, lo que rompe cualquier prueba que solo
# quiera la fabrica. El servidor se arranca con `--factory`:
#
#     uv run uvicorn app.main:crear_aplicacion --factory --reload


__all__ = ["PREFIJO_API", "crear_aplicacion"]
