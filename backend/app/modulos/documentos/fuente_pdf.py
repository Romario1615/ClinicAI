"""Fuente Unicode incorporada: solo archivos propios, sin contenido de pacientes en caché."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from unicodedata import bidirectional, category, normalize

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from app.nucleo.errores import DatosInvalidos


@dataclass(frozen=True)
class FuentePdf:
    datos: bytes
    nombre: str
    bbox: tuple[int, ...]
    ascent: int
    descent: int
    cap_height: int
    caracteres: dict[int, tuple[int, int]]

    def normalizar(self, texto: str) -> str:
        texto = normalize("NFC", texto.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4))
        faltantes = sorted(
            {
                ord(c)
                for c in texto
                if c != "\n"
                and (
                    ord(c) not in self.caracteres
                    or category(c).startswith("M")
                    or category(c) in {"Cc", "Cf", "Zl", "Zp"}
                    or bidirectional(c) in {"R", "AL", "AN"}
                )
            }
        )
        if faltantes:
            codigos = ", ".join(f"U+{c:04X}" for c in faltantes[:5])
            raise DatosInvalidos(
                f"El PDF no puede representar estos caracteres: {codigos}. "
                "Revise el texto del documento con el profesional antes de exportarlo."
            )
        return texto

    def ancho(self, texto: str, tamano: int) -> float:
        return sum(self.caracteres[ord(c)][1] for c in texto) * tamano / 1000

    def filas(self, texto: str, ancho: int = 511, tamano: int = 11) -> list[str]:
        resultado = []
        for parrafo in self.normalizar(texto).split("\n"):
            fila = ""
            for c in parrafo:
                if fila and self.ancho(fila + c, tamano) > ancho:
                    posicion = fila.rfind(" ")
                    if posicion > 0:
                        resultado.append(fila[:posicion].rstrip())
                        fila = fila[posicion + 1 :]
                    else:
                        resultado.append(fila.rstrip())
                        fila = ""
                fila += c
            resultado.append(fila.rstrip())
        return resultado


@cache
def fuente_pdf() -> FuentePdf:
    directorio = Path(__file__).with_name("fuentes")
    datos = (directorio / "DejaVuSans.ttf").read_bytes()
    metricas = json.loads((directorio / "DejaVuSans.json").read_text(encoding="utf-8"))
    if hashlib.sha256(datos).hexdigest() != metricas["sha256"]:
        raise RuntimeError("La fuente PDF no coincide con sus métricas de distribución.")
    return FuentePdf(
        datos,
        metricas["nombre"],
        tuple(metricas["bbox"]),
        metricas["ascent"],
        metricas["descent"],
        metricas["cap_height"],
        {int(cp): (gid, ancho) for cp, (gid, ancho) in metricas["caracteres"].items()},
    )


def _flujo(escritor: PdfWriter, datos: bytes, longitud: bool = False) -> IndirectObject:
    flujo = DecodedStreamObject()
    flujo.set_data(datos)
    if longitud:
        flujo[NameObject("/Length1")] = NumberObject(len(datos))
    return escritor._add_object(flujo.flate_encode())


def incorporar_fuente(escritor: PdfWriter) -> IndirectObject:
    fuente = fuente_pdf()
    descriptor = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/FontDescriptor"),
            NameObject("/FontName"): NameObject("/" + fuente.nombre),
            NameObject("/Flags"): NumberObject(32),
            NameObject("/FontBBox"): ArrayObject([NumberObject(v) for v in fuente.bbox]),
            NameObject("/ItalicAngle"): NumberObject(0),
            NameObject("/Ascent"): NumberObject(fuente.ascent),
            NameObject("/Descent"): NumberObject(fuente.descent),
            NameObject("/CapHeight"): NumberObject(fuente.cap_height),
            NameObject("/StemV"): NumberObject(80),
            NameObject("/FontFile2"): _flujo(escritor, fuente.datos, longitud=True),
        }
    )
    glifos = bytearray(65536 * 2)
    anchos = ArrayObject()
    for cp, (gid, ancho) in fuente.caracteres.items():
        glifos[cp * 2 : cp * 2 + 2] = gid.to_bytes(2, "big")
        anchos.extend([NumberObject(cp), ArrayObject([NumberObject(ancho)])])
    descendiente = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/CIDFontType2"),
            NameObject("/BaseFont"): NameObject("/" + fuente.nombre),
            NameObject("/CIDSystemInfo"): DictionaryObject(
                {
                    NameObject("/Registry"): TextStringObject("Adobe"),
                    NameObject("/Ordering"): TextStringObject("Identity"),
                    NameObject("/Supplement"): NumberObject(0),
                }
            ),
            NameObject("/FontDescriptor"): escritor._add_object(descriptor),
            NameObject("/CIDToGIDMap"): _flujo(escritor, bytes(glifos)),
            NameObject("/W"): anchos,
        }
    )
    cmap = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /ClinicAI-Unicode def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    caracteres = list(fuente.caracteres)
    for indice in range(0, len(caracteres), 100):
        grupo = caracteres[indice : indice + 100]
        cmap.extend(
            [f"{len(grupo)} beginbfchar", *(f"<{cp:04X}> <{cp:04X}>" for cp in grupo), "endbfchar"]
        )
    cmap.extend(["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"])
    return escritor._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type0"),
                NameObject("/BaseFont"): NameObject("/" + fuente.nombre),
                NameObject("/Encoding"): NameObject("/Identity-H"),
                NameObject("/DescendantFonts"): ArrayObject([escritor._add_object(descendiente)]),
                NameObject("/ToUnicode"): _flujo(escritor, "\n".join(cmap).encode("ascii")),
            }
        )
    )


def texto_pdf(valor: str, x: int, y: int, tamano: int = 11) -> str:
    # El hexadecimal UTF-16 evita interpretar datos como operadores PDF.
    valor = fuente_pdf().normalizar(valor)
    return f"BT /F1 {tamano} Tf {x} {y} Td <{valor.encode('utf-16-be').hex()}> Tj ET"
