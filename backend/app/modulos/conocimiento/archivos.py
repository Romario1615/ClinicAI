"""Validación, análisis y extracción de documentos PDF y Word (.docx) para el RAG."""

from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

import filetype
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.nucleo.archivos import ArchivoInfectado, analizar_clamd
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    ArchivoNoPermitido,
    ProveedorExternoNoDisponible,
)
from app.nucleo.registro import obtener_logger

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element as _ElementoXML

MAXIMO_PAGINAS_PDF = 200
MAXIMO_CARACTERES_EXTRAIDOS = 500_000
ACCIONES_PDF_ACTIVAS = frozenset({"/OpenAction", "/AA"})
# Word: el texto vive en `word/document.xml` dentro de un ZIP.
DOCX_DOCUMENTO = "word/document.xml"
MAXIMO_XML_DOCX = 20 * 1024 * 1024
MAXIMA_COMPRESION_DOCX = 100
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
logger = obtener_logger(__name__)


async def _exigir_antivirus(datos: bytes, configuracion: Configuracion) -> None:
    if configuracion.antivirus_habilitado:
        if not await analizar_clamd(
            datos, host=configuracion.clamav_host, puerto=configuracion.clamav_puerto
        ):
            raise ArchivoInfectado("El antivirus rechazó el archivo.")
        return
    if configuracion.entorno.es_produccion:
        raise ProveedorExternoNoDisponible(
            "La carga de documentos exige antivirus en producción y no está habilitado."
        )
    logger.warning("conocimiento.pdf.sin_antivirus", entorno=configuracion.entorno.value)


def _extraer_texto_pdf(datos: bytes) -> str:
    try:
        lector = PdfReader(BytesIO(datos), strict=True)
        if lector.is_encrypted:
            raise ArchivoNoPermitido("No se admiten PDF protegidos con contraseña.")
        if len(lector.pages) > MAXIMO_PAGINAS_PDF:
            raise ArchivoNoPermitido(
                f"El documento supera el máximo de {MAXIMO_PAGINAS_PDF} páginas."
            )

        catalogo = lector.trailer.get("/Root")
        if catalogo and any(clave in catalogo for clave in ACCIONES_PDF_ACTIVAS):
            raise ArchivoNoPermitido("El PDF contiene acciones activas y no se puede procesar.")
        nombres = catalogo.get("/Names") if catalogo else None
        if nombres and any(clave in nombres for clave in ("/JavaScript", "/EmbeddedFiles")):
            raise ArchivoNoPermitido("El PDF contiene contenido activo y no se puede procesar.")

        textos: list[str] = []
        cantidad = 0
        for pagina in lector.pages:
            texto = pagina.extract_text() or ""
            cantidad += len(texto)
            if cantidad > MAXIMO_CARACTERES_EXTRAIDOS:
                raise ArchivoDemasiadoGrande(
                    "El texto extraído supera el máximo de 500 000 caracteres."
                )
            if texto.strip():
                textos.append(texto)
    except (ArchivoNoPermitido, ArchivoDemasiadoGrande):
        raise
    except (PdfReadError, ValueError, OSError, KeyError) as exc:
        raise ArchivoNoPermitido("El PDF está dañado o no se puede extraer.") from exc

    contenido = "\n\n".join(textos).strip()
    if not contenido:
        raise ArchivoNoPermitido(
            "El PDF no contiene texto extraíble. Los documentos escaneados requieren OCR."
        )
    return contenido


def _leer_xml_docx(datos: bytes) -> bytes:
    """`word/document.xml` de un .docx, con las defensas del paquete ZIP.

    Miembro de tamaño acotado y relación de compresión razonable (bomba ZIP) y
    sin macros (.docm renombrado). Las imágenes y objetos incrustados se ignoran.
    """
    try:
        with zipfile.ZipFile(BytesIO(datos)) as paquete:
            nombres = set(paquete.namelist())
            if DOCX_DOCUMENTO not in nombres or "[Content_Types].xml" not in nombres:
                raise ArchivoNoPermitido("El archivo no es un documento Word (.docx) válido.")
            if any(n.lower().endswith("vbaproject.bin") for n in nombres):
                raise ArchivoNoPermitido("El documento contiene macros y no se puede procesar.")
            info = paquete.getinfo(DOCX_DOCUMENTO)
            if (
                info.file_size > MAXIMO_XML_DOCX
                or info.file_size > max(info.compress_size, 1) * MAXIMA_COMPRESION_DOCX
            ):
                raise ArchivoNoPermitido("El documento Word es demasiado grande para procesarlo.")
            return paquete.read(DOCX_DOCUMENTO)
    except zipfile.BadZipFile as exc:
        raise ArchivoNoPermitido("El documento Word está dañado o no se puede abrir.") from exc


