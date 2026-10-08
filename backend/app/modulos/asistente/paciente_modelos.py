"""Memoria operativa privada por paciente y operador, sin transcripción clínica."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador


class SesionAgentePaciente(Base, MezclaIdentificador):
    __tablename__ = "sesion_agente_paciente"
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    negocio: Mapped[dict[str, Any]] = mapped_column(JSONB)
    memoria: Mapped[dict[str, Any]] = mapped_column(JSONB)
    propuesta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    creado_en: Mapped[datetime] = mapped_column()
    expira_en: Mapped[datetime] = mapped_column()
    __table_args__ = (
        Index("ix_sesion_agente_paciente_operador", "clinica_id", "usuario_id", "paciente_id"),
    )
