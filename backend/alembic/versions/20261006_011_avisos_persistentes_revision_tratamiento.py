"""Guarda avisos revisables para reportes explícitos sobre tratamiento.

Revision ID: 20261006_011
Revises: 20261006_010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_011"
down_revision: str | None = "20261006_010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aviso_revision_tratamiento",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("conversacion_id", sa.Uuid(), nullable=False),
        sa.Column("mensaje_entrante_id", sa.Uuid(), nullable=False),
        sa.Column("revisada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revisada_por", sa.Uuid(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "(revisada_en IS NULL AND revisada_por IS NULL) OR "
            "(revisada_en IS NOT NULL AND revisada_por IS NOT NULL)",
            name=op.f("ck_aviso_revision_tratamiento_revision_con_actor_y_fecha"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_aviso_revision_tratamiento_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversacion_id"],
            ["conversacion.id"],
            name=op.f("fk_aviso_revision_tratamiento_conversacion_id_conversacion"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mensaje_entrante_id"],
            ["mensaje_entrante.id"],
            name=op.f("fk_aviso_revision_tratamiento_mensaje_entrante_id_mensaje_entrante"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aviso_revision_tratamiento")),
        sa.UniqueConstraint(
            "mensaje_entrante_id",
            name=op.f("uq_aviso_revision_tratamiento_mensaje_entrante_id"),
        ),
    )
    op.create_index(
        "ix_aviso_tratamiento_pendiente",
        "aviso_revision_tratamiento",
        ["clinica_id", "creado_en"],
        unique=False,
        postgresql_where=sa.text("revisada_en IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_aviso_tratamiento_pendiente", table_name="aviso_revision_tratamiento")
    op.drop_table("aviso_revision_tratamiento")
