"""Registra llegada del paciente e inicio de atención en una cita.

Revision ID: 20261005_005
Revises: 20261005_004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_005"
down_revision: str | None = "20261005_004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cita", sa.Column("llegada_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "cita", sa.Column("atencion_iniciada_en", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_cita_atencion_exige_llegada",
        "cita",
        "atencion_iniciada_en IS NULL OR llegada_en IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cita_atencion_exige_llegada", "cita", type_="check")
    op.drop_column("cita", "atencion_iniciada_en")
    op.drop_column("cita", "llegada_en")
