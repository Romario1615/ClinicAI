"""Sesiones del agente interno, aisladas por paciente y operador."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_035"
down_revision: str | None = "20261008_034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sesion_agente_paciente",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "clinica_id",
            sa.Uuid(),
            sa.ForeignKey("clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            sa.Uuid(),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "paciente_id",
            sa.Uuid(),
            sa.ForeignKey("paciente.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("negocio", postgresql.JSONB(), nullable=False),
        sa.Column("memoria", postgresql.JSONB(), nullable=False),
        sa.Column("propuesta", postgresql.JSONB(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_sesion_agente_paciente_operador",
        "sesion_agente_paciente",
        ["clinica_id", "usuario_id", "paciente_id"],
    )


def downgrade() -> None:
    op.drop_table("sesion_agente_paciente")
