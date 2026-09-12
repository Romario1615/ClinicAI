"""Esquemas de entrada y salida del calendario.

Los de salida son explicitos y **nunca** incluyen los tokens, ni cifrados.
Un token cifrado en una respuesta HTTP sigue siendo material sensible en un
log de acceso, en la cache de un proxy y en el historial del navegador.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RespuestaConexion(BaseModel):
    """Estado de una conexion de calendario, sin material sensible."""

    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    proveedor: str
    calendar_id: str
    estado_sincronizacion: str
    ultima_sincronizacion_en: datetime | None
    # Se expone si el token esta a punto de caducar, no el token.
    expira_en: datetime | None
    alcances: str | None
    # Mensaje para el profesional, no la traza del proveedor.
    ultimo_error: str | None


class PaginaConexiones(BaseModel):
    elementos: list[RespuestaConexion]
    total: int


class SolicitudInicioOauth(BaseModel):
    """Peticion para iniciar la autorizacion de un calendario."""

    # El calendario al que conectarse. `primary` es el calendario principal
    # de la cuenta y es el caso habitual.
    calendar_id: str = Field(default="primary", min_length=1, max_length=255)


class RespuestaInicioOauth(BaseModel):
    """URL a la que hay que enviar al profesional.

    El `state` va dentro de la URL. No se devuelve aparte para que ningun
    cliente lo guarde ni lo reutilice: es de un solo uso.
    """

    url_autorizacion: str
    expira_en: datetime


class SolicitudDesconexion(BaseModel):
    motivo: str = Field(min_length=5, max_length=255)


class RespuestaSincronizacion(BaseModel):
    """Resultado de una sincronizacion, para el panel."""

    creados: int
    actualizados: int
    eliminados: int
    recreados: int
    conflictos: int
    reintentables: int
    errores: int


class RespuestaEventoCalendario(BaseModel):
    """Evento de calendario. **No** incluye datos de la cita.

    Ni paciente, ni servicio, ni motivo: este endpoint sirve para diagnosticar
    la sincronizacion, y para eso basta el estado (RF-I09).
    """

    id: uuid.UUID
    cita_id: uuid.UUID
    estado: str
    external_event_id: str | None
    sincronizado_en: datetime | None
    intentos: int
    ultimo_error: str | None


class PaginaEventos(BaseModel):
    elementos: list[RespuestaEventoCalendario]
    total: int


__all__ = [
    "PaginaConexiones",
    "PaginaEventos",
    "RespuestaConexion",
    "RespuestaEventoCalendario",
    "RespuestaInicioOauth",
    "RespuestaSincronizacion",
    "SolicitudDesconexion",
    "SolicitudInicioOauth",
]
