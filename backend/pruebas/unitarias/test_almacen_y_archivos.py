"""Pruebas del almacen de objetos y del saneado de imagenes.

* **SigV4** se compara con el ejemplo publicado por AWS ("GET Object" de la
  documentacion de Signature Version 4). Si la firma propia se desviara un
  caracter, MinIO y S3 rechazarian todas las subidas.
* **Recorrido de rutas**: una clave con `..` no sale de la carpeta.
* **Metadatos**: el GPS desaparece y la orientacion sobrevive.
* **Tipo real**: un HTML con extension de imagen se rechaza.
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.nucleo.almacen import (
    AlmacenLocal,
    AlmacenS3,
    ObjetoNoEncontrado,
    firmar_sigv4,
    validar_clave,
)
from app.nucleo.archivos import (
    ResultadoAntivirus,
    limpiar_jpeg,
    limpiar_png,
    limpiar_webp,
    sanear_imagen,
)
from app.nucleo.configuracion import Configuracion, Entorno
from app.nucleo.errores import (
    ArchivoDemasiadoGrande,
    ArchivoNoPermitido,
    ProveedorExternoNoDisponible,
)
from app.nucleo.reloj import RelojFijo
from app.nucleo.seguridad import CifradorDatos

pytestmark = pytest.mark.unitaria


# ===========================================================================
#  SigV4
# ===========================================================================
def test_firma_sigv4_coincide_con_el_ejemplo_de_aws() -> None:
    cabecera = firmar_sigv4(
        metodo="GET",
        host="examplebucket.s3.amazonaws.com",
        ruta="/test.txt",
        cabeceras={
            "range": "bytes=0-9",
            "x-amz-content-sha256": (
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
            "x-amz-date": "20130524T000000Z",
        },
        hash_cuerpo="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        clave_acceso="AKIAIOSFODNN7EXAMPLE",
        clave_secreta="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        instante=datetime(2013, 5, 24, tzinfo=UTC),
    )
    assert cabecera == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


# ===========================================================================
#  Almacen local
# ===========================================================================
@pytest.mark.parametrize("clave", ["../fuera", "a/../../b", "/absoluta", "a//b", "con espacio"])
def test_claves_peligrosas_se_rechazan(clave: str) -> None:
    with pytest.raises(ValueError):
        validar_clave(clave)


@pytest.mark.asyncio
async def test_almacen_local_guarda_y_lee(tmp_path: Path) -> None:
    almacen = AlmacenLocal(tmp_path)
    await almacen.guardar("clinica/paciente/objeto", b"cifrado")
    assert await almacen.existe("clinica/paciente/objeto")
    assert await almacen.leer("clinica/paciente/objeto") == b"cifrado"
    with pytest.raises(ObjetoNoEncontrado):
        await almacen.leer("clinica/paciente/otro")


def test_cifrado_de_bytes_liga_el_contexto() -> None:
    """Un objeto copiado a la fila de otro paciente no descifra."""
    cifrador = CifradorDatos("clave-de-prueba-sintetica")
    cifrado = cifrador.cifrar_bytes(b"\xff\xd8imagen", contexto=b"imagen-1")
    assert b"imagen" not in cifrado
    assert cifrador.descifrar_bytes(cifrado, contexto=b"imagen-1") == b"\xff\xd8imagen"
    with pytest.raises(ValueError):
        cifrador.descifrar_bytes(cifrado, contexto=b"imagen-2")


# ===========================================================================
#  Imagenes sinteticas
# ===========================================================================
def _segmento(marcador: int, carga: bytes) -> bytes:
    return b"\xff" + bytes([marcador]) + struct.pack(">H", len(carga) + 2) + carga


def _exif(orientacion: int) -> bytes:
    """EXIF little-endian con orientacion y una etiqueta GPS ficticia."""
    entradas = [
        struct.pack("<HHIHH", 0x0112, 3, 1, orientacion, 0),
        struct.pack("<HHII", 0x8825, 4, 1, 0),  # puntero GPS
    ]
    tiff = b"II\x2a\x00\x08\x00\x00\x00" + struct.pack("<H", len(entradas)) + b"".join(entradas)
    return b"Exif\x00\x00" + tiff + b"GPS-LATITUD-SINTETICA"


def _jpeg(orientacion: int = 6) -> bytes:
    return (
        b"\xff\xd8"
        + _segmento(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
        + _segmento(0xE1, _exif(orientacion))
        + _segmento(0xFE, b"comentario con nombre de paciente")
        + _segmento(0xDB, b"\x00" * 65)
        + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00datos-de-imagen\xff\xd9"
    )


def _trozo_png(tipo: bytes, datos: bytes) -> bytes:
    return struct.pack(">I", len(datos)) + tipo + datos + b"\x00\x00\x00\x00"


def _png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + _trozo_png(b"IHDR", b"\x00" * 13)
        + _trozo_png(b"tEXt", b"Author\x00Persona Sintetica")
        + _trozo_png(b"IDAT", b"pixeles")
        + _trozo_png(b"IEND", b"")
    )


def test_jpeg_pierde_gps_y_conserva_orientacion() -> None:
    limpio = limpiar_jpeg(_jpeg(orientacion=6))
    assert b"GPS-LATITUD-SINTETICA" not in limpio
    assert b"nombre de paciente" not in limpio
    assert b"datos-de-imagen" in limpio
    # JFIF sigue primero y el EXIF minimo va despues con orientacion 6.
    assert limpio[2:4] == b"\xff\xe0"
    assert struct.pack(">HHIHH", 0x0112, 3, 1, 6, 0) in limpio


def test_jpeg_con_orientacion_normal_no_lleva_exif() -> None:
    assert b"Exif" not in limpiar_jpeg(_jpeg(orientacion=1))


def test_png_pierde_los_textos() -> None:
    limpio = limpiar_png(_png())
    assert b"Persona Sintetica" not in limpio
    assert b"IDAT" in limpio
    assert limpio.endswith(_trozo_png(b"IEND", b""))


def test_webp_pierde_exif_y_ajusta_cabecera() -> None:
    vp8x = b"VP8X" + struct.pack("<I", 10) + bytes([0x08 | 0x04]) + b"\x00" * 9
    exif = b"EXIF" + struct.pack("<I", 4) + b"GPS!"
    imagen = b"VP8L" + struct.pack("<I", 5) + b"datos\x00"
    cuerpo = b"WEBP" + vp8x + exif + imagen
    webp = b"RIFF" + struct.pack("<I", len(cuerpo)) + cuerpo

    limpio = limpiar_webp(webp)

    assert b"GPS!" not in limpio
    assert struct.unpack("<I", limpio[4:8])[0] == len(limpio) - 8
    assert limpio[20] & 0x0C == 0  # banderas EXIF y XMP apagadas


def test_jpeg_danado_se_rechaza() -> None:
    with pytest.raises(ArchivoNoPermitido):
        limpiar_jpeg(b"\xff\xd8\x00\x00basura")


# ===========================================================================
#  sanear_imagen
# ===========================================================================
def _config(**cambios: object) -> Configuracion:
    return Configuracion(**{"max_tamano_archivo_mb": 1, **cambios})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_html_disfrazado_de_imagen_se_rechaza() -> None:
    with pytest.raises(ArchivoNoPermitido):
        await sanear_imagen(b"<html><script>alert(1)</script></html>", _config())


@pytest.mark.asyncio
async def test_imagen_demasiado_grande_se_rechaza() -> None:
    with pytest.raises(ArchivoDemasiadoGrande):
        await sanear_imagen(b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024), _config())


@pytest.mark.asyncio
async def test_sin_antivirus_en_desarrollo_se_declara() -> None:
    resultado = await sanear_imagen(_jpeg(), _config())
    assert resultado.tipo_mime == "image/jpeg"
    assert resultado.antivirus is ResultadoAntivirus.NO_DISPONIBLE
    assert len(resultado.sha256) == 64


@pytest.mark.asyncio
async def test_sin_antivirus_en_produccion_se_rechaza() -> None:
    """Segunda barrera: la configuracion de produccion ya exige antivirus al
    arrancar; si esa validacion se relajara, la carga sigue rechazandose."""
    configuracion = Configuracion.model_construct(
        entorno=Entorno.PRODUCCION, antivirus_habilitado=False, max_tamano_archivo_mb=1
    )
    with pytest.raises(ProveedorExternoNoDisponible):
        await sanear_imagen(_jpeg(), configuracion)


# ===========================================================================
#  Almacen S3 contra un transporte simulado
# ===========================================================================
@pytest.mark.asyncio
async def test_almacen_s3_crea_el_bucket_y_firma_cada_peticion() -> None:
    objetos: dict[str, bytes] = {}
    vistas: list[tuple[str, str]] = []

    def manejador(peticion: httpx.Request) -> httpx.Response:
        vistas.append((peticion.method, peticion.url.path))
        assert peticion.headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=acceso/")
        ruta = peticion.url.path
        if ruta == "/clinica-archivos":
            return httpx.Response(404 if peticion.method == "HEAD" and not objetos else 200)
        if peticion.method == "PUT":
            objetos[ruta] = peticion.content
            return httpx.Response(200)
        if ruta in objetos:
            return httpx.Response(200, content=objetos[ruta])
        return httpx.Response(404)

    almacen = AlmacenS3(
        endpoint="http://127.0.0.1:9000",
        bucket="clinica-archivos",
        clave_acceso="acceso",
        clave_secreta="secreta-sintetica",
        cliente=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
        reloj=RelojFijo(datetime(2026, 10, 5, tzinfo=UTC)),
    )
    await almacen.asegurar_bucket()
    assert ("PUT", "/clinica-archivos") in vistas

    await almacen.guardar("c/p/objeto", b"cifrado")
    assert await almacen.leer("c/p/objeto") == b"cifrado"
    assert await almacen.existe("c/p/objeto")
    with pytest.raises(ObjetoNoEncontrado):
        await almacen.leer("c/p/otro")
