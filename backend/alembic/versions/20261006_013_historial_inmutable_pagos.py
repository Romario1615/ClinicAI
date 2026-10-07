"""historial inmutable de pagos

Revision ID: 20261006_013
Revises: 20261006_012
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_013"
down_revision: str | None = "20261006_012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pago_historial",
        sa.Column("pago_id", sa.Uuid(), nullable=False),
        sa.Column("estado_anterior", sa.String(length=20), nullable=True),
        sa.Column("estado_nuevo", sa.String(length=20), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "ocurrido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "estado_anterior IS NULL OR estado_anterior IN "
            "('PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW', 'CONFIRMED', 'REJECTED', 'REFUND_PENDING')",
            name=op.f("ck_pago_historial_estado_anterior_valido"),
        ),
        sa.CheckConstraint(
            "estado_nuevo IN "
            "('PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW', 'CONFIRMED', 'REJECTED', 'REFUND_PENDING')",
            name=op.f("ck_pago_historial_estado_nuevo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["pago_id"],
            ["pago.id"],
            ondelete="RESTRICT",
            name=op.f("fk_pago_historial_pago_id_pago"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pago_historial")),
    )
    op.create_index("ix_pago_historial_pago", "pago_historial", ["pago_id", "ocurrido_en", "id"])
    op.execute(
        """
        INSERT INTO pago_historial (
          pago_id, estado_anterior, estado_nuevo, comentario
        )
        SELECT id, NULL, estado, NULL
        FROM pago
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pago_historial_sin_modificacion() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'El historial de pagos es inmutable.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pago_historial_sin_modificacion
          BEFORE UPDATE OR DELETE ON pago_historial
          FOR EACH ROW EXECUTE FUNCTION pago_historial_sin_modificacion();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS pago_historial_sin_modificacion ON pago_historial")
    op.execute("DROP FUNCTION IF EXISTS pago_historial_sin_modificacion()")
    op.drop_index("ix_pago_historial_pago", table_name="pago_historial")
    op.drop_table("pago_historial")
