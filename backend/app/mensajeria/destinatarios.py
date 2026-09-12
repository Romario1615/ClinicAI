"""Resolucion del dato de contacto del destinatario.

Por que no se guarda el telefono en el outbox
---------------------------------------------
Seria mas simple copiar el numero en la carga util al encolar.  Se resuelve
aqui, en el momento de entregar, por dos motivos:

1. **Minimizacion.**  El outbox conserva historico de mensajes entregados.
   Copiar el telefono en cada fila crea un segundo registro de datos de
   contacto, fuera de la tabla de pacientes y por tanto fuera de sus
   controles de acceso y de su politica de retencion.

2. **Correccion.**  Entre encolar un recordatorio de 24 horas y entregarlo
   pasa un dia.  Si el paciente corrige su numero en ese intervalo, un numero
   copiado enviaria el mensaje al antiguo -- que puede pertenecer ya a otra
   persona.

El coste es una consulta por mensaje en la entrega.  Es aceptable: el cuello
de botella del envio es la red del proveedor, no esta lectura por clave
primaria.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.outbox.modelos import CanalOutbox
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario

# La Cloud API exige el numero en formato internacional, solo digitos, sin
# «+», espacios ni guiones. Un numero con formato de panel («+593 99 123
# 4567») es rechazado por el proveedor, y ese rechazo aparece como fallo de
# entrega sin explicacion util.
_SOLO_DIGITOS = re.compile(r"\D+")


class DestinatarioNoResoluble(Exception):
    """No se pudo obtener un dato de contacto utilizable.

    No es un `ErrorDominio`: no llega a una respuesta HTTP.  Lo consume el
    procesador del outbox, que decide si es un fallo permanente.
    """


@dataclass(frozen=True, slots=True)
class Contacto:
    valor: str
    nombre: str


def normalizar_telefono(numero: str) -> str:
    """Deja el numero en el formato que acepta la Cloud API."""
    limpio = _SOLO_DIGITOS.sub("", numero)
    if not limpio:
        raise DestinatarioNoResoluble("El numero de contacto no contiene digitos.")
    # Se mantiene sin validar la longitud por pais: una validacion estricta
    # rechazaria numeros extranjeros validos de pacientes en transito, y el
    # proveedor ya rechaza los mal formados con un codigo permanente.
    return limpio


class ResolutorContacto:
    """Obtiene el dato de contacto de un destinatario para un canal."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def resolver(
        self, *, destino_tipo: str, destino_id: uuid.UUID, canal: CanalOutbox
    ) -> Contacto:
        if destino_tipo == "PACIENTE":
            return await self._paciente(destino_id, canal)
        if destino_tipo == "PROFESIONAL":
            return await self._profesional(destino_id, canal)
        if destino_tipo == "USUARIO":
            return await self._usuario(destino_id, canal)
        raise DestinatarioNoResoluble(f"Tipo de destinatario no soportado: {destino_tipo}.")

    async def _paciente(self, destino_id: uuid.UUID, canal: CanalOutbox) -> Contacto:
        paciente = (
            await self._sesion.execute(select(Paciente).where(Paciente.id == destino_id))
        ).scalar_one_or_none()
        if paciente is None:
            raise DestinatarioNoResoluble("El paciente destinatario no existe.")
        nombre = _primer_nombre(paciente.nombre)

        if canal is CanalOutbox.WHATSAPP:
            if not paciente.telefono_whatsapp:
                raise DestinatarioNoResoluble("El paciente no tiene numero de WhatsApp.")
            # Enviar a un numero no verificado es enviar a quien dijo tenerlo.
            # Se permite -- la verificacion se gana respondiendo al primer
            # mensaje -- pero las plantillas no llevan datos clinicos, asi que
            # un numero equivocado no expone informacion sensible.
            return Contacto(valor=normalizar_telefono(paciente.telefono_whatsapp), nombre=nombre)

        if canal is CanalOutbox.CORREO:
            if not paciente.correo:
                raise DestinatarioNoResoluble("El paciente no tiene correo registrado.")
            return Contacto(valor=paciente.correo, nombre=nombre)

        raise DestinatarioNoResoluble(f"Canal {canal.value} no aplicable a un paciente.")

    async def _profesional(self, destino_id: uuid.UUID, canal: CanalOutbox) -> Contacto:
        profesional = (
            await self._sesion.execute(select(Profesional).where(Profesional.id == destino_id))
        ).scalar_one_or_none()
        if profesional is None:
            raise DestinatarioNoResoluble("El profesional destinatario no existe.")
        nombre = _primer_nombre(profesional.nombre)

        if canal is CanalOutbox.WHATSAPP:
            if not profesional.telefono_whatsapp:
                raise DestinatarioNoResoluble("El profesional no tiene numero de WhatsApp.")
            return Contacto(valor=normalizar_telefono(profesional.telefono_whatsapp), nombre=nombre)
        if canal is CanalOutbox.CORREO:
            if not profesional.correo_calendario:
                raise DestinatarioNoResoluble("El profesional no tiene correo registrado.")
            return Contacto(valor=profesional.correo_calendario, nombre=nombre)

        raise DestinatarioNoResoluble(f"Canal {canal.value} no aplicable a un profesional.")

    async def _usuario(self, destino_id: uuid.UUID, canal: CanalOutbox) -> Contacto:
        usuario = (
            await self._sesion.execute(select(Usuario).where(Usuario.id == destino_id))
        ).scalar_one_or_none()
        if usuario is None:
            raise DestinatarioNoResoluble("El usuario destinatario no existe.")
        nombre = _primer_nombre(usuario.nombre)

        if canal is CanalOutbox.CORREO:
            return Contacto(valor=usuario.correo, nombre=nombre)
        if canal is CanalOutbox.WHATSAPP:
            if not usuario.telefono:
                raise DestinatarioNoResoluble("El usuario no tiene telefono registrado.")
            return Contacto(valor=normalizar_telefono(usuario.telefono), nombre=nombre)

        raise DestinatarioNoResoluble(f"Canal {canal.value} no aplicable a un usuario.")


def _primer_nombre(nombre: str) -> str:
    """Primer nombre, para encabezar el mensaje.

    «Hola Maria» en lugar de «Hola Maria Fernanda Torres Villacis». El nombre
    completo en un mensaje de WhatsApp resulta impersonal y, en la pantalla de
    bloqueo, identifica al destinatario ante quien pase al lado.
    """
    partes = nombre.strip().split()
    return partes[0] if partes else nombre.strip()


__all__ = [
    "Contacto",
    "DestinatarioNoResoluble",
    "ResolutorContacto",
    "normalizar_telefono",
]
