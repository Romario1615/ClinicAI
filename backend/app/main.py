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

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis_async
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.manejadores import registrar_manejadores
from app.api.middleware import MiddlewareCorrelacion
from app.ia.decisiones import construir_clasificador
from app.ia.embeddings import construir_proveedor_embeddings
from app.ia.imagenes_generativas import construir_generador
from app.ia.proveedores_clinica import cerrar_proveedores_clinica
from app.ia.seleccion_llm import construir_fabrica_conversacional
from app.mensajeria import rutas as rutas_whatsapp
from app.modulos.agenda import bloqueos_rutas as rutas_bloqueos_agenda
from app.modulos.agenda import recorrido_rutas as rutas_recorrido
from app.modulos.agenda import rutas as rutas_agenda
from app.modulos.asistente import rutas as rutas_asistente
from app.modulos.automatizaciones import rutas as rutas_automatizaciones
from app.modulos.ayuda import rutas as rutas_ayuda
from app.modulos.calendario import rutas as rutas_calendario
from app.modulos.calendario.seleccion import construir_proveedores
from app.modulos.configuracion import rutas as rutas_configuracion
from app.modulos.conocimiento import revision_riesgo as rutas_revision_riesgo
from app.modulos.conocimiento import rutas as rutas_conocimiento
from app.modulos.conversaciones import demo_rutas
from app.modulos.conversaciones import rutas as rutas_conversaciones
from app.modulos.dashboard import indicadores as indicadores_dashboard
from app.modulos.dashboard import rutas as rutas_dashboard
from app.modulos.historia import acceso_emergencia as rutas_acceso_emergencia
from app.modulos.historia import anamnesis_rutas as rutas_anamnesis
from app.modulos.historia import especialidades as rutas_especialidades_historia
from app.modulos.historia import resumen_clinico as rutas_resumen_clinico
from app.modulos.historia import rutas as rutas_historia
from app.modulos.imagenes import rutas as rutas_imagenes
from app.modulos.lista_espera import rutas as rutas_espera
from app.modulos.odontologia import formulario_033 as rutas_formulario_033
from app.modulos.odontologia import placa as rutas_placa
from app.modulos.odontologia import planes_rutas
from app.modulos.odontologia import rutas as rutas_odontologia
from app.modulos.organizacion import agenda_rutas as rutas_configuracion_agenda
from app.modulos.organizacion import plataforma as rutas_plataforma
from app.modulos.organizacion import rutas as rutas_catalogo
from app.modulos.pacientes import acceso_clinico_rutas as rutas_acceso_clinico
from app.modulos.pacientes import consentimientos as rutas_consentimientos
from app.modulos.pacientes import rutas as rutas_pacientes
from app.modulos.pagos import rutas as rutas_pagos
from app.modulos.postconsulta import rutas as rutas_postconsulta
from app.modulos.profesionales import agenda_rutas as rutas_agenda_profesionales
from app.modulos.profesionales import delegaciones as rutas_delegaciones
from app.modulos.profesionales import gestion_rutas as rutas_gestion_profesionales
from app.modulos.promociones import rutas as rutas_promociones
from app.modulos.usuarios import fotos as rutas_fotos_usuario
from app.modulos.usuarios import rutas as rutas_usuarios
from app.nucleo.almacen import AlmacenS3, ErrorAlmacen, construir_almacen
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.limite_tasa import ClienteRedis, LimitadorTasa
from app.nucleo.metricas import MetricasAplicacion, actualizar_metricas_outbox
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

    # Mismo criterio que la base: se avisa y se arranca. Una carga de imagen
    # sin almacen falla con 503 y lo dice; un proceso que no arranca no.
    almacen = getattr(aplicacion.state, "almacen_objetos", None)
    if isinstance(almacen, AlmacenS3):
        try:
            await almacen.asegurar_bucket()
            _logger.info("arranque.almacen_listo", almacen="s3")
        except ErrorAlmacen as exc:
            _logger.error("arranque.almacen_inaccesible", motivo=str(exc))

    yield

    await gestor.cerrar()
    fabrica = getattr(aplicacion.state, "fabrica_conversacional", None)
    if fabrica is not None:
        await fabrica.cerrar()
    await cerrar_proveedores_clinica()
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
    aplicacion.state.almacen_objetos = construir_almacen(configuracion)
    aplicacion.state.redis = (
        cliente_redis if cliente_redis is not None else _crear_cliente_redis(configuracion)
    )
    aplicacion.state.limitador = LimitadorTasa(aplicacion.state.redis, aplicacion.state.reloj)
    # Adaptadores de calendario. Van en `app.state` y no como global del
    # modulo para que la suite pueda levantar varias aplicaciones con
    # adaptadores distintos en el mismo proceso.
    aplicacion.state.proveedores_calendario = construir_proveedores(configuracion)
    # Proveedor de embeddings. Se construye una vez por aplicacion porque el
    # real carga un modelo ONNX de cientos de megabytes: hacerlo por peticion
    # seria inviable.
    aplicacion.state.embeddings = construir_proveedor_embeddings(
        configuracion.proveedor_embeddings,
        modelo=configuracion.modelo_embeddings,
        dimension=configuracion.dimension_embeddings,
        ruta_cache=str(configuracion.ruta_cache_embeddings),
    )
    # Fabrica del proveedor conversacional. Es una fabrica y no una instancia
    # porque el proveedor real guarda la transcripcion del turno; el cliente
    # HTTP, que es lo caro, si se comparte (ver `ia/seleccion_llm.py`).
    aplicacion.state.fabrica_conversacional = construir_fabrica_conversacional(configuracion)
    # Modelo de decision tipada (Jev o reglas). Decide; nunca ejecuta.
    aplicacion.state.clasificador = construir_clasificador(configuracion)
    aplicacion.state.generador_imagenes = construir_generador(configuracion)
    aplicacion.state.metricas = MetricasAplicacion()

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

    # Todos los manejadores HTTP devuelven el mismo sobre de error. Las rutas
    # declaran sus respuestas de éxito, pero sin una respuesta `default` los
    # clientes OpenAPI y Schemathesis consideran inesperado un 401/403/404.
    documento = aplicacion.openapi()
    respuesta_error = {
        "description": "Error de autenticación, permisos, validación o negocio.",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["codigo", "mensaje"],
                    "properties": {
                        "codigo": {"type": "string"},
                        "mensaje": {"type": "string"},
                        "detalles": {"type": "object", "additionalProperties": True},
                        "correlacion_id": {"type": "string"},
                    },
                }
            }
        },
    }
    for ruta in documento.get("paths", {}).values():
        for operacion in ruta.values():
            if isinstance(operacion, dict) and "responses" in operacion:
                operacion["responses"].setdefault("default", respuesta_error)
    aplicacion.openapi_schema = documento
    if configuracion.metricas_habilitadas:
        rutas_metricas = list(aplicacion.openapi()["paths"])
        rutas_metricas.append(configuracion.ruta_metricas)
        aplicacion.state.metricas.configurar_rutas(rutas_metricas)
    return aplicacion


