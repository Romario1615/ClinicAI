from io import BytesIO

import pytest
from pypdf import PdfReader
from pypdf.generic import ContentStream

from app.modulos.documentos.pdf import generar_pdf
from app.nucleo.errores import DatosInvalidos


def test_pdf_paginas_unicode_y_texto_sin_operadores_inyectados() -> None:
    datos = generar_pdf(
        "Cotización de estética", ["Atención ñ á é í ó ú (test) BT /JS <script>"] * 140
    )
    pdf = PdfReader(BytesIO(datos))
    assert len(pdf.pages) == 4
    assert "Atención ñ á é í ó ú" in pdf.pages[0].extract_text()
    assert "/OpenAction" not in pdf.trailer["/Root"]
    assert "Página 4 de 4" in pdf.pages[3].extract_text()


def test_pdf_conserva_unidades_unicode_y_parrafos() -> None:
    pdf = PdfReader(
        BytesIO(
            generar_pdf(
                "Receta sintética",
                ["Unidad: μg / µg ≤ 5 ≥ 2 °C cm²", "Primera línea\nSegunda línea\n\nÚltima línea"],
            )
        )
    )
    texto = pdf.pages[0].extract_text()
    assert "μg / µg ≤ 5 ≥ 2 °C cm²" in texto
    assert "Primera línea\nSegunda línea" in texto
    fuente = pdf.pages[0]["/Resources"]["/Font"]["/F1"]
    assert "/ToUnicode" in fuente
    assert fuente["/DescendantFonts"][0]["/FontDescriptor"]["/FontFile2"].get_data()


@pytest.mark.parametrize(
    "valor, codigo",
    [
        ("😀", "1F600"),
        ("\u200d", "200D"),
        ("\u202e", "202E"),
        ("א", "05D0"),
        ("\u2028", "2028"),
        ("\u2029", "2029"),
        ("\u034f", "034F"),
        ("\ufe0f", "FE0F"),
    ],
)
def test_pdf_rechaza_glifos_no_disponibles_sin_sustituir_el_contenido(valor, codigo) -> None:
    with pytest.raises(DatosInvalidos, match=f"U\\+{codigo}"):
        generar_pdf("Documento", [f"Texto {valor}"])


def test_inyeccion_es_texto_literal_sin_acciones_ni_operadores_extra() -> None:
    ataque = ") Tj ET /JS (app.alert) /OpenAction /Launch BT <script>"
    pdf = PdfReader(BytesIO(generar_pdf("Texto sintético", [ataque])))
    assert ataque in pdf.pages[0].extract_text()
    operadores = [op for _, op in ContentStream(pdf.pages[0]["/Contents"], pdf).operations]
    assert set(operadores) <= {b"rg", b"re", b"f", b"BT", b"Tf", b"Td", b"Tj", b"ET"}
    assert operadores.count(b"BT") == operadores.count(b"ET")
    assert "/OpenAction" not in pdf.trailer["/Root"]
    assert "/AA" not in pdf.pages[0] and "/Annots" not in pdf.pages[0]
