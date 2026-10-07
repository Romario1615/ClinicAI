from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class RegistroPaciente(Base, MezclaIdentificador, MezclaAuditoria):
    """Una versión inmutable: facial, presupuesto, cotización o receta emitida."""

    __tablename__ = "registro_paciente"
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    cita_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="RESTRICT"), default=None
    )
    especialidad_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("especialidad.id", ondelete="RESTRICT")
    )
    sede_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sede.id", ondelete="RESTRICT"), default=None
    )
    raiz_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    tipo: Mapped[str] = mapped_column(String(16))
    titulo: Mapped[str] = mapped_column(String(200))
    contenido: Mapped[dict[str, object]] = mapped_column(JSONB)
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2), default="N2")
    motivo: Mapped[str] = mapped_column(Text)
    anulado: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("raiz_id", "version"),
        Index(
            "uq_registro_paciente_vigente", "raiz_id", unique=True, postgresql_where=text("vigente")
        ),
        Index("ix_registro_paciente_contexto", "clinica_id", "paciente_id", "especialidad_id"),
        CheckConstraint("version >= 1", name="version_positiva"),
        CheckConstraint(
            "tipo IN ('FACIOGRAMA', 'PRESUPUESTO', 'COTIZACION', 'RECETA')", name="tipo_valido"
        ),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        CheckConstraint("length(motivo) >= 5", name="motivo_obligatorio"),
    )


class EntregaDocumento(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "entrega_documento"
    registro_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registro_paciente.id", ondelete="RESTRICT")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expira_en: Mapped[datetime] = mapped_column()
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    anulada: Mapped[bool] = mapped_column(Boolean, default=False)
    outbox_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbox_mensaje.id", ondelete="RESTRICT"), default=None
    )
    clave_idempotencia: Mapped[str] = mapped_column(String(64), unique=True)
    # El token solo se conserva cifrado para devolver el mismo enlace en un reintento.
    token_cifrado: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("intentos_fallidos >= 0", name="intentos_no_negativos"),)
