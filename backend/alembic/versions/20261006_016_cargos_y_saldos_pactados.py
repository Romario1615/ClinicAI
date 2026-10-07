"""Cargos con total pactado y pagos parciales.

Revision ID: 20261006_016
Revises: 20261006_015
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_016"
down_revision: str | None = "20261006_015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cargo_pago",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("cita_id", sa.Uuid(), nullable=False),
        sa.Column("total_acordado", sa.Numeric(12, 2), nullable=True),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("origen", sa.String(length=24), nullable=False),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "total_acordado IS NULL OR total_acordado > 0",
            name=op.f("ck_cargo_pago_total_positivo"),
        ),
        sa.CheckConstraint("moneda = 'USD'", name=op.f("ck_cargo_pago_moneda_usd")),
        sa.CheckConstraint(
            "(total_acordado IS NULL AND origen = 'HISTORICO_SIN_TOTAL') OR "
            "(total_acordado IS NOT NULL AND origen = 'PACTADO')",
            name=op.f("ck_cargo_pago_origen_coherente"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"], ["clinica.id"], name=op.f("fk_cargo_pago_clinica_id_clinica")
        ),
        sa.ForeignKeyConstraint(["cita_id"], ["cita.id"], name=op.f("fk_cargo_pago_cita_id_cita")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cargo_pago")),
        sa.UniqueConstraint("cita_id", name=op.f("uq_cargo_pago_cita")),
        sa.UniqueConstraint(
            "id", "cita_id", "clinica_id", name=op.f("uq_cargo_pago_id_cita_clinica")
        ),
    )

    # El importe registrado en un pago histórico no demuestra por sí solo el
    # total acordado. Los cargos migrados quedan expresamente sin total.
    op.execute(
        """
        INSERT INTO cargo_pago (clinica_id, cita_id, total_acordado, moneda, origen)
        SELECT DISTINCT clinica_id, cita_id, NULL::numeric(12, 2), 'USD', 'HISTORICO_SIN_TOTAL'
        FROM pago
        """
    )
    op.add_column("pago", sa.Column("cargo_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE pago AS p
        SET cargo_id = c.id
        FROM cargo_pago AS c
        WHERE c.cita_id = p.cita_id AND c.clinica_id = p.clinica_id
        """
    )
    op.drop_constraint("uq_pago_cita", "pago", type_="unique")
    op.create_index("ix_pago_cargo_estado", "pago", ["cargo_id", "estado"])
    op.create_foreign_key(
        "fk_pago_cargo_cita_clinica",
        "pago",
        "cargo_pago",
        ["cargo_id", "cita_id", "clinica_id"],
        ["id", "cita_id", "clinica_id"],
        ondelete="RESTRICT",
    )

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
    op.execute(
        """
        CREATE TRIGGER cargo_pago_total_inmutable
          BEFORE UPDATE OR DELETE ON cargo_pago
          FOR EACH ROW EXECUTE FUNCTION cargo_pago_total_inmutable();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM cargo_pago WHERE total_acordado IS NOT NULL)
             OR EXISTS (
               SELECT cita_id FROM pago GROUP BY cita_id HAVING count(*) > 1
             ) THEN
            RAISE EXCEPTION 'No se puede revertir: ya hay totales pactados o abonos múltiples.';
          END IF;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS cargo_pago_total_inmutable ON cargo_pago")
    op.execute("DROP FUNCTION IF EXISTS cargo_pago_total_inmutable()")
    op.drop_constraint("fk_pago_cargo_cita_clinica", "pago", type_="foreignkey")
    op.drop_index("ix_pago_cargo_estado", table_name="pago")
    op.drop_column("pago", "cargo_id")
    op.create_unique_constraint("uq_pago_cita", "pago", ["cita_id"])
    op.drop_table("cargo_pago")
