"""Controles y correcciones append-only, protegidos también en PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class Periodontograma(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "periodontograma"
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    especialidad_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("especialidad.id", ondelete="RESTRICT")
    )
    sede_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sede.id", ondelete="RESTRICT"))
    cita_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cita.id", ondelete="RESTRICT"))
    raiz_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    fecha_examen: Mapped[date] = mapped_column()
    piezas: Mapped[dict[str, Any]] = mapped_column(JSONB)
    observaciones: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str] = mapped_column(String(500))
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2))
    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    solicitud_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("raiz_id", "version"),
        CheckConstraint("version >= 1", name="version_positiva"),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        CheckConstraint("length(trim(motivo)) >= 8", name="motivo_obligatorio"),
        Index("ix_periodontograma_ambito", "clinica_id", "paciente_id", "profesional_id"),
    )
