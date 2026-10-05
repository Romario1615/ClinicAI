"""Delegacion de firma de recetas (residente -> adjunto), con vigencia y motivo.

Revision ID: 20261005_008
Revises: 20261005_007
Fecha: 2026-10-05 16:36:09.532830+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_008"
down_revision: str | None = "20261005_007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delegacion_firma",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("delegante_id", sa.Uuid(), nullable=False),
        sa.Column("delegado_id", sa.Uuid(), nullable=False),
        sa.Column("vigente_desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("revocada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocada_por", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "char_length(motivo) >= 5", name=op.f("ck_delegacion_firma_motivo_obligatorio")
        ),
        sa.CheckConstraint(
            "delegante_id <> delegado_id", name=op.f("ck_delegacion_firma_no_autodelegacion")
        ),
        sa.CheckConstraint(
            "vigente_hasta > vigente_desde", name=op.f("ck_delegacion_firma_vigencia_valida")
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_delegacion_firma_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delegado_id"],
            ["profesional.id"],
            name=op.f("fk_delegacion_firma_delegado_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delegante_id"],
            ["profesional.id"],
            name=op.f("fk_delegacion_firma_delegante_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delegacion_firma")),
    )
    op.create_index(
        "ix_delegacion_firma_delegado",
        "delegacion_firma",
        ["delegado_id", "delegante_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_delegacion_firma_delegado", table_name="delegacion_firma")
    op.drop_table("delegacion_firma")
