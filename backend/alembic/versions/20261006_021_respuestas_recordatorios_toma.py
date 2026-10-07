"""Posposición de recordatorios y respuestas de adherencia por WhatsApp.

Revision ID: 20261006_021
Revises: 20261006_020
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_021"
down_revision: str | None = "20261006_020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "toma",
        sa.Column("recordatorio_diferido_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"), "mensaje_entrante", type_="check"
    )
    op.create_check_constraint(
        "intencion_valida",
        "mensaje_entrante",
        "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', "
        "'RECORDAR_TOMA_DESPUES', 'NO_PUDO_TOMAR', 'PROBLEMA_TRATAMIENTO', 'BAJA', "
        "'BAJA_PROMOCIONES', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM mensaje_entrante
            WHERE intencion IN ('RECORDAR_TOMA_DESPUES', 'NO_PUDO_TOMAR')
          ) THEN
            RAISE EXCEPTION 'No se puede revertir: existen respuestas de toma nuevas.';
          END IF;
        END;
        $$;
        """
    )
    op.drop_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"), "mensaje_entrante", type_="check"
    )
    op.create_check_constraint(
        "intencion_valida",
        "mensaje_entrante",
        "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', "
        "'PROBLEMA_TRATAMIENTO', 'BAJA', 'BAJA_PROMOCIONES', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
    )
    op.drop_column("toma", "recordatorio_diferido_en")
