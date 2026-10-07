"""Cargos por cita y pagos parciales, sin credenciales financieras."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class CargoPago(Base, MezclaIdentificador):
    """Total y vencimiento pactados de una cita; los cargos antiguos pueden ser desconocidos."""

    __tablename__ = "cargo_pago"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id"), nullable=False)
    cita_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cita.id"), nullable=False)
    total_acordado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, default=None)
    moneda: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    origen: Mapped[str] = mapped_column(String(24), nullable=False)
    creado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        UniqueConstraint("cita_id", name="uq_cargo_pago_cita"),
        UniqueConstraint("id", "cita_id", "clinica_id", name="uq_cargo_pago_id_cita_clinica"),
        CheckConstraint("total_acordado IS NULL OR total_acordado > 0", name="total_positivo"),
        CheckConstraint("moneda = 'USD'", name="moneda_usd"),
        CheckConstraint(
            "(total_acordado IS NULL AND origen = 'HISTORICO_SIN_TOTAL') OR "
            "(total_acordado IS NOT NULL AND origen = 'PACTADO')",
            name="origen_coherente",
        ),
    )


class Pago(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "pago"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id"))
    cita_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cita.id"))
    cargo_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    metodo: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), default="PENDING")
    referencia: Mapped[str | None] = mapped_column(String(100), default=None)
    comentario: Mapped[str | None] = mapped_column(String(500), default=None)
    validado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    validado_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        ForeignKeyConstraint(
            ["cargo_id", "cita_id", "clinica_id"],
            ["cargo_pago.id", "cargo_pago.cita_id", "cargo_pago.clinica_id"],
            name="fk_pago_cargo_cita_clinica",
            ondelete="RESTRICT",
        ),
        Index("ix_pago_cargo_estado", "cargo_id", "estado"),
        CheckConstraint("importe > 0", name="importe_positivo"),
        CheckConstraint("moneda = 'USD'", name="moneda_usd"),
        CheckConstraint("metodo IN ('EFECTIVO', 'TRANSFERENCIA')", name="metodo_pago_valido"),
        CheckConstraint(
            "estado IN ('PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW', 'CONFIRMED', 'REJECTED', 'REFUND_PENDING')",
            name="estado_pago_valido",
        ),
    )


class PagoHistorial(Base, MezclaIdentificador):
    """Registro inmutable de cada estado y su explicación administrativa."""

    __tablename__ = "pago_historial"

    pago_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pago.id", ondelete="RESTRICT"), nullable=False
    )
    estado_anterior: Mapped[str | None] = mapped_column(String(20), default=None)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text, default=None)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        Index("ix_pago_historial_pago", "pago_id", "secuencia"),
        UniqueConstraint("pago_id", "secuencia", name="uq_pago_historial_secuencia"),
        CheckConstraint(
            "estado_anterior IS NULL OR estado_anterior IN "
            "('PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW', 'CONFIRMED', 'REJECTED', 'REFUND_PENDING')",
            name="estado_anterior_valido",
        ),
        CheckConstraint(
            "estado_nuevo IN "
            "('PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW', 'CONFIRMED', 'REJECTED', 'REFUND_PENDING')",
            name="estado_nuevo_valido",
        ),
    )


class PagoComprobante(Base, MezclaIdentificador):
    """Metadatos inmutables de un comprobante almacenado de forma cifrada."""

    __tablename__ = "pago_comprobante"

    pago_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pago.id", ondelete="RESTRICT"), nullable=False
    )
    tipo_mime: Mapped[str] = mapped_column(String(32), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    clave_objeto: Mapped[str] = mapped_column(String(300), nullable=False)
    antivirus: Mapped[str] = mapped_column(String(16), nullable=False)
    cargado_por: Mapped[uuid.UUID] = mapped_column(nullable=False)
    cargado_en: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)

    __table_args__ = (
        UniqueConstraint("clave_objeto", name="uq_pago_comprobante_clave_objeto"),
        CheckConstraint("tamano_bytes > 0", name="tamano_positivo"),
        CheckConstraint(
            "tipo_mime IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')",
            name="tipo_valido",
        ),
        CheckConstraint("antivirus IN ('LIMPIO', 'NO_DISPONIBLE')", name="antivirus_valido"),
        Index("ix_pago_comprobante_pago_fecha", "pago_id", "cargado_en", "id"),
    )
