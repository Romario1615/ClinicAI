"""Validacion y saneamiento de imagenes subidas.

Tres controles, en este orden
-----------------------------
1. **Tamano**, antes de mirar nada mas: una subida de 2 GB no se analiza.
2. **Tipo real por contenido** (`filetype`, firma magica), nunca por la
   extension ni por el `Content-Type` que manda el navegador. Un `.jpg` que
   en realidad es un HTML con script se rechaza aqui.
3. **Metadatos fuera.** Una foto de movil lleva EXIF con coordenadas GPS,
   modelo de telefono y fecha. En una foto intraoral, la ubicacion es la casa
   del paciente o la clinica: dato personal que nadie pidio guardar. Se
   eliminan EXIF, XMP, IPTC y comentarios.

La orientacion se conserva
--------------------------
El movil guarda la foto «de lado» y anota en EXIF como girarla. Quitar el
EXIF entero haria que la mitad de las fotos intraorales se vieran rotadas.
En JPEG se reescribe un EXIF minimo con **solo** la etiqueta de orientacion.

Por que sin Pillow
------------------
Pillow esta fuera del arbol base a proposito (vulnerabilidades de codecs,
ver `pyproject.toml` y la limitacion E-12). Aqui no se decodifica la imagen:
se recorren sus segmentos y se copian los que no son metadatos. Es mas
estrecho y no ejecuta ningun codec sobre datos que manda un tercero.

Antivirus
---------
Con `ANTIVIRUS_HABILITADO` se analiza con clamd (protocolo INSTREAM). Sin el,
en produccion la carga se rechaza; en desarrollo se registra como
`NO_DISPONIBLE` y queda declarado.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import struct
from dataclasses import dataclass
from enum import StrEnum

import filetype
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject

from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    ArchivoNoPermitido,
    ProveedorExternoNoDisponible,
)

TIPOS_IMAGEN: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})


class ResultadoAntivirus(StrEnum):
    LIMPIO = "LIMPIO"
    NO_DISPONIBLE = "NO_DISPONIBLE"


@dataclass(frozen=True, slots=True)
class ImagenSaneada:
    datos: bytes
    tipo_mime: str
    sha256: str
    antivirus: ResultadoAntivirus


class ArchivoInfectado(ArchivoNoPermitido):
    codigo = "ARCHIVO_INFECTADO"
    estado_http = 422


# ---------------------------------------------------------------------------
#  JPEG
# ---------------------------------------------------------------------------
_APP1 = 0xE1  # EXIF / XMP
_APP13 = 0xED  # IPTC / Photoshop
_COM = 0xFE  # comentario
_SOS = 0xDA
_ETIQUETA_ORIENTACION = 0x0112
# Prefijo Exif (6 bytes) + cabecera TIFF (8): lo minimo para leer el IFD0.
_LONGITUD_MINIMA_EXIF = 14


def _orientacion_exif(carga: bytes) -> int | None:
    """Lee la etiqueta de orientacion del IFD0 de un segmento EXIF."""
    if not carga.startswith(b"Exif\x00\x00") or len(carga) < _LONGITUD_MINIMA_EXIF:
        return None
    tiff = carga[6:]
    orden = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if orden is None:
        return None
    try:
        (desplazamiento,) = struct.unpack(f"{orden}I", tiff[4:8])
        (entradas,) = struct.unpack(f"{orden}H", tiff[desplazamiento : desplazamiento + 2])
        for indice in range(min(entradas, 512)):
            inicio = desplazamiento + 2 + indice * 12
            etiqueta, tipo, _cuenta = struct.unpack(f"{orden}HHI", tiff[inicio : inicio + 8])
            if etiqueta == _ETIQUETA_ORIENTACION and tipo == 3:  # noqa: PLR2004 - SHORT
                (valor,) = struct.unpack(f"{orden}H", tiff[inicio + 8 : inicio + 10])
                return valor if 1 <= valor <= 8 else None  # noqa: PLR2004
    except struct.error:
        return None
    return None


def _exif_solo_orientacion(orientacion: int) -> bytes:
    """Segmento APP1 con un EXIF minimo: una sola etiqueta, la orientacion."""
    tiff = (
        b"MM\x00\x2a\x00\x00\x00\x08"  # cabecera big-endian, IFD0 en 8
        + struct.pack(">H", 1)
        + struct.pack(">HHIHH", _ETIQUETA_ORIENTACION, 3, 1, orientacion, 0)
        + struct.pack(">I", 0)  # sin IFD siguiente
    )
    carga = b"Exif\x00\x00" + tiff
    return b"\xff" + bytes([_APP1]) + struct.pack(">H", len(carga) + 2) + carga


def limpiar_jpeg(datos: bytes) -> bytes:
    if not datos.startswith(b"\xff\xd8"):
        raise ArchivoNoPermitido("El archivo JPEG esta danado.")
    salida = bytearray(b"\xff\xd8")
    orientacion: int | None = None
    posicion = 2
    while posicion < len(datos):
        if datos[posicion] != 0xFF:  # noqa: PLR2004
            raise ArchivoNoPermitido("El archivo JPEG esta danado.")
        marcador = datos[posicion + 1]
        if marcador == _SOS:
            # A partir de aqui son datos de imagen: se copian tal cual.
            if orientacion and orientacion != 1:
                # JFIF exige que APP0 vaya primero: el EXIF va despues.
                insercion = 2
                if salida[2:4] == b"\xff\xe0":
                    (largo_app0,) = struct.unpack(">H", salida[4:6])
                    insercion = 4 + largo_app0
                salida[insercion:insercion] = _exif_solo_orientacion(orientacion)
            salida += datos[posicion:]
            return bytes(salida)
        if 0xD0 <= marcador <= 0xD7 or marcador == 0x01:  # noqa: PLR2004 - sin longitud
            salida += datos[posicion : posicion + 2]
            posicion += 2
            continue
        (longitud,) = struct.unpack(">H", datos[posicion + 2 : posicion + 4])
        segmento = datos[posicion : posicion + 2 + longitud]
        if len(segmento) < 2 + longitud:
            raise ArchivoNoPermitido("El archivo JPEG esta truncado.")
        if marcador == _APP1:
            orientacion = orientacion or _orientacion_exif(segmento[4:])
        elif marcador not in (_APP13, _COM):
            salida += segmento
        posicion += 2 + longitud
    raise ArchivoNoPermitido("El archivo JPEG no contiene datos de imagen.")


# ---------------------------------------------------------------------------
#  PNG
# ---------------------------------------------------------------------------
_PNG_FIRMA = b"\x89PNG\r\n\x1a\n"
_PNG_DESCARTAR = frozenset({b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"})


def limpiar_png(datos: bytes) -> bytes:
    if not datos.startswith(_PNG_FIRMA):
        raise ArchivoNoPermitido("El archivo PNG esta danado.")
    salida = bytearray(_PNG_FIRMA)
    posicion = len(_PNG_FIRMA)
    while posicion + 8 <= len(datos):
        (longitud,) = struct.unpack(">I", datos[posicion : posicion + 4])
        tipo = datos[posicion + 4 : posicion + 8]
        fin = posicion + 12 + longitud
        if fin > len(datos):
            raise ArchivoNoPermitido("El archivo PNG esta truncado.")
        if tipo not in _PNG_DESCARTAR:
            salida += datos[posicion:fin]
        posicion = fin
        if tipo == b"IEND":
            return bytes(salida)
    raise ArchivoNoPermitido("El archivo PNG esta incompleto.")


# ---------------------------------------------------------------------------
#  WebP
# ---------------------------------------------------------------------------
_WEBP_DESCARTAR = frozenset({b"EXIF", b"XMP "})
_VP8X_EXIF = 0x08
_VP8X_XMP = 0x04


def limpiar_webp(datos: bytes) -> bytes:
    if len(datos) < 12 or datos[:4] != b"RIFF" or datos[8:12] != b"WEBP":  # noqa: PLR2004
        raise ArchivoNoPermitido("El archivo WebP esta danado.")
    trozos = bytearray()
    posicion = 12
    while posicion + 8 <= len(datos):
        tipo = datos[posicion : posicion + 4]
        (longitud,) = struct.unpack("<I", datos[posicion + 4 : posicion + 8])
        fin = posicion + 8 + longitud + (longitud % 2)
        if posicion + 8 + longitud > len(datos):
            raise ArchivoNoPermitido("El archivo WebP esta truncado.")
        trozo = bytearray(datos[posicion:fin])
        if tipo == b"VP8X" and len(trozo) > 8:  # noqa: PLR2004
            trozo[8] &= ~(_VP8X_EXIF | _VP8X_XMP) & 0xFF
        if tipo not in _WEBP_DESCARTAR:
            trozos += trozo
        posicion = fin
    return b"RIFF" + struct.pack("<I", len(trozos) + 4) + b"WEBP" + bytes(trozos)


_LIMPIADORES = {
    "image/jpeg": limpiar_jpeg,
    "image/png": limpiar_png,
    "image/webp": limpiar_webp,
}


@dataclass(frozen=True, slots=True)
class ComprobanteSaneado:
    datos: bytes
    tipo_mime: str
    sha256: str
    antivirus: ResultadoAntivirus


def _catalogo_pdf(lector: PdfReader) -> DictionaryObject:
    raiz = lector.trailer["/Root"].get_object()
    if not isinstance(raiz, DictionaryObject):
        raise ArchivoNoPermitido("El PDF tiene un catálogo raíz inválido.")
    return raiz


def _validar_pdf_comprobante(datos: bytes) -> None:
    """Comprueba estructura acotada y rechaza acciones ejecutables o adjuntos."""
    if not datos.startswith(b"%PDF-"):
        raise ArchivoNoPermitido("El contenido no es un documento PDF válido.")
    try:
        lector = PdfReader(io.BytesIO(datos), strict=True)
        if lector.is_encrypted:
            raise ArchivoNoPermitido("No se admiten comprobantes PDF protegidos con contraseña.")
        if not lector.pages or len(lector.pages) > 20:  # noqa: PLR2004
            raise ArchivoNoPermitido("El PDF debe tener entre 1 y 20 páginas.")
        raiz = _catalogo_pdf(lector)
        if any(clave in raiz for clave in ("/OpenAction", "/AA", "/JavaScript", "/JS")):
            raise ArchivoNoPermitido("El PDF contiene acciones activas y no se puede aceptar.")
        nombres = raiz.get("/Names")
        if nombres:
            catalogo_nombres = nombres.get_object()
            if "/JavaScript" in catalogo_nombres:
                raise ArchivoNoPermitido("El PDF contiene JavaScript y no se puede aceptar.")
            if "/EmbeddedFiles" in catalogo_nombres:
                raise ArchivoNoPermitido("El PDF contiene archivos adjuntos y no se puede aceptar.")
        for pagina in lector.pages:
            for anotacion in pagina.get("/Annots", []):
                objeto = anotacion.get_object()
                accion = objeto.get("/A")
                if "/AA" in objeto or (
                    accion and accion.get_object().get("/S") in {"/JavaScript", "/Launch"}
                ):
                    raise ArchivoNoPermitido(
                        "El PDF contiene acciones activas y no se puede aceptar."
                    )
    except ArchivoNoPermitido:
        raise
    except (PdfReadError, KeyError, ValueError, TypeError, IndexError) as exc:
        raise ArchivoNoPermitido("El PDF está dañado o no se puede validar.") from exc


async def sanear_comprobante(datos: bytes, configuracion: Configuracion) -> ComprobanteSaneado:
    """Acepta PDF o imagen raster, valida contenido, analiza virus y calcula hash."""
    maximo = configuracion.max_tamano_archivo_bytes
    if len(datos) > maximo:
        raise ArchivoDemasiadoGrande(
            f"El comprobante supera {configuracion.max_tamano_archivo_mb} MB."
        )
    if not datos:
        raise ArchivoNoPermitido("El archivo está vacío.")
    detectado = filetype.guess(datos)
    tipo = detectado.mime if detectado else None
    if tipo in TIPOS_IMAGEN:
        imagen = await sanear_imagen(datos, configuracion)
        return ComprobanteSaneado(imagen.datos, imagen.tipo_mime, imagen.sha256, imagen.antivirus)
    if tipo != "application/pdf":
        raise ArchivoNoPermitido("Solo se admiten comprobantes PDF, JPEG, PNG o WebP.")

    _validar_pdf_comprobante(datos)
    if configuracion.antivirus_habilitado:
        if not await analizar_clamd(
            datos, host=configuracion.clamav_host, puerto=configuracion.clamav_puerto
        ):
            raise ArchivoInfectado("El antivirus rechazó el comprobante.")
        antivirus = ResultadoAntivirus.LIMPIO
    elif configuracion.entorno.es_produccion:
        raise ProveedorExternoNoDisponible(
            "La carga de comprobantes exige antivirus en producción y no está habilitado."
        )
    else:
        antivirus = ResultadoAntivirus.NO_DISPONIBLE
    return ComprobanteSaneado(datos, tipo, hashlib.sha256(datos).hexdigest(), antivirus)


# ---------------------------------------------------------------------------
#  Antivirus
# ---------------------------------------------------------------------------
async def analizar_clamd(datos: bytes, *, host: str, puerto: int) -> bool:
    """Cierto si clamd no encuentra nada. Protocolo INSTREAM."""
    try:
        lector, escritor = await asyncio.wait_for(asyncio.open_connection(host, puerto), timeout=5)
    except (OSError, TimeoutError) as exc:
        raise ProveedorExternoNoDisponible("El antivirus no esta disponible.") from exc
    try:
        escritor.write(b"zINSTREAM\x00")
        for inicio in range(0, len(datos), 65536):
            bloque = datos[inicio : inicio + 65536]
            escritor.write(struct.pack(">I", len(bloque)) + bloque)
        escritor.write(struct.pack(">I", 0))
        await escritor.drain()
        respuesta = await asyncio.wait_for(lector.read(4096), timeout=30)
    finally:
        escritor.close()
    return respuesta.rstrip(b"\x00").endswith(b"OK")


# ---------------------------------------------------------------------------
#  Punto de entrada
# ---------------------------------------------------------------------------
async def sanear_imagen(datos: bytes, configuracion: Configuracion) -> ImagenSaneada:
    """Valida, limpia y analiza una imagen. Lanza un error de dominio si no sirve."""
    maximo = configuracion.max_tamano_archivo_mb * 1024 * 1024
    if len(datos) > maximo:
        raise ArchivoDemasiadoGrande(f"La imagen supera {configuracion.max_tamano_archivo_mb} MB.")
    if not datos:
        raise ArchivoNoPermitido("El archivo esta vacio.")

    detectado = filetype.guess(datos)
    tipo = detectado.mime if detectado else None
    if tipo not in TIPOS_IMAGEN:
        raise ArchivoNoPermitido(
            "Solo se admiten imagenes JPEG, PNG o WebP. El contenido del archivo no corresponde "
            "a ninguno de esos formatos."
        )

    limpio = _LIMPIADORES[tipo](datos)

    if configuracion.antivirus_habilitado:
        if not await analizar_clamd(
            limpio, host=configuracion.clamav_host, puerto=configuracion.clamav_puerto
        ):
            raise ArchivoInfectado("El antivirus rechazo el archivo.")
        antivirus = ResultadoAntivirus.LIMPIO
    elif configuracion.entorno.es_produccion:
        raise ProveedorExternoNoDisponible(
            "La carga de archivos exige antivirus en produccion y no esta habilitado."
        )
    else:
        antivirus = ResultadoAntivirus.NO_DISPONIBLE

    return ImagenSaneada(
        datos=limpio,
        tipo_mime=tipo,
        sha256=hashlib.sha256(limpio).hexdigest(),
        antivirus=antivirus,
    )


__all__ = [
    "TIPOS_IMAGEN",
    "ArchivoInfectado",
    "ComprobanteSaneado",
    "ImagenSaneada",
    "ResultadoAntivirus",
    "analizar_clamd",
    "limpiar_jpeg",
    "limpiar_png",
    "limpiar_webp",
    "sanear_comprobante",
    "sanear_imagen",
]
