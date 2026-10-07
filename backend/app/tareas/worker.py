"""Worker de ARQ.

Se arranca con:

    uv run arq app.tareas.worker.ConfiguracionWorker

Por que los periodicos se declaran aqui y no se programan al vuelo
------------------------------------------------------------------
Un trabajo programado de forma dinamica vive en Redis. Si Redis se vacia --
un reinicio sin persistencia, un `FLUSHDB` de mantenimiento --, ese trabajo
deja de existir y nadie se entera hasta que alguien nota que los bloqueos ya
no se liberan. Declarado como `cron` en el codigo, se reconstruye solo en cada
arranque del worker.

Por que `unique=True` en los periodicos
---------------------------------------
Con varias replicas del worker, ARQ ejecutaria el mismo cron una vez por
replica. La ejecucion simultanea no romperia los datos -- el barrido usa
`FOR UPDATE SKIP LOCKED` --, pero multiplicaria las consultas sin repartir
mas trabajo. `unique=True` hace que solo una replica lo ejecute.
"""

from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.nucleo.configuracion import Configuracion
from app.tareas.adherencia import evaluar_alertas_adherencia
from app.tareas.agenda import expirar_bloqueos
from app.tareas.al_ingestas_conocimiento import procesar_ingestas_conocimiento
from app.tareas.calendario import reconciliar_calendarios, sincronizar_calendarios
from app.tareas.contexto import al_arrancar, al_parar
from app.tareas.lista_espera import expirar_ofertas
from app.tareas.outbox import (
    encolar_recordatorios,
    procesar_outbox,
    recuperar_mensajes_huerfanos,
)


def _ajustes_redis() -> RedisSettings:
    return RedisSettings.from_dsn(Configuracion().url_redis)


class ConfiguracionWorker:
    """Configuracion que ARQ lee por reflexion."""

    functions: list[Any] = [  # noqa: RUF012
        expirar_bloqueos,
        expirar_ofertas,
        procesar_outbox,
        encolar_recordatorios,
        recuperar_mensajes_huerfanos,
        sincronizar_calendarios,
        reconciliar_calendarios,
        evaluar_alertas_adherencia,
        procesar_ingestas_conocimiento,
    ]

    cron_jobs: list[Any] = [  # noqa: RUF012
        cron(expirar_ofertas, minute=set(range(60)), unique=True, timeout=120, max_tries=1),
        cron(
            procesar_ingestas_conocimiento,
            minute=set(range(60)),
            unique=True,
            timeout=900,
            max_tries=1,
        ),
        # Diario a las 09:20 de Ecuador (14:20 UTC): las omisiones se cuentan
        # sobre siete dias y una alerta abierta bloquea repeticiones.
        cron(
            evaluar_alertas_adherencia,
            hour={14},
            minute={20},
            unique=True,
            timeout=600,
            max_tries=1,
        ),
        # Cada minuto. Es la resolucion util: el bloqueo dura minutos, y
        # barrer cada cinco significaria que un turno abandonado sigue
        # retenido hasta cinco minutos de mas. La consulta esta indexada por
        # (estado, expira_en) y no devuelve nada la mayoria de las veces.
        cron(
            expirar_bloqueos,
            minute=set(range(60)),
            unique=True,
            # Si una ejecucion se atasca, la siguiente no se acumula encima:
            # se aborta la anterior. Dos barridos simultaneos del mismo lote
            # no aportan nada.
            timeout=120,
            max_tries=1,
        ),
        # Cada minuto tambien. Es la cadencia que decide la puntualidad de los
        # recordatorios: con cinco minutos, un aviso programado para las 07:00
        # podria salir a las 07:04, y el paciente que iba a las 07:30 ya salio
        # de casa.
        cron(
            encolar_recordatorios,
            minute=set(range(60)),
            unique=True,
            timeout=120,
            max_tries=1,
        ),
        cron(
            procesar_outbox,
            minute=set(range(60)),
            unique=True,
            timeout=120,
            max_tries=1,
        ),
        # Cada diez minutos. Solo actua si un worker murio a media entrega, y
        # la ventana de deteccion son quince minutos de todas formas: barrer
        # mas a menudo no adelantaria nada.
        cron(
            recuperar_mensajes_huerfanos,
            minute={0, 10, 20, 30, 40, 50},
            unique=True,
            timeout=60,
            max_tries=1,
        ),
        # Cada dos minutos. Un reflejo de calendario no tiene una hora
        # concreta a la que deba salir -- solo tiene que estar antes de que el
        # profesional mire su agenda --, asi que no necesita la cadencia del
        # outbox y evita barridos vacios contra el proveedor.
        cron(
            sincronizar_calendarios,
            minute=set(range(0, 60, 2)),
            unique=True,
            timeout=180,
            max_tries=1,
        ),
        # Cada hora, y no mas a menudo: consume una lectura del proveedor por
        # evento, asi que es el trabajo mas caro en cuota de API. Su ventana de
        # deteccion aceptable se mide en horas.
        cron(
            reconciliar_calendarios,
            minute={7},
            unique=True,
            timeout=300,
            max_tries=1,
        ),
    ]

    on_startup = al_arrancar
    on_shutdown = al_parar

    # Un solo trabajo a la vez por proceso. Los trabajos de este sistema
    # escriben en la base de datos; la concurrencia se consigue con mas
    # replicas, que reparten el trabajo con SKIP LOCKED, no con mas corrutinas
    # compitiendo por el mismo pool de conexiones.
    max_jobs = 1

    # Reintentar un trabajo que fallo por un error de programacion solo repite
    # el error. Los reintentos que importan -- los envios a terceros -- los
    # gestiona el outbox con su propio contador y su retroceso (ADR-0008).
    max_tries = 1

    # ARQ lee esto como atributo, no como metodo, asi que la conexion queda
    # resuelta al importar el modulo. Es exactamente cuando ARQ lo carga, y
    # tiene una ventaja: una configuracion de Redis invalida hace fallar el
    # arranque del worker con un error claro, en lugar de fallar en el primer
    # trabajo, media hora despues y dentro de un reintento.
    redis_settings = _ajustes_redis()


__all__ = ["ConfiguracionWorker"]
