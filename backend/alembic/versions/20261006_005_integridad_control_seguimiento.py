"""Refuerza la coherencia del control posterior.

Revision ID: 20261006_005
Revises: 20261006_004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_005"
down_revision: str | None = "20261006_004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

_RESTRICCION = "ck_procedimiento_plan_control_atendido_coherente"


def upgrade() -> None:
    op.drop_constraint(op.f(_RESTRICCION), "procedimiento_plan", type_="check")
    op.create_check_constraint(
        op.f(_RESTRICCION),
        "procedimiento_plan",
        "(control_recomendado_en IS NULL OR estado = 'COMPLETADO') AND "
        "(control_nota IS NULL OR (control_recomendado_en IS NOT NULL "
        "AND control_atendido_en IS NOT NULL)) AND "
        "((control_atendido_en IS NULL AND control_atendido_por IS NULL) OR "
        "(control_recomendado_en IS NOT NULL AND control_atendido_en IS NOT NULL "
        "AND control_atendido_por IS NOT NULL))",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(_RESTRICCION), "procedimiento_plan", type_="check")
    op.create_check_constraint(
        op.f(_RESTRICCION),
        "procedimiento_plan",
        "(control_atendido_en IS NULL AND control_atendido_por IS NULL) OR "
        "(control_recomendado_en IS NOT NULL AND control_atendido_en IS NOT NULL "
        "AND control_atendido_por IS NOT NULL)",
    )
