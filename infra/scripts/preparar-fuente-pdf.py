"""Genera métricas de una fuente local de confianza; no se ejecuta en la API.

Uso: uv run --no-project --with fonttools==4.66.1 python
     infra/scripts/preparar-fuente-pdf.py backend/app/modulos/documentos/fuentes/DejaVuSans.ttf
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

MAXIMO_UNICODE_BMP = 0xFFFF


def preparar(ruta: Path) -> None:
    with TTFont(ruta) as fuente:
        escala = 1000 / fuente["head"].unitsPerEm
        cmap = fuente.getBestCmap()
        if cmap is None:
            raise ValueError("La fuente no contiene un mapa Unicode.")
        metricas = {
            "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(),
            "nombre": fuente["name"].getDebugName(6),
            "bbox": [
                round(getattr(fuente["head"], c) * escala) for c in ("xMin", "yMin", "xMax", "yMax")
            ],
            "ascent": round(fuente["hhea"].ascent * escala),
            "descent": round(fuente["hhea"].descent * escala),
            "cap_height": round(
                getattr(fuente["OS/2"], "sCapHeight", fuente["glyf"][cmap[ord("H")]].yMax) * escala
            ),
            "caracteres": {
                str(cp): [fuente.getGlyphID(nombre), round(fuente["hmtx"][nombre][0] * escala)]
                for cp, nombre in sorted(cmap.items())
                if cp <= MAXIMO_UNICODE_BMP
            },
        }
    ruta.with_suffix(".json").write_text(
        json.dumps(metricas, ensure_ascii=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    preparar(Path(sys.argv[1]))
