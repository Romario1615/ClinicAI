"""Plantillas de planes de tratamiento por clinica.

Catalogo reutilizable; se retiran con motivo y no se borran. El nombre es
unico solo entre las vigentes (indice parcial).

Revision ID: 20261005_006
Revises: 20261005_005
Fecha: 2026-10-05 14:40:36.834903+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261005_006"
down_revision: str | None = "20261005_005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plantilla_plan",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("procedimientos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_por", sa.Uuid(), nullable=True),
        sa.Column("motivo_anulacion", sa.String(), nullable=True),
        sa.CheckConstraint(
            "jsonb_typeof(procedimientos) = 'array' AND jsonb_array_length(procedimientos) > 0",
            name=op.f("ck_plantilla_plan_con_procedimientos"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_plantilla_plan_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plantilla_plan")),
    )
    op.create_index(
        "uq_plantilla_plan_nombre_vigente",
        "plantilla_plan",
        ["clinica_id", "nombre"],
        unique=True,
        postgresql_where=sa.text("anulado_en IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_plantilla_plan_nombre_vigente",
        table_name="plantilla_plan",
        postgresql_where=sa.text("anulado_en IS NULL"),
    )
    op.drop_table("plantilla_plan")
