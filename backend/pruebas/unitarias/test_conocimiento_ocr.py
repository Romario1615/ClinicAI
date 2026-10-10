"""Límites, aislamiento de procesos y errores de OCR sin ejecutar herramientas externas."""

from __future__ import annotations

import asyncio
import json
import subprocess
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from app.modulos.conocimiento import ocr, ocr_proceso
from app.modulos.conocimiento.esquemas import RespuestaExtraccion
from app.nucleo.configuracion import Configuracion, Entorno
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    ArchivoNoPermitido,
    ProveedorExternoNoDisponible,
)
from pruebas.documentos_ocr import pdf_escanado

pytestmark = pytest.mark.unitaria


def pdf(paginas: int = 1, *, protegido: bool = False, activo: str | None = None) -> bytes:
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=612, height=792)
    if activo:
        escritor._root_object[NameObject(activo)] = DictionaryObject()
    if protegido:
        escritor.encrypt("clave-sintetica")
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


@pytest.mark.parametrize("datos", [b"", b"PK\x03\x04", b"una imagen", b"%PDF-1.7\nfallo"])
def test_estructura_invalida(datos: bytes) -> None:
    with pytest.raises(ocr_proceso.FalloOcr):
        ocr_proceso.validar_pdf(datos, 20)


@pytest.mark.parametrize(
    "datos", [pdf(protegido=True), pdf(21), pdf(0), pdf(activo="/OpenAction"), pdf(activo="/AA")]
)
def test_rechaza_protegidos_activos_o_paginas_excesivas(datos: bytes) -> None:
    with pytest.raises(ocr_proceso.FalloOcr):
        ocr_proceso.validar_pdf(datos, 20)


def test_renderiza_todas_las_paginas_y_avisa_paginas_vacias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motor = MagicMock(side_effect=["Horario sintético", ""])
    monkeypatch.setattr(ocr_proceso, "reconocer_imagen", motor)
    resultado = ocr_proceso.reconocer_pdf(pdf_escanado(pagina_blanca=True), 20, "local", "clinica")
    assert resultado == {"contenido": "Horario sintético", "paginas": 2, "paginas_sin_texto": [2]}
    assert motor.call_count == 2
    assert motor.call_args.args[0].startswith(b"P5\n")


def test_limite_texto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_proceso, "reconocer_imagen", lambda *_: "x" * 500_001)
    with pytest.raises(ocr_proceso.FalloOcr, match="500 000"):
        ocr_proceso.reconocer_pdf(pdf(), 20, "local", "clinica")


def test_escaneo_sin_texto_no_devuelve_exito(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_proceso, "reconocer_imagen", lambda *_: "")
    with pytest.raises(ocr_proceso.FalloOcr, match="No se reconoció"):
        ocr_proceso.reconocer_pdf(pdf(), 20, "local", "clinica")


def test_limite_pixeles_antes_de_renderizar() -> None:
    escritor = PdfWriter()
    escritor.add_blank_page(width=10000, height=10000)
    salida = BytesIO()
    escritor.write(salida)
    with pytest.raises(ocr_proceso.FalloOcr, match="tamaño"):
        ocr_proceso.reconocer_pdf(salida.getvalue(), 20, "local", "clinica")


@pytest.mark.parametrize("ejecucion", ["local", "wsl"])
def test_tesseract_usa_pipes_argumentos_y_plazo(
    monkeypatch: pytest.MonkeyPatch, ejecucion: str
) -> None:
    proceso = MagicMock(return_value=subprocess.CompletedProcess([], 0, b"Texto\n"))
    monkeypatch.setattr(ocr_proceso.subprocess, "run", proceso)
    assert ocr_proceso.reconocer_imagen(b"PGM", ejecucion, "clinica") == "Texto"
    argumentos = proceso.call_args.args[0]
    assert argumentos[-7:] == ["tesseract", "stdin", "stdout", "-l", "spa+eng", "--psm", "3"]
    assert proceso.call_args.kwargs["input"] == b"PGM"
    assert proceso.call_args.kwargs["timeout"] == 17
    assert not proceso.call_args.kwargs.get("shell")
    if ejecucion == "wsl":
        assert argumentos[:7] == [
            "wsl.exe",
            "-d",
            "clinica",
            "--exec",
            "timeout",
            "15s",
            "tesseract",
        ]


@pytest.mark.parametrize("fallo", [OSError("motor"), subprocess.TimeoutExpired("tesseract", 15)])
def test_motor_ausente_o_timeout(monkeypatch: pytest.MonkeyPatch, fallo: Exception) -> None:
    monkeypatch.setattr(ocr_proceso.subprocess, "run", MagicMock(side_effect=fallo))
    with pytest.raises(ocr_proceso.FalloOcr, match="plazo"):
        ocr_proceso.reconocer_imagen(b"PGM", "local", "clinica")


