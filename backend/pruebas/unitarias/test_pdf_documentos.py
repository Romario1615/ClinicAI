from io import BytesIO

from pypdf import PdfReader

from app.modulos.documentos.pdf import generar_pdf


def test_pdf_paginas_unicode_y_texto_sin_operadores_inyectados() -> None:
    datos = generar_pdf(
        "Cotización de estética", ["Atención ñ á é í ó ú (test) BT /JS <script>"] * 140
    )
    pdf = PdfReader(BytesIO(datos))
    assert len(pdf.pages) == 4
    assert "Atención ñ á é í ó ú" in pdf.pages[0].extract_text()
    assert "/OpenAction" not in pdf.trailer["/Root"]
    assert "Página 4 de 4" in pdf.pages[3].extract_text()
