"""Indexa los miembros de cada serie recurrente de citas.

Revision ID: 20261007_030
Revises: 20261007_029
Create Date: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_030"
down_revision: str | None = "20261007_029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_cita_serie_recurrente",
        "cita",
        ["serie_recurrente_id"],
        unique=False,
        postgresql_where=sa.text("serie_recurrente_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_cita_serie_recurrente", table_name="cita")
