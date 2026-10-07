"""Nivel de sensibilidad por versión de nota clínica.

Revision ID: 20261006_022
Revises: 20261006_021
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_022"
down_revision: str | None = "20261006_021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nota_evolucion",
        sa.Column(
            "nivel_sensibilidad",
            sa.String(length=2),
            server_default=sa.text("'N2'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_nota_evolucion_sensibilidad_valida"),
        "nota_evolucion",
        "nivel_sensibilidad IN ('N2', 'N3')",
    )
    op.alter_column("nota_evolucion", "nivel_sensibilidad", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_nota_evolucion_sensibilidad_valida"),
        "nota_evolucion",
        type_="check",
    )
    op.drop_column("nota_evolucion", "nivel_sensibilidad")
