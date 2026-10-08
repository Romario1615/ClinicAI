"""Filtro SQL de autores por especialidad para registros clinicos privados."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, false, func, or_, select
from sqlalchemy.orm import aliased

from app.modulos.organizacion.modelos import Especialidad
from app.modulos.profesionales.modelos import DelegacionFirma, Profesional
from app.nucleo.autorizacion import Principal


def autores_en_ambito(principal: Principal, modulo: str | None = None) -> Select[tuple[uuid.UUID]]:
    """La propia especialidad y las concedidas expresamente, dentro de su clinica.

    El comodin no amplía las especialidades de un especialista. Los autores
    históricos pueden estar inactivos: sus registros conservan la trazabilidad.
    """
    consulta = (
        select(Profesional.id)
        .join(Especialidad, Especialidad.id == Profesional.especialidad_id)
        .where(
            Profesional.clinica_id == principal.clinica_id,
            Especialidad.clinica_id == principal.clinica_id,
        )
    )
    if principal.clinica_id is None:
        return consulta.where(false())
    if modulo in {"odontograma", "periodoncia", "planes"}:
        nombre = func.lower(func.translate(Especialidad.nombre, "áéíóúÁÉÍÓÚ", "aeiouAEIOU"))
        consulta = consulta.where(
            or_(func.upper(Especialidad.codigo).startswith("ODO"), nombre.contains("odont"))
        )
    if principal.profesional_id is not None:
        perfil = aliased(Profesional)
        propia = (
            select(perfil.especialidad_id)
            .where(
                perfil.id == principal.profesional_id,
                perfil.clinica_id == principal.clinica_id,
                perfil.activo.is_(True),
                perfil.anulado_en.is_(None),
            )
            .scalar_subquery()
        )
        return consulta.where(
            or_(
                Profesional.especialidad_id == propia,
                (Profesional.especialidad_id.in_(principal.ambito.especialidades))
                & Especialidad.activa.is_(True),
            )
        )
    if "profesional" in principal.roles:
        return consulta.where(false())
    if not principal.ambito.todas_las_especialidades:
        consulta = consulta.where(Profesional.especialidad_id.in_(principal.ambito.especialidades))
    return consulta


def firmantes_delegados(principal: Principal, ahora: datetime) -> Select[tuple[uuid.UUID]]:
    """Responsables cuya firma fue delegada expresamente y sigue vigente."""
    return (
        select(DelegacionFirma.delegante_id)
        .join(Profesional, Profesional.id == DelegacionFirma.delegante_id)
        .where(
            DelegacionFirma.clinica_id == principal.clinica_id,
            DelegacionFirma.delegado_id == principal.profesional_id,
            DelegacionFirma.revocada_en.is_(None),
            DelegacionFirma.vigente_desde <= ahora,
            DelegacionFirma.vigente_hasta > ahora,
            Profesional.clinica_id == principal.clinica_id,
            Profesional.activo.is_(True),
            Profesional.anulado_en.is_(None),
        )
    )
