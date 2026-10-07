"""Gasto: una salida de dinero de la clinica, inmutable salvo su anulacion.

Por que no se edita un gasto
----------------------------
Un libro de egresos que se puede reescribir no sirve para conciliar: el
saldo de ayer cambiaria sin dejar rastro. Como en la historia clinica y en
los pagos, la correccion es explicita: se anula el gasto erroneo con un
motivo y se registra uno nuevo. Un disparador de PostgreSQL lo garantiza
tambien frente a una sentencia SQL directa (ver la migracion 029).

Un gasto sin sede es de toda la clinica (arriendo de la oficina central,
nomina comun). Solo lo ve quien tiene ambito sobre todas las sedes.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador

CATEGORIAS_GASTO: tuple[str, ...] = (
    "INSUMOS",
    "LABORATORIO",
    "NOMINA",
    "HONORARIOS",
    "ARRIENDO",
    "SERVICIOS_BASICOS",
    "MANTENIMIENTO",
    "EQUIPAMIENTO",
    "MARKETING",
    "IMPUESTOS",
    "OTROS",
)
METODOS_GASTO: tuple[str, ...] = ("EFECTIVO", "TRANSFERENCIA", "TARJETA")
ESTADOS_GASTO: tuple[str, ...] = ("REGISTRADO", "ANULADO")


def _lista_sql(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{valor}'" for valor in valores)


class Gasto(Base, MezclaIdentificador):
    __tablename__ = "gasto"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id"), nullable=False)
    sede_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sede.id"), default=None)
    # Dia local en que se pago: es el dato del comprobante, no la hora del
    # registro, y por eso no se guarda como instante.
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    categoria: Mapped[str] = mapped_column(String(24), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    proveedor: Mapped[str | None] = mapped_column(String(200), default=None)
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    metodo: Mapped[str] = mapped_column(String(20), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(100), default=None)
    estado: Mapped[str] = mapped_column(String(12), default="REGISTRADO", nullable=False)
    creado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
    anulado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    anulado_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(500), default=None)

    __table_args__ = (
        CheckConstraint("importe > 0", name="importe_positivo"),
        CheckConstraint("moneda = 'USD'", name="moneda_usd"),
        CheckConstraint(f"categoria IN ({_lista_sql(CATEGORIAS_GASTO)})", name="categoria_valida"),
        CheckConstraint(f"metodo IN ({_lista_sql(METODOS_GASTO)})", name="metodo_valido"),
        CheckConstraint(f"estado IN ({_lista_sql(ESTADOS_GASTO)})", name="estado_valido"),
        CheckConstraint("length(btrim(descripcion)) > 0", name="descripcion_no_vacia"),
        # Una anulacion siempre lleva quien, cuando y por que; un gasto
        # vigente no lleva ninguno de los tres.
        CheckConstraint(
            "(estado = 'REGISTRADO' AND anulado_en IS NULL AND anulado_por IS NULL "
            "AND motivo_anulacion IS NULL) OR "
            "(estado = 'ANULADO' AND anulado_en IS NOT NULL AND anulado_por IS NOT NULL "
            "AND length(btrim(motivo_anulacion)) > 0)",
            name="anulacion_coherente",
        ),
        Index("ix_gasto_clinica_fecha", "clinica_id", "fecha"),
        Index("ix_gasto_sede_fecha", "sede_id", "fecha"),
    )
