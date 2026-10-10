"""Configuracion OAuth por clinica; una desactivacion nunca usa claves globales."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.proveedores_clinica import descifrar, leer_integracion
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import ProveedorExternoNoDisponible
from app.nucleo.seguridad import CifradorDatos


@dataclass(frozen=True, slots=True)
class ParametrosGoogle:
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    scopes: str


async def parametros_google(
    sesion: AsyncSession,
    clinica_id: uuid.UUID,
    configuracion: Configuracion,
    cifrador: CifradorDatos,
) -> ParametrosGoogle:
    integracion = await leer_integracion(sesion, clinica_id, "google_calendar")
    if integracion is not None:
        if not integracion.habilitada:
            raise ProveedorExternoNoDisponible(
                "Google Calendar esta desactivado para esta clinica."
            )
        ajustes = integracion.ajustes
        parametros = ParametrosGoogle(
            client_id=str(ajustes.get("client_id") or ""),
            client_secret=descifrar(
                cifrador, clinica_id, "google_calendar", "client_secret", integracion
            )
            or "",
            redirect_uri=str(ajustes.get("redirect_uri") or configuracion.google_redirect_uri),
            scopes=str(ajustes.get("scopes") or configuracion.google_scopes),
        )
    else:
        parametros = ParametrosGoogle(
            configuracion.google_client_id,
            configuracion.google_client_secret.get_secret_value(),
            configuracion.google_redirect_uri,
            configuracion.google_scopes,
        )
    if not parametros.client_id or not parametros.client_secret:
        raise ProveedorExternoNoDisponible(
            "Configure las credenciales de Google Calendar en Integraciones."
        )
    return parametros
