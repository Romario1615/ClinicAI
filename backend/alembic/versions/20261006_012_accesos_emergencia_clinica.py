"""Persistir la notificación de acceso clínico de emergencia.

Revision ID: 20261006_012
Revises: 20261006_011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_012"
down_revision: str | None = "20261006_011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aviso_acceso_emergencia",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("relacion_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
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
            name=op.f("ck_aviso_acceso_emergencia_revision_con_actor_y_fecha"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_aviso_acceso_emergencia_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["relacion_id"],
            ["relacion_asistencial.id"],
            name=op.f("fk_aviso_acceso_emergencia_relacion_id_relacion_asistencial"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_aviso_acceso_emergencia_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aviso_acceso_emergencia")),
        sa.UniqueConstraint("relacion_id", name=op.f("uq_aviso_acceso_emergencia_relacion_id")),
    )
    op.create_index(
        "ix_aviso_acceso_emergencia_pendiente",
        "aviso_acceso_emergencia",
        ["clinica_id", "creado_en"],
        unique=False,
        postgresql_where=sa.text("revisada_en IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_aviso_acceso_emergencia_pendiente", table_name="aviso_acceso_emergencia")
    op.drop_table("aviso_acceso_emergencia")