def _registrar_rutas_del_equipo(aplicacion: FastAPI) -> None:
    """Fotos del equipo, especialidad de la historia, recorrido y asistente interno."""
    aplicacion.include_router(rutas_fotos_usuario.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_especialidades_historia.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_recorrido.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_asistente.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_ayuda.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_revision_riesgo.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_acceso_clinico.enrutador, prefix=PREFIJO_API)


def _registrar_rutas(aplicacion: FastAPI) -> None:
    _registrar_rutas_del_equipo(aplicacion)
    aplicacion.include_router(rutas_usuarios.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_usuarios.enrutador_usuarios, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_configuracion.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_agenda.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_bloqueos_agenda.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_catalogo.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_configuracion_agenda.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_plataforma.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_consentimientos.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_pacientes.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_pagos.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_dashboard.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(indicadores_dashboard.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_automatizaciones.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_resumen_clinico.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_postconsulta.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_espera.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(demo_rutas.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_conversaciones.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_historia.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_anamnesis.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_acceso_emergencia.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_imagenes.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_imagenes.enrutador_imagenes, prefix=PREFIJO_API)
    # El webhook no lleva autenticacion: lo protege la firma HMAC, no un
    # token. Ver el encabezado de app/mensajeria/rutas.py.
    aplicacion.include_router(rutas_whatsapp.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_calendario.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_conocimiento.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_promociones.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_placa.enrutador_placa, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_formulario_033.enrutador_formulario_033, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_delegaciones.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_agenda_profesionales.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_gestion_profesionales.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(rutas_odontologia.enrutador, prefix=PREFIJO_API)
    aplicacion.include_router(planes_rutas.enrutador_planes, prefix=PREFIJO_API)

    if aplicacion.state.configuracion.metricas_habilitadas:

        @aplicacion.get(
            aplicacion.state.configuracion.ruta_metricas,
            include_in_schema=False,
            tags=["salud"],
        )
        async def metricas(request: Request) -> Response:
            token = aplicacion.state.configuracion.metricas_token.get_secret_value()
            if token and not hmac.compare_digest(
                request.headers.get("Authorization", ""), f"Bearer {token}"
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credencial de métricas inválida.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            await actualizar_metricas_outbox(
                aplicacion.state.metricas,
                aplicacion.state.gestor_bd,
                aplicacion.state.reloj,
            )
            return Response(
                content=aplicacion.state.metricas.exportar(),
                media_type=CONTENT_TYPE_LATEST,
            )

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
