"""Limita y conserva la profundidad de reagendamientos en cadena.

Revision ID: 20261006_003
Revises: 20261006_002
Fecha: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_003"
down_revision: str | None = "20261006_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cita",
        sa.Column(
            "cadena_lista_espera_id",
            sa.Uuid(),
            nullable=True,
            comment="Identificador de la cadena de reagendamientos desde lista de espera",
        ),
    )
    op.add_column(
        "cita",
        sa.Column(
            "profundidad_lista_espera",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Máximo: 5 eslabones de horarios liberados",
        ),
    )
    op.create_check_constraint(
        op.f("ck_cita_profundidad_lista_espera_valida"),
        "cita",
        "profundidad_lista_espera >= 0 AND profundidad_lista_espera <= 6",
    )
    op.create_index(
        "ix_cita_cadena_lista_espera",
        "cita",
        ["cadena_lista_espera_id", "profundidad_lista_espera"],
        postgresql_where=sa.text("cadena_lista_espera_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_cita_cadena_lista_espera", table_name="cita")
    op.drop_constraint(op.f("ck_cita_profundidad_lista_espera_valida"), "cita", type_="check")
    op.drop_column("cita", "profundidad_lista_espera")
    op.drop_column("cita", "cadena_lista_espera_id")