def test_idiomas_ausentes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ocr_proceso.subprocess,
        "run",
        MagicMock(return_value=subprocess.CompletedProcess([], 1, b"")),
    )
    with pytest.raises(ocr_proceso.FalloOcr, match="idiomas"):
        ocr_proceso.reconocer_imagen(b"PGM", "local", "clinica")


@pytest.mark.asyncio
async def test_antivirus_precede_al_motor(monkeypatch: pytest.MonkeyPatch) -> None:
    antivirus = AsyncMock()
    extraccion = RespuestaExtraccion(contenido="Horario", paginas=1, escaneo_antivirus="LIMPIO")
    motor = AsyncMock(return_value=extraccion)
    monkeypatch.setattr(ocr, "_exigir_antivirus", antivirus)
    monkeypatch.setattr(ocr, "_ejecutar", motor)
    assert await ocr.extraer_escaneo(pdf(), Configuracion(_env_file=None)) == extraccion
    antivirus.assert_awaited_once()
    motor.assert_awaited_once()


@pytest.mark.asyncio
async def test_produccion_no_procesa_sin_antivirus(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Configuracion(_env_file=None)
    config = config.model_copy(update={"entorno": Entorno.PRODUCCION})
    motor = AsyncMock()
    monkeypatch.setattr(ocr, "_ejecutar", motor)
    with pytest.raises(ProveedorExternoNoDisponible, match="antivirus"):
        await ocr.extraer_escaneo(pdf(), config)
    motor.assert_not_called()


@pytest.mark.parametrize(
    "datos,config,excepcion",
    [
        (b"", {}, ArchivoNoPermitido),
        (b"no pdf", {}, ArchivoNoPermitido),
        (b"%PDF-" + b"x" * 1024**2, {"max_tamano_archivo_mb": 1}, ArchivoDemasiadoGrande),
        (b"%PDF-1.7", {"ocr_habilitado": False}, ProveedorExternoNoDisponible),
    ],
    ids=["vacio", "otro-formato", "tamano", "desactivado"],
)
@pytest.mark.asyncio
async def test_entrada_y_motor_desactivado(
    datos: bytes, config: dict, excepcion: type[Exception]
) -> None:
    with pytest.raises(excepcion):
        await ocr.extraer_escaneo(datos, Configuracion(_env_file=None, **config))


@pytest.mark.asyncio
async def test_ocupado_no_encola_archivos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "_plazas", asyncio.Semaphore(0))
    with pytest.raises(ProveedorExternoNoDisponible, match="ocupado"):
        await ocr.extraer_escaneo(pdf(), Configuracion(_env_file=None))


@pytest.mark.parametrize(
    "salida,codigo,excepcion",
    [
        (b"no JSON", 0, ProveedorExternoNoDisponible),
        (b"[]", 0, ProveedorExternoNoDisponible),
        (b"{}", 1, ProveedorExternoNoDisponible),
        (b"{}", 0, ProveedorExternoNoDisponible),
        (b'{"error":"ARCHIVO","mensaje":"No permitido"}', 0, ArchivoNoPermitido),
        (b'{"error":"TAMANO","mensaje":"Grande"}', 0, ArchivoDemasiadoGrande),
        (b'{"error":"MOTOR","mensaje":"No disponible"}', 0, ProveedorExternoNoDisponible),
    ],
)
@pytest.mark.asyncio
async def test_resultados_del_proceso(
    monkeypatch: pytest.MonkeyPatch, salida: bytes, codigo: int, excepcion: type[Exception]
) -> None:
    proceso = MagicMock(returncode=codigo, communicate=AsyncMock(return_value=(salida, None)))
    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", AsyncMock(return_value=proceso))
    with pytest.raises(excepcion):
        await ocr._ejecutar(pdf(), Configuracion(_env_file=None))


@pytest.mark.asyncio
async def test_respuesta_correcta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_CONTRASENA", "valor-sintetico-no-se-propaga")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "valor-sintetico-no-se-propaga")
    salida = json.dumps({"contenido": "Horario", "paginas": 1, "paginas_sin_texto": []}).encode()
    proceso = MagicMock(returncode=0, communicate=AsyncMock(return_value=(salida, None)))
    inicio = AsyncMock(return_value=proceso)
    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", inicio)
    res = await ocr._ejecutar(pdf(), Configuracion(_env_file=None))
    assert res.requiere_revision_humana and res.escaneo_antivirus == "NO_DISPONIBLE"
    assert inicio.call_args.args[1:3] == ("-m", "app.modulos.conocimiento.ocr_proceso")
    entorno = inicio.call_args.kwargs["env"]
    assert "POSTGRES_CONTRASENA" not in entorno and "GOOGLE_CLIENT_SECRET" not in entorno
    assert entorno["OMP_THREAD_LIMIT"] == "1"


