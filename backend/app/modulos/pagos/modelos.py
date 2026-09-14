"""Un cobro por cita, con importe decimal y sin credenciales financieras."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class Pago(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "pago"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id"))
    cita_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cita.id"))
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    metodo: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), default="PENDING")
    referencia: Mapped[str | None] = mapped_column(String(100), default=None)
    comentario: Mapped[str | None] = mapped_column(String(500), default=None)
    validado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    validado_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("cita_id", name="uq_pago_cita"),
        CheckConstraint("importe > 0", name="importe_positivo"),
        CheckConstraint("moneda = 'USD'", name="moneda_usd"),
        CheckConstraint("metodo IN ('EFECTIVO', 'TRANSFERENCIA')", name="metodo_pago_valido"),
        CheckConstraint(
            "estado IN ('PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW', 'CONFIRMED', 'REJECTED', 'REFUND_PENDING')",
            name="estado_pago_valido",
        ),
    )
