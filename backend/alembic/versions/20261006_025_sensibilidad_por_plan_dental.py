"""Sensibilidad N2/N3 por plan de tratamiento dental."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_025"
down_revision: str | None = "20261006_024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "plan_tratamiento",
        sa.Column(
            "nivel_sensibilidad",
            sa.String(length=2),
            server_default=sa.text("'N2'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_plan_tratamiento_sensibilidad_valida"),
        "plan_tratamiento",
        "nivel_sensibilidad IN ('N2', 'N3')",
    )
    op.alter_column("plan_tratamiento", "nivel_sensibilidad", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_plan_tratamiento_sensibilidad_valida"), "plan_tratamiento", type_="check"
    )
    op.drop_column("plan_tratamiento", "nivel_sensibilidad")