@pytest.mark.parametrize("fallo", [TimeoutError(), asyncio.CancelledError()])
@pytest.mark.asyncio
async def test_timeout_o_cancelacion_termina_el_arbol(
    monkeypatch: pytest.MonkeyPatch, fallo: BaseException
) -> None:
    proceso = MagicMock(communicate=AsyncMock(side_effect=fallo))
    monkeypatch.setattr(ocr.asyncio, "create_subprocess_exec", AsyncMock(return_value=proceso))
    terminar = AsyncMock()
    monkeypatch.setattr(ocr, "_terminar", terminar)
    esperada = (
        ProveedorExternoNoDisponible if isinstance(fallo, TimeoutError) else asyncio.CancelledError
    )
    with pytest.raises(esperada):
        await ocr._ejecutar(pdf(), Configuracion(_env_file=None))
    terminar.assert_awaited_once_with(proceso)


@pytest.mark.asyncio
async def test_fallo_al_iniciar_proceso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ocr.asyncio, "create_subprocess_exec", AsyncMock(side_effect=OSError("no disponible"))
    )
    with pytest.raises(ProveedorExternoNoDisponible, match="motor OCR"):
        await ocr._ejecutar(pdf(), Configuracion(_env_file=None))


@pytest.mark.parametrize("plataforma", ["win32", "linux"])
@pytest.mark.asyncio
async def test_termina_unicamente_su_proceso_y_descendientes(
    monkeypatch: pytest.MonkeyPatch, plataforma: str
) -> None:
    proceso = MagicMock(pid=12345, returncode=None, wait=AsyncMock())
    terminador = MagicMock(wait=AsyncMock())
    inicio = AsyncMock(return_value=terminador)
    killpg = MagicMock()
    with monkeypatch.context() as contexto:
        contexto.setattr(ocr.sys, "platform", plataforma)
        contexto.setattr(ocr.asyncio, "create_subprocess_exec", inicio)
        contexto.setattr(ocr.os, "killpg", killpg, raising=False)
        contexto.setattr(ocr.signal, "SIGKILL", 9, raising=False)
        await ocr._terminar(proceso)
    proceso.wait.assert_awaited_once()
    if plataforma == "win32":
        assert inicio.call_args.args == ("taskkill.exe", "/PID", "12345", "/T", "/F")
        terminador.wait.assert_awaited_once()
        killpg.assert_not_called()
    else:
        killpg.assert_called_once_with(12345, 9)
        inicio.assert_not_called()


@pytest.mark.asyncio
async def test_no_mata_proceso_ya_finalizado() -> None:
    proceso = MagicMock(returncode=0, wait=AsyncMock())
    await ocr._terminar(proceso)
    proceso.wait.assert_not_called()


@pytest.mark.parametrize("caso", ["correcto", "archivo", "inesperado", "tamano"])
def test_entrada_salida_del_proceso_es_json_acotado(
    monkeypatch: pytest.MonkeyPatch, caso: str
) -> None:
    entrada = b"%PDF-1.7" if caso != "tamano" else b"x" * (ocr_proceso.MAXIMO_BYTES + 1)
    salida = BytesIO()
    monkeypatch.setattr(ocr_proceso.sys, "stdin", SimpleNamespace(buffer=BytesIO(entrada)))
    monkeypatch.setattr(ocr_proceso.sys, "stdout", SimpleNamespace(buffer=salida))
    monkeypatch.setattr(ocr_proceso.sys, "argv", ["ocr", "20", "local", "clinica"])
    motor = MagicMock(return_value={"contenido": "Horario", "paginas": 1, "paginas_sin_texto": []})
    if caso == "archivo":
        motor.side_effect = ocr_proceso.FalloOcr("ARCHIVO", "No permitido")
    if caso == "inesperado":
        motor.side_effect = RuntimeError("secreto-sintetico-no-expuesto")
    monkeypatch.setattr(ocr_proceso, "reconocer_pdf", motor)
    ocr_proceso.main()
    respuesta = json.loads(salida.getvalue())
    if caso == "correcto":
        assert respuesta["contenido"] == "Horario"
    else:
        assert respuesta["error"] == ("TAMANO" if caso == "tamano" else "ARCHIVO")
        assert b"secreto-sintetico" not in salida.getvalue()


@pytest.mark.parametrize("sitio", ["nombres", "pagina", "anotacion"])
def test_rechaza_acciones_en_nombres_paginas_y_anotaciones(sitio: str) -> None:
    escritor = PdfWriter()
    pagina = escritor.add_blank_page(width=612, height=792)
    if sitio == "nombres":
        escritor._root_object[NameObject("/Names")] = DictionaryObject(
            {NameObject("/JavaScript"): DictionaryObject()}
        )
    elif sitio == "pagina":
        pagina[NameObject("/AA")] = DictionaryObject()
    else:
        pagina[NameObject("/Annots")] = ArrayObject(
            [escritor._add_object(DictionaryObject({NameObject("/A"): DictionaryObject()}))]
        )
    salida = BytesIO()
    escritor.write(salida)
    with pytest.raises(ocr_proceso.FalloOcr, match="no admitid"):
        ocr_proceso.validar_pdf(salida.getvalue(), 20)
