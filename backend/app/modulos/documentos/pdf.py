"""PDF A4 vectorial sin HTML, JavaScript, llamadas externas ni fuentes remotas."""

from __future__ import annotations

from io import BytesIO
from textwrap import wrap

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, IndirectObject, NameObject

from app.modulos.documentos.esquemas import ZONAS


def generar_pdf(titulo: str, lineas: list[str], mapa: dict[str, str] | None = None) -> bytes:
    escritor = PdfWriter()
    fuente = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    referencia = escritor._add_object(fuente)
    filas = [
        fragmento
        for linea in [titulo, "", *lineas]
        for fragmento in (wrap(linea, 48, replace_whitespace=False) or [""])
    ]
    grupos = [filas[i : i + 42] for i in range(0, len(filas), 42)] or [[]]
    for indice, grupo in enumerate(grupos):
        pagina = escritor.add_blank_page(width=595, height=842)
        pagina[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): referencia})}
        )
        comandos = ["0.08 0.35 0.37 rg 0 755 595 87 re f", "1 1 1 rg"]

        def texto(valor: str, x: int, y: int, tamano: int = 11) -> str:
            # Hexadecimal evita cualquier interpretación como operadores PDF.
            codificado = valor.encode("cp1252", errors="replace").hex()
            return f"BT /F1 {tamano} Tf {x} {y} Td <{codificado}> Tj ET"

        cabecera = wrap(titulo, 38)[:2]
        comandos.append(texto("ClinicAI", 42, 811, 20))
        comandos.extend(texto(linea, 42, 787 - i * 16, 13) for i, linea in enumerate(cabecera))
        comandos.append("0.12 0.17 0.22 rg")
        comandos.extend(texto(fila, 42, 738 - i * 15) for i, fila in enumerate(grupo))
        comandos.extend(
            [
                "0.45 0.5 0.55 rg",
                texto(
                    f"Documento generado por ClinicAI | Página {indice + 1} de {len(grupos) + (mapa is not None)}",
                    42,
                    52,
                    9,
                ),
            ]
        )
        flujo = DecodedStreamObject()
        flujo.set_data("\n".join(comandos).encode("ascii"))
        pagina[NameObject("/Contents")] = escritor._add_object(flujo)
    if mapa is not None:
        _agregar_mapa(escritor, referencia, mapa)
    escritor.add_metadata({"/Title": titulo, "/Creator": "ClinicAI"})
    salida = BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def _agregar_mapa(escritor: PdfWriter, referencia: IndirectObject, estados: dict[str, str]) -> None:
    pagina = escritor.add_blank_page(width=595, height=842)
    pagina[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): referencia})}
    )

    def texto(valor: str, x: int, y: int, tamano: int = 9) -> str:
        return f"BT /F1 {tamano} Tf {x} {y} Td <{valor.encode('cp1252', errors='replace').hex()}> Tj ET"

    comandos = [
        "0.08 0.35 0.37 rg",
        texto("ClinicAI · Faciograma", 42, 790, 20),
        "0.87 0.94 0.94 rg 0.4 0.6 0.6 RG 1.5 w",
        "150 720 m 72 720 75 590 100 530 c 132 470 169 470 201 530 c 227 590 229 720 150 720 c B",
        "0.4 0.6 0.6 RG 109 634 m 124 645 135 645 143 634 c S 158 634 m 172 645 186 645 193 634 c S",
        "149 630 m 141 597 l 155 597 l S 129 565 m 142 552 161 552 174 565 c S",
        "0.12 0.17 0.22 rg",
        texto("D", 52, 603),
        texto("I", 242, 603),
    ]
    colores = {
        "OBSERVACION": "0.3 0.5 0.8",
        "PLANIFICADO": "0.85 0.6 0.2",
        "REALIZADO": "0.1 0.65 0.5",
    }
    for i, (codigo, (nombre, x, y)) in enumerate(ZONAS.items(), 1):
        estado = estados.get(codigo, "SIN REGISTRO")
        px, py = 50 + x * 0.65, 741 - y * 0.65
        comandos.extend(
            [
                f"{colores.get(estado, '0.65 0.7 0.7')} rg {px - 7:.2f} {py - 7:.2f} 14 14 re f",
                "0.08 0.16 0.2 rg",
                texto(str(i), int(px - 4), int(py - 3), 8),
                texto(f"{i}. {nombre}", 280, 723 - i * 22),
                texto(estado, 290, 713 - i * 22, 7),
            ]
        )
    comandos.extend(
        [
            texto("Vista frontal · Derecha/izquierda del paciente", 42, 175),
            texto("Zonas de documentación; no son puntos de inyección.", 42, 155),
            texto(
                "Consulte las observaciones y procedimientos en las páginas anteriores.", 42, 135
            ),
        ]
    )
    flujo = DecodedStreamObject()
    flujo.set_data("\n".join(comandos).encode("ascii"))
    pagina[NameObject("/Contents")] = escritor._add_object(flujo)
