"""historia clinica, recetas y adherencia

Revision ID: 57eead6d29aa
Revises: 107738e8a543
Fecha: 2026-09-12 01:35:46.276707+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "57eead6d29aa"
down_revision: str | None = "107738e8a543"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
#  Disparadores que sostienen las tres reglas clinicas
# ---------------------------------------------------------------------------
#  Estan en la base de datos y no en Python a proposito. Una regla que vive
#  solo en el servicio deja de aplicarse en cuanto alguien anade otro camino
#  de escritura -- un script de migracion de datos, una tarea de
#  mantenimiento, el propio Alembic --, y estas tres pueden hacer dano a un
#  paciente.
# ---------------------------------------------------------------------------

NOTA_RAIZ_AUTOMATICA = """
CREATE OR REPLACE FUNCTION nota_evolucion_raiz() RETURNS trigger AS $$
BEGIN
    -- La primera version de una nota es su propia raiz. El identificador lo
    -- genera la base, asi que la aplicacion no puede fijarlo antes de
    -- insertar, y fijarlo despues con un UPDATE lo rechazaria el disparador
    -- de inmutabilidad -- correctamente.
    --
    -- Los BEFORE INSERT se ejecutan despues de aplicar los valores por
    -- omision de las columnas, asi que NEW.id ya esta poblado aqui.
    IF NEW.raiz_id IS NULL THEN
        NEW.raiz_id := NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER nota_evolucion_raiz
  BEFORE INSERT ON nota_evolucion
  FOR EACH ROW EXECUTE FUNCTION nota_evolucion_raiz();
"""

NOTA_SOLO_INSERCION = """
CREATE OR REPLACE FUNCTION nota_evolucion_inmutable() RETURNS trigger AS $$
BEGIN
    -- Se permite un unico cambio: marcar una version como no vigente al
    -- crear la siguiente. Todo lo demas se rechaza.
    IF TG_OP = 'UPDATE' THEN
        IF NEW.vigente = false AND OLD.vigente = true
           AND NEW.id = OLD.id
           AND NEW.raiz_id = OLD.raiz_id
           AND NEW.version = OLD.version
           AND NEW.paciente_id = OLD.paciente_id
           AND NEW.motivo_consulta IS NOT DISTINCT FROM OLD.motivo_consulta
           AND NEW.subjetivo IS NOT DISTINCT FROM OLD.subjetivo
           AND NEW.objetivo IS NOT DISTINCT FROM OLD.objetivo
           AND NEW.analisis IS NOT DISTINCT FROM OLD.analisis
           AND NEW.plan IS NOT DISTINCT FROM OLD.plan
           AND NEW.signos_vitales IS NOT DISTINCT FROM OLD.signos_vitales THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION
            'Una nota clinica no se modifica: cree una version nueva con su motivo (ADR-0011).'
            USING ERRCODE = '23514';
    END IF;

    RAISE EXCEPTION 'Una nota clinica no se borra (ADR-0011).'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER nota_evolucion_inmutable
  BEFORE UPDATE OR DELETE ON nota_evolucion
  FOR EACH ROW EXECUTE FUNCTION nota_evolucion_inmutable();
"""

TOMA_EXIGE_RECETA_CONFIRMADA = """
CREATE OR REPLACE FUNCTION toma_exige_receta_confirmada() RETURNS trigger AS $$
DECLARE
    estado_receta text;
    es_prn boolean;
BEGIN
    SELECT r.estado, m.cuando_sea_necesario
      INTO estado_receta, es_prn
      FROM receta_medicamento m
      JOIN receta r ON r.id = m.receta_id
     WHERE m.id = NEW.receta_medicamento_id;

    IF estado_receta IS NULL THEN
        RAISE EXCEPTION 'La linea de receta no existe.' USING ERRCODE = '23503';
    END IF;

    -- Regla 2: una receta sin confirmar no genera calendario de tomas.
    -- Generar recordatorios desde un borrador significaria avisar a un
    -- paciente de que tome algo que nadie le ha indicado todavia.
    IF estado_receta <> 'CONFIRMADA' THEN
        RAISE EXCEPTION
            'Solo una receta confirmada por un profesional genera tomas (estado actual: %).',
            estado_receta
            USING ERRCODE = '23514';
    END IF;

    -- Regla 3: un medicamento «cuando sea necesario» no tiene horarios
    -- fijos. Convertir un PRN en pauta fija es un error de medicacion.
    IF es_prn THEN
        RAISE EXCEPTION
            'Un medicamento «cuando sea necesario» no genera tomas programadas.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER toma_exige_receta_confirmada
  BEFORE INSERT ON toma
  FOR EACH ROW EXECUTE FUNCTION toma_exige_receta_confirmada();
