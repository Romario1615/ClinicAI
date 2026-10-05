"""Generacion de imagenes para promociones mediante un modelo por API.

La IA propone, una persona decide
---------------------------------
La imagen generada queda en la campana como **propuesta**. No sale a ningun
paciente hasta que alguien con `promocion.aprobar` la ve y aprueba la
campana. Se puede regenerar o sustituir por una imagen subida a mano.

Que se le pide al modelo
------------------------
El texto que escribe el personal va precedido de una politica fija: imagen
publicitaria de una clinica, sin personas reales identificables, sin
imagenes clinicas explicitas y sin texto con datos personales. El prompt no
admite cifras largas (telefonos, documentos): una campana no necesita datos
de nadie, y un prompt con ellos es un error de quien lo escribe.

Proveedores
-----------
* `openai`: API de imagenes compatible con OpenAI (`/images/generations`,
  respuesta en `b64_json`). URL y modelo configurables, para usar cualquier
  servicio compatible.
* `sandbox`: dibuja localmente un PNG con la paleta de la clinica. Sin red ni
  credenciales. Es lo que se usa mientras no haya clave (CLAUDE.md, regla 3).
"""

from __future__ import annotations

import base64
import re
import struct
import zlib
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import DatosInvalidos, ProveedorExternoNoDisponible

POLITICA_PROMPT = (
    "Imagen publicitaria cuadrada para una clinica de salud. Estilo limpio, luminoso y "
    "profesional. Sin personas reales identificables, sin imagenes clinicas explicitas "
    "(sangre, heridas, procedimientos), sin logotipos de terceros y sin texto con datos "
    "personales. Tema: "
)
_CIFRAS_LARGAS = re.compile(r"\d[\d\s\-]{6,}\d")
LONGITUD_MAXIMA_PROMPT = 600


@dataclass(frozen=True, slots=True)
class ImagenGenerada:
    datos: bytes
    tipo_mime: str
    proveedor: str


class GeneradorImagenes(Protocol):
    @property
    def nombre(self) -> str: ...

    async def generar(self, prompt: str) -> ImagenGenerada: ...


def validar_prompt(prompt: str) -> str:
    limpio = " ".join(prompt.split())
    if len(limpio) < 10:  # noqa: PLR2004
        raise DatosInvalidos("Describa la imagen con al menos 10 caracteres.")
    if len(limpio) > LONGITUD_MAXIMA_PROMPT:
        raise DatosInvalidos(
            f"La descripcion no puede superar {LONGITUD_MAXIMA_PROMPT} caracteres."
        )
    if _CIFRAS_LARGAS.search(limpio):
        raise DatosInvalidos(
            "La descripcion contiene una cifra larga (telefono o documento). "
            "Una imagen de campana no lleva datos de nadie."
        )
    return limpio


# ---------------------------------------------------------------------------
#  Sandbox
# ---------------------------------------------------------------------------
def _png(ancho: int, alto: int, pixel: object) -> bytes:
    """PNG RGB sin dependencias. `pixel(x, y) -> (r, g, b)`."""
    filas = bytearray()
    for y in range(alto):
        filas.append(0)
        for x in range(ancho):
            filas.extend(pixel(x, y))  # type: ignore[operator]

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (
            struct.pack(">I", len(datos))
            + tipo
            + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
        )

    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", cabecera)
        + trozo(b"IDAT", zlib.compress(bytes(filas), 9))
        + trozo(b"IEND", b"")
    )


class GeneradorSandbox:
    """Banner local: degradado de la marca con una cruz. Determinista por prompt."""

    nombre = "sandbox"

    async def generar(self, prompt: str) -> ImagenGenerada:
        semilla = zlib.crc32(prompt.encode("utf-8"))
        tono = 90 + semilla % 60
        lado = 256

        def pixel(x: int, y: int) -> tuple[int, int, int]:
            centro = lado // 2
            brazo, grosor = 70, 26
            en_cruz = (abs(x - centro) <= grosor and abs(y - centro) <= brazo) or (
                abs(y - centro) <= grosor and abs(x - centro) <= brazo
            )
            if en_cruz:
                return (255, 255, 255)
            mezcla = (x + y) / (2 * lado)
            return (int(11 + 40 * mezcla), int(tono + 60 * mezcla), int(106 + 80 * mezcla))

        return ImagenGenerada(_png(lado, lado, pixel), "image/png", self.nombre)


# ---------------------------------------------------------------------------
#  API compatible con OpenAI
# ---------------------------------------------------------------------------
class GeneradorOpenAI:
    nombre = "openai"

    def __init__(
        self,
        *,
        clave: str,
        modelo: str,
        url_base: str = "https://api.openai.com/v1",
        tiempo_limite: float = 90.0,
        cliente: httpx.AsyncClient | None = None,
    ) -> None:
        if not clave:
            raise ValueError("El generador de imagenes necesita IMAGENES_API_KEY.")
        self._clave = clave
        self._modelo = modelo
        self._url = f"{url_base.rstrip('/')}/images/generations"
        self._cliente = cliente or httpx.AsyncClient(timeout=tiempo_limite)

    async def generar(self, prompt: str) -> ImagenGenerada:
        try:
            respuesta = await self._cliente.post(
                self._url,
                headers={"Authorization": f"Bearer {self._clave}"},
                json={
                    "model": self._modelo,
                    "prompt": POLITICA_PROMPT + prompt,
                    "size": "1024x1024",
                    "n": 1,
                },
            )
            respuesta.raise_for_status()
            datos = base64.b64decode(respuesta.json()["data"][0]["b64_json"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProveedorExternoNoDisponible(
                f"El generador de imagenes no respondio: {type(exc).__name__}"
            ) from exc
        return ImagenGenerada(datos, "image/png", self.nombre)


def construir_generador(configuracion: Configuracion) -> GeneradorImagenes:
    if configuracion.proveedor_imagenes == "openai":
        return GeneradorOpenAI(
            clave=configuracion.imagenes_api_key.get_secret_value(),
            modelo=configuracion.imagenes_modelo,
            url_base=configuracion.imagenes_api_url,
        )
    return GeneradorSandbox()


__all__ = [
    "POLITICA_PROMPT",
    "GeneradorImagenes",
    "GeneradorOpenAI",
    "GeneradorSandbox",
    "ImagenGenerada",
    "construir_generador",
    "validar_prompt",
]
