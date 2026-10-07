"""Fecha de vencimiento explícita por cargo.

Revision ID: 20261006_017
Revises: 20261006_016
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_017"
down_revision: str | None = "20261006_016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cargo_pago", sa.Column("fecha_vencimiento", sa.Date(), nullable=True))
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cargo_pago_total_inmutable() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Los cargos de pago no se pueden borrar.';
          END IF;
          IF OLD.total_acordado IS NULL
             AND OLD.origen = 'HISTORICO_SIN_TOTAL'
             AND NEW.total_acordado IS NOT NULL
             AND NEW.origen = 'PACTADO'
             AND OLD.creado_por IS NULL
             AND NEW.creado_por IS NOT NULL
             AND OLD.id = NEW.id
             AND OLD.clinica_id = NEW.clinica_id
             AND OLD.cita_id = NEW.cita_id
             AND OLD.moneda = NEW.moneda
             AND OLD.creado_en = NEW.creado_en
             AND (NEW.fecha_vencimiento IS NOT DISTINCT FROM OLD.fecha_vencimiento
                  OR (OLD.fecha_vencimiento IS NULL AND NEW.fecha_vencimiento IS NOT NULL)) THEN
            RETURN NEW;
          END IF;
          IF OLD.fecha_vencimiento IS NULL
             AND NEW.fecha_vencimiento IS NOT NULL
             AND NEW.total_acordado IS NOT DISTINCT FROM OLD.total_acordado
             AND NEW.origen = OLD.origen
             AND NEW.creado_por IS NOT DISTINCT FROM OLD.creado_por
             AND NEW.id = OLD.id
             AND NEW.clinica_id = OLD.clinica_id
             AND NEW.cita_id = OLD.cita_id
             AND NEW.moneda = OLD.moneda
             AND NEW.creado_en = OLD.creado_en THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'El total pactado y su vencimiento son inmutables después de fijarlos.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM cargo_pago WHERE fecha_vencimiento IS NOT NULL) THEN
            RAISE EXCEPTION 'No se puede revertir: existen cargos con fecha de vencimiento.';
          END IF;
        END;
        $$;
        """
    )
    op.drop_column("cargo_pago", "fecha_vencimiento")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION cargo_pago_total_inmutable() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Los cargos de pago no se pueden borrar.';
          END IF;
          IF OLD.total_acordado IS NULL
             AND OLD.origen = 'HISTORICO_SIN_TOTAL'
             AND NEW.total_acordado IS NOT NULL
             AND NEW.origen = 'PACTADO'
             AND OLD.creado_por IS NULL
             AND NEW.creado_por IS NOT NULL
             AND OLD.id = NEW.id
             AND OLD.clinica_id = NEW.clinica_id
             AND OLD.cita_id = NEW.cita_id
             AND OLD.moneda = NEW.moneda
             AND OLD.creado_en = NEW.creado_en THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'El total pactado es inmutable y solo se puede conciliar una vez.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
