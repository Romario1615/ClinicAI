"""Dependencias de lectura clínica que ocultan recursos protegidos con 404."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.nucleo.autorizacion import Principal
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.dependencias import PrincipalActual, exige_permiso, obtener_gestor_bd
from app.nucleo.errores import PermisoDenegado, RecursoNoEncontrado


async def exigir_lectura_historia_discreta(
    peticion: Request,
    principal: PrincipalActual,
    gestor: Annotated[GestorBaseDatos, Depends(obtener_gestor_bd)],
) -> Principal:
    """Oculta con 404 la historia a quien carece del permiso clínico de lectura.

    Reutiliza el control normal de permiso y su auditoría de denegación. Un
    rol sin acceso clínico no puede distinguir una ficha real de un ID ajeno.
    """
    try:
        return await exige_permiso("historia_clinica.leer")(peticion, principal, gestor)
    except PermisoDenegado as exc:
        raise RecursoNoEncontrado("El paciente solicitado no existe.") from exc


PuedeLeerHistoriaDiscreta = Annotated[Principal, Depends(exigir_lectura_historia_discreta)]


__all__ = ["PuedeLeerHistoriaDiscreta", "exigir_lectura_historia_discreta"]
