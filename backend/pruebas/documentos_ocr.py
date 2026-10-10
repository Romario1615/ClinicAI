"""PDF imagen sintético, sin capa de texto ni datos clínicos, para OCR real."""

from contextlib import closing
from io import BytesIO

import pypdfium2 as pdfium
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject


def pdf_escanado(*, pagina_blanca: bool = False) -> bytes:
    original = PdfWriter()
    pagina = original.add_blank_page(width=612, height=792)
    fuente = original._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    pagina[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): fuente}),
        }
    )
    texto = DecodedStreamObject()
    texto.set_data(
        b"BT /F1 32 Tf 60 700 Td (HORARIO SINTETICO) Tj 0 -60 Td (LUNES A VIERNES) Tj 0 -60 Td (08:00 A 17:00) Tj ET"
    )
    pagina[NameObject("/Contents")] = original._add_object(texto)
    salida = BytesIO()
    original.write(salida)
    with (
        pdfium.PdfDocument(salida.getvalue()) as documento,
        closing(documento[0]) as pagina_pdf,
        closing(pagina_pdf.render(scale=1, grayscale=True)) as bitmap,
    ):
        pixeles = bytes(bitmap.buffer)
        ancho, alto = bitmap.width, bitmap.height
        filas = b"".join(
            pixeles[f * bitmap.stride : f * bitmap.stride + ancho] for f in range(alto)
        )
    escritor = PdfWriter()
    imagen = DecodedStreamObject()
    imagen.set_data(filas)
    imagen.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(ancho),
            NameObject("/Height"): NumberObject(alto),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    pagina_imagen = escritor.add_blank_page(width=612, height=792)
    pagina_imagen[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Imagen"): escritor._add_object(imagen.flate_encode())}
            ),
        }
    )
    flujo = DecodedStreamObject()
    flujo.set_data(b"q 612 0 0 792 0 0 cm /Imagen Do Q")
    pagina_imagen[NameObject("/Contents")] = escritor._add_object(flujo)
    if pagina_blanca:
        escritor.add_blank_page(width=612, height=792)
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()
