"""Conserva la especialidad que determina el acceso a registros históricos."""

from __future__ import annotations

import uuid

from sqlalchemy import exists, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.documentos.modelos import RegistroPaciente
from app.modulos.historia.modelos import NotaEvolucion, Receta, RespuestaAnamnesis
from app.modulos.imagenes.modelos import ImagenPaciente
from app.modulos.odontologia.modelos import (
    Formulario033,
    Odontograma,
    PlanTratamiento,
    RegistroPlaca,
)
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.errores import ConflictoEstado


async def preservar_especialidad(
    sesion: AsyncSession, profesional: Profesional, especialidad_id: uuid.UUID
) -> None:
    """Cambiar el perfil no puede trasladar historias privadas de un área a otra."""
    if profesional.especialidad_id == especialidad_id:
        return
    modelos = (
        NotaEvolucion,
        Receta,
        RespuestaAnamnesis,
        ImagenPaciente,
        Formulario033,
        Odontograma,
        PlanTratamiento,
        RegistroPlaca,
        RegistroPaciente,
    )
    registros = union_all(
        *(
            select(literal(1)).where(
                modelo.profesional_id == profesional.id, modelo.clinica_id == profesional.clinica_id
            )
            for modelo in modelos
        )
    )
    if await sesion.scalar(select(exists(registros))):
        raise ConflictoEstado(
            "La especialidad de un perfil con registros clínicos no puede cambiarse. "
            "Conserve ese perfil y cree uno para la nueva especialidad."
        )
