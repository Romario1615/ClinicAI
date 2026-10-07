"""Clasifica reportes explicitos de problemas de tratamiento para derivacion.

Revision ID: 20261006_010
Revises: 20261006_009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_010"
down_revision: str | None = "20261006_009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"), "mensaje_entrante", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"),
        "mensaje_entrante",
        "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', "
        "'PROBLEMA_TRATAMIENTO', 'BAJA', 'BAJA_PROMOCIONES', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
    )


def downgrade() -> None:
    # La intencion clasificada deja de existir en el esquema anterior. El
    # texto original y el motivo del hilo se conservan para el personal.
    op.execute(
        "UPDATE mensaje_entrante SET intencion = 'DESCONOCIDA' "
        "WHERE intencion = 'PROBLEMA_TRATAMIENTO'"
    )
    op.drop_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"), "mensaje_entrante", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"),
        "mensaje_entrante",
        "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', "
        "'BAJA', 'BAJA_PROMOCIONES', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
    )
