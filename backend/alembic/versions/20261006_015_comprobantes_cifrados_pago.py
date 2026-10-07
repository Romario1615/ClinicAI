"""Comprobantes de pago cifrados, escaneados e inmutables.

Revision ID: 20261006_015
Revises: 20261006_014
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_015"
down_revision: str | None = "20261006_014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pago_comprobante",
        sa.Column("pago_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_mime", sa.String(length=32), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("clave_objeto", sa.String(length=300), nullable=False),
        sa.Column("antivirus", sa.String(length=16), nullable=False),
        sa.Column("cargado_por", sa.Uuid(), nullable=False),
        sa.Column(
            "cargado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("tamano_bytes > 0", name=op.f("ck_pago_comprobante_tamano_positivo")),
        sa.CheckConstraint(
            "tipo_mime IN ('application/pdf', 'image/jpeg', 'image/png', 'image/webp')",
            name=op.f("ck_pago_comprobante_tipo_valido"),
        ),
        sa.CheckConstraint(
            "antivirus IN ('LIMPIO', 'NO_DISPONIBLE')",
            name=op.f("ck_pago_comprobante_antivirus_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["pago_id"],
            ["pago.id"],
            ondelete="RESTRICT",
            name=op.f("fk_pago_comprobante_pago_id_pago"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pago_comprobante")),
        sa.UniqueConstraint("clave_objeto", name=op.f("uq_pago_comprobante_clave_objeto")),
    )
    op.create_index(
        "ix_pago_comprobante_pago_fecha", "pago_comprobante", ["pago_id", "cargado_en", "id"]
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION pago_comprobante_sin_modificacion() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Los comprobantes de pago son inmutables.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pago_comprobante_sin_modificacion
          BEFORE UPDATE OR DELETE ON pago_comprobante
          FOR EACH ROW EXECUTE FUNCTION pago_comprobante_sin_modificacion();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS pago_comprobante_sin_modificacion ON pago_comprobante")
    op.execute("DROP FUNCTION IF EXISTS pago_comprobante_sin_modificacion()")
    op.drop_index("ix_pago_comprobante_pago_fecha", table_name="pago_comprobante")
    op.drop_table("pago_comprobante")
