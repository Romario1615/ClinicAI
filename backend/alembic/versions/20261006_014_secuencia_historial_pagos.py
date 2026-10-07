"""secuencia estable del historial de pagos

Revision ID: 20261006_014
Revises: 20261006_013
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_014"
down_revision: str | None = "20261006_013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pago_historial",
        sa.Column("secuencia", sa.Integer(), server_default="1", nullable=False),
    )
    op.alter_column("pago_historial", "secuencia", server_default=None)
    op.drop_index("ix_pago_historial_pago", table_name="pago_historial")
    op.create_index("ix_pago_historial_pago", "pago_historial", ["pago_id", "secuencia"])
    op.create_unique_constraint(
        "uq_pago_historial_secuencia", "pago_historial", ["pago_id", "secuencia"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_pago_historial_secuencia", "pago_historial", type_="unique")
    op.drop_index("ix_pago_historial_pago", table_name="pago_historial")
    op.create_index(
        "ix_pago_historial_pago",
        "pago_historial",
        ["pago_id", "ocurrido_en", "id"],
    )
    op.drop_column("pago_historial", "secuencia")
