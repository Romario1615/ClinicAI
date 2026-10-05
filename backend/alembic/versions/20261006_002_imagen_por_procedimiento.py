"""Fotos ligadas a un procedimiento del plan de tratamiento.

Revision ID: 20261006_002
Revises: 20261006_001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261006_002"
down_revision: str | None = "20261006_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "imagen_paciente",
        sa.Column("procedimiento_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_imagen_paciente_procedimiento_id_procedimiento_plan"),
        "imagen_paciente",
        "procedimiento_plan",
        ["procedimiento_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_imagen_paciente_procedimiento",
        "imagen_paciente",
        ["procedimiento_id"],
        postgresql_where=sa.text("procedimiento_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_imagen_paciente_procedimiento", table_name="imagen_paciente")
    op.drop_constraint(
        op.f("fk_imagen_paciente_procedimiento_id_procedimiento_plan"),
        "imagen_paciente",
        type_="foreignkey",
    )
    op.drop_column("imagen_paciente", "procedimiento_id")
