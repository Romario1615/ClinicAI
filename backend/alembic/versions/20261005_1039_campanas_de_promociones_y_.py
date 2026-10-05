"""Campanas de promociones y consentimiento de marketing.

Anade el consentimiento PROMOCIONES (separado de los recordatorios) y la
intencion entrante BAJA_PROMOCIONES. Las restricciones CHECK se recrean con
los valores nuevos; el downgrade las devuelve a los anteriores y falla si
quedan filas con los valores nuevos, en lugar de borrarlas.

Revision ID: 20261005_004
Revises: 20261005_003
Fecha: 2026-10-05 10:39:06.858461+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261005_004"
down_revision: str | None = "20261005_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campana_promocion",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("plantilla_meta", sa.String(length=100), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("segmento", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("imagen_clave", sa.String(length=300), nullable=True),
        sa.Column("imagen_mime", sa.String(length=32), nullable=True),
        sa.Column("imagen_sha256", sa.String(length=64), nullable=True),
        sa.Column("imagen_origen", sa.String(length=10), nullable=True),
        sa.Column("imagen_proveedor", sa.String(length=32), nullable=True),
        sa.Column("imagen_prompt", sa.Text(), nullable=True),
        sa.Column("imagen_media_id", sa.String(length=120), nullable=True),
        sa.Column("aprobada_por", sa.Uuid(), nullable=True),
        sa.Column("aprobada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("programada_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encolados", sa.Integer(), nullable=False),
        sa.Column("omitidos", sa.Integer(), nullable=False),
        sa.Column("cancelada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado <> 'CANCELADA' OR motivo_cancelacion IS NOT NULL",
            name=op.f("ck_campana_promocion_cancelacion_con_motivo"),
        ),
        sa.CheckConstraint(
            "estado IN ('BORRADOR', 'APROBADA', 'ENVIADA', 'CANCELADA')",
            name=op.f("ck_campana_promocion_estado_valido"),
        ),
        sa.CheckConstraint(
            "estado NOT IN ('APROBADA', 'ENVIADA') OR (imagen_clave IS NOT NULL AND aprobada_en IS NOT NULL AND aprobada_por IS NOT NULL)",
            name=op.f("ck_campana_promocion_aprobada_con_imagen"),
        ),
        sa.CheckConstraint(
            "imagen_origen IS NULL OR imagen_origen IN ('SUBIDA', 'GENERADA')",
            name=op.f("ck_campana_promocion_origen_imagen_valido"),
        ),
        sa.CheckConstraint(
            "char_length(texto) BETWEEN 10 AND 500", name=op.f("ck_campana_promocion_texto_acotado")
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_campana_promocion_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campana_promocion")),
    )
    op.create_index(
        "ix_campana_promocion_clinica",
        "campana_promocion",
        ["clinica_id", "estado", "creado_en"],
        unique=False,
    )

    op.drop_constraint(op.f("ck_consentimiento_tipo_valido"), "consentimiento", type_="check")
    op.create_check_constraint(
        op.f("ck_consentimiento_tipo_valido"),
        "consentimiento",
        "tipo IN ('TRATAMIENTO_DATOS', 'COMUNICACION_WHATSAPP', 'RECORDATORIOS_MEDICACION', 'COMPARTIR_CON_TERCEROS', 'PROMOCIONES')",
    )
    op.drop_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"), "mensaje_entrante", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"),
        "mensaje_entrante",
        "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', 'BAJA', 'BAJA_PROMOCIONES', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"), "mensaje_entrante", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_mensaje_entrante_intencion_valida"),
        "mensaje_entrante",
        "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', 'BAJA', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
    )
    op.drop_constraint(op.f("ck_consentimiento_tipo_valido"), "consentimiento", type_="check")
    op.create_check_constraint(
        op.f("ck_consentimiento_tipo_valido"),
        "consentimiento",
        "tipo IN ('TRATAMIENTO_DATOS', 'COMUNICACION_WHATSAPP', 'RECORDATORIOS_MEDICACION', 'COMPARTIR_CON_TERCEROS')",
    )
    op.drop_index("ix_campana_promocion_clinica", table_name="campana_promocion")
    op.drop_table("campana_promocion")
