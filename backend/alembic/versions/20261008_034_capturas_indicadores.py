"""Capturas diarias de indicadores por actor y ámbito para aprender estados."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_034"
down_revision: str | None = "20261008_033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "captura_indicadores",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "clinica_id",
            sa.Uuid(),
            sa.ForeignKey("clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("ambito_hash", sa.String(64), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("capturado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valores", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("clinica_id", "actor_id", "ambito_hash", "fecha"),
    )


def downgrade() -> None:
    op.drop_table("captura_indicadores")
