"""Fotos privadas asociadas a un registro validado en una lista cerrada."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAnulacion, MezclaAuditoria, MezclaIdentificador


class FotoRegistro(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    __tablename__ = "foto_registro"
    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    tipo_registro: Mapped[str] = mapped_column(String(32))
    registro_id: Mapped[uuid.UUID] = mapped_column()
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paciente.id", ondelete="RESTRICT"), default=None
    )
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2))
    clave_objeto: Mapped[str] = mapped_column(String(300), unique=True)
    tipo_mime: Mapped[str] = mapped_column(String(32))
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    descripcion: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        Index("ix_foto_registro_destino", "clinica_id", "tipo_registro", "registro_id"),
        CheckConstraint(
            "nivel_sensibilidad IN ('N1','N2','N3') OR (tipo_registro = 'conocimiento' AND nivel_sensibilidad = 'N0')",
            name="sensibilidad_valida",
        ),
        CheckConstraint("tamano_bytes > 0", name="tamano_positivo"),
    )
