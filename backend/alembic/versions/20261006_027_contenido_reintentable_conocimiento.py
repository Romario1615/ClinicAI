"""Conserva temporalmente el texto para reintentar ingestas fallidas."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_027"
down_revision: str | None = "20261006_026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("knowledge_versions", sa.Column("contenido_texto", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_versions", "contenido_texto")
