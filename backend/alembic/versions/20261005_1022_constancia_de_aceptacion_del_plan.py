"""Constancia de la aceptacion del plan de tratamiento por el paciente.

Un plan solo pasa a ACEPTADO con medio, referencia del documento firmado y
fecha. La restriccion lo exige en el motor.

Revision ID: 20261005_003
Revises: 20261005_002
Fecha: 2026-10-05 10:22:46.786497+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_003"
down_revision: str | None = "20261005_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plan_tratamiento", sa.Column("aceptacion_medio", sa.String(length=24), nullable=True)
    )
    op.add_column(
        "plan_tratamiento", sa.Column("aceptacion_referencia", sa.String(length=200), nullable=True)
    )
    op.add_column("plan_tratamiento", sa.Column("aceptacion_imagen_id", sa.Uuid(), nullable=True))
    op.add_column(
        "plan_tratamiento", sa.Column("aceptacion_registrada_por", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_plan_tratamiento_aceptacion_imagen_id_imagen_paciente"),
        "plan_tratamiento",
        "imagen_paciente",
        ["aceptacion_imagen_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_plan_tratamiento_aceptacion_con_constancia"),
        "plan_tratamiento",
        "estado NOT IN ('ACEPTADO', 'COMPLETADO') "
        "OR (aceptado_en IS NOT NULL AND aceptacion_medio IS NOT NULL "
        "AND aceptacion_referencia IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_plan_tratamiento_aceptacion_con_constancia"), "plan_tratamiento", type_="check"
    )
    op.drop_constraint(
        op.f("fk_plan_tratamiento_aceptacion_imagen_id_imagen_paciente"),
        "plan_tratamiento",
        type_="foreignkey",
    )
    op.drop_column("plan_tratamiento", "aceptacion_registrada_por")
    op.drop_column("plan_tratamiento", "aceptacion_imagen_id")
    op.drop_column("plan_tratamiento", "aceptacion_referencia")
    op.drop_column("plan_tratamiento", "aceptacion_medio")