def _texto_parrafo(parrafo: _ElementoXML) -> str:
    partes: list[str] = []
    for nodo in parrafo.iter():
        if nodo.tag == f"{_W}t" and nodo.text:
            partes.append(nodo.text)
        elif nodo.tag == f"{_W}tab":
            partes.append("\t")
        elif nodo.tag in (f"{_W}br", f"{_W}cr"):
            partes.append("\n")
    return "".join(partes).strip()


def _extraer_texto_docx(datos: bytes) -> str:
    """Texto de un .docx, párrafo a párrafo, sin ejecutar ni conservar nada.

    Además de las defensas del paquete, el XML no puede declarar DTD ni
    entidades (bomba XML / XXE).
    """
    xml = _leer_xml_docx(datos)
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ArchivoNoPermitido("El documento Word contiene declaraciones no admitidas.")
    try:
        raiz = ElementTree.fromstring(xml)
    except (DefusedXmlException, ElementTree.ParseError) as exc:
        raise ArchivoNoPermitido(
            "El documento Word contiene XML no seguro o no se puede extraer."
        ) from exc

    parrafos: list[str] = []
    cantidad = 0
    for parrafo in raiz.iter(f"{_W}p"):
        texto = _texto_parrafo(parrafo)
        if texto:
            cantidad += len(texto)
            if cantidad > MAXIMO_CARACTERES_EXTRAIDOS:
                raise ArchivoDemasiadoGrande(
                    "El texto extraído supera el máximo de 500 000 caracteres."
                )
            parrafos.append(texto)
    contenido = "\n\n".join(parrafos).strip()
    if not contenido:
        raise ArchivoNoPermitido("El documento Word no contiene texto.")
    return contenido


def _validar_tamano(datos: bytes, configuracion: Configuracion) -> None:
    if len(datos) > configuracion.max_tamano_archivo_bytes:
        raise ArchivoDemasiadoGrande(
            f"El archivo supera el límite de {configuracion.max_tamano_archivo_mb} MB."
        )
    if not datos:
        raise ArchivoNoPermitido("El archivo está vacío.")


async def extraer_docx(datos: bytes, configuracion: Configuracion) -> str:
    """Analiza y extrae el texto de un .docx sin conservar ni servir el archivo."""
    _validar_tamano(datos, configuracion)
    if not datos.startswith(b"PK\x03\x04"):
        raise ArchivoNoPermitido("El contenido no es un documento Word (.docx) válido.")
    await _exigir_antivirus(datos, configuracion)
    return await asyncio.to_thread(_extraer_texto_docx, datos)


async def extraer_documento(datos: bytes, configuracion: Configuracion) -> tuple[str, str]:
    """PDF o Word según el contenido real, no la extensión. Devuelve (texto, tipo)."""
    if datos.startswith(b"%PDF-"):
        return await extraer_pdf(datos, configuracion), "PDF"
    if datos.startswith(b"PK\x03\x04"):
        return await extraer_docx(datos, configuracion), "DOCX"
    _validar_tamano(datos, configuracion)
    raise ArchivoNoPermitido("Formato no admitido. Suba un PDF o un documento Word (.docx).")


async def extraer_pdf(datos: bytes, configuracion: Configuracion) -> str:
    """Analiza y extrae texto de un PDF sin conservar ni servir el archivo.

    En producción el análisis antivirus es obligatorio. En desarrollo se
    permite trabajar sin ClamAV, como con las imágenes, y esa limitación queda
    en el registro; la extracción nunca interpreta JavaScript del documento.
    """
    maximo_bytes = configuracion.max_tamano_archivo_bytes
    if len(datos) > maximo_bytes:
        raise ArchivoDemasiadoGrande(
            f"El archivo supera el límite de {configuracion.max_tamano_archivo_mb} MB."
        )
    if not datos:
        raise ArchivoNoPermitido("El archivo está vacío.")

    detectado = filetype.guess(datos)
    if not datos.startswith(b"%PDF-") or detectado is None or detectado.mime != "application/pdf":
        raise ArchivoNoPermitido("El contenido no es un documento PDF válido.")

    await _exigir_antivirus(datos, configuracion)
    return await asyncio.to_thread(_extraer_texto_pdf, datos)


__all__ = [
    "MAXIMO_CARACTERES_EXTRAIDOS",
    "MAXIMO_PAGINAS_PDF",
    "extraer_documento",
    "extraer_docx",
    "extraer_pdf",
]
