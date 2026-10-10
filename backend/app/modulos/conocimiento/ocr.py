"""OCR local explícito y efímero; revisar el resultado no equivale a publicarlo."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from contextlib import suppress

from pydantic import ValidationError

from app.modulos.conocimiento.archivos import _exigir_antivirus, _validar_tamano
from app.modulos.conocimiento.esquemas import RespuestaExtraccion
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    ArchivoNoPermitido,
    ProveedorExternoNoDisponible,
)

# Máximo por proceso de API; no acumular una cola de archivos en memoria.
_plazas = asyncio.Semaphore(2)
MAXIMO_RESPUESTA = 3_000_000
VARIABLES_DEL_MOTOR = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
    }
)


async def _terminar(proceso: asyncio.subprocess.Process) -> None:
    if proceso.returncode is not None:
        return
    if sys.platform == "win32":
        terminador = await asyncio.create_subprocess_exec(
            "taskkill.exe",
            "/PID",
            str(proceso.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x08000000,
        )
        await terminador.wait()
    else:
        with suppress(ProcessLookupError):
            os.killpg(proceso.pid, signal.SIGKILL)
    await proceso.wait()


async def _ejecutar(datos: bytes, configuracion: Configuracion) -> RespuestaExtraccion:
    opciones = (
        {"creationflags": 0x08000000} if sys.platform == "win32" else {"start_new_session": True}
    )
    try:
        # El parser nativo no recibe credenciales de BD, JWT, OAuth ni proveedores.
        entorno = {k: v for k, v in os.environ.items() if k.upper() in VARIABLES_DEL_MOTOR}
        entorno.update(PYTHONIOENCODING="utf-8", OMP_THREAD_LIMIT="1")
        proceso = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modulos.conocimiento.ocr_proceso",
            str(configuracion.ocr_max_paginas),
            configuracion.ocr_ejecucion,
            configuracion.ocr_distribucion_wsl,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=entorno,
            **opciones,
        )
    except OSError as exc:
        raise ProveedorExternoNoDisponible("El motor OCR local no está disponible.") from exc
    try:
        salida, _ = await asyncio.wait_for(
            proceso.communicate(datos), timeout=configuracion.ocr_tiempo_maximo_segundos
        )
    except TimeoutError as exc:
        await _terminar(proceso)
        raise ProveedorExternoNoDisponible(
            "El OCR agotó su plazo. Divida el documento y vuelva a intentar."
        ) from exc
    except asyncio.CancelledError:
        await _terminar(proceso)
        raise
    try:
        if proceso.returncode != 0 or len(salida) > MAXIMO_RESPUESTA:
            raise ValueError("Proceso OCR sin respuesta válida")
        respuesta = json.loads(salida)
        if not isinstance(respuesta, dict):
            raise ValueError("El proceso OCR no devolvió un objeto")
        if respuesta.get("error"):
            errores = {"ARCHIVO": ArchivoNoPermitido, "TAMANO": ArchivoDemasiadoGrande}
            error = errores.get(respuesta["error"], ProveedorExternoNoDisponible)
            raise error(respuesta["mensaje"])
        return RespuestaExtraccion(
            **respuesta,
            escaneo_antivirus="LIMPIO" if configuracion.antivirus_habilitado else "NO_DISPONIBLE",
        )
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        raise ProveedorExternoNoDisponible("El motor OCR no devolvió un resultado válido.") from exc


async def extraer_escaneo(datos: bytes, configuracion: Configuracion) -> RespuestaExtraccion:
    _validar_tamano(datos, configuracion)
    if len(datos) > 20 * 1024 * 1024:
        raise ArchivoDemasiadoGrande("El OCR admite archivos de hasta 20 MB.")
    if not datos.startswith(b"%PDF-"):
        raise ArchivoNoPermitido("El reconocimiento OCR admite únicamente documentos PDF.")
    if not configuracion.ocr_habilitado:
        raise ProveedorExternoNoDisponible(
            "El reconocimiento OCR está desactivado en este servidor."
        )
    if _plazas.locked():
        raise ProveedorExternoNoDisponible("El OCR está ocupado. Reintente en unos momentos.")
    async with _plazas:
        await _exigir_antivirus(datos, configuracion)
        return await _ejecutar(datos, configuracion)
