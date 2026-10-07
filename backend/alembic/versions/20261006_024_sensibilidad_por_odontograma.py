"""Sensibilidad N2/N3 por versión de odontograma."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_024"
down_revision: str | None = "20261006_023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "odontograma",
        sa.Column(
            "nivel_sensibilidad",
            sa.String(length=2),
            server_default=sa.text("'N2'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_odontograma_sensibilidad_valida"),
        "odontograma",
        "nivel_sensibilidad IN ('N2', 'N3')",
    )
    op.alter_column("odontograma", "nivel_sensibilidad", server_default=None)


def downgrade() -> None:
    op.drop_constraint(op.f("ck_odontograma_sensibilidad_valida"), "odontograma", type_="check")
    op.drop_column("odontograma", "nivel_sensibilidad")
