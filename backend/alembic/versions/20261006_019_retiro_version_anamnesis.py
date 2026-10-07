"""Permite conservar la fecha al retirar una plantilla publicada.

Revision ID: 20261006_019
Revises: 20261006_018
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_019"
down_revision: str | None = "20261006_018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REGLA_CORRECTA = "(estado = 'BORRADOR') = (publicada_en IS NULL)"
_REGLA_ANTERIOR = "(estado = 'PUBLICADA') = (publicada_en IS NOT NULL)"
_RESTRICCION = "ck_plantilla_anamnesis_publicada_exige_fecha"


def upgrade() -> None:
    op.drop_constraint(op.f(_RESTRICCION), "plantilla_anamnesis", type_="check")
    op.create_check_constraint(op.f(_RESTRICCION), "plantilla_anamnesis", _REGLA_CORRECTA)


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM plantilla_anamnesis WHERE estado = 'RETIRADA') THEN
            RAISE EXCEPTION 'No se puede revertir: existen versiones retiradas con historial.';
          END IF;
        END;
        $$;
        """
    )
    op.drop_constraint(op.f(_RESTRICCION), "plantilla_anamnesis", type_="check")
    op.create_check_constraint(op.f(_RESTRICCION), "plantilla_anamnesis", _REGLA_ANTERIOR)
