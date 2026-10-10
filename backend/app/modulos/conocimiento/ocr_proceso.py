"""Proceso desechable de OCR. PDFium no comparte memoria con la API ni con otro PDF.

Entrada/salida por pipes; no escribe archivos. El padre impone el plazo total
y termina el árbol del proceso. Tesseract tiene además un plazo por página.
"""

from __future__ import annotations

import json
import math

# OCR mediante argv fijo, pipes y plazo; nunca mediante un shell.
import subprocess  # nosec B404
import sys
from contextlib import closing
from io import BytesIO
from typing import TypedDict, cast

import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject

MAXIMO_BYTES = 20 * 1024 * 1024
MAXIMO_PIXELES = 8_000_000
MAXIMO_CARACTERES = 500_000
ESCALA = 180 / 72
TIEMPO_PAGINA = 15


class TextoReconocido(TypedDict):
    contenido: str
    paginas: int
    paginas_sin_texto: list[int]


class FalloOcr(Exception):
    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


def validar_pdf(datos: bytes, maximo_paginas: int) -> int:
    """Inspección estructural anterior al parser nativo y sin interpretar acciones."""
    try:
        lector = PdfReader(BytesIO(datos), strict=True)
        if lector.is_encrypted:
            raise FalloOcr("ARCHIVO", "No se admiten PDF protegidos con contraseña.")
        paginas = len(lector.pages)
        if not 1 <= paginas <= maximo_paginas:
            raise FalloOcr("ARCHIVO", f"El OCR admite entre 1 y {maximo_paginas} páginas.")
        catalogo = cast(DictionaryObject, lector.trailer["/Root"])
        referencia_nombres = catalogo.get("/Names")
        nombres = referencia_nombres.get_object() if referencia_nombres else None
        if any(c in catalogo for c in ("/OpenAction", "/AA")) or (
            nombres and any(c in nombres for c in ("/JavaScript", "/EmbeddedFiles"))
        ):
            raise FalloOcr("ARCHIVO", "El PDF contiene acciones o adjuntos no admitidos.")
        for pagina in lector.pages:
            if "/AA" in pagina:
                raise FalloOcr("ARCHIVO", "El PDF contiene acciones no admitidas.")
            for referencia in pagina.get("/Annots", []):
                anotacion = referencia.get_object()
                if any(c in anotacion for c in ("/A", "/AA", "/FS")):
                    raise FalloOcr("ARCHIVO", "El PDF contiene anotaciones activas no admitidas.")
        return paginas
    except (PdfReadError, ValueError, OSError, KeyError, TypeError) as exc:
        raise FalloOcr("ARCHIVO", "El PDF está dañado o no se puede procesar.") from exc


def reconocer_imagen(imagen: bytes, ejecucion: str, distribucion: str) -> str:
    orden = ["tesseract", "stdin", "stdout", "-l", "spa+eng", "--psm", "3"]
    if ejecucion == "wsl":
        # `timeout` también termina el motor Linux si el padre Windows se cierra.
        orden = ["wsl.exe", "-d", distribucion, "--exec", "timeout", "15s", *orden]
    try:
        # Argumentos fijos; solo la distribución viene de configuración del servidor.
        resultado = subprocess.run(  # noqa: S603  # nosec B603
            orden,
            input=imagen,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=TIEMPO_PAGINA + 2,
            check=False,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FalloOcr(
            "MOTOR", "El motor OCR no está disponible o agotó su plazo. Puede reintentar."
        ) from exc
    if resultado.returncode != 0:
        raise FalloOcr("MOTOR", "Revise el motor OCR y sus idiomas español e inglés.")
    return resultado.stdout.decode("utf-8", errors="replace").strip()


def reconocer_pdf(
    datos: bytes, maximo_paginas: int, ejecucion: str, distribucion: str
) -> TextoReconocido:
    paginas = validar_pdf(datos, maximo_paginas)
    textos: list[str] = []
    sin_texto: list[int] = []
    cantidad = 0
    with pdfium.PdfDocument(datos) as documento:
        if len(documento) != paginas:
            raise FalloOcr("ARCHIVO", "No se pudo verificar el número de páginas del PDF.")
        for indice in range(paginas):
            with closing(documento[indice]) as pagina:
                ancho, alto = pagina.get_size()
                if (
                    not math.isfinite(ancho * alto)
                    or ancho <= 0
                    or alto <= 0
                    or math.ceil(ancho * ESCALA) * math.ceil(alto * ESCALA) > MAXIMO_PIXELES
                ):
                    raise FalloOcr("ARCHIVO", "Una página supera el tamaño admitido para OCR.")
                with closing(
                    pagina.render(scale=ESCALA, grayscale=True, draw_annots=False)
                ) as bitmap:
                    # PGM sin Pillow/NumPy. Quita el relleno de cada fila del bitmap.
                    pixeles = bytes(bitmap.buffer)
                    filas = b"".join(
                        pixeles[fila * bitmap.stride : fila * bitmap.stride + bitmap.width]
                        for fila in range(bitmap.height)
                    )
                    imagen = f"P5\n{bitmap.width} {bitmap.height}\n255\n".encode() + filas
            texto = reconocer_imagen(imagen, ejecucion, distribucion)
            cantidad += len(texto) + 2
            if cantidad > MAXIMO_CARACTERES:
                raise FalloOcr("TAMANO", "El texto reconocido supera 500 000 caracteres.")
            if not texto:
                sin_texto.append(indice + 1)
            textos.append(texto)
    contenido = "\n\n".join(textos).strip()
    if not contenido:
        raise FalloOcr("ARCHIVO", "No se reconoció texto. Revise la calidad del escaneo.")
    return {"contenido": contenido, "paginas": paginas, "paginas_sin_texto": sin_texto}


def main() -> None:
    # Linux: límite de memoria virtual y CPU, adicional al plazo del padre.
    # Windows: límites de bytes/píxeles y árbol de procesos, sin RLIMIT_AS.
    if sys.platform != "win32":
        import resource  # noqa: PLC0415 — este módulo solo existe en Unix.

        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    respuesta: TextoReconocido | dict[str, str]
    try:
        datos = sys.stdin.buffer.read(MAXIMO_BYTES + 1)
        if len(datos) > MAXIMO_BYTES:
            raise FalloOcr("TAMANO", "El OCR admite archivos de hasta 20 MB.")
        respuesta = reconocer_pdf(datos, int(sys.argv[1]), sys.argv[2], sys.argv[3])
    except FalloOcr as exc:
        respuesta = {"error": exc.codigo, "mensaje": str(exc)}
    except Exception:
        # Nunca devolver trazas, texto del documento o mensajes del parser nativo.
        respuesta = {"error": "ARCHIVO", "mensaje": "No se pudo procesar el PDF mediante OCR."}
    sys.stdout.buffer.write(json.dumps(respuesta, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
