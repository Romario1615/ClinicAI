"""Genera los logos portables desde el símbolo y la tipografía local de ClinicAI.

Desde la raíz: uv run --no-project --with fonttools==4.61.0 --with brotli==1.2.0
--with defusedxml==0.7.1 python infra/scripts/generar-logos.py.
No modifica dependencias de la aplicación.
"""

from pathlib import Path
from copy import deepcopy
from defusedxml.ElementTree import parse
from fontTools.misc import etree as ET
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen

RAIZ = Path(__file__).resolve().parents[2]
IMAGENES = RAIZ / "frontend/public/images"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
FUENTE = (
    RAIZ
    / "frontend/node_modules/@fontsource-variable/plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2"
)
simbolo = parse(IMAGENES / "clinicai-simbolo.svg", forbid_dtd=True).getroot()


def trazos(texto, peso, tamano, espaciado):
    fuente = instantiateVariableFont(TTFont(FUENTE), {"wght": peso}, inplace=False)
    glifos = fuente.getGlyphSet()
    caracteres = fuente.getBestCmap()
    escala = tamano / fuente["head"].unitsPerEm
    grupos = []
    avance = 0.0
    for letra in texto:
        glifo = glifos[caracteres[ord(letra)]]
        pluma = SVGPathPen(glifos)
        glifo.draw(pluma)
        grupos.append((letra, avance, pluma.getCommands()))
        avance += glifo.width * escala + espaciado
    return grupos, avance - espaciado


nombre, ancho = trazos("ClinicAI", 750, 68, -3.06)
descriptor, ancho_descriptor = trazos("GESTIÓN CLÍNICA CON IA", 650, 10.8, 1.15)


def texto_en_trazos(padre, partes, tamano, x, y, color, color_ia=None):
    for indice, (letra, avance, dibujo) in enumerate(partes):
        if not dibujo:
            continue
        ET.SubElement(
            padre,
            f"{{{NS}}}path",
            {
                "d": dibujo,
                "transform": f"translate({x + avance:.3f} {y}) scale({tamano / 1000:.4f} {-tamano / 1000:.4f})",
                "fill": color_ia if color_ia and indice >= 6 else color,
            },
        )


def escribir(archivo, raiz):
    (IMAGENES / archivo).write_text(
        ET.tostring(raiz, encoding="unicode", pretty_print=True), encoding="utf-8"
    )


for variante, color, color_ia, tenue in [
    ("claro", "#133F52", "#087983", "#456875"),
    ("oscuro", "#F0FCFD", "#86E2E1", "#B3D8DD"),
]:
    ancho_total = round(120 + max(ancho, ancho_descriptor) + 5)
    logo = ET.Element(
        f"{{{NS}}}svg",
        {
            "viewBox": f"0 0 {ancho_total} 128",
            "fill": "none",
            "role": "img",
            "aria-labelledby": "titulo descripcion",
        },
    )
    ET.SubElement(logo, f"{{{NS}}}title", {"id": "titulo"}).text = "ClinicAI"
    ET.SubElement(
        logo, f"{{{NS}}}desc", {"id": "descripcion"}
    ).text = "Gestión clínica con inteligencia artificial. Logotipo con C, cruz de cuidado y nodos conectados."
    icono = ET.SubElement(logo, f"{{{NS}}}g", {"transform": "translate(0 16)"})
    for hijo in simbolo:
        if hijo.tag not in {f"{{{NS}}}title", f"{{{NS}}}desc"}:
            icono.append(deepcopy(hijo))
    texto_en_trazos(logo, nombre, 68, 120, 82, color, color_ia)
    texto_en_trazos(logo, descriptor, 10.8, 122, 105, tenue)
    escribir(f"clinicai-logo-{variante}.svg", logo)
    print(f"clinicai-logo-{variante}.svg: {ancho_total} × 128, tipografía en trazos")

# Versión de una tinta: los huecos de los nodos son transparentes.
logo_mono = deepcopy(
    parse(IMAGENES / "clinicai-logo-claro.svg", forbid_dtd=True).getroot()
)
icono = logo_mono.find(f"{{{NS}}}g")
for hijo in list(icono):
    if hijo.tag in {f"{{{NS}}}defs", f"{{{NS}}}rect"}:
        icono.remove(hijo)
for elemento in logo_mono.iter():
    for propiedad in ["stroke", "fill"]:
        if propiedad in elemento.attrib and elemento.attrib[propiedad] != "none":
            elemento.set(propiedad, "#133F52")
defs = ET.SubElement(logo_mono, f"{{{NS}}}defs")
mascara = ET.SubElement(
    defs,
    f"{{{NS}}}mask",
    {
        "id": "huecos",
        "maskUnits": "userSpaceOnUse",
        "x": "0",
        "y": "0",
        "width": "96",
        "height": "96",
    },
)
ET.SubElement(mascara, f"{{{NS}}}rect", {"width": "96", "height": "96", "fill": "#fff"})
for y in [24, 72]:
    ET.SubElement(
        mascara,
        f"{{{NS}}}circle",
        {"cx": "64", "cy": str(y), "r": "3.5", "fill": "#000"},
    )
icono.set("mask", "url(#huecos)")
escribir("clinicai-logo-monocromo.svg", logo_mono)
