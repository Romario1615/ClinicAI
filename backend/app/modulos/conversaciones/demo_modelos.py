import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador


class SesionDemo(Base, MezclaIdentificador):
    """Memoria administrativa por operador e hilo. Nunca almacena el texto libre."""

    __tablename__ = "sesion_agente_demo"
    conversacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversacion.id"), unique=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id"))
    negocio: Mapped[dict[str, Any]] = mapped_column(JSONB)
    memoria: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    expira_en: Mapped[datetime] = mapped_column()
