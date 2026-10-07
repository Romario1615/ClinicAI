"""Sensibilidad por receta clínica.

Revision ID: 20261006_023
Revises: 20261006_022
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_023"
down_revision: str | None = "20261006_022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receta",
        sa.Column(
            "nivel_sensibilidad",
            sa.String(length=2),
            server_default=sa.text("'N2'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_receta_sensibilidad_valida"),
        "receta",
        "nivel_sensibilidad IN ('N2', 'N3')",
    )
    op.alter_column("receta", "nivel_sensibilidad", server_default=None)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_receta_sensibilidad_valida"), "receta", type_="check")
    op.drop_column("receta", "nivel_sensibilidad")
