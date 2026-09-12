"""Flujo OAuth de autorizacion del calendario.

El parametro `state` es un control de seguridad, no un identificador
---------------------------------------------------------------------
El error habitual es usar `state` como un campo informativo -- meter ahi el
identificador del profesional y leerlo tal cual al volver. Eso abre un ataque
concreto: un tercero prepara una URL de callback con el `state` de **otra**
persona y consigue que el sistema asocie su propio calendario de Google a la
cuenta de esa persona, o al contrario.

Aqui `state` es un valor firmado con HMAC que lleva dentro el profesional, el
instante de emision y un valor aleatorio. Al volver:

1. Se verifica la firma en tiempo constante. Sin firma valida no se sigue.
2. Se comprueba que no haya caducado. Un `state` eterno es un vale de
   autorizacion reutilizable indefinidamente.
3. Se comprueba que no se haya usado ya (un solo uso, en `token_un_uso`).

Sin credenciales
----------------
La URL de autorizacion y el intercambio de codigo estan escritos contra la
documentacion publica de Google, y **no se han ejecutado contra Google**: no
hay credenciales y no se inventan (CLAUDE.md, regla 3). Lo que si se verifica
es todo lo de arriba, que es donde esta el riesgo de seguridad.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.nucleo.errores import FirmaInvalida, ProveedorExternoNoDisponible
from app.nucleo.registro import obtener_logger

logger = obtener_logger(__name__)

URL_AUTORIZACION_GOOGLE = "https://accounts.google.com/o/oauth2/v2/auth"
# Es la URL del endpoint de tokens de Google, no una credencial.
URL_TOKEN_GOOGLE = "https://oauth2.googleapis.com/token"  # noqa: S105

# Vida del `state`. Suficiente para que una persona complete la pantalla de
# consentimiento de Google sin prisa, y corta para que un valor filtrado no
# sirva al dia siguiente.
VIGENCIA_ESTADO = timedelta(minutes=15)

# El `state` firmado tiene exactamente dos partes: cuerpo y firma.
_PARTES_ESTADO = 2

# A partir de aqui, la respuesta del proveedor es un rechazo.
_HTTP_ERROR_CLIENTE = 400


@dataclass(frozen=True, slots=True)
class EstadoOauth:
    profesional_id: uuid.UUID
    emitido_en: datetime
    aleatorio: str

    @property
    def identificador(self) -> str:
        """Valor que identifica este `state` para el control de un solo uso."""
        return self.aleatorio


def firmar_estado(estado: EstadoOauth, secreto: str) -> str:
    """Serializa y firma el `state`.

    El formato es `base64(json).base64(hmac)`. Se firma el texto ya
    codificado, no el diccionario: firmar una estructura y volver a
    serializarla al verificar produce firmas que no coinciden cuando cambia el
    orden de las claves -- el mismo error que en el webhook de WhatsApp.
    """
    if not secreto:
        raise FirmaInvalida("No hay secreto configurado para firmar el estado de OAuth.")

    cuerpo = json.dumps(
        {
            "p": str(estado.profesional_id),
            "t": int(estado.emitido_en.timestamp()),
            "n": estado.aleatorio,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    codificado = base64.urlsafe_b64encode(cuerpo).rstrip(b"=")
    firma = hmac.new(secreto.encode("utf-8"), codificado, hashlib.sha256).digest()
    return f"{codificado.decode('ascii')}.{base64.urlsafe_b64encode(firma).rstrip(b'=').decode('ascii')}"


def verificar_estado(valor: str, secreto: str, *, ahora: datetime) -> EstadoOauth:
    """Verifica firma y vigencia, y devuelve el estado.

    Lanza `FirmaInvalida` en todos los casos de rechazo, con mensajes que no
    distinguen «firma mal» de «caducado» hacia el exterior: la ruta devuelve
    403 sin detalle, porque afinar el mensaje ayuda a quien esta probando.
    """
    if not secreto:
        raise FirmaInvalida("No hay secreto configurado para verificar el estado de OAuth.")

    partes = valor.split(".")
    if len(partes) != _PARTES_ESTADO:
        raise FirmaInvalida("El estado de OAuth no tiene el formato esperado.")

    codificado, firma_recibida = partes
    esperada = (
        base64.urlsafe_b64encode(
            hmac.new(secreto.encode("utf-8"), codificado.encode("ascii"), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    if not hmac.compare_digest(esperada, firma_recibida):
        raise FirmaInvalida("La firma del estado de OAuth no coincide.")

    try:
        relleno = "=" * (-len(codificado) % 4)
        datos = json.loads(base64.urlsafe_b64decode(codificado + relleno))
        profesional_id = uuid.UUID(str(datos["p"]))
        emitido_en = datetime.fromtimestamp(int(datos["t"]), tz=ahora.tzinfo)
        aleatorio = str(datos["n"])
    except (ValueError, KeyError, TypeError) as exc:
        raise FirmaInvalida("El estado de OAuth no se puede interpretar.") from exc

    if ahora - emitido_en > VIGENCIA_ESTADO:
        raise FirmaInvalida("El estado de OAuth caduco.")
    # Un `state` emitido en el futuro indica manipulacion o un reloj
    # desincronizado; en ambos casos no se sigue.
    if emitido_en - ahora > timedelta(minutes=1):
        raise FirmaInvalida("El estado de OAuth tiene una fecha de emision invalida.")

    return EstadoOauth(profesional_id=profesional_id, emitido_en=emitido_en, aleatorio=aleatorio)


def nuevo_estado(profesional_id: uuid.UUID, *, ahora: datetime) -> EstadoOauth:
    return EstadoOauth(
        profesional_id=profesional_id,
        emitido_en=ahora,
        aleatorio=secrets.token_urlsafe(24),
    )


def url_autorizacion(
    *,
    client_id: str,
    redirect_uri: str,
    scopes: str,
    estado_firmado: str,
) -> str:
    """URL a la que se envia al profesional para que autorice.

    `access_type=offline` es lo que hace que Google entregue un token de
    refresco; sin el, la conexion deja de funcionar en una hora y hay que
    volver a autorizar cada vez. `prompt=consent` fuerza que lo entregue de
    nuevo incluso si el profesional ya habia autorizado antes, que es el caso
    en el que se pierde el refresco y nadie entiende por que.
    """
    if not client_id:
        raise ProveedorExternoNoDisponible(
            "Falta GOOGLE_CLIENT_ID. Para trabajar sin credenciales use MODO_CALENDARIO=sandbox."
        )
    parametros = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": estado_firmado,
    }
    return f"{URL_AUTORIZACION_GOOGLE}?{urlencode(parametros)}"


@dataclass(frozen=True, slots=True)
class TokensObtenidos:
    token_acceso: str
    token_refresco: str
    expira_en: datetime
    alcances: str | None

    def __repr__(self) -> str:
        return f"TokensObtenidos(expira_en={self.expira_en!r}, tokens=<oculto>)"


async def intercambiar_codigo(
    *,
    codigo: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    ahora: datetime,
    cliente: httpx.AsyncClient | None = None,
) -> TokensObtenidos:
    """Cambia el codigo de autorizacion por tokens.

    **Sin verificar contra Google** (limitacion E-1).

    Si la respuesta no trae `refresh_token` se falla de forma explicita en
    lugar de guardar solo el de acceso: una conexion sin token de refresco
    parece funcionar durante una hora y luego se rompe, y el sintoma -- «la
    sincronizacion dejo de ir» -- no apunta a su causa.
    """
    if not client_id or not client_secret:
        raise ProveedorExternoNoDisponible(
            "Faltan GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET. Para trabajar sin "
            "credenciales use MODO_CALENDARIO=sandbox."
        )

    propio = cliente is None
    http = cliente or httpx.AsyncClient(timeout=15.0)
    try:
        respuesta = await http.post(
            URL_TOKEN_GOOGLE,
            data={
                "code": codigo,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    except httpx.HTTPError as exc:
        raise ProveedorExternoNoDisponible(
            f"No se pudo contactar con el proveedor de OAuth: {type(exc).__name__}"
        ) from exc
    finally:
        if propio:
            await http.aclose()

    if respuesta.status_code >= _HTTP_ERROR_CLIENTE:
        # No se incluye el cuerpo de la respuesta en el error: puede contener
        # fragmentos del codigo de autorizacion.
        logger.warning("calendario.oauth.intercambio_rechazado", estado=respuesta.status_code)
        raise ProveedorExternoNoDisponible(
            "El proveedor de OAuth rechazo el intercambio del codigo."
        )

    try:
        datos = respuesta.json()
        acceso = str(datos["access_token"])
        refresco = str(datos["refresh_token"])
        segundos = int(datos.get("expires_in", 3600))
    except (ValueError, KeyError, TypeError) as exc:
        raise ProveedorExternoNoDisponible(
            "El proveedor de OAuth no devolvio un token de refresco. Vuelva a "
            "autorizar con prompt=consent."
        ) from exc

    alcances = datos.get("scope")
    return TokensObtenidos(
        token_acceso=acceso,
        token_refresco=refresco,
        expira_en=ahora + timedelta(seconds=segundos),
        alcances=str(alcances) if alcances else None,
    )


__all__ = [
    "URL_AUTORIZACION_GOOGLE",
    "URL_TOKEN_GOOGLE",
    "VIGENCIA_ESTADO",
    "EstadoOauth",
    "TokensObtenidos",
    "firmar_estado",
    "intercambiar_codigo",
    "nuevo_estado",
    "url_autorizacion",
    "verificar_estado",
]
