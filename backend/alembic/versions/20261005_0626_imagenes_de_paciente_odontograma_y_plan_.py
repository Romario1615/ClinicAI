"""Imagenes de paciente, odontograma versionado y plan de tratamiento.

El odontograma sigue el patron de `nota_evolucion` (ADR-0011): un disparador
rechaza `DELETE` y todo `UPDATE` salvo apagar `vigente` al crear la version
siguiente. La garantia vive en el motor, no en el servicio.

Revision ID: 20261005_002
Revises: 20261005_001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261005_002"
down_revision: str | None = "20261005_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ODONTOGRAMA_INMUTABLE = """
CREATE OR REPLACE FUNCTION odontograma_inmutable() RETURNS trigger AS $$
BEGIN
    -- Unico cambio permitido: marcar una version como no vigente al crear la
    -- siguiente. El contenido clinico no se reescribe nunca.
    IF TG_OP = 'UPDATE' THEN
        IF NEW.vigente = false AND OLD.vigente = true
           AND NEW.id = OLD.id
           AND NEW.paciente_id = OLD.paciente_id
           AND NEW.version = OLD.version
           AND NEW.denticion = OLD.denticion
           AND NEW.piezas = OLD.piezas
           AND NEW.motivo_modificacion IS NOT DISTINCT FROM OLD.motivo_modificacion
           AND NEW.procedimiento_id IS NOT DISTINCT FROM OLD.procedimiento_id THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION
            'Un odontograma no se modifica: registre una version nueva con su motivo.'
            USING ERRCODE = '23514';
    END IF;

    RAISE EXCEPTION 'Un odontograma no se borra.' USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER odontograma_inmutable
  BEFORE UPDATE OR DELETE ON odontograma
  FOR EACH ROW EXECUTE FUNCTION odontograma_inmutable();
