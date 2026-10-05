"""Vincula una cita vigente a una entrada de lista de espera.

Revision ID: 20261006_001
Revises: 20261005_008
Fecha: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_001"
down_revision: str | None = "20261005_008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lista_espera", sa.Column("cita_previa_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_lista_espera_cita_previa_id_cita"),
        "lista_espera",
        "cita",
        ["cita_previa_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_espera_cita_previa_activa",
        "lista_espera",
        ["cita_previa_id"],
        unique=True,
        postgresql_where=sa.text("cita_previa_id IS NOT NULL AND estado IN ('ACTIVA', 'OFERTADA')"),
    )


def downgrade() -> None:
    op.drop_index("ix_espera_cita_previa_activa", table_name="lista_espera")
    op.drop_constraint(
        op.f("fk_lista_espera_cita_previa_id_cita"), "lista_espera", type_="foreignkey"
    )
    op.drop_column("lista_espera", "cita_previa_id")
