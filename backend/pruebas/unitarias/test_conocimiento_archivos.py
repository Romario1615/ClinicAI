"""Validación de archivos PDF antes de incorporarlos al corpus del RAG."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)

from app.modulos.conocimiento import archivos as archivos_conocimiento
from app.modulos.conocimiento.archivos import extraer_pdf
from app.nucleo.configuracion import Configuracion, Entorno
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    ArchivoNoPermitido,
    ProveedorExternoNoDisponible,
)

pytestmark = pytest.mark.unitaria


def pdf_con_texto(texto: str = "Preparación antes del examen.", *, activo: bool = False) -> bytes:
    escritor = PdfWriter()
    pagina = escritor.add_blank_page(width=612, height=792)
    fuente = escritor._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    recursos = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): fuente}),
        }
    )
    pagina[NameObject("/Resources")] = recursos
    flujo = DecodedStreamObject()
    flujo.set_data(f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1"))
    pagina[NameObject("/Contents")] = escritor._add_object(flujo)
    if activo:
        escritor._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("app.alert('x')"),
            }
        )
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


@pytest.mark.asyncio
async def test_extrae_texto_y_no_guarda_el_archivo() -> None:
    contenido = await extraer_pdf(pdf_con_texto(), Configuracion(_env_file=None))

    assert contenido == "Preparación antes del examen."


@pytest.mark.asyncio
async def test_rechaza_un_archivo_que_solo_finge_ser_pdf() -> None:
    with pytest.raises(ArchivoNoPermitido, match="está dañado"):
        await extraer_pdf(b"%PDF-1.7\n<script>alert(1)</script>", Configuracion(_env_file=None))


@pytest.mark.asyncio
async def test_rechaza_pdf_con_acciones_activas() -> None:
    with pytest.raises(ArchivoNoPermitido, match="acciones activas"):
        await extraer_pdf(pdf_con_texto(activo=True), Configuracion(_env_file=None))


@pytest.mark.asyncio
async def test_rechaza_pdf_sin_texto_seleccionable() -> None:
    with pytest.raises(ArchivoNoPermitido, match="requieren OCR"):
        await extraer_pdf(pdf_con_texto(""), Configuracion(_env_file=None))


@pytest.mark.asyncio
async def test_rechaza_archivo_mayor_al_limite_configurado() -> None:
    config = Configuracion(_env_file=None, max_tamano_archivo_mb=1)

    with pytest.raises(ArchivoDemasiadoGrande):
        await extraer_pdf(b"%PDF-1.7" + b"x" * (1024 * 1024), config)


@pytest.mark.asyncio
async def test_rechaza_mas_de_200_paginas() -> None:
    escritor = PdfWriter()
    for _ in range(201):
        escritor.add_blank_page(width=612, height=792)
    salida = BytesIO()
    escritor.write(salida)

    with pytest.raises(ArchivoNoPermitido, match="200 páginas"):
        await extraer_pdf(salida.getvalue(), Configuracion(_env_file=None))


@pytest.mark.asyncio
async def test_rechaza_texto_extraido_mayor_al_limite() -> None:
    with pytest.raises(ArchivoDemasiadoGrande, match="500 000 caracteres"):
        await extraer_pdf(
            pdf_con_texto("x" * 500_001),
            Configuracion(_env_file=None),
        )


@pytest.mark.asyncio
async def test_rechaza_pdf_cifrado() -> None:
    lector = PdfReader(BytesIO(pdf_con_texto()))
    escritor = PdfWriter()
    escritor.clone_document_from_reader(lector)
    escritor.encrypt("secreto")
    salida = BytesIO()
    escritor.write(salida)

    with pytest.raises(ArchivoNoPermitido, match="contraseña"):
        await extraer_pdf(salida.getvalue(), Configuracion(_env_file=None))


@pytest.mark.asyncio
async def test_produccion_exige_antivirus_antes_de_parsear() -> None:
    config = Configuracion(_env_file=None).model_copy(update={"entorno": Entorno.PRODUCCION})

    with pytest.raises(ProveedorExternoNoDisponible, match="exige antivirus"):
        await extraer_pdf(pdf_con_texto(), config)


@pytest.mark.asyncio
async def test_rechaza_pdf_marcado_como_infectado(monkeypatch: pytest.MonkeyPatch) -> None:
    async def infectado(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(archivos_conocimiento, "analizar_clamd", infectado)
    config = Configuracion(_env_file=None, antivirus_habilitado=True)

    with pytest.raises(archivos_conocimiento.ArchivoInfectado):
        await extraer_pdf(pdf_con_texto(), config)
