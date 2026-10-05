"""Almacen de objetos para archivos clinicos.

Que guarda y que no
-------------------
Guarda **bytes ya cifrados**. El cifrado ocurre antes, en el servicio, con
`CifradorDatos.cifrar_bytes`: ni el disco local ni MinIO ven nunca una
radiografia en claro. Si alguien copia el bucket, se lleva ruido.

Tampoco entrega URLs firmadas. Toda descarga pasa por el API, que comprueba
permiso y relacion asistencial y deja la entrada de auditoria. Con una URL
firmada la descarga no tocaria el backend y la pregunta «quien vio esta
radiografia» quedaria sin respuesta.

Dos adaptadores
---------------
* `AlmacenLocal`: carpeta en disco. Desarrollo y pruebas.
* `AlmacenS3`: cualquier servicio compatible con S3 (MinIO en desarrollo,
  S3 o R2 en produccion). Firma SigV4 propia sobre `httpx`, sin `boto3`: son
  cuatro operaciones y una dependencia de 80 MB con su propia superficie de
  vulnerabilidades no se justifica para eso.

Las claves de objeto las genera el servicio (`<clinica>/<paciente>/<uuid>`) y
nunca derivan del nombre de archivo que envio el usuario: un nombre con
`../` no puede escapar del prefijo.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.nucleo.configuracion import Configuracion
from app.nucleo.reloj import Reloj, RelojSistema

# Solo identificadores, guiones y barras: la clave la compone el servicio.
_PATRON_CLAVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_\-.]{0,500}$")


class ErrorAlmacen(RuntimeError):
    """El almacen no respondio como se esperaba."""


class ObjetoNoEncontrado(ErrorAlmacen):
    """La clave no existe en el almacen."""


def validar_clave(clave: str) -> str:
    """Rechaza claves con recorridos de ruta o caracteres fuera del patron."""
    if not _PATRON_CLAVE.match(clave) or ".." in clave or "//" in clave:
        raise ValueError(f"Clave de objeto no valida: {clave!r}")
    return clave


class AlmacenObjetos(Protocol):
    """Operaciones minimas sobre un almacen de objetos."""

    @property
    def nombre(self) -> str: ...

    async def guardar(self, clave: str, datos: bytes) -> None: ...

    async def leer(self, clave: str) -> bytes: ...

    async def existe(self, clave: str) -> bool: ...


# ---------------------------------------------------------------------------
#  Local
# ---------------------------------------------------------------------------
class AlmacenLocal:
    """Carpeta en disco. Escritura atomica: archivo temporal y renombrado."""

    nombre = "local"

    def __init__(self, raiz: Path) -> None:
        self._raiz = raiz.resolve()

    def _ruta(self, clave: str) -> Path:
        ruta = (self._raiz / validar_clave(clave)).resolve()
        # Defensa en profundidad ademas del patron: la ruta resuelta tiene que
        # quedar dentro de la raiz.
        if self._raiz not in ruta.parents:
            raise ValueError("La clave escapa de la carpeta del almacen.")
        return ruta

    async def guardar(self, clave: str, datos: bytes) -> None:
        ruta = self._ruta(clave)

        def _escribir() -> None:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal = ruta.with_suffix(ruta.suffix + ".tmp")
            temporal.write_bytes(datos)
            temporal.replace(ruta)

        await asyncio.to_thread(_escribir)

    async def leer(self, clave: str) -> bytes:
        ruta = self._ruta(clave)
        try:
            return await asyncio.to_thread(ruta.read_bytes)
        except FileNotFoundError as exc:
            raise ObjetoNoEncontrado(clave) from exc

    async def existe(self, clave: str) -> bool:
        return await asyncio.to_thread(self._ruta(clave).is_file)


# ---------------------------------------------------------------------------
#  S3 / MinIO
# ---------------------------------------------------------------------------
_SHA256_VACIO = hashlib.sha256(b"").hexdigest()


def _hmac(clave: bytes, mensaje: str) -> bytes:
    return hmac.new(clave, mensaje.encode("utf-8"), hashlib.sha256).digest()


def firmar_sigv4(
    *,
    metodo: str,
    host: str,
    ruta: str,
    cabeceras: dict[str, str],
    hash_cuerpo: str,
    clave_acceso: str,
    clave_secreta: str,
    region: str,
    instante: datetime,
    consulta: str = "",
) -> str:
    """Devuelve la cabecera `Authorization` de AWS Signature Version 4 para S3.

    `cabeceras` debe incluir las que se firman ademas de `host`
    (`x-amz-date` y `x-amz-content-sha256` como minimo). Se valida contra el
    ejemplo publicado por AWS en la prueba unitaria.
    """
    fecha_larga = instante.strftime("%Y%m%dT%H%M%SZ")
    fecha_corta = instante.strftime("%Y%m%d")

    firmadas = {"host": host, **{k.lower(): v.strip() for k, v in cabeceras.items()}}
    nombres = sorted(firmadas)
    cabeceras_canonicas = "".join(f"{nombre}:{firmadas[nombre]}\n" for nombre in nombres)
    lista_firmadas = ";".join(nombres)

    solicitud_canonica = "\n".join(
        [metodo, ruta, consulta, cabeceras_canonicas, lista_firmadas, hash_cuerpo]
    )
    alcance = f"{fecha_corta}/{region}/s3/aws4_request"
    cadena = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            fecha_larga,
            alcance,
            hashlib.sha256(solicitud_canonica.encode("utf-8")).hexdigest(),
        ]
    )
    clave = _hmac(("AWS4" + clave_secreta).encode("utf-8"), fecha_corta)
    clave = _hmac(clave, region)
    clave = _hmac(clave, "s3")
    clave = _hmac(clave, "aws4_request")
    firma = hmac.new(clave, cadena.encode("utf-8"), hashlib.sha256).hexdigest()
    return (
        f"AWS4-HMAC-SHA256 Credential={clave_acceso}/{alcance},"
        f"SignedHeaders={lista_firmadas},Signature={firma}"
    )


class AlmacenS3:
    """Almacen compatible con S3, con direccionamiento por ruta (`/bucket/clave`).

    El direccionamiento por ruta es el que entiende MinIO sin configurar DNS,
    y S3 y R2 tambien lo aceptan.
    """

    nombre = "s3"

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        clave_acceso: str,
        clave_secreta: str,
        region: str = "us-east-1",
        cliente: httpx.AsyncClient | None = None,
        reloj: Reloj | None = None,
    ) -> None:
        if not (endpoint and bucket and clave_acceso and clave_secreta):
            raise ValueError("El almacen S3 necesita endpoint, bucket y credenciales.")
        self._endpoint = endpoint.rstrip("/")
        self._host = httpx.URL(self._endpoint).netloc.decode("ascii")
        self._bucket = bucket
        self._acceso = clave_acceso
        self._secreta = clave_secreta
        self._region = region
        self._cliente = cliente or httpx.AsyncClient(timeout=30.0)
        # La firma lleva la hora: con un reloj desfasado mas de 15 minutos, S3
        # rechaza la peticion. Se usa el reloj del sistema, inyectable.
        self._reloj = reloj or RelojSistema()

    def _ruta(self, clave: str) -> str:
        return f"/{self._bucket}/{quote(validar_clave(clave), safe='/')}"

    async def _peticion(self, metodo: str, ruta: str, cuerpo: bytes = b"") -> httpx.Response:
        instante = self._reloj.ahora()
        hash_cuerpo = hashlib.sha256(cuerpo).hexdigest() if cuerpo else _SHA256_VACIO
        cabeceras = {
            "x-amz-date": instante.strftime("%Y%m%dT%H%M%SZ"),
            "x-amz-content-sha256": hash_cuerpo,
        }
        cabeceras["Authorization"] = firmar_sigv4(
            metodo=metodo,
            host=self._host,
            ruta=ruta,
            cabeceras=cabeceras,
            hash_cuerpo=hash_cuerpo,
            clave_acceso=self._acceso,
            clave_secreta=self._secreta,
            region=self._region,
            instante=instante,
        )
        try:
            return await self._cliente.request(
                metodo, f"{self._endpoint}{ruta}", content=cuerpo or None, headers=cabeceras
            )
        except httpx.HTTPError as exc:
            raise ErrorAlmacen(f"El almacen S3 no respondio: {type(exc).__name__}") from exc

    async def asegurar_bucket(self) -> None:
        """Crea el bucket si no existe. Se llama al arrancar."""
        respuesta = await self._peticion("HEAD", f"/{self._bucket}")
        if respuesta.status_code == httpx.codes.NOT_FOUND:
            creado = await self._peticion("PUT", f"/{self._bucket}")
            if creado.status_code not in (httpx.codes.OK, httpx.codes.CONFLICT):
                raise ErrorAlmacen(f"No se pudo crear el bucket ({creado.status_code}).")
        elif respuesta.status_code >= httpx.codes.BAD_REQUEST:
            raise ErrorAlmacen(f"El bucket no es accesible ({respuesta.status_code}).")

    async def guardar(self, clave: str, datos: bytes) -> None:
        respuesta = await self._peticion("PUT", self._ruta(clave), datos)
        if respuesta.status_code != httpx.codes.OK:
            raise ErrorAlmacen(f"No se pudo guardar el objeto ({respuesta.status_code}).")

    async def leer(self, clave: str) -> bytes:
        respuesta = await self._peticion("GET", self._ruta(clave))
        if respuesta.status_code == httpx.codes.NOT_FOUND:
            raise ObjetoNoEncontrado(clave)
        if respuesta.status_code != httpx.codes.OK:
            raise ErrorAlmacen(f"No se pudo leer el objeto ({respuesta.status_code}).")
        return respuesta.content

    async def existe(self, clave: str) -> bool:
        respuesta = await self._peticion("HEAD", self._ruta(clave))
        return respuesta.status_code == httpx.codes.OK


def construir_almacen(configuracion: Configuracion) -> AlmacenObjetos:
    """Elige el adaptador segun la configuracion."""
    if configuracion.almacenamiento_archivos == "s3":
        return AlmacenS3(
            endpoint=configuracion.s3_endpoint,
            bucket=configuracion.s3_bucket,
            clave_acceso=configuracion.s3_clave_acceso,
            clave_secreta=configuracion.s3_clave_secreta.get_secret_value(),
            region=configuracion.s3_region,
        )
    return AlmacenLocal(configuracion.ruta_almacenamiento_local)


__all__ = [
    "AlmacenLocal",
    "AlmacenObjetos",
    "AlmacenS3",
    "ErrorAlmacen",
    "ObjetoNoEncontrado",
    "construir_almacen",
    "firmar_sigv4",
    "validar_clave",
]
