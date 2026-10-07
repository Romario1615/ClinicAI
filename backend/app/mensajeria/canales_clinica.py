"""Canales salientes con las credenciales que cada clínica guarda en Configuración.

Hasta ahora WhatsApp salía siempre con las variables de entorno y el correo no
tenía adaptador: lo que una clínica escribía en «Integraciones» no tenía
efecto. Aquí cada mensaje usa la integración de SU clínica si está habilitada
y completa; si no, el adaptador de respaldo (el del entorno o el sandbox), que
es el comportamiento anterior.

Las credenciales se leen de `configuracion_clinica` (`integracion.<codigo>`),
con los secretos descifrados con el contexto de la clínica: una clave copiada
a otra clínica no se puede descifrar.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.ia.proveedores_clinica import descifrar, leer_integracion
from app.mensajeria.adaptadores import (
    AdaptadorCanal,
    AdaptadorWhatsAppCloud,
    CredencialesWhatsApp,
    MensajeSaliente,
    RespuestaEnvio,
    ResultadoEnvio,
)
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.registro import obtener_logger
from app.nucleo.seguridad import CifradorDatos

logger = obtener_logger(__name__)

ASUNTO_POR_DEFECTO = "Aviso de su clínica"


@dataclass(frozen=True, slots=True)
class CredencialesSmtp:
    host: str
    puerto: int
    usuario: str
    contrasena: str
    tls: bool
    correo_remitente: str
    nombre_remitente: str


# ---------------------------------------------------------------------------
#  Lectura de credenciales por clínica
# ---------------------------------------------------------------------------
async def credenciales_whatsapp(
    gestor: GestorBaseDatos, cifrador: CifradorDatos, clinica_id: uuid.UUID
) -> CredencialesWhatsApp | None:
    async for sesion in gestor.sesion():
        integ = await leer_integracion(sesion, clinica_id, "whatsapp")
        if integ is None or not integ.habilitada:
            return None
        numero = str(integ.ajustes.get("id_numero_telefono") or "").strip()
        token = descifrar(cifrador, clinica_id, "whatsapp", "token_acceso", integ)
        if not numero or not token:
            logger.warning("whatsapp.integracion_incompleta", clinica_id=str(clinica_id))
            return None
        return CredencialesWhatsApp(
            id_numero_telefono=numero,
            token_acceso=token,
            version_api=str(integ.ajustes.get("version_api") or "v21.0"),
        )
    return None


async def credenciales_smtp(
    gestor: GestorBaseDatos, cifrador: CifradorDatos, clinica_id: uuid.UUID
) -> CredencialesSmtp | None:
    async for sesion in gestor.sesion():
        integ = await leer_integracion(sesion, clinica_id, "smtp")
        if integ is None or not integ.habilitada:
            return None
        ajustes = integ.ajustes
        host = str(ajustes.get("host") or "").strip()
        remitente = str(ajustes.get("correo_remitente") or "").strip()
        if not host or not remitente:
            logger.warning("smtp.integracion_incompleta", clinica_id=str(clinica_id))
            return None
        return CredencialesSmtp(
            host=host,
            puerto=int(ajustes.get("puerto") or 587),
            usuario=str(ajustes.get("usuario") or ""),
            contrasena=descifrar(cifrador, clinica_id, "smtp", "contrasena", integ) or "",
            tls=bool(ajustes.get("tls", True)),
            correo_remitente=remitente,
            nombre_remitente=str(ajustes.get("nombre_remitente") or ""),
        )
    return None


# ---------------------------------------------------------------------------
#  Adaptadores
# ---------------------------------------------------------------------------
CargadorWhatsApp = Callable[[uuid.UUID], Awaitable[CredencialesWhatsApp | None]]
CargadorSmtp = Callable[[uuid.UUID], Awaitable[CredencialesSmtp | None]]


class AdaptadorWhatsAppPorClinica:
    """WhatsApp con la cuenta de la clínica del mensaje; si no tiene, el respaldo."""

    nombre = "whatsapp_por_clinica"

    def __init__(self, respaldo: AdaptadorCanal, cargar: CargadorWhatsApp) -> None:
        self._respaldo = respaldo
        self._cargar = cargar
        self._cache: dict[uuid.UUID, CredencialesWhatsApp | None] = {}

    async def enviar(self, mensaje: MensajeSaliente) -> RespuestaEnvio:
        if mensaje.clinica_id is None:
            return await self._respaldo.enviar(mensaje)
        if mensaje.clinica_id not in self._cache:
            self._cache[mensaje.clinica_id] = await self._cargar(mensaje.clinica_id)
        credenciales = self._cache[mensaje.clinica_id]
        if credenciales is None:
            return await self._respaldo.enviar(mensaje)
        return await AdaptadorWhatsAppCloud(credenciales).enviar(mensaje)


def _enviar_smtp(credenciales: CredencialesSmtp, correo: EmailMessage, timeout: float) -> None:
    contexto = ssl.create_default_context()
    if credenciales.puerto == smtplib.SMTP_SSL_PORT:
        with smtplib.SMTP_SSL(
            credenciales.host, credenciales.puerto, timeout=timeout, context=contexto
        ) as servidor:
            if credenciales.usuario:
                servidor.login(credenciales.usuario, credenciales.contrasena)
            servidor.send_message(correo)
        return
    with smtplib.SMTP(credenciales.host, credenciales.puerto, timeout=timeout) as servidor:
        if credenciales.tls:
            servidor.starttls(context=contexto)
        if credenciales.usuario:
            servidor.login(credenciales.usuario, credenciales.contrasena)
        servidor.send_message(correo)


class AdaptadorCorreoPorClinica:
    """Correo por el SMTP de la clínica del mensaje; si no tiene, el respaldo.

    El texto es el mismo que ya se redacta para el mensaje (sin datos
    clínicos, regla 10): aquí solo se envuelve en un correo.
    """

    nombre = "correo_por_clinica"

    def __init__(
        self, respaldo: AdaptadorCanal, cargar: CargadorSmtp, *, timeout_segundos: float = 20.0
    ) -> None:
        self._respaldo = respaldo
        self._cargar = cargar
        self._timeout = timeout_segundos
        self._cache: dict[uuid.UUID, CredencialesSmtp | None] = {}

    async def enviar(self, mensaje: MensajeSaliente) -> RespuestaEnvio:
        if mensaje.clinica_id is None:
            return await self._respaldo.enviar(mensaje)
        if mensaje.clinica_id not in self._cache:
            self._cache[mensaje.clinica_id] = await self._cargar(mensaje.clinica_id)
        credenciales = self._cache[mensaje.clinica_id]
        if credenciales is None:
            return await self._respaldo.enviar(mensaje)

        correo = EmailMessage()
        correo["From"] = formataddr((credenciales.nombre_remitente, credenciales.correo_remitente))
        correo["To"] = mensaje.destino
        correo["Subject"] = ASUNTO_POR_DEFECTO
        identificador = make_msgid(domain=credenciales.correo_remitente.rsplit("@", 1)[-1])
        correo["Message-ID"] = identificador
        correo.set_content(mensaje.texto or "")
        try:
            await asyncio.to_thread(_enviar_smtp, credenciales, correo, self._timeout)
        except smtplib.SMTPAuthenticationError:
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_PERMANENTE,
                detalle="El servidor SMTP rechazó el usuario o la contraseña.",
            )
        except smtplib.SMTPRecipientsRefused:
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_PERMANENTE,
                detalle="El servidor SMTP rechazó la dirección de destino.",
            )
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("smtp.envio_fallido", motivo=type(exc).__name__)
            return RespuestaEnvio(
                resultado=ResultadoEnvio.FALLO_TEMPORAL,
                detalle="No se pudo contactar con el servidor SMTP.",
            )
        return RespuestaEnvio(resultado=ResultadoEnvio.ENTREGADO, referencia_externa=identificador)


__all__ = [
    "AdaptadorCorreoPorClinica",
    "AdaptadorWhatsAppPorClinica",
    "CredencialesSmtp",
    "credenciales_smtp",
    "credenciales_whatsapp",
]