"""

ALERTA_SIN_MODIFICACION = """
CREATE OR REPLACE FUNCTION alerta_adherencia_solo_cierre() RETURNS trigger AS $$
BEGIN
    -- Una alerta se atiende, no se reescribe: los recuentos y el periodo
    -- quedan como estaban. Si pudieran cambiarse, el registro dejaria de
    -- servir para revisar despues que se vio y cuando.
    IF NEW.tomas_omitidas <> OLD.tomas_omitidas
       OR NEW.tomas_esperadas <> OLD.tomas_esperadas
       OR NEW.periodo_desde <> OLD.periodo_desde
       OR NEW.periodo_hasta <> OLD.periodo_hasta
       OR NEW.receta_id <> OLD.receta_id
       OR NEW.paciente_id <> OLD.paciente_id THEN
        RAISE EXCEPTION 'Una alerta de adherencia se atiende, no se reescribe.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER alerta_adherencia_solo_cierre
  BEFORE UPDATE ON alerta_adherencia
  FOR EACH ROW EXECUTE FUNCTION alerta_adherencia_solo_cierre();
"""


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "nota_evolucion",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("cita_id", sa.Uuid(), nullable=True),
        sa.Column("raiz_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("motivo_modificacion", sa.Text(), nullable=True),
        sa.Column("tipo", sa.String(length=16), nullable=False),
        sa.Column("motivo_consulta", sa.Text(), nullable=True),
        sa.Column("subjetivo", sa.Text(), nullable=True),
        sa.Column("objetivo", sa.Text(), nullable=True),
        sa.Column("analisis", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("signos_vitales", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('EVOLUCION', 'ENFERMERIA', 'INTERCONSULTA', 'PROCEDIMIENTO')",
            name=op.f("ck_nota_evolucion_tipo_nota_valido"),
        ),
        sa.CheckConstraint(
            "version = 1 OR motivo_modificacion IS NOT NULL",
            name=op.f("ck_nota_evolucion_modificacion_exige_motivo"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_nota_evolucion_version_positiva")),
        sa.ForeignKeyConstraint(
            ["cita_id"],
            ["cita.id"],
            name=op.f("fk_nota_evolucion_cita_id_cita"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_nota_evolucion_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_nota_evolucion_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_nota_evolucion_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nota_evolucion")),
        sa.UniqueConstraint("raiz_id", "version", name="uq_nota_raiz_version"),
    )
    op.create_index("ix_nota_cita", "nota_evolucion", ["cita_id"], unique=False)
    op.create_index(
        "ix_nota_paciente", "nota_evolucion", ["paciente_id", "creado_en"], unique=False
    )
    op.create_index(
        "ix_nota_profesional", "nota_evolucion", ["profesional_id", "creado_en"], unique=False
    )
    op.create_index(
        "ix_nota_vigente_unica",
        "nota_evolucion",
        ["raiz_id"],
        unique=True,
        postgresql_where=sa.text("vigente"),
    )
    op.create_table(
        "diagnostico",
        sa.Column("nota_id", sa.Uuid(), nullable=False),
        sa.Column("codigo_cie10", sa.String(length=16), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("principal", sa.Boolean(), nullable=False),
        sa.Column("presuntivo", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["nota_id"],
            ["nota_evolucion.id"],
            name=op.f("fk_diagnostico_nota_id_nota_evolucion"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnostico")),
    )
    op.create_index("ix_diagnostico_cie10", "diagnostico", ["codigo_cie10"], unique=False)
    op.create_index("ix_diagnostico_nota", "diagnostico", ["nota_id"], unique=False)
    op.create_table(
        "receta",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("nota_id", sa.Uuid(), nullable=True),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("confirmada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmada_por", sa.Uuid(), nullable=True),
        sa.Column("suspendida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_suspension", sa.Text(), nullable=True),
        sa.Column("receta_anterior_id", sa.Uuid(), nullable=True),
        sa.Column("indicaciones_generales", sa.Text(), nullable=True),
        sa.Column("vigente_desde", sa.Date(), nullable=True),
        sa.Column("vigente_hasta", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado <> 'CONFIRMADA' OR (confirmada_en IS NOT NULL AND confirmada_por IS NOT NULL)",
            name=op.f("ck_receta_confirmada_exige_responsable"),
        ),
        sa.CheckConstraint(
            "estado <> 'SUSPENDIDA' OR motivo_suspension IS NOT NULL",
            name=op.f("ck_receta_suspension_exige_motivo"),
        ),
        sa.CheckConstraint(
            "estado IN ('BORRADOR', 'CONFIRMADA', 'SUSPENDIDA', 'CUMPLIDA')",
            name=op.f("ck_receta_estado_receta_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_receta_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nota_id"],
            ["nota_evolucion.id"],
            name=op.f("fk_receta_nota_id_nota_evolucion"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_receta_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_receta_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receta_anterior_id"],
            ["receta.id"],
            name=op.f("fk_receta_receta_anterior_id_receta"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receta")),
    )
    op.create_index("ix_receta_estado", "receta", ["clinica_id", "estado"], unique=False)
    op.create_index("ix_receta_paciente", "receta", ["paciente_id", "creado_en"], unique=False)
    op.create_table(
        "alerta_adherencia",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("receta_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("severidad", sa.String(length=16), nullable=False),
        sa.Column("tomas_omitidas", sa.SmallInteger(), nullable=False),
        sa.Column("tomas_esperadas", sa.SmallInteger(), nullable=False),
        sa.Column("periodo_desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("periodo_hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atendida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atendida_por", sa.Uuid(), nullable=True),
        sa.Column("nota_profesional", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "severidad IN ('INFORMATIVA', 'ATENCION', 'URGENTE')",
            name=op.f("ck_alerta_adherencia_severidad_valida"),
        ),
        sa.CheckConstraint(
            "periodo_hasta > periodo_desde", name=op.f("ck_alerta_adherencia_periodo_coherente")
        ),
        sa.CheckConstraint(
            "tomas_esperadas > 0", name=op.f("ck_alerta_adherencia_esperadas_positivas")
        ),
        sa.CheckConstraint(
            "tomas_omitidas >= 0", name=op.f("ck_alerta_adherencia_omitidas_no_negativas")
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_alerta_adherencia_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_alerta_adherencia_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_alerta_adherencia_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receta_id"],
            ["receta.id"],
            name=op.f("fk_alerta_adherencia_receta_id_receta"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerta_adherencia")),
    )
    op.create_index(
        "ix_alerta_abierta_unica",
        "alerta_adherencia",
        ["receta_id"],
        unique=True,
        postgresql_where=sa.text("atendida_en IS NULL"),
    )
    op.create_index(
        "ix_alerta_paciente", "alerta_adherencia", ["paciente_id", "creado_en"], unique=False
    )
    op.create_table(
        "receta_medicamento",
        sa.Column("receta_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("concentracion", sa.String(length=64), nullable=True),
        sa.Column("forma", sa.String(length=48), nullable=True),
        sa.Column("dosis", sa.String(length=120), nullable=False),
        sa.Column("via", sa.String(length=16), nullable=False),
        sa.Column("cuando_sea_necesario", sa.Boolean(), nullable=False),
        sa.Column("frecuencia_horas", sa.SmallInteger(), nullable=True),
        sa.Column("duracion_dias", sa.SmallInteger(), nullable=True),
        sa.Column("hora_primera_toma", sa.String(length=5), nullable=True),
        sa.Column("instrucciones", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "via IN ('ORAL', 'TOPICA', 'INHALATORIA', 'INTRAMUSCULAR', 'INTRAVENOSA', 'SUBCUTANEA', 'OFTALMICA', 'OTICA', 'RECTAL', 'OTRA')",
            name=op.f("ck_receta_medicamento_via_valida"),
        ),
        sa.CheckConstraint(
            "NOT cuando_sea_necesario OR frecuencia_horas IS NULL",
            name=op.f("ck_receta_medicamento_prn_sin_frecuencia"),
        ),
        sa.CheckConstraint(
            "cuando_sea_necesario OR frecuencia_horas IS NOT NULL",
            name=op.f("ck_receta_medicamento_pauta_fija_exige_frecuencia"),
        ),
        sa.CheckConstraint(
            "frecuencia_horas IS NULL OR (frecuencia_horas >= 1 AND frecuencia_horas <= 168)",
            name=op.f("ck_receta_medicamento_frecuencia_razonable"),
        ),
        sa.ForeignKeyConstraint(
            ["receta_id"],
            ["receta.id"],
            name=op.f("fk_receta_medicamento_receta_id_receta"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receta_medicamento")),
    )
    op.create_index("ix_medicamento_receta", "receta_medicamento", ["receta_id"], unique=False)
    op.create_table(
        "toma",
        sa.Column("receta_medicamento_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("programada_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("registrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registrada_por_tipo", sa.String(length=16), nullable=True),
        sa.Column("registrada_por_id", sa.Uuid(), nullable=True),
        sa.Column("nota_paciente", sa.Text(), nullable=True),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "estado = 'PENDIENTE' OR estado = 'CANCELADA' OR registrada_en IS NOT NULL",
            name=op.f("ck_toma_registro_exige_instante"),
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'TOMADA', 'OMITIDA', 'CANCELADA')",
            name=op.f("ck_toma_estado_toma_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_toma_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receta_medicamento_id"],
            ["receta_medicamento.id"],
            name=op.f("fk_toma_receta_medicamento_id_receta_medicamento"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_toma")),
        sa.UniqueConstraint(
            "receta_medicamento_id", "programada_en", name="uq_toma_medicamento_instante"
        ),
    )
    op.create_index("ix_toma_paciente", "toma", ["paciente_id", "programada_en"], unique=False)
    op.create_index(
        "ix_toma_pendientes",
        "toma",
        ["programada_en"],
        unique=False,
        postgresql_where=sa.text("estado = 'PENDIENTE'"),
    )
    # ### end Alembic commands ###

    # --- Disparadores ---
    #
    # Van despues de crear las tablas, y su orden entre si no importa: cada
    # uno protege una tabla distinta.
    # El de raiz va primero: rellena `raiz_id` antes de que nada mas lo
    # mire.
    op.execute(NOTA_RAIZ_AUTOMATICA)
    op.execute(NOTA_SOLO_INSERCION)
    op.execute(TOMA_EXIGE_RECETA_CONFIRMADA)
    op.execute(ALERTA_SIN_MODIFICACION)


def downgrade() -> None:
    # Se retiran primero los disparadores: soltar una tabla con un
    # disparador que consulta otra produce errores confusos segun el orden.
    op.execute("DROP TRIGGER IF EXISTS alerta_adherencia_solo_cierre ON alerta_adherencia")
    op.execute("DROP TRIGGER IF EXISTS toma_exige_receta_confirmada ON toma")
    op.execute("DROP TRIGGER IF EXISTS nota_evolucion_inmutable ON nota_evolucion")
    op.execute("DROP TRIGGER IF EXISTS nota_evolucion_raiz ON nota_evolucion")
    op.execute("DROP FUNCTION IF EXISTS alerta_adherencia_solo_cierre()")
    op.execute("DROP FUNCTION IF EXISTS toma_exige_receta_confirmada()")
    op.execute("DROP FUNCTION IF EXISTS nota_evolucion_inmutable()")
    op.execute("DROP FUNCTION IF EXISTS nota_evolucion_raiz()")

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "ix_toma_pendientes", table_name="toma", postgresql_where=sa.text("estado = 'PENDIENTE'")
    )
    op.drop_index("ix_toma_paciente", table_name="toma")
    op.drop_table("toma")
    op.drop_index("ix_medicamento_receta", table_name="receta_medicamento")
    op.drop_table("receta_medicamento")
    op.drop_index("ix_alerta_paciente", table_name="alerta_adherencia")
    op.drop_index(
        "ix_alerta_abierta_unica",
        table_name="alerta_adherencia",
        postgresql_where=sa.text("atendida_en IS NULL"),
    )
    op.drop_table("alerta_adherencia")
    op.drop_index("ix_receta_paciente", table_name="receta")
    op.drop_index("ix_receta_estado", table_name="receta")
    op.drop_table("receta")
    op.drop_index("ix_diagnostico_nota", table_name="diagnostico")
    op.drop_index("ix_diagnostico_cie10", table_name="diagnostico")
    op.drop_table("diagnostico")
    op.drop_index(
        "ix_nota_vigente_unica", table_name="nota_evolucion", postgresql_where=sa.text("vigente")
    )
    op.drop_index("ix_nota_profesional", table_name="nota_evolucion")
    op.drop_index("ix_nota_paciente", table_name="nota_evolucion")
    op.drop_index("ix_nota_cita", table_name="nota_evolucion")
    op.drop_table("nota_evolucion")
    # ### end Alembic commands ###
