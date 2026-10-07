"""Plantillas versionadas y respuestas inmutables de anamnesis.

Revision ID: 20261006_018
Revises: 20261006_017
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261006_018"
down_revision: str | None = "20261006_017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plantilla_anamnesis",
        sa.Column(
            "clinica_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("nivel_sensibilidad", sa.String(length=2), nullable=False),
        sa.Column("preguntas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("publicada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_plantilla_anamnesis_version_positiva")),
        sa.CheckConstraint(
            "estado IN ('BORRADOR', 'PUBLICADA', 'RETIRADA')",
            name=op.f("ck_plantilla_anamnesis_estado_valido"),
        ),
        sa.CheckConstraint(
            "nivel_sensibilidad IN ('N2', 'N3')",
            name=op.f("ck_plantilla_anamnesis_sensibilidad_valida"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(preguntas) = 'array' AND jsonb_array_length(preguntas) BETWEEN 1 AND 40",
            name=op.f("ck_plantilla_anamnesis_preguntas_acotadas"),
        ),
        sa.CheckConstraint(
            "(estado = 'BORRADOR') = (publicada_en IS NULL)",
            name=op.f("ck_plantilla_anamnesis_publicada_exige_fecha"),
        ),
        sa.UniqueConstraint(
            "clinica_id", "nombre", "version", name="uq_plantilla_anamnesis_version"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plantilla_anamnesis")),
    )
    op.create_index(
        "ix_plantilla_anamnesis_publicada",
        "plantilla_anamnesis",
        ["clinica_id", sa.text("lower(nombre)")],
        unique=True,
        postgresql_where=sa.text("estado = 'PUBLICADA'"),
    )
    op.create_index(
        "ix_plantilla_anamnesis_clinica",
        "plantilla_anamnesis",
        ["clinica_id", "creado_en"],
        unique=False,
    )

    op.create_table(
        "respuesta_anamnesis",
        sa.Column(
            "clinica_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "paciente_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("paciente.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "plantilla_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("plantilla_anamnesis.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_plantilla", sa.SmallInteger(), nullable=False),
        sa.Column(
            "profesional_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("profesional.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("respuestas", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "registrada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("creado_por", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_plantilla > 0", name=op.f("ck_respuesta_anamnesis_version_positiva")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(respuestas) = 'object'",
            name=op.f("ck_respuesta_anamnesis_respuestas_objeto"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_respuesta_anamnesis")),
    )
    op.create_index(
        "ix_respuesta_anamnesis_paciente",
        "respuesta_anamnesis",
        ["clinica_id", "paciente_id", "registrada_en"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION proteger_plantilla_anamnesis() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Las plantillas de anamnesis no se borran; se conservan sus versiones.';
          END IF;
          IF OLD.estado = 'BORRADOR'
             AND NEW.estado IN ('BORRADOR', 'PUBLICADA')
             AND NEW.id IS NOT DISTINCT FROM OLD.id
             AND NEW.clinica_id IS NOT DISTINCT FROM OLD.clinica_id
             AND NEW.version IS NOT DISTINCT FROM OLD.version
             AND NEW.creado_en IS NOT DISTINCT FROM OLD.creado_en
             AND NEW.creado_por IS NOT DISTINCT FROM OLD.creado_por
             AND ((NEW.estado = 'BORRADOR' AND NEW.publicada_en IS NULL)
                  OR (NEW.estado = 'PUBLICADA' AND NEW.publicada_en IS NOT NULL)) THEN
            RETURN NEW;
          END IF;
          IF OLD.estado = 'PUBLICADA'
             AND NEW.estado = 'RETIRADA'
             AND NEW.id IS NOT DISTINCT FROM OLD.id
             AND NEW.clinica_id IS NOT DISTINCT FROM OLD.clinica_id
             AND NEW.nombre IS NOT DISTINCT FROM OLD.nombre
             AND NEW.version IS NOT DISTINCT FROM OLD.version
             AND NEW.nivel_sensibilidad IS NOT DISTINCT FROM OLD.nivel_sensibilidad
             AND NEW.preguntas IS NOT DISTINCT FROM OLD.preguntas
             AND NEW.publicada_en IS NOT DISTINCT FROM OLD.publicada_en
             AND NEW.creado_en IS NOT DISTINCT FROM OLD.creado_en
             AND NEW.creado_por IS NOT DISTINCT FROM OLD.creado_por THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Una plantilla publicada solo puede retirarse; su contenido es inmutable.';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_plantilla_anamnesis_inmutable
        BEFORE UPDATE OR DELETE ON plantilla_anamnesis
        FOR EACH ROW EXECUTE FUNCTION proteger_plantilla_anamnesis();

        CREATE FUNCTION validar_respuesta_anamnesis() RETURNS trigger AS $$
        DECLARE
          datos_plantilla plantilla_anamnesis%ROWTYPE;
          clinica_paciente uuid;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Las respuestas de anamnesis son inmutables.';
          END IF;
          SELECT * INTO datos_plantilla FROM plantilla_anamnesis
            WHERE id = NEW.plantilla_id FOR SHARE;
          IF NOT FOUND OR datos_plantilla.clinica_id <> NEW.clinica_id
             OR datos_plantilla.version <> NEW.version_plantilla
             OR datos_plantilla.estado <> 'PUBLICADA' THEN
            RAISE EXCEPTION 'La respuesta debe corresponder a una versión publicada de la clínica.';
          END IF;
          SELECT clinica_id INTO clinica_paciente FROM paciente WHERE id = NEW.paciente_id;
          IF clinica_paciente IS DISTINCT FROM NEW.clinica_id THEN
            RAISE EXCEPTION 'El paciente y la respuesta deben pertenecer a la misma clínica.';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_respuesta_anamnesis_inmutable
        BEFORE INSERT OR UPDATE OR DELETE ON respuesta_anamnesis
        FOR EACH ROW EXECUTE FUNCTION validar_respuesta_anamnesis();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM respuesta_anamnesis)
             OR EXISTS (SELECT 1 FROM plantilla_anamnesis) THEN
            RAISE EXCEPTION 'No se puede revertir: existen plantillas o respuestas de anamnesis.';
          END IF;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER trg_respuesta_anamnesis_inmutable ON respuesta_anamnesis")
    op.execute("DROP FUNCTION validar_respuesta_anamnesis()")
    op.execute("DROP TRIGGER trg_plantilla_anamnesis_inmutable ON plantilla_anamnesis")
    op.execute("DROP FUNCTION proteger_plantilla_anamnesis()")
    op.drop_index("ix_respuesta_anamnesis_paciente", table_name="respuesta_anamnesis")
    op.drop_table("respuesta_anamnesis")
    op.drop_index("ix_plantilla_anamnesis_clinica", table_name="plantilla_anamnesis")
    op.drop_index("ix_plantilla_anamnesis_publicada", table_name="plantilla_anamnesis")
    op.drop_table("plantilla_anamnesis")
