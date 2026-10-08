"""Especialidad real del perfil vinculado; no concede permisos ni ambitos."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Especialidad
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario


async def especialidades_de_usuarios(
    sesion: AsyncSession, usuarios: Sequence[uuid.UUID], *, clinica_id: uuid.UUID | None = None
) -> dict[uuid.UUID, str]:
    """Resuelve en lote los nombres solo para las cuentas ya autorizadas.

    Los tres registros deben pertenecer a la misma clinica. Una especialidad
    ajena o un perfil inactivo/anulado no se presenta como asignacion vigente.
    """
    if not usuarios:
        return {}
    consulta = (
        select(Usuario.id, Especialidad.nombre)
        .join(Profesional, Profesional.usuario_id == Usuario.id)
        .join(Especialidad, Especialidad.id == Profesional.especialidad_id)
        .where(
            Usuario.id.in_(usuarios),
            Profesional.clinica_id == Usuario.clinica_id,
            Especialidad.clinica_id == Usuario.clinica_id,
            Profesional.activo.is_(True),
            Profesional.anulado_en.is_(None),
            Especialidad.activa.is_(True),
            Especialidad.anulado_en.is_(None),
        )
    )
    if clinica_id is not None:
        consulta = consulta.where(Usuario.clinica_id == clinica_id)
    return dict((await sesion.execute(consulta)).tuples().all())
