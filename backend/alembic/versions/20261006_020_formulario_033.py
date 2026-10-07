"""Registro versionado para Formulario MSP 033/2021.

Revision ID: 20261006_020
Revises: 20261006_019
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261006_020"
down_revision: str | None = "20261006_019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "formulario_033",
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
            "sede_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("sede.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profesional_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("profesional.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "cita_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("cita.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "nota_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("nota_evolucion.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "odontograma_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("odontograma.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "registro_placa_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("registro_placa.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("raiz_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("motivo_modificacion", sa.Text(), nullable=True),
        sa.Column("contexto_identidad", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("contenido", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.CheckConstraint("version >= 1", name=op.f("ck_formulario_033_version_positiva")),
        sa.CheckConstraint(
            "version = 1 OR motivo_modificacion IS NOT NULL",
            name=op.f("ck_formulario_033_modificacion_con_motivo"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(contexto_identidad) = 'object'",
            name=op.f("ck_formulario_033_identidad_objeto"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(contenido) = 'object'",
            name=op.f("ck_formulario_033_contenido_objeto"),
        ),
        sa.UniqueConstraint("raiz_id", "version", name="uq_formulario_033_raiz_version"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formulario_033")),
    )
    op.create_index(
        "uq_formulario_033_vigente",
        "formulario_033",
        ["raiz_id"],
        unique=True,
        postgresql_where=sa.text("vigente"),
    )
    op.create_index(
        "uq_formulario_033_cita_vigente",
        "formulario_033",
        ["cita_id"],
        unique=True,
        postgresql_where=sa.text("vigente AND cita_id IS NOT NULL"),
    )
    op.create_index(
        "ix_formulario_033_paciente",
        "formulario_033",
        ["clinica_id", "paciente_id", "creado_en"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION formulario_033_raiz() RETURNS trigger AS $$
        BEGIN
          IF NEW.raiz_id IS NULL THEN
            NEW.raiz_id := NEW.id;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER formulario_033_raiz
        BEFORE INSERT ON formulario_033
        FOR EACH ROW EXECUTE FUNCTION formulario_033_raiz();

        CREATE FUNCTION formulario_033_inmutable() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND OLD.vigente
             AND NOT NEW.vigente
             AND NEW.id IS NOT DISTINCT FROM OLD.id
             AND NEW.clinica_id IS NOT DISTINCT FROM OLD.clinica_id
             AND NEW.paciente_id IS NOT DISTINCT FROM OLD.paciente_id
             AND NEW.sede_id IS NOT DISTINCT FROM OLD.sede_id
             AND NEW.profesional_id IS NOT DISTINCT FROM OLD.profesional_id
             AND NEW.cita_id IS NOT DISTINCT FROM OLD.cita_id
             AND NEW.nota_id IS NOT DISTINCT FROM OLD.nota_id
             AND NEW.odontograma_id IS NOT DISTINCT FROM OLD.odontograma_id
             AND NEW.registro_placa_id IS NOT DISTINCT FROM OLD.registro_placa_id
             AND NEW.raiz_id IS NOT DISTINCT FROM OLD.raiz_id
             AND NEW.version IS NOT DISTINCT FROM OLD.version
             AND NEW.motivo_modificacion IS NOT DISTINCT FROM OLD.motivo_modificacion
             AND NEW.contexto_identidad IS NOT DISTINCT FROM OLD.contexto_identidad
             AND NEW.contenido IS NOT DISTINCT FROM OLD.contenido
             AND NEW.creado_en IS NOT DISTINCT FROM OLD.creado_en
             AND NEW.creado_por IS NOT DISTINCT FROM OLD.creado_por THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'El Formulario 033 es inmutable; cree una nueva versión con motivo.'
            USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER formulario_033_inmutable
        BEFORE UPDATE OR DELETE ON formulario_033
        FOR EACH ROW EXECUTE FUNCTION formulario_033_inmutable();

        CREATE FUNCTION formulario_033_validar_referencias() RETURNS trigger AS $$
        DECLARE
          clinica_paciente uuid;
          clinica_profesional uuid;
          clinica_sede uuid;
          paciente_cita uuid;
          clinica_cita uuid;
          paciente_nota uuid;
          clinica_nota uuid;
          paciente_odontograma uuid;
          clinica_odontograma uuid;
          paciente_placa uuid;
          clinica_placa uuid;
          paciente_raiz uuid;
          clinica_raiz uuid;
          version_maxima smallint;
          profesional_cita uuid;
          sede_cita uuid;
        BEGIN
          IF NEW.version = 1 THEN
            IF NEW.raiz_id IS DISTINCT FROM NEW.id THEN
              RAISE EXCEPTION 'La primera versión debe ser la raíz del formulario.';
            END IF;
          ELSE
            SELECT paciente_id, clinica_id INTO paciente_raiz, clinica_raiz
              FROM formulario_033 WHERE id = NEW.raiz_id;
            IF paciente_raiz IS DISTINCT FROM NEW.paciente_id
               OR clinica_raiz IS DISTINCT FROM NEW.clinica_id THEN
              RAISE EXCEPTION 'La raíz de versión no corresponde al paciente y clínica.';
            END IF;
            SELECT coalesce(max(version), 0) INTO version_maxima
              FROM formulario_033 WHERE raiz_id = NEW.raiz_id;
            IF NEW.version <> version_maxima + 1 THEN
              RAISE EXCEPTION 'La versión debe continuar la secuencia del formulario.';
            END IF;
          END IF;
          SELECT clinica_id INTO clinica_paciente FROM paciente WHERE id = NEW.paciente_id;
          SELECT clinica_id INTO clinica_profesional FROM profesional WHERE id = NEW.profesional_id;
          IF clinica_paciente IS DISTINCT FROM NEW.clinica_id
             OR clinica_profesional IS DISTINCT FROM NEW.clinica_id THEN
            RAISE EXCEPTION 'Paciente, profesional y formulario deben pertenecer a la misma clínica.';
          END IF;
          IF NEW.sede_id IS NOT NULL THEN
            SELECT clinica_id INTO clinica_sede FROM sede WHERE id = NEW.sede_id;
            IF clinica_sede IS DISTINCT FROM NEW.clinica_id THEN
              RAISE EXCEPTION 'La sede no pertenece a la clínica del formulario.';
            END IF;
          END IF;
          IF NEW.cita_id IS NOT NULL THEN
            SELECT paciente_id, clinica_id, profesional_id, sede_id
              INTO paciente_cita, clinica_cita, profesional_cita, sede_cita
              FROM cita WHERE id = NEW.cita_id;
            IF paciente_cita IS DISTINCT FROM NEW.paciente_id
               OR clinica_cita IS DISTINCT FROM NEW.clinica_id
               OR profesional_cita IS DISTINCT FROM NEW.profesional_id
               OR sede_cita IS DISTINCT FROM NEW.sede_id THEN
              RAISE EXCEPTION 'La cita no corresponde al paciente y clínica del formulario.';
            END IF;
          END IF;
          IF NEW.nota_id IS NOT NULL THEN
            SELECT paciente_id, clinica_id INTO paciente_nota, clinica_nota
              FROM nota_evolucion WHERE id = NEW.nota_id;
            IF paciente_nota IS DISTINCT FROM NEW.paciente_id
               OR clinica_nota IS DISTINCT FROM NEW.clinica_id THEN
              RAISE EXCEPTION 'La nota no corresponde al paciente y clínica del formulario.';
            END IF;
          END IF;
          IF NEW.odontograma_id IS NOT NULL THEN
            SELECT paciente_id, clinica_id INTO paciente_odontograma, clinica_odontograma
              FROM odontograma WHERE id = NEW.odontograma_id;
            IF paciente_odontograma IS DISTINCT FROM NEW.paciente_id
               OR clinica_odontograma IS DISTINCT FROM NEW.clinica_id THEN
              RAISE EXCEPTION 'El odontograma no corresponde al paciente y clínica del formulario.';
            END IF;
          END IF;
          IF NEW.registro_placa_id IS NOT NULL THEN
            SELECT paciente_id, clinica_id INTO paciente_placa, clinica_placa
              FROM registro_placa WHERE id = NEW.registro_placa_id;
            IF paciente_placa IS DISTINCT FROM NEW.paciente_id
               OR clinica_placa IS DISTINCT FROM NEW.clinica_id THEN
              RAISE EXCEPTION 'El índice de placa no corresponde al paciente y clínica del formulario.';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER formulario_033_validar_referencias
        BEFORE INSERT ON formulario_033
        FOR EACH ROW EXECUTE FUNCTION formulario_033_validar_referencias();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM formulario_033) THEN
            RAISE EXCEPTION 'No se puede revertir: existen formularios 033 con historial clínico.';
          END IF;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER formulario_033_validar_referencias ON formulario_033")
    op.execute("DROP FUNCTION formulario_033_validar_referencias()")
    op.execute("DROP TRIGGER formulario_033_inmutable ON formulario_033")
    op.execute("DROP FUNCTION formulario_033_inmutable()")
    op.execute("DROP TRIGGER formulario_033_raiz ON formulario_033")
    op.execute("DROP FUNCTION formulario_033_raiz()")
    op.drop_index("ix_formulario_033_paciente", table_name="formulario_033")
    op.drop_index("uq_formulario_033_cita_vigente", table_name="formulario_033")
    op.drop_index("uq_formulario_033_vigente", table_name="formulario_033")
    op.drop_table("formulario_033")
