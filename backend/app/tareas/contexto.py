"""Contexto compartido por los trabajos en segundo plano.

ARQ pasa un diccionario a cada trabajo. Aqui se construye al arrancar el
worker y se cierra al pararlo, con los mismos objetos que usa la API:
configuracion, reloj inyectable y gestor de base de datos.

Por que el mismo reloj inyectable
---------------------------------
Un trabajo que decide si un bloqueo caduco comparando contra `datetime.now()`
no se puede probar sin esperar en tiempo real (ADR-0010). Con el reloj
inyectado, la prueba fija el instante y comprueba el limite exacto: un bloqueo
que vence dentro de un segundo **no** se cancela, y uno que vencio hace un
segundo si.
"""

from __future__ import annotations

from typing import Any

from app.ia.embeddings import construir_proveedor_embeddings
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.registro import configurar_registro, obtener_logger
from app.nucleo.reloj import RelojSistema

_logger = obtener_logger(__name__)


# Claves que este modulo deja en el contexto (`ctx`), y que los trabajos leen:
#
#   ctx["configuracion"] -> Configuracion
#   ctx["reloj"]         -> Reloj
#   ctx["gestor_bd"]     -> GestorBaseDatos
#
# No se declara como TypedDict porque ARQ anade las suyas al mismo diccionario
# (`job_id`, `enqueue_time`, `score`, `redis`) y exige la firma
# `dict[Any, Any]`; un TypedDict daria una falsa sensacion de contrato cerrado
# sobre un diccionario que ARQ comparte.


async def al_arrancar(ctx: dict[Any, Any]) -> None:
    """Abre los recursos de larga vida del worker.

    El motor usa un pool pequeno: un worker no atiende peticiones
    concurrentes de usuarios, ejecuta trabajos de uno en uno por proceso. Un
    pool del tamano del de la API consumiria conexiones del servidor sin
    usarlas, y las conexiones de PostgreSQL son un recurso limitado que la API
    necesita mas.
    """
    configuracion = Configuracion()
    configurar_registro(
        nivel=configuracion.nivel_log,
        formato=configuracion.formato_log,
        redactar=configuracion.redactar_datos_sensibles,
    )

    ctx["configuracion"] = configuracion
    ctx["reloj"] = RelojSistema()
    ctx["embeddings"] = construir_proveedor_embeddings(
        configuracion.proveedor_embeddings,
        modelo=configuracion.modelo_embeddings,
        dimension=configuracion.dimension_embeddings,
        ruta_cache=str(configuracion.ruta_cache_embeddings),
    )
    ctx["gestor_bd"] = GestorBaseDatos(
        configuracion.url_base_datos,
        tamano_pool=2,
        desborde_maximo=2,
    )
    _logger.info("worker.arrancado", entorno=configuracion.entorno.value)


async def al_parar(ctx: dict[Any, Any]) -> None:
    gestor: GestorBaseDatos | None = ctx.get("gestor_bd")
    if gestor is not None:
        await gestor.cerrar()
    _logger.info("worker.parado")


__all__ = ["al_arrancar", "al_parar"]
