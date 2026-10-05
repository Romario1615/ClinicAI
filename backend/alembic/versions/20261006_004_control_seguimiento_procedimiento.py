"""Control de seguimiento posterior en procedimientos completados.

Revision ID: 20261006_004
Revises: 20261006_003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_004"
down_revision: str | None = "20261006_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "procedimiento_plan",
        sa.Column("control_recomendado_en", sa.Date(), nullable=True),
    )
    op.add_column(
        "procedimiento_plan",
        sa.Column("control_atendido_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "procedimiento_plan",
        sa.Column("control_atendido_por", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "procedimiento_plan",
        sa.Column("control_nota", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_procedimiento_plan_control_atendido_coherente"),
        "procedimiento_plan",
        "(control_atendido_en IS NULL AND control_atendido_por IS NULL) OR "
        "(control_recomendado_en IS NOT NULL AND control_atendido_en IS NOT NULL "
        "AND control_atendido_por IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_procedimiento_plan_control_atendido_coherente"),
        "procedimiento_plan",
        type_="check",
    )
    op.drop_column("procedimiento_plan", "control_nota")
    op.drop_column("procedimiento_plan", "control_atendido_por")
    op.drop_column("procedimiento_plan", "control_atendido_en")
    op.drop_column("procedimiento_plan", "control_recomendado_en")