"""


def upgrade() -> None:
    op.create_table(
        "odontograma",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("denticion", sa.String(length=10), nullable=False),
        sa.Column("piezas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("motivo_modificacion", sa.Text(), nullable=True),
        sa.Column("procedimiento_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "denticion IN ('PERMANENTE', 'TEMPORAL', 'MIXTA')",
            name=op.f("ck_odontograma_denticion_valida"),
        ),
        sa.CheckConstraint(
            "version = 1 OR motivo_modificacion IS NOT NULL",
            name=op.f("ck_odontograma_motivo_desde_version_dos"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_odontograma_version_positiva")),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_odontograma_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_odontograma_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_odontograma_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_odontograma")),
        sa.UniqueConstraint("paciente_id", "version", name="uq_odontograma_paciente_id_version"),
    )
    op.create_index(
        "uq_odontograma_vigente",
        "odontograma",
        ["paciente_id"],
        unique=True,
        postgresql_where=sa.text("vigente"),
    )
    op.create_table(
        "plan_tratamiento",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("propuesto_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aceptado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado <> 'CANCELADO' OR motivo_cancelacion IS NOT NULL",
            name=op.f("ck_plan_tratamiento_cancelacion_con_motivo"),
        ),
        sa.CheckConstraint(
            "estado IN ('BORRADOR', 'PROPUESTO', 'ACEPTADO', 'COMPLETADO', 'CANCELADO')",
            name=op.f("ck_plan_tratamiento_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_plan_tratamiento_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_plan_tratamiento_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_plan_tratamiento_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_tratamiento")),
    )
    op.create_index(
        "ix_plan_tratamiento_paciente", "plan_tratamiento", ["paciente_id", "estado"], unique=False
    )
    op.create_table(
        "imagen_paciente",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("nivel_sensibilidad", sa.String(length=2), nullable=False),
        sa.Column("piezas", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("tomada_en", sa.Date(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("cita_id", sa.Uuid(), nullable=True),
        sa.Column("profesional_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_mime", sa.String(length=32), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("clave_objeto", sa.String(length=300), nullable=False),
        sa.Column("antivirus", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.Column("anulado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anulado_por", sa.Uuid(), nullable=True),
        sa.Column("motivo_anulacion", sa.String(), nullable=True),
        sa.CheckConstraint(
            "(tipo = 'PERFIL' AND nivel_sensibilidad = 'N1') OR (tipo <> 'PERFIL' AND nivel_sensibilidad IN ('N2', 'N3'))",
            name=op.f("ck_imagen_paciente_nivel_coherente_con_tipo"),
        ),
        sa.CheckConstraint(
            "tipo IN ('PERFIL', 'RADIOGRAFIA_PERIAPICAL', 'RADIOGRAFIA_BITEWING', 'RADIOGRAFIA_PANORAMICA', 'RADIOGRAFIA_CEFALOMETRICA', 'FOTO_INTRAORAL', 'FOTO_EXTRAORAL', 'OTRA')",
            name=op.f("ck_imagen_paciente_tipo_valido"),
        ),
        sa.CheckConstraint(
            "descripcion IS NULL OR char_length(descripcion) <= 500",
            name=op.f("ck_imagen_paciente_descripcion_corta"),
        ),
        sa.CheckConstraint("tamano_bytes > 0", name=op.f("ck_imagen_paciente_tamano_positivo")),
        sa.ForeignKeyConstraint(
            ["cita_id"],
            ["cita.id"],
            name=op.f("fk_imagen_paciente_cita_id_cita"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_imagen_paciente_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_imagen_paciente_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_imagen_paciente_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imagen_paciente")),
        sa.UniqueConstraint("clave_objeto", name="uq_imagen_paciente_clave_objeto"),
    )
    op.create_index(
        "ix_imagen_paciente_paciente_tipo",
        "imagen_paciente",
        ["paciente_id", "tipo", "creado_en"],
        unique=False,
    )
    op.create_table(
        "procedimiento_plan",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("fase", sa.SmallInteger(), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("pieza", sa.SmallInteger(), nullable=True),
        sa.Column("caras", sa.String(length=5), nullable=True),
        sa.Column("servicio_id", sa.Uuid(), nullable=True),
        sa.Column("descripcion", sa.String(length=300), nullable=False),
        sa.Column("precio", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("hallazgo_resultante", sa.String(length=32), nullable=True),
        sa.Column("cita_id", sa.Uuid(), nullable=True),
        sa.Column("completado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completado_por", sa.Uuid(), nullable=True),
        sa.Column("cancelado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado <> 'CANCELADO' OR motivo_cancelacion IS NOT NULL",
            name=op.f("ck_procedimiento_plan_cancelacion_con_motivo"),
        ),
        sa.CheckConstraint(
            "estado <> 'COMPLETADO' OR completado_en IS NOT NULL",
            name=op.f("ck_procedimiento_plan_completado_con_fecha"),
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'COMPLETADO', 'CANCELADO')",
            name=op.f("ck_procedimiento_plan_estado_valido"),
        ),
        sa.CheckConstraint(
            "fase >= 1 AND fase <= 20", name=op.f("ck_procedimiento_plan_fase_valida")
        ),
        sa.CheckConstraint("precio >= 0", name=op.f("ck_procedimiento_plan_precio_no_negativo")),
        sa.ForeignKeyConstraint(
            ["cita_id"],
            ["cita.id"],
            name=op.f("fk_procedimiento_plan_cita_id_cita"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plan_tratamiento.id"],
            name=op.f("fk_procedimiento_plan_plan_id_plan_tratamiento"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["servicio_id"],
            ["servicio.id"],
            name=op.f("fk_procedimiento_plan_servicio_id_servicio"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procedimiento_plan")),
    )
    op.create_index(
        "ix_procedimiento_plan_plan",
        "procedimiento_plan",
        ["plan_id", "fase", "orden"],
        unique=False,
    )
    # Ciclo odontograma <-> procedimiento: la clave se anade al final.
    op.create_foreign_key(
        op.f("fk_odontograma_procedimiento_id_procedimiento_plan"),
        "odontograma",
        "procedimiento_plan",
        ["procedimiento_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(ODONTOGRAMA_INMUTABLE)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS odontograma_inmutable ON odontograma")
    op.execute("DROP FUNCTION IF EXISTS odontograma_inmutable()")
    op.drop_constraint(
        op.f("fk_odontograma_procedimiento_id_procedimiento_plan"),
        "odontograma",
        type_="foreignkey",
    )
    op.drop_index("ix_procedimiento_plan_plan", table_name="procedimiento_plan")
    op.drop_table("procedimiento_plan")
    op.drop_index("ix_imagen_paciente_paciente_tipo", table_name="imagen_paciente")
    op.drop_table("imagen_paciente")
    op.drop_index("ix_plan_tratamiento_paciente", table_name="plan_tratamiento")
    op.drop_table("plan_tratamiento")
    op.drop_index(
        "uq_odontograma_vigente", table_name="odontograma", postgresql_where=sa.text("vigente")
    )
    op.drop_table("odontograma")
