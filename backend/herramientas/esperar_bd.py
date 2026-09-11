"""Espera a que PostgreSQL y Redis esten realmente listos.

Por que hace falta
------------------
El proxy de Docker acepta la conexion TCP en cuanto el contenedor arranca,
mucho antes de que PostgreSQL termine de inicializarse.  El resultado es el
peor modo de fallo posible: el socket conecta, nadie responde al protocolo y
el cliente se queda esperando hasta agotar su tiempo limite.

Comprobar que el puerto esta abierto NO sirve.  Este script espera hasta que
la base de datos responde una consulta de verdad, que es la unica senal
fiable de que esta lista.

Uso:
    python -m herramientas.esperar_bd
    python -m herramientas.esperar_bd --segundos 120 --solo postgres

Codigos de salida:
    0  todo listo
    1  se agoto la espera
    2  error de configuracion
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Permite ejecutarlo como script sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nucleo.configuracion import Configuracion


def _escribir(mensaje: str) -> None:
    print(mensaje, flush=True)


def esperar_postgres(cfg: Configuracion, limite_segundos: int) -> bool:
    """Espera hasta que PostgreSQL responda una consulta real."""
    import sqlalchemy as sa

    destino = f"{cfg.postgres_host}:{cfg.postgres_puerto}/{cfg.postgres_bd}"
    _escribir(f"Esperando PostgreSQL en {destino} ...")

    limite = time.monotonic() + limite_segundos
    ultimo_error = ""
    intento = 0

    while time.monotonic() < limite:
        intento += 1
        try:
            motor = sa.create_engine(
                cfg.url_base_datos_sincrona,
                # Tiempo corto por intento: si el contenedor esta a medio
                # arrancar, es mejor reintentar pronto que esperar 30 s a un
                # servidor que todavia no va a contestar.
                connect_args={"connect_timeout": 3},
                pool_pre_ping=False,
            )
            with motor.connect() as conexion:
                # No basta con conectar: se comprueba que las extensiones
                # criticas existan.  Un PostgreSQL sano sin `vector` ni
                # `btree_gist` no sirve para este sistema.
                presentes = {
                    fila[0]
                    for fila in conexion.execute(sa.text("SELECT extname FROM pg_extension"))
                }
                requeridas = {"vector", "btree_gist", "pg_trgm", "pgcrypto"}
                faltantes = requeridas - presentes
                if faltantes:
                    _escribir(f"  PostgreSQL responde pero faltan extensiones: {sorted(faltantes)}")
                    _escribir(
                        "  El volumen puede haberse creado antes del script de inicializacion."
                    )
                    _escribir("  Recree con:  .\\infra\\scripts\\infra-abajo.ps1 -BorrarDatos")
                    return False
            motor.dispose()
            _escribir(f"  PostgreSQL listo tras {intento} intento(s).")
            return True
        except Exception as exc:
            ultimo_error = f"{type(exc).__name__}"
            time.sleep(1.5)

    _escribir(
        f"  PostgreSQL no respondio en {limite_segundos}s "
        f"({intento} intentos, ultimo: {ultimo_error})."
    )
    return False


def esperar_redis(cfg: Configuracion, limite_segundos: int) -> bool:
    """Espera hasta que Redis responda un PING."""
    import redis

    _escribir(f"Esperando Redis en {cfg.redis_host}:{cfg.redis_puerto} ...")

    limite = time.monotonic() + limite_segundos
    ultimo_error = ""
    intento = 0

    while time.monotonic() < limite:
        intento += 1
        try:
            cliente = redis.Redis.from_url(
                cfg.url_redis, socket_connect_timeout=3, socket_timeout=3
            )
            if cliente.ping():
                cliente.close()
                _escribir(f"  Redis listo tras {intento} intento(s).")
                return True
        except Exception as exc:
            ultimo_error = f"{type(exc).__name__}"
        time.sleep(1.0)

    _escribir(
        f"  Redis no respondio en {limite_segundos}s ({intento} intentos, ultimo: {ultimo_error})."
    )
    return False


def main(argumentos: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(
        description="Espera a que la infraestructura de datos este lista."
    )
    analizador.add_argument(
        "--segundos",
        type=int,
        default=90,
        help="Tiempo maximo de espera por servicio (por defecto 90).",
    )
    analizador.add_argument(
        "--solo",
        choices=["postgres", "redis"],
        default=None,
        help="Esperar solo a un servicio.",
    )
    opciones = analizador.parse_args(argumentos)

    try:
        cfg = Configuracion()
    except Exception as exc:
        _escribir(f"Configuracion invalida: {exc}")
        return 2

    listo = True
    if opciones.solo in (None, "postgres"):
        listo = esperar_postgres(cfg, opciones.segundos) and listo
    if opciones.solo in (None, "redis"):
        listo = esperar_redis(cfg, opciones.segundos) and listo

    if listo:
        _escribir("Infraestructura de datos lista.")
        return 0
    _escribir("La infraestructura de datos NO esta lista.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
