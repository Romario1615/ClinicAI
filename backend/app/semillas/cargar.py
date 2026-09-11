"""Script de carga de semillas.

Uso:
    python -m app.semillas.cargar                  # catalogos + datos sinteticos
    python -m app.semillas.cargar --solo-catalogos # solo permisos y roles
    python -m app.semillas.cargar --verificar      # comprueba coherencia
    python -m app.semillas.cargar --pacientes 200 --citas 800

Los catalogos (permisos y roles) se cargan en TODOS los entornos: son parte
del funcionamiento.  Los datos sinteticos solo fuera de produccion, y la
salvaguarda esta en `sinteticos.py`, no aqui: quien llame a esa funcion desde
otro sitio tambien queda protegido.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.nucleo.configuracion import Configuracion
from app.semillas.catalogos import (
    cargar_catalogos,
    verificar_coherencia,
)
from app.semillas.sinteticos import cargar_datos_sinteticos


def _escribir(mensaje: str = "") -> None:
    print(mensaje, flush=True)  # noqa: T201


async def _ejecutar(opciones: argparse.Namespace) -> int:
    configuracion = Configuracion()
    motor = create_async_engine(configuracion.url_base_datos)
    fabrica = async_sessionmaker(bind=motor, expire_on_commit=False)

    codigo_salida = 0

    try:
        # --- Verificacion ---
        if opciones.verificar:
            async with fabrica() as sesion:
                problemas = await verificar_coherencia(sesion)
            if problemas:
                _escribir("Problemas de coherencia encontrados:")
                for problema in problemas:
                    _escribir(f"  - {problema}")
                return 1
            _escribir("Los catalogos de la base de datos son coherentes con el codigo.")
            return 0

        # --- Catalogos ---
        #
        # Transaccion propia: los catalogos deben quedar aplicados aunque la
        # carga de datos sinteticos falle despues.  Sin permisos ni roles, el
        # sistema no funciona; sin datos de ejemplo, solo esta vacio.
        _escribir("=== Catalogos del sistema ===")
        async with fabrica() as sesion:
            async with sesion.begin():
                resumen = await cargar_catalogos(sesion)
            _escribir(resumen.describir())

        if opciones.solo_catalogos:
            return 0

        # --- Datos sinteticos ---
        _escribir()
        _escribir("=== Datos sinteticos ===")
        _escribir(f"Entorno: {configuracion.entorno.value}")

        async with fabrica() as sesion:
            async with sesion.begin():
                sinteticos = await cargar_datos_sinteticos(
                    sesion,
                    configuracion,
                    cantidad_pacientes=opciones.pacientes,
                    cantidad_citas=opciones.citas,
                    semilla=opciones.semilla,
                )
            _escribir()
            _escribir(sinteticos.describir())

    except RuntimeError as exc:
        _escribir()
        _escribir(f"Carga detenida: {exc}")
        codigo_salida = 2
    except Exception as exc:
        _escribir()
        _escribir(f"Error inesperado: {type(exc).__name__}: {exc}")
        codigo_salida = 1
    finally:
        await motor.dispose()

    return codigo_salida


def main(argumentos: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(
        description="Carga los catalogos del sistema y datos sinteticos."
    )
    analizador.add_argument(
        "--solo-catalogos",
        action="store_true",
        help="Carga unicamente permisos y roles. Apto para produccion.",
    )
    analizador.add_argument(
        "--verificar",
        action="store_true",
        help="Comprueba que la base de datos coincida con el catalogo del codigo.",
    )
    analizador.add_argument("--pacientes", type=int, default=60, help="Pacientes sinteticos (60).")
    analizador.add_argument("--citas", type=int, default=200, help="Citas sinteticas (200).")
    analizador.add_argument(
        "--semilla",
        type=int,
        default=20260415,
        help="Semilla del generador aleatorio; fijarla hace la carga reproducible.",
    )
    opciones = analizador.parse_args(argumentos)

    return asyncio.run(_ejecutar(opciones))


if __name__ == "__main__":
    raise SystemExit(main())
