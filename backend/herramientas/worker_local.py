"""Arranque del worker en Windows, donde asyncio no admite senales POSIX."""

import sys

from arq.worker import run_worker

from app.nucleo.configuracion import Configuracion
from app.tareas.worker import ConfiguracionWorker


def main() -> None:
    configuracion = Configuracion()
    if configuracion.entorno.value != "local":
        raise SystemExit("Este arranque es exclusivo de la demostracion local.")
    if configuracion.modo_whatsapp != "sandbox" or configuracion.modo_calendario != "sandbox":
        raise SystemExit("El worker de demostracion requiere WhatsApp y calendario en sandbox.")
    run_worker(ConfiguracionWorker, handle_signals=sys.platform != "win32")


if __name__ == "__main__":
    main()
