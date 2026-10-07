"""Impide vaciar la auditoría con TRUNCATE.

Revision ID: 20261006_028
Revises: 20261006_027
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_028"
down_revision: str | None = "20261006_027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER auditoria_sin_vaciado "
        "BEFORE TRUNCATE ON auditoria "
        "FOR EACH STATEMENT EXECUTE FUNCTION tabla_solo_insercion()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS auditoria_sin_vaciado ON auditoria")
