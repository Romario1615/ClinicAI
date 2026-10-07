"""Extracción de texto de documentos Word (.docx) para la base de conocimiento.

Se construyen .docx mínimos en memoria (un ZIP con `word/document.xml`): no
hace falta Word ni una librería extra para probar lo que importa, que es el
texto extraído y el rechazo de paquetes peligrosos.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app.modulos.conocimiento.archivos import (
    _extraer_texto_docx,
    extraer_documento,
)
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import ArchivoNoPermitido

pytestmark = [pytest.mark.unitaria]

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(cuerpo: str, *, extra: dict[str, bytes] | None = None, cabecera: str = "") -> bytes:
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>{cabecera}'
        f'<w:document xmlns:w="{W}"><w:body>{cuerpo}</w:body></w:document>'
    )
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("[Content_Types].xml", "<Types/>")
        paquete.writestr("word/document.xml", xml)
        for nombre, datos in (extra or {}).items():
            paquete.writestr(nombre, datos)
    return salida.getvalue()


def _p(texto: str) -> str:
    return f"<w:p><w:r><w:t>{texto}</w:t></w:r></w:p>"


def test_extrae_los_parrafos_en_orden() -> None:
    datos = _docx(_p("Horario sintético.") + _p("") + _p("Los sábados de 8:00 a 13:00."))
    assert _extraer_texto_docx(datos) == "Horario sintético.\n\nLos sábados de 8:00 a 13:00."


def test_rechaza_macros() -> None:
    datos = _docx(_p("Texto"), extra={"word/vbaProject.bin": b"\x00macro"})
    with pytest.raises(ArchivoNoPermitido, match="macros"):
        _extraer_texto_docx(datos)


def test_rechaza_dtd_y_entidades() -> None:
    cabecera = '<!DOCTYPE x [<!ENTITY a "aaaa">]>'
    with pytest.raises(ArchivoNoPermitido, match="declaraciones"):
        _extraer_texto_docx(_docx(_p("&a;"), cabecera=cabecera))


def test_rechaza_dtd_y_entidades_en_xml_utf16() -> None:
    """La detección de bytes UTF-8 no debe ser la única barrera XXE."""
    xml = (
        f'<?xml version="1.0" encoding="UTF-16"?>'
        f'<!DOCTYPE w:document [<!ENTITY a "contenido externo">]>'
        f'<w:document xmlns:w="{W}"><w:body>{_p("&a;")}</w:body></w:document>'
    ).encode("utf-16")
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("[Content_Types].xml", "<Types/>")
        paquete.writestr("word/document.xml", xml)

    with pytest.raises(ArchivoNoPermitido, match="XML no seguro"):
        _extraer_texto_docx(salida.getvalue())


def test_rechaza_una_bomba_de_compresion() -> None:
    datos = _docx(_p("a" * 3_000_000))
    with pytest.raises(ArchivoNoPermitido, match="demasiado grande"):
        _extraer_texto_docx(datos)


def test_rechaza_un_zip_que_no_es_word_y_un_word_vacio() -> None:
    salida = BytesIO()
    with zipfile.ZipFile(salida, "w") as paquete:
        paquete.writestr("otra.txt", "hola")
    with pytest.raises(ArchivoNoPermitido, match="no es un documento Word"):
        _extraer_texto_docx(salida.getvalue())
    with pytest.raises(ArchivoNoPermitido, match="no contiene texto"):
        _extraer_texto_docx(_docx(_p("")))


async def test_el_formato_se_decide_por_el_contenido() -> None:
    configuracion = Configuracion(_env_file=None, antivirus_habilitado=False)  # type: ignore[call-arg]
    texto, tipo = await extraer_documento(_docx(_p("Protocolo sintético.")), configuracion)
    assert (texto, tipo) == ("Protocolo sintético.", "DOCX")
    with pytest.raises(ArchivoNoPermitido, match="Formato no admitido"):
        await extraer_documento(b"texto plano disfrazado de pdf", configuracion)
