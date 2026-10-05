"""Indicaciones después de la consulta, entregadas por enlace seguro.

El profesional escribe lo que el paciente debe hacer tras la consulta
(cuidados, signos de alarma, cuándo volver) y, si aplica, lo liga a la receta
confirmada. El paciente no recibe ese texto por WhatsApp (CLAUDE.md, regla
10): recibe un aviso genérico con un enlace que caduca y que exige confirmar
su identidad antes de mostrar nada.

* Se guarda el **hash** del token, nunca el token: con una copia de la base
  no se puede abrir ningún enlace.
* Append-only: una corrección es una indicación nueva; la anterior se anula
  con motivo y deja de abrirse, pero no se borra.
* Cinco verificaciones fallidas bloquean el enlace.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador

MAXIMO_INTENTOS = 5


class IndicacionPostconsulta(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "indicacion_postconsulta"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    cita_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="RESTRICT"), default=None
    )
    receta_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("receta.id", ondelete="RESTRICT"), default=None
    )
    texto: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expira_en: Mapped[datetime] = mapped_column()
    intentos_fallidos: Mapped[int] = mapped_column(SmallInteger, default=0)
    bloqueada: Mapped[bool] = mapped_column(Boolean, default=False)
    lecturas: Mapped[int] = mapped_column(SmallInteger, default=0)
    primera_lectura_en: Mapped[datetime | None] = mapped_column(default=None)
    ultima_lectura_en: Mapped[datetime | None] = mapped_column(default=None)
    anulada_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_anulacion: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint("length(texto) BETWEEN 10 AND 4000", name="texto_acotado"),
        CheckConstraint(
            "anulada_en IS NULL OR motivo_anulacion IS NOT NULL", name="anulacion_con_motivo"
        ),
        Index("ix_indicacion_postconsulta_paciente", "paciente_id", "creado_en"),
    )


__all__ = ["MAXIMO_INTENTOS", "IndicacionPostconsulta"]
