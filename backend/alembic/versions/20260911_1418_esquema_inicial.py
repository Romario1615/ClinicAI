"""esquema_inicial

Revision ID: 107738e8a543
Revises:
Fecha: 2026-09-11 14:18:19.788625+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "107738e8a543"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
#  PARCHE_MIGRACION_INICIAL_APLICADO
#
#  Sentencias que Alembic no autogenera.  Anadidas por
#  `python -m herramientas.parchear_migracion_inicial`.
#  Si se regenera esta migracion, hay que volver a ejecutar esa herramienta.
# ---------------------------------------------------------------------------

SQL_CONFIGURACION_TEXTUAL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'espanol_sin_tildes'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION espanol_sin_tildes ( COPY = spanish );
        ALTER TEXT SEARCH CONFIGURATION espanol_sin_tildes
            ALTER MAPPING FOR hword, hword_part, word
            WITH unaccent, spanish_stem;
    END IF;
END
$$;
"""

# ---------------------------------------------------------------------------
#  Calculo de `cita.fin`
# ---------------------------------------------------------------------------
# No puede ser una columna generada: PostgreSQL exige que la expresion sea
# IMMUTABLE y `timestamptz + interval` es solo STABLE, porque la aritmetica de
# meses y dias depende de la zona horaria de la sesion.
#
# Con un disparador BEFORE el calculo sigue estando en el motor: un camino de
# codigo que olvidara el tiempo de preparacion no puede producir un rango
# incorrecto, porque el disparador lo sobrescribe.  Los disparadores BEFORE se
# ejecutan antes de comprobar NOT NULL, asi que la aplicacion puede insertar
# sin dar valor a `fin`.
SQL_FUNCION_CALCULAR_FIN = """
CREATE OR REPLACE FUNCTION cita_calcular_fin()
RETURNS trigger AS $$
BEGIN
    NEW.fin := NEW.inicio
        + make_interval(mins => NEW.duracion_minutos + NEW.minutos_preparacion);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

SQL_TRIGGER_CALCULAR_FIN = """
CREATE TRIGGER cita_fin_calculado
  BEFORE INSERT OR UPDATE OF inicio, duracion_minutos, minutos_preparacion
  ON cita
  FOR EACH ROW EXECUTE FUNCTION cita_calcular_fin();
"""

# ---------------------------------------------------------------------------
#  Verificacion del anti doble reserva (ADR-0009)
# ---------------------------------------------------------------------------
# Las restricciones las crea `op.create_table`, no este parche.  Aqui solo se
# comprueba que EXISTAN de verdad en el esquema resultante.
#
# El motivo: son la unica garantia real contra la doble reserva, y una
# version anterior del modelo hizo que Alembic dejara de generarlas sin dar
# ningun aviso.  Una migracion que termina "bien" y deja el sistema sin esa
# proteccion es el peor resultado posible, porque el fallo aparece meses
# despues con dos pacientes citados a la misma hora.
SQL_VERIFICAR_EXCLUSIONES = """
DO $$
DECLARE
    faltantes text;
BEGIN
    SELECT string_agg(esperada, ', ')
      INTO faltantes
      FROM (
        VALUES ('cita_sin_solape_profesional'), ('cita_sin_solape_consultorio')
      ) AS r(esperada)
     WHERE NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conname = r.esperada
           AND contype = 'x'
     );

    IF faltantes IS NOT NULL THEN
        RAISE EXCEPTION
            'Faltan restricciones de exclusion: %. Son la unica garantia '
            'contra la doble reserva (ADR-0009). Revise que el modelo de '
            'Cita conserve sus ExcludeConstraint y regenere la migracion.',
            faltantes;
    END IF;
END
$$;
"""

# ---------------------------------------------------------------------------
#  Tablas de solo insercion
# ---------------------------------------------------------------------------
# Se aplica con disparador y no solo revocando privilegios.  Revocar UPDATE y
# DELETE al rol de la aplicacion es la defensa correcta en produccion, pero
# exige un rol distinto del propietario del esquema, lo que depende del
# despliegue.  El disparador funciona en cualquier configuracion, incluida la
# local, donde la aplicacion suele conectarse como propietaria.
SQL_FUNCION_SOLO_INSERCION = """
CREATE OR REPLACE FUNCTION tabla_solo_insercion()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'La tabla % es de solo insercion: % no esta permitido. Para corregir '
        'un registro erroneo, inserte una entrada nueva que lo aclare.',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""

SQL_TRIGGER_AUDITORIA = """
CREATE TRIGGER auditoria_sin_modificacion
  BEFORE UPDATE OR DELETE ON auditoria
  FOR EACH ROW EXECUTE FUNCTION tabla_solo_insercion();
"""

SQL_TRIGGER_CITA_HISTORIAL = """
CREATE TRIGGER cita_historial_sin_modificacion
  BEFORE UPDATE OR DELETE ON cita_historial
  FOR EACH ROW EXECUTE FUNCTION tabla_solo_insercion();
"""


def upgrade() -> None:
    # =======================================================================
    #  Extensiones
    # =======================================================================
    #  Se crean AQUI, no solo en el script de inicializacion del contenedor.
    #  Ese script es exclusivo del entorno local: una instancia gestionada de
    #  PostgreSQL nunca lo ejecuta.  Sin `btree_gist` la restriccion de
    #  exclusion no se puede crear y la migracion fallaria a mitad.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(SQL_CONFIGURACION_TEXTUAL)

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "auditoria",
        sa.Column("accion", sa.String(length=64), nullable=False),
        sa.Column("actor_tipo", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("resultado", sa.String(length=16), nullable=False),
        sa.Column("entidad_tipo", sa.String(length=48), nullable=True),
        sa.Column("entidad_id", sa.Uuid(), nullable=True),
        sa.Column("clinica_id", sa.Uuid(), nullable=True),
        sa.Column("sede_id", sa.Uuid(), nullable=True),
        sa.Column("paciente_id", sa.Uuid(), nullable=True),
        sa.Column("nivel_sensibilidad", sa.String(length=4), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("origen", sa.String(length=16), nullable=False),
        sa.Column("correlacion_id", sa.String(length=64), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("metadatos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "ocurrido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "actor_tipo IN ('USUARIO', 'SISTEMA', 'AGENTE_IA', 'PACIENTE')",
            name=op.f("ck_auditoria_actor_tipo_valido"),
        ),
        sa.CheckConstraint(
            "nivel_sensibilidad IS NULL OR nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')",
            name=op.f("ck_auditoria_nivel_valido"),
        ),
        sa.CheckConstraint(
            "origen IN ('WEB', 'API', 'WHATSAPP', 'WORKER')",
            name=op.f("ck_auditoria_origen_valido"),
        ),
        sa.CheckConstraint(
            "resultado IN ('EXITO', 'DENEGADO', 'ERROR')",
            name=op.f("ck_auditoria_resultado_valido"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria")),
    )
    op.create_index(
        "ix_auditoria_accion", "auditoria", ["clinica_id", "accion", "ocurrido_en"], unique=False
    )
    op.create_index("ix_auditoria_actor", "auditoria", ["actor_id", "ocurrido_en"], unique=False)
    op.create_index("ix_auditoria_correlacion", "auditoria", ["correlacion_id"], unique=False)
    op.create_index(
        "ix_auditoria_entidad", "auditoria", ["entidad_tipo", "entidad_id"], unique=False
    )
    op.create_index(
        "ix_auditoria_paciente", "auditoria", ["paciente_id", "ocurrido_en"], unique=False
    )
    op.create_index(
        "ix_auditoria_revision_seguridad",
        "auditoria",
        ["clinica_id", "ocurrido_en"],
        unique=False,
        postgresql_where=sa.text("resultado = 'DENEGADO' OR nivel_sensibilidad = 'N3'"),
    )
    op.create_table(
        "clave_idempotencia",
        sa.Column("clave", sa.String(length=200), nullable=False),
        sa.Column("alcance", sa.String(length=50), nullable=False),
        sa.Column("clinica_id", sa.Uuid(), nullable=True),
        sa.Column("hash_peticion", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("respuesta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("codigo_http", sa.SmallInteger(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("completado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "estado IN ('EN_CURSO', 'COMPLETADA', 'FALLIDA')",
            name=op.f("ck_clave_idempotencia_estado_valido"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clave_idempotencia")),
        sa.UniqueConstraint("alcance", "clave", name="uq_clave_idempotencia_alcance_clave"),
    )
    op.create_index(
        "ix_clave_idempotencia_expiracion", "clave_idempotencia", ["expira_en"], unique=False
    )
    op.create_table(
        "clinica",
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("identificacion_fiscal", sa.String(length=50), nullable=True),
        sa.Column("zona_horaria", sa.String(length=64), nullable=False),
        sa.Column("idioma", sa.String(length=8), nullable=False),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("telefono", sa.String(length=32), nullable=True),
        sa.Column("correo", sa.String(length=200), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinica")),
        sa.UniqueConstraint("identificacion_fiscal", name="uq_clinica_identificacion_fiscal"),
    )
    op.create_table(
        "horario_atencion",
        sa.Column("propietario_tipo", sa.String(length=16), nullable=False),
        sa.Column("propietario_id", sa.Uuid(), nullable=False),
        sa.Column("dia_semana", sa.SmallInteger(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("granularidad_minutos", sa.SmallInteger(), nullable=False),
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
            "propietario_tipo IN ('SEDE', 'PROFESIONAL')",
            name=op.f("ck_horario_atencion_propietario_valido"),
        ),
        sa.CheckConstraint(
            "dia_semana BETWEEN 1 AND 7", name=op.f("ck_horario_atencion_dia_semana_iso")
        ),
        sa.CheckConstraint(
            "granularidad_minutos > 0", name=op.f("ck_horario_atencion_granularidad_positiva")
        ),
        sa.CheckConstraint(
            "hora_fin > hora_inicio", name=op.f("ck_horario_atencion_franja_con_duracion")
        ),
        sa.CheckConstraint(
            "vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
            name=op.f("ck_horario_atencion_vigencia_coherente"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_horario_atencion")),
    )
    op.create_index(
        "ix_horario_propietario",
        "horario_atencion",
        ["propietario_tipo", "propietario_id", "dia_semana"],
        unique=False,
    )
    op.create_table(
        "outbox_mensaje",
        sa.Column("tipo", sa.String(length=48), nullable=False),
        sa.Column("canal", sa.String(length=16), nullable=False),
        sa.Column("clinica_id", sa.Uuid(), nullable=True),
        sa.Column("destino_tipo", sa.String(length=16), nullable=False),
        sa.Column("destino_id", sa.Uuid(), nullable=False),
        sa.Column("carga_util", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("clave_deduplicacion", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("intentos", sa.SmallInteger(), nullable=False),
        sa.Column("max_intentos", sa.SmallInteger(), nullable=False),
        sa.Column(
            "proximo_intento_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("entidad_origen_tipo", sa.String(length=48), nullable=True),
        sa.Column("entidad_origen_id", sa.Uuid(), nullable=True),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("referencia_externa", sa.String(length=255), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entregado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tomado_por", sa.String(length=64), nullable=True),
        sa.Column("tomado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "canal IN ('WHATSAPP', 'CORREO', 'CALENDARIO', 'INTERNO')",
            name=op.f("ck_outbox_mensaje_canal_valido"),
        ),
        sa.CheckConstraint(
            "destino_tipo IN ('PACIENTE', 'PROFESIONAL', 'USUARIO', 'CLINICA')",
            name=op.f("ck_outbox_mensaje_destino_tipo_valido"),
        ),
        sa.CheckConstraint(
            "estado <> 'FALLIDO' OR ultimo_error IS NOT NULL",
            name=op.f("ck_outbox_mensaje_fallido_con_error"),
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'EN_PROCESO', 'ENTREGADO', 'FALLIDO', 'DESCARTADO')",
            name=op.f("ck_outbox_mensaje_estado_valido"),
        ),
        sa.CheckConstraint("intentos >= 0", name=op.f("ck_outbox_mensaje_intentos_no_negativos")),
        sa.CheckConstraint(
            "max_intentos > 0", name=op.f("ck_outbox_mensaje_max_intentos_positivo")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_mensaje")),
        sa.UniqueConstraint("clave_deduplicacion", name="uq_outbox_mensaje_clave_deduplicacion"),
    )
    op.create_index(
        "ix_outbox_en_proceso",
        "outbox_mensaje",
        ["tomado_en"],
        unique=False,
        postgresql_where=sa.text("estado = 'EN_PROCESO'"),
    )
    op.create_index(
        "ix_outbox_fallidos",
        "outbox_mensaje",
        ["clinica_id", "creado_en"],
        unique=False,
        postgresql_where=sa.text("estado = 'FALLIDO'"),
    )
    op.create_index(
        "ix_outbox_origen",
        "outbox_mensaje",
        ["entidad_origen_tipo", "entidad_origen_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_pendientes",
        "outbox_mensaje",
        ["proximo_intento_en"],
        unique=False,
        postgresql_where=sa.text("estado = 'PENDIENTE'"),
    )
    op.create_index(
        "ix_outbox_referencia_externa", "outbox_mensaje", ["referencia_externa"], unique=False
    )
    op.create_table(
        "permiso",
        sa.Column("codigo", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=False),
        sa.Column("categoria", sa.String(length=50), nullable=False),
        sa.Column("requiere_relacion_asistencial", sa.Boolean(), nullable=False),
        sa.Column("nivel_sensibilidad", sa.String(length=4), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')", name=op.f("ck_permiso_nivel_valido")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permiso")),
        sa.UniqueConstraint("codigo", name="uq_permiso_codigo"),
    )
    op.create_table(
        "configuracion_clinica",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("clave", sa.String(length=100), nullable=False),
        sa.Column("valor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_configuracion_clinica_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_configuracion_clinica")),
        sa.UniqueConstraint(
            "clinica_id", "clave", "version", name="uq_configuracion_clinica_id_clave"
        ),
    )
    op.create_index(
        "ix_configuracion_una_vigente_por_clave",
        "configuracion_clinica",
        ["clinica_id", "clave"],
        unique=True,
        postgresql_where=sa.text("vigente"),
    )
    op.create_table(
        "descanso",
        sa.Column("horario_atencion_id", sa.Uuid(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("motivo", sa.String(length=150), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "hora_fin > hora_inicio", name=op.f("ck_descanso_descanso_con_duracion")
        ),
        sa.ForeignKeyConstraint(
            ["horario_atencion_id"],
            ["horario_atencion.id"],
            name=op.f("fk_descanso_horario_atencion_id_horario_atencion"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_descanso")),
    )
    op.create_table(
        "especialidad",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_especialidad_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_especialidad")),
        sa.UniqueConstraint("clinica_id", "nombre", name="uq_especialidad_clinica_id_nombre"),
    )
    op.create_table(
        "paciente",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_documento", sa.String(length=16), nullable=False),
        sa.Column("numero_documento", sa.String(length=32), nullable=True),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("apellido", sa.String(length=100), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("sexo", sa.String(length=16), nullable=True),
        sa.Column("telefono_whatsapp", sa.String(length=32), nullable=True),
        sa.Column("whatsapp_verificado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correo", sa.String(length=200), nullable=True),
        sa.Column("direccion", sa.Text(), nullable=True),
        sa.Column("preferencias_horario", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("nivel_verificacion", sa.String(length=16), nullable=False),
        sa.Column("verificado_por", sa.Uuid(), nullable=True),
        sa.Column("verificado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
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
            "nivel_verificacion IN ('NO_VERIFICADO', 'TELEFONO') OR verificado_en IS NOT NULL",
            name=op.f("ck_paciente_verificacion_con_trazabilidad"),
        ),
        sa.CheckConstraint(
            "nivel_verificacion IN ('NO_VERIFICADO', 'TELEFONO', 'DOCUMENTO', 'PRESENCIAL')",
            name=op.f("ck_paciente_nivel_verificacion_valido"),
        ),
        sa.CheckConstraint(
            "tipo_documento = 'SIN_DOCUMENTO' OR numero_documento IS NOT NULL",
            name=op.f("ck_paciente_documento_exige_numero"),
        ),
        sa.CheckConstraint(
            "tipo_documento IN ('CEDULA', 'PASAPORTE', 'RUC', 'SIN_DOCUMENTO')",
            name=op.f("ck_paciente_tipo_documento_valido"),
        ),
        sa.CheckConstraint(
            "fecha_nacimiento IS NULL OR fecha_nacimiento <= CURRENT_DATE",
            name=op.f("ck_paciente_nacimiento_no_futuro"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_paciente_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paciente")),
    )
    op.create_index(
        "ix_paciente_apellido", "paciente", ["clinica_id", "apellido", "nombre"], unique=False
    )
    op.create_index(
        "ix_paciente_documento",
        "paciente",
        ["clinica_id", "tipo_documento", "numero_documento"],
        unique=True,
        postgresql_where=sa.text("numero_documento IS NOT NULL"),
    )
    op.create_index(
        "ix_paciente_whatsapp", "paciente", ["clinica_id", "telefono_whatsapp"], unique=False
    )
    op.create_table(
        "recordatorio",
        sa.Column("tipo", sa.String(length=48), nullable=False),
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("entidad_tipo", sa.String(length=48), nullable=False),
        sa.Column("entidad_id", sa.Uuid(), nullable=False),
        sa.Column("destinatario_tipo", sa.String(length=16), nullable=False),
        sa.Column("destinatario_id", sa.Uuid(), nullable=False),
        sa.Column("programado_para", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("outbox_mensaje_id", sa.Uuid(), nullable=True),
        sa.Column("cancelado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_cancelacion", sa.String(length=255), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "estado <> 'CANCELADO' OR motivo_cancelacion IS NOT NULL",
            name=op.f("ck_recordatorio_cancelacion_con_motivo"),
        ),
        sa.CheckConstraint(
            "estado IN ('PROGRAMADO', 'ENCOLADO', 'CANCELADO', 'OMITIDO')",
            name=op.f("ck_recordatorio_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["outbox_mensaje_id"],
            ["outbox_mensaje.id"],
            name=op.f("fk_recordatorio_outbox_mensaje_id_outbox_mensaje"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recordatorio")),
    )
    op.create_index(
        "ix_recordatorio_a_encolar",
        "recordatorio",
        ["programado_para"],
        unique=False,
        postgresql_where=sa.text("estado = 'PROGRAMADO'"),
    )
    op.create_index(
        "ix_recordatorio_entidad",
        "recordatorio",
        ["entidad_tipo", "entidad_id"],
        unique=False,
        postgresql_where=sa.text("estado = 'PROGRAMADO'"),
    )
    op.create_table(
        "rol",
        sa.Column("clinica_id", sa.Uuid(), nullable=True),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("es_sistema", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "NOT es_sistema OR clinica_id IS NULL", name=op.f("ck_rol_rol_sistema_sin_clinica")
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_rol_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rol")),
    )
    op.create_index(
        "ix_rol_clinica_codigo",
        "rol",
        ["clinica_id", "codigo"],
        unique=True,
        postgresql_where=sa.text("clinica_id IS NOT NULL"),
    )
    op.create_index(
        "ix_rol_sistema_codigo",
        "rol",
        ["codigo"],
        unique=True,
        postgresql_where=sa.text("clinica_id IS NULL"),
    )
    op.create_table(
        "sede",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("direccion", sa.Text(), nullable=True),
        sa.Column("telefono", sa.String(length=32), nullable=True),
        sa.Column("zona_horaria", sa.String(length=64), nullable=True),
        sa.Column("minutos_antelacion_minima", sa.SmallInteger(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_sede_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sede")),
        sa.UniqueConstraint("clinica_id", "nombre", name="uq_sede_clinica_id_nombre"),
    )
    op.create_index("ix_sede_clinica_activa", "sede", ["clinica_id", "activa"], unique=False)
    op.create_table(
        "usuario",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("correo", sa.String(length=200), nullable=False),
        sa.Column("hash_contrasena", sa.String(length=255), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("apellido", sa.String(length=100), nullable=False),
        sa.Column("telefono", sa.String(length=32), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("correo_verificado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("debe_cambiar_contrasena", sa.Boolean(), nullable=False),
        sa.Column("ultimo_acceso_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intentos_fallidos", sa.SmallInteger(), nullable=False),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("secreto_2fa_cifrado", sa.Text(), nullable=True),
        sa.Column("2fa_habilitado", sa.Boolean(), nullable=False),
        sa.Column("2fa_confirmado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            'NOT "2fa_habilitado" OR secreto_2fa_cifrado IS NOT NULL',
            name=op.f("ck_usuario_2fa_exige_secreto"),
        ),
        sa.CheckConstraint("intentos_fallidos >= 0", name=op.f("ck_usuario_intentos_no_negativos")),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_usuario_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario")),
        sa.UniqueConstraint("clinica_id", "correo", name="uq_usuario_clinica_id_correo"),
    )
    op.create_index("ix_usuario_clinica_activo", "usuario", ["clinica_id", "activo"], unique=False)
    op.create_table(
        "codigo_recuperacion_2fa",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("hash_codigo", sa.String(length=64), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_codigo_recuperacion_2fa_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_codigo_recuperacion_2fa")),
        sa.UniqueConstraint(
            "usuario_id", "hash_codigo", name="uq_codigo_recuperacion_usuario_id_hash"
        ),
    )
    op.create_index(
        "ix_codigo_recuperacion_disponibles",
        "codigo_recuperacion_2fa",
        ["usuario_id"],
        unique=False,
        postgresql_where=sa.text("usado_en IS NULL"),
    )
    op.create_table(
        "consentimiento",
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("otorgado", sa.Boolean(), nullable=False),
        sa.Column("version_texto", sa.String(length=32), nullable=False),
        sa.Column("texto_hash", sa.String(length=64), nullable=False),
        sa.Column("canal", sa.String(length=16), nullable=False),
        sa.Column(
            "otorgado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revocado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidencia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "canal IN ('PANEL', 'WHATSAPP', 'PRESENCIAL', 'CORREO')",
            name=op.f("ck_consentimiento_canal_valido"),
        ),
        sa.CheckConstraint(
            "tipo IN ('TRATAMIENTO_DATOS', 'COMUNICACION_WHATSAPP', 'RECORDATORIOS_MEDICACION', 'COMPARTIR_CON_TERCEROS')",
            name=op.f("ck_consentimiento_tipo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_consentimiento_paciente_id_paciente"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consentimiento")),
    )
    op.create_index(
        "ix_consentimiento_vigente",
        "consentimiento",
        ["paciente_id", "tipo"],
        unique=False,
        postgresql_where=sa.text("revocado_en IS NULL"),
    )
    op.create_table(
        "consultorio",
        sa.Column("sede_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("capacidad", sa.SmallInteger(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("capacidad > 0", name=op.f("ck_consultorio_capacidad_positiva")),
        sa.ForeignKeyConstraint(
            ["sede_id"], ["sede.id"], name=op.f("fk_consultorio_sede_id_sede"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consultorio")),
        sa.UniqueConstraint("sede_id", "nombre", name="uq_consultorio_sede_id_nombre"),
    )
    op.create_table(
        "documento_paciente",
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column("ruta_almacenamiento", sa.String(length=512), nullable=False),
        sa.Column("tipo_mime", sa.String(length=100), nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger(), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("subido_por", sa.Uuid(), nullable=True),
        sa.Column("escaneo_antivirus", sa.String(length=16), nullable=False),
        sa.Column("escaneo_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("nivel_sensibilidad", sa.String(length=4), nullable=False),
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
            "escaneo_antivirus IN ('PENDIENTE', 'LIMPIO', 'INFECTADO', 'NO_DISPONIBLE')",
            name=op.f("ck_documento_paciente_escaneo_valido"),
        ),
        sa.CheckConstraint(
            "nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')",
            name=op.f("ck_documento_paciente_nivel_valido"),
        ),
        sa.CheckConstraint("tamano_bytes > 0", name=op.f("ck_documento_paciente_tamano_positivo")),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_documento_paciente_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_documento_paciente_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documento_paciente")),
    )
    op.create_index(
        "ix_documento_escaneo_pendiente",
        "documento_paciente",
        ["escaneo_antivirus"],
        unique=False,
        postgresql_where=sa.text("escaneo_antivirus = 'PENDIENTE'"),
    )
    op.create_index(
        "ix_documento_hash", "documento_paciente", ["clinica_id", "hash_sha256"], unique=False
    )
    op.create_index(
        "ix_documento_paciente", "documento_paciente", ["paciente_id", "tipo"], unique=False
    )
    op.create_table(
        "feriado",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("sede_id", sa.Uuid(), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("recurrente_anual", sa.Boolean(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=True),
        sa.Column("hora_fin", sa.Time(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(hora_inicio IS NULL) = (hora_fin IS NULL)",
            name=op.f("ck_feriado_feriado_parcial_completo"),
        ),
        sa.CheckConstraint(
            "hora_fin IS NULL OR hora_fin > hora_inicio",
            name=op.f("ck_feriado_feriado_parcial_con_duracion"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_feriado_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sede_id"], ["sede.id"], name=op.f("fk_feriado_sede_id_sede"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feriado")),
    )
    op.create_index("ix_feriado_clinica_fecha", "feriado", ["clinica_id", "fecha"], unique=False)
    op.create_table(
        "historial_acceso",
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("clinica_id", sa.Uuid(), nullable=True),
        sa.Column("correo_intentado", sa.String(length=200), nullable=False),
        sa.Column("resultado", sa.String(length=32), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(length=512), nullable=True),
        sa.Column(
            "ocurrido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("metadatos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "resultado IN ('EXITO', 'CREDENCIAL_INVALIDA', 'CUENTA_INACTIVA', 'BLOQUEADO', 'SEGUNDO_FACTOR_FALLIDO')",
            name=op.f("ck_historial_acceso_resultado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_historial_acceso_usuario_id_usuario"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_historial_acceso")),
    )
    op.create_index(
        "ix_historial_acceso_correo",
        "historial_acceso",
        ["correo_intentado", "ocurrido_en"],
        unique=False,
    )
    op.create_index(
        "ix_historial_acceso_ip", "historial_acceso", ["ip", "ocurrido_en"], unique=False
    )
    op.create_index(
        "ix_historial_acceso_usuario",
        "historial_acceso",
        ["usuario_id", "ocurrido_en"],
        unique=False,
    )
    op.create_table(
        "paciente_contacto",
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("relacion", sa.String(length=50), nullable=True),
        sa.Column("telefono", sa.String(length=32), nullable=True),
        sa.Column("correo", sa.String(length=200), nullable=True),
        sa.Column("es_emergencia", sa.Boolean(), nullable=False),
        sa.Column("autorizado_a_recibir_informacion", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_paciente_contacto_paciente_id_paciente"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paciente_contacto")),
    )
    op.create_index(
        "ix_contacto_emergencia",
        "paciente_contacto",
        ["paciente_id"],
        unique=False,
        postgresql_where=sa.text("es_emergencia"),
    )
    op.create_table(
        "profesional",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("especialidad_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("apellido", sa.String(length=100), nullable=False),
        sa.Column("numero_registro_profesional", sa.String(length=64), nullable=True),
        sa.Column("telefono_whatsapp", sa.String(length=32), nullable=True),
        sa.Column("correo_calendario", sa.String(length=200), nullable=True),
        sa.Column("estado_disponibilidad", sa.String(length=24), nullable=False),
        sa.Column("acepta_pacientes_nuevos", sa.Boolean(), nullable=False),
        sa.Column("minutos_preparacion_propio", sa.SmallInteger(), nullable=False),
        sa.Column("config_recordatorios", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
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
            "estado_disponibilidad IN ('DISPONIBLE', 'AGENDA_COMPLETA', 'AUSENTE', 'INACTIVO')",
            name=op.f("ck_profesional_estado_disponibilidad_valido"),
        ),
        sa.CheckConstraint(
            "minutos_preparacion_propio >= 0", name=op.f("ck_profesional_preparacion_no_negativa")
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_profesional_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["especialidad_id"],
            ["especialidad.id"],
            name=op.f("fk_profesional_especialidad_id_especialidad"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_profesional_usuario_id_usuario"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profesional")),
        sa.UniqueConstraint(
            "clinica_id",
            "numero_registro_profesional",
            name="uq_profesional_clinica_id_numero_registro_profesional",
        ),
        sa.UniqueConstraint("usuario_id", name="uq_profesional_usuario_id"),
    )
    op.create_index(
        "ix_profesional_clinica_activo", "profesional", ["clinica_id", "activo"], unique=False
    )
    op.create_index(
        "ix_profesional_especialidad", "profesional", ["especialidad_id", "activo"], unique=False
    )
    op.create_table(
        "rol_permiso",
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("permiso_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permiso_id"],
            ["permiso.id"],
            name=op.f("fk_rol_permiso_permiso_id_permiso"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rol_id"], ["rol.id"], name=op.f("fk_rol_permiso_rol_id_rol"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("rol_id", "permiso_id", name=op.f("pk_rol_permiso")),
    )
    op.create_table(
        "servicio",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("especialidad_id", sa.Uuid(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("duracion_minutos", sa.SmallInteger(), nullable=False),
        sa.Column("minutos_preparacion", sa.SmallInteger(), nullable=False),
        sa.Column("precio", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("requiere_pago_previo", sa.Boolean(), nullable=False),
        sa.Column("instrucciones_preparacion", sa.Text(), nullable=True),
        sa.Column("tipo_consultorio_requerido", sa.String(length=32), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("duracion_minutos > 0", name=op.f("ck_servicio_duracion_positiva")),
        sa.CheckConstraint(
            "minutos_preparacion >= 0", name=op.f("ck_servicio_preparacion_no_negativa")
        ),
        sa.CheckConstraint(
            "precio IS NULL OR precio >= 0", name=op.f("ck_servicio_precio_no_negativo")
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_servicio_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["especialidad_id"],
            ["especialidad.id"],
            name=op.f("fk_servicio_especialidad_id_especialidad"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_servicio")),
        sa.UniqueConstraint("clinica_id", "nombre", name="uq_servicio_clinica_id_nombre"),
    )
    op.create_index(
        "ix_servicio_especialidad_activo", "servicio", ["especialidad_id", "activo"], unique=False
    )
    op.create_table(
        "sesion",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("jti_refresco_hash", sa.String(length=64), nullable=False),
        sa.Column("familia", sa.String(length=64), nullable=False),
        sa.Column("sesion_anterior_id", sa.Uuid(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("agente_usuario", sa.String(length=512), nullable=True),
        sa.Column("segundo_factor_cumplido", sa.Boolean(), nullable=False),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_revocacion", sa.String(length=32), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "revocada_en IS NULL OR motivo_revocacion IS NOT NULL",
            name=op.f("ck_sesion_revocacion_con_motivo"),
        ),
        sa.ForeignKeyConstraint(
            ["sesion_anterior_id"],
            ["sesion.id"],
            name=op.f("fk_sesion_sesion_anterior_id_sesion"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_sesion_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sesion")),
        sa.UniqueConstraint("jti_refresco_hash", name="uq_sesion_jti_refresco_hash"),
    )
    op.create_index(
        "ix_sesion_activas",
        "sesion",
        ["usuario_id", "familia"],
        unique=False,
        postgresql_where=sa.text("revocada_en IS NULL AND usada_en IS NULL"),
    )
    op.create_index("ix_sesion_familia", "sesion", ["familia"], unique=False)
    op.create_table(
        "token_un_uso",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("hash_token", sa.String(length=64), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_uso", postgresql.INET(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('VERIFICACION_CORREO', 'RECUPERACION_CONTRASENA')",
            name=op.f("ck_token_un_uso_tipo_token_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_token_un_uso_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_token_un_uso")),
        sa.UniqueConstraint("hash_token", name="uq_token_un_uso_hash_token"),
    )
    op.create_index(
        "ix_token_un_uso_pendientes",
        "token_un_uso",
        ["usuario_id", "tipo"],
        unique=False,
        postgresql_where=sa.text("usado_en IS NULL"),
    )
    op.create_table(
        "usuario_rol",
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("rol_id", sa.Uuid(), nullable=False),
        sa.Column("otorgado_por", sa.Uuid(), nullable=True),
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
            "vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
            name=op.f("ck_usuario_rol_vigencia_coherente"),
        ),
        sa.ForeignKeyConstraint(
            ["rol_id"], ["rol.id"], name=op.f("fk_usuario_rol_rol_id_rol"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_usuario_rol_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario_rol")),
        sa.UniqueConstraint("usuario_id", "rol_id", name="uq_usuario_rol_usuario_id_rol_id"),
    )
    op.create_table(
        "agenda_plantilla",
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("sede_id", sa.Uuid(), nullable=False),
        sa.Column("dia_semana", sa.SmallInteger(), nullable=False),
        sa.Column("hora_inicio", sa.String(length=8), nullable=False),
        sa.Column("hora_fin", sa.String(length=8), nullable=False),
        sa.Column("granularidad_minutos", sa.SmallInteger(), nullable=False),
        sa.Column("vigente_desde", sa.String(length=10), nullable=True),
        sa.Column("vigente_hasta", sa.String(length=10), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "dia_semana BETWEEN 1 AND 7", name=op.f("ck_agenda_plantilla_dia_semana_iso")
        ),
        sa.CheckConstraint(
            "granularidad_minutos > 0", name=op.f("ck_agenda_plantilla_granularidad_positiva")
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_agenda_plantilla_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sede_id"],
            ["sede.id"],
            name=op.f("fk_agenda_plantilla_sede_id_sede"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agenda_plantilla")),
    )
    op.create_index(
        "ix_agenda_plantilla_profesional",
        "agenda_plantilla",
        ["profesional_id", "dia_semana"],
        unique=False,
    )
    op.create_table(
        "alergia",
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("sustancia", sa.String(length=200), nullable=False),
        sa.Column("tipo_reaccion", sa.String(length=200), nullable=True),
        sa.Column("severidad", sa.String(length=16), nullable=False),
        sa.Column("registrado_por", sa.Uuid(), nullable=False),
        sa.Column(
            "registrado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("desactivada_por", sa.Uuid(), nullable=True),
        sa.Column("desactivada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_desactivacion", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "severidad IN ('LEVE', 'MODERADA', 'GRAVE', 'ANAFILAXIA')",
            name=op.f("ck_alergia_severidad_valida"),
        ),
        sa.CheckConstraint(
            "activa OR motivo_desactivacion IS NOT NULL",
            name=op.f("ck_alergia_desactivacion_con_motivo"),
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_alergia_paciente_id_paciente"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["registrado_por"],
            ["profesional.id"],
            name=op.f("fk_alergia_registrado_por_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alergia")),
    )
    op.create_index(
        "ix_alergia_activa",
        "alergia",
        ["paciente_id"],
        unique=False,
        postgresql_where=sa.text("activa"),
    )
    op.create_table(
        "ambito_asignacion",
        sa.Column("usuario_rol_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=24), nullable=False),
        sa.Column("valor_id", sa.Uuid(), nullable=True),
        sa.Column("incluir", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('CLINICA', 'SEDE', 'ESPECIALIDAD', 'PROFESIONAL', 'PACIENTE', 'TIPO_INFORMACION')",
            name=op.f("ck_ambito_asignacion_tipo_ambito_valido"),
        ),
        sa.CheckConstraint(
            "incluir OR valor_id IS NOT NULL",
            name=op.f("ck_ambito_asignacion_exclusion_exige_destino"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_rol_id"],
            ["usuario_rol.id"],
            name=op.f("fk_ambito_asignacion_usuario_rol_id_usuario_rol"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ambito_asignacion")),
    )
    op.create_index(
        "ix_ambito_usuario_rol_tipo", "ambito_asignacion", ["usuario_rol_id", "tipo"], unique=False
    )
    op.create_table(
        "antecedente",
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("categoria", sa.String(length=32), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("registrado_por", sa.Uuid(), nullable=False),
        sa.Column(
            "registrado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("nivel_sensibilidad", sa.String(length=4), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "categoria IN ('PERSONAL', 'FAMILIAR', 'QUIRURGICO', 'FARMACOLOGICO', 'HABITOS', 'OTRO')",
            name=op.f("ck_antecedente_categoria_valida"),
        ),
        sa.CheckConstraint(
            "nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')",
            name=op.f("ck_antecedente_nivel_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_antecedente_paciente_id_paciente"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["registrado_por"],
            ["profesional.id"],
            name=op.f("fk_antecedente_registrado_por_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_antecedente")),
    )
    op.create_index(
        "ix_antecedente_paciente", "antecedente", ["paciente_id", "categoria"], unique=False
    )
    op.create_table(
        "bloqueo_agenda",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("sede_id", sa.Uuid(), nullable=True),
        sa.Column("profesional_id", sa.Uuid(), nullable=True),
        sa.Column("consultorio_id", sa.Uuid(), nullable=True),
        sa.Column("tipo", sa.String(length=24), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "rango",
            postgresql.TSTZRANGE(),
            sa.Computed("tstzrange(inicio, fin, '[)')", persisted=True),
            nullable=False,
        ),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("creado_con_citas_afectadas", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('VACACIONES', 'AUSENCIA', 'CAPACITACION', 'MANTENIMIENTO', 'OTRO')",
            name=op.f("ck_bloqueo_agenda_tipo_valido"),
        ),
        sa.CheckConstraint("fin > inicio", name=op.f("ck_bloqueo_agenda_bloqueo_con_duracion")),
        sa.CheckConstraint(
            "sede_id IS NOT NULL OR profesional_id IS NOT NULL OR consultorio_id IS NOT NULL",
            name=op.f("ck_bloqueo_agenda_bloqueo_con_destino"),
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_bloqueo_agenda_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["consultorio_id"],
            ["consultorio.id"],
            name=op.f("fk_bloqueo_agenda_consultorio_id_consultorio"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_bloqueo_agenda_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sede_id"],
            ["sede.id"],
            name=op.f("fk_bloqueo_agenda_sede_id_sede"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bloqueo_agenda")),
    )
    op.create_index(
        "ix_bloqueo_profesional_rango",
        "bloqueo_agenda",
        ["profesional_id", "inicio", "fin"],
        unique=False,
    )
    op.create_index(
        "ix_bloqueo_sede_rango", "bloqueo_agenda", ["sede_id", "inicio", "fin"], unique=False
    )
    op.create_table(
        "calendario_conexion",
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("proveedor", sa.String(length=24), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("token_acceso_cifrado", sa.Text(), nullable=True),
        sa.Column("token_refresco_cifrado", sa.Text(), nullable=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("alcances", sa.Text(), nullable=True),
        sa.Column("estado_sincronizacion", sa.String(length=24), nullable=False),
        sa.Column("ultima_sincronizacion_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("token_sincronizacion_incremental", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado_sincronizacion <> 'CONECTADO' OR token_refresco_cifrado IS NOT NULL",
            name=op.f("ck_calendario_conexion_conectado_exige_token"),
        ),
        sa.CheckConstraint(
            "estado_sincronizacion IN ('CONECTADO', 'TOKEN_VENCIDO', 'DESCONECTADO', 'ERROR')",
            name=op.f("ck_calendario_conexion_estado_sincronizacion_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_calendario_conexion_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendario_conexion")),
        sa.UniqueConstraint(
            "profesional_id",
            "proveedor",
            "calendar_id",
            name="uq_calendario_conexion_profesional_id_proveedor",
        ),
    )
    op.create_index(
        "ix_calendario_conexion_a_renovar",
        "calendario_conexion",
        ["expira_en"],
        unique=False,
        postgresql_where=sa.text("estado_sincronizacion = 'CONECTADO'"),
    )
    op.create_table(
        "cita",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("sede_id", sa.Uuid(), nullable=False),
        sa.Column("consultorio_id", sa.Uuid(), nullable=True),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("servicio_id", sa.Uuid(), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duracion_minutos", sa.SmallInteger(), nullable=False),
        sa.Column("minutos_preparacion", sa.SmallInteger(), nullable=False),
        sa.Column("fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "rango",
            postgresql.TSTZRANGE(),
            sa.Computed("tstzrange(inicio, fin, '[)')", persisted=True),
            nullable=False,
        ),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origen", sa.String(length=16), nullable=False),
        sa.Column("cita_origen_id", sa.Uuid(), nullable=True),
        sa.Column("serie_recurrente_id", sa.Uuid(), nullable=True),
        sa.Column("clave_idempotencia", sa.String(length=200), nullable=True),
        sa.Column("confirmada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelada_por", sa.Uuid(), nullable=True),
        sa.Column("motivo_cancelacion", sa.Text(), nullable=True),
        sa.Column("notas_recepcion", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        postgresql.ExcludeConstraint(
            (sa.column("consultorio_id"), "="),
            (sa.column("rango"), "&&"),
            where=sa.text(
                "estado IN ('CONFIRMED', 'HELD', 'RESCHEDULED') AND consultorio_id IS NOT NULL"
            ),
            using="gist",
            name="cita_sin_solape_consultorio",
        ),
        postgresql.ExcludeConstraint(
            (sa.column("profesional_id"), "="),
            (sa.column("rango"), "&&"),
            where=sa.text("estado IN ('CONFIRMED', 'HELD', 'RESCHEDULED')"),
            using="gist",
            name="cita_sin_solape_profesional",
        ),
        sa.CheckConstraint(
            "estado <> 'CANCELLED' OR motivo_cancelacion IS NOT NULL",
            name=op.f("ck_cita_cancelacion_exige_motivo"),
        ),
        sa.CheckConstraint(
            "estado <> 'HELD' OR expira_en IS NOT NULL", name=op.f("ck_cita_held_exige_expiracion")
        ),
        sa.CheckConstraint(
            "estado IN ('PENDING', 'HELD', 'CONFIRMED', 'RESCHEDULED', 'CANCELLED', 'COMPLETED', 'NO_SHOW')",
            name=op.f("ck_cita_estado_valido"),
        ),
        sa.CheckConstraint(
            "origen IN ('PANEL', 'WHATSAPP', 'LISTA_ESPERA', 'RECURRENTE')",
            name=op.f("ck_cita_origen_valido"),
        ),
        sa.CheckConstraint("duracion_minutos > 0", name=op.f("ck_cita_duracion_positiva")),
        sa.CheckConstraint("fin > inicio", name=op.f("ck_cita_fin_posterior_al_inicio")),
        sa.CheckConstraint(
            "minutos_preparacion >= 0", name=op.f("ck_cita_preparacion_no_negativa")
        ),
        sa.ForeignKeyConstraint(
            ["cita_origen_id"],
            ["cita.id"],
            name=op.f("fk_cita_cita_origen_id_cita"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_cita_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consultorio_id"],
            ["consultorio.id"],
            name=op.f("fk_cita_consultorio_id_consultorio"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_cita_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_cita_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sede_id"], ["sede.id"], name=op.f("fk_cita_sede_id_sede"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["servicio_id"],
            ["servicio.id"],
            name=op.f("fk_cita_servicio_id_servicio"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cita")),
    )
    op.create_index(
        "ix_cita_estado_inicio", "cita", ["clinica_id", "estado", "inicio"], unique=False
    )
    op.create_index(
        "ix_cita_held_expirando",
        "cita",
        ["expira_en"],
        unique=False,
        postgresql_where=sa.text("estado = 'HELD'"),
    )
    op.create_index(
        "ix_cita_idempotencia",
        "cita",
        ["clinica_id", "clave_idempotencia"],
        unique=True,
        postgresql_where=sa.text("clave_idempotencia IS NOT NULL"),
    )
    op.create_index("ix_cita_paciente_inicio", "cita", ["paciente_id", "inicio"], unique=False)
    op.create_index(
        "ix_cita_profesional_inicio", "cita", ["profesional_id", "inicio"], unique=False
    )
    op.create_index("ix_cita_sede_inicio", "cita", ["sede_id", "inicio"], unique=False)
    op.create_table(
        "profesional_sede",
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("sede_id", sa.Uuid(), nullable=False),
        sa.Column("principal", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_profesional_sede_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sede_id"],
            ["sede.id"],
            name=op.f("fk_profesional_sede_sede_id_sede"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("profesional_id", "sede_id", name=op.f("pk_profesional_sede")),
    )
    op.create_index(
        "ix_profesional_sede_principal",
        "profesional_sede",
        ["profesional_id"],
        unique=True,
        postgresql_where=sa.text("principal"),
    )
    op.create_table(
        "profesional_servicio",
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("servicio_id", sa.Uuid(), nullable=False),
        sa.Column("duracion_minutos_override", sa.SmallInteger(), nullable=True),
        sa.Column("precio_override", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.CheckConstraint(
            "duracion_minutos_override IS NULL OR duracion_minutos_override > 0",
            name=op.f("ck_profesional_servicio_duracion_override_positiva"),
        ),
        sa.CheckConstraint(
            "precio_override IS NULL OR precio_override >= 0",
            name=op.f("ck_profesional_servicio_precio_override_no_negativo"),
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_profesional_servicio_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["servicio_id"],
            ["servicio.id"],
            name=op.f("fk_profesional_servicio_servicio_id_servicio"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "profesional_id", "servicio_id", name=op.f("pk_profesional_servicio")
        ),
    )
    op.create_table(
        "relacion_asistencial",
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("origen", sa.String(length=24), nullable=False),
        sa.Column("cita_id", sa.Uuid(), nullable=True),
        sa.Column("vigente_hasta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("revocada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "origen <> 'EMERGENCIA' OR (motivo IS NOT NULL AND vigente_hasta IS NOT NULL)",
            name=op.f("ck_relacion_asistencial_emergencia_exige_motivo_y_caducidad"),
        ),
        sa.CheckConstraint(
            "origen IN ('CITA', 'ASIGNACION', 'DERIVACION', 'EMERGENCIA')",
            name=op.f("ck_relacion_asistencial_origen_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_relacion_asistencial_paciente_id_paciente"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_relacion_asistencial_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relacion_asistencial")),
    )
    op.create_index(
        "ix_relacion_profesional", "relacion_asistencial", ["profesional_id"], unique=False
    )
    op.create_index(
        "ix_relacion_vigente",
        "relacion_asistencial",
        ["paciente_id", "profesional_id"],
        unique=False,
        postgresql_where=sa.text("revocada_en IS NULL"),
    )
    op.create_table(
        "calendario_evento",
        sa.Column("cita_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("calendario_conexion_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("estado", sa.String(length=32), nullable=False),
        sa.Column("sincronizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("intentos", sa.SmallInteger(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'SINCRONIZADO', 'ELIMINADO_EXTERNAMENTE', 'CONFLICTO', 'ERROR')",
            name=op.f("ck_calendario_evento_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["calendario_conexion_id"],
            ["calendario_conexion.id"],
            name=op.f("fk_calendario_evento_calendario_conexion_id_calendario_conexion"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cita_id"],
            ["cita.id"],
            name=op.f("fk_calendario_evento_cita_id_cita"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_calendario_evento_profesional_id_profesional"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendario_evento")),
        sa.UniqueConstraint(
            "cita_id",
            "calendario_conexion_id",
            name="uq_calendario_evento_cita_id_calendario_conexion_id",
        ),
    )
    op.create_index(
        "ix_calendario_evento_externo",
        "calendario_evento",
        ["calendario_conexion_id", "external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )
    op.create_index(
        "ix_calendario_evento_pendientes",
        "calendario_evento",
        ["estado"],
        unique=False,
        postgresql_where=sa.text("estado IN ('PENDIENTE', 'ERROR')"),
    )
    op.create_table(
        "cita_historial",
        sa.Column("cita_id", sa.Uuid(), nullable=False),
        sa.Column("estado_anterior", sa.String(length=16), nullable=True),
        sa.Column("estado_nuevo", sa.String(length=16), nullable=False),
        sa.Column("inicio_anterior", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inicio_nuevo", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profesional_anterior_id", sa.Uuid(), nullable=True),
        sa.Column("profesional_nuevo_id", sa.Uuid(), nullable=True),
        sa.Column("actor_tipo", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column(
            "ocurrido_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("metadatos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["cita_id"],
            ["cita.id"],
            name=op.f("fk_cita_historial_cita_id_cita"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cita_historial")),
    )
    op.create_index(
        "ix_cita_historial_cita", "cita_historial", ["cita_id", "ocurrido_en"], unique=False
    )
    # =======================================================================
    #  Calculo de cita.fin  (ver la nota junto a SQL_FUNCION_CALCULAR_FIN)
    # =======================================================================
    op.execute(SQL_FUNCION_CALCULAR_FIN)
    op.execute(SQL_TRIGGER_CALCULAR_FIN)

    # Rellena `fin` en las filas que ya existieran.  En la migracion inicial
    # la tabla esta vacia, pero deja la sentencia por si se reordena.
    op.execute(
        "UPDATE cita SET fin = inicio "
        "+ make_interval(mins => duracion_minutos + minutos_preparacion) "
        "WHERE fin IS NULL"
    )

    # =======================================================================
    #  Verificacion del anti doble reserva (ADR-0009)
    # =======================================================================
    #  Las crea `op.create_table`; aqui se comprueba que existan.  Si no
    #  estan, la migracion falla en lugar de dejar el sistema sin proteccion.
    op.execute(SQL_VERIFICAR_EXCLUSIONES)

    # =======================================================================
    #  Tablas de solo insercion
    # =======================================================================
    op.execute(SQL_FUNCION_SOLO_INSERCION)
    op.execute(SQL_TRIGGER_AUDITORIA)
    op.execute(SQL_TRIGGER_CITA_HISTORIAL)

    # ### end Alembic commands ###


def downgrade() -> None:
    # Se deshace primero lo anadido a mano, en orden inverso.
    op.execute("DROP TRIGGER IF EXISTS cita_historial_sin_modificacion ON cita_historial")
    op.execute("DROP TRIGGER IF EXISTS auditoria_sin_modificacion ON auditoria")
    op.execute("DROP FUNCTION IF EXISTS tabla_solo_insercion()")
    # Las restricciones de exclusion no se sueltan aqui: las elimina el
    # `op.drop_table("cita")` que genera Alembic mas abajo.
    op.execute("DROP TRIGGER IF EXISTS cita_fin_calculado ON cita")
    op.execute("DROP FUNCTION IF EXISTS cita_calcular_fin()")

    # Las extensiones NO se eliminan a proposito: otras bases de datos del
    # mismo servidor podrian estar usandolas, y `DROP EXTENSION ... CASCADE`
    # borraria sus indices y columnas.  Dejarlas instaladas no tiene coste.

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_cita_historial_cita", table_name="cita_historial")
    op.drop_table("cita_historial")
    op.drop_index(
        "ix_calendario_evento_pendientes",
        table_name="calendario_evento",
        postgresql_where=sa.text("estado IN ('PENDIENTE', 'ERROR')"),
    )
    op.drop_index(
        "ix_calendario_evento_externo",
        table_name="calendario_evento",
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )
    op.drop_table("calendario_evento")
    op.drop_index(
        "ix_relacion_vigente",
        table_name="relacion_asistencial",
        postgresql_where=sa.text("revocada_en IS NULL"),
    )
    op.drop_index("ix_relacion_profesional", table_name="relacion_asistencial")
    op.drop_table("relacion_asistencial")
    op.drop_table("profesional_servicio")
    op.drop_index(
        "ix_profesional_sede_principal",
        table_name="profesional_sede",
        postgresql_where=sa.text("principal"),
    )
    op.drop_table("profesional_sede")
    op.drop_index("ix_cita_sede_inicio", table_name="cita")
    op.drop_index("ix_cita_profesional_inicio", table_name="cita")
    op.drop_index("ix_cita_paciente_inicio", table_name="cita")
    op.drop_index(
        "ix_cita_idempotencia",
        table_name="cita",
        postgresql_where=sa.text("clave_idempotencia IS NOT NULL"),
    )
    op.drop_index(
        "ix_cita_held_expirando", table_name="cita", postgresql_where=sa.text("estado = 'HELD'")
    )
    op.drop_index("ix_cita_estado_inicio", table_name="cita")
    op.drop_table("cita")
    op.drop_index(
        "ix_calendario_conexion_a_renovar",
        table_name="calendario_conexion",
        postgresql_where=sa.text("estado_sincronizacion = 'CONECTADO'"),
    )
    op.drop_table("calendario_conexion")
    op.drop_index("ix_bloqueo_sede_rango", table_name="bloqueo_agenda")
    op.drop_index("ix_bloqueo_profesional_rango", table_name="bloqueo_agenda")
    op.drop_table("bloqueo_agenda")
    op.drop_index("ix_antecedente_paciente", table_name="antecedente")
    op.drop_table("antecedente")
    op.drop_index("ix_ambito_usuario_rol_tipo", table_name="ambito_asignacion")
    op.drop_table("ambito_asignacion")
    op.drop_index("ix_alergia_activa", table_name="alergia", postgresql_where=sa.text("activa"))
    op.drop_table("alergia")
    op.drop_index("ix_agenda_plantilla_profesional", table_name="agenda_plantilla")
    op.drop_table("agenda_plantilla")
    op.drop_table("usuario_rol")
    op.drop_index(
        "ix_token_un_uso_pendientes",
        table_name="token_un_uso",
        postgresql_where=sa.text("usado_en IS NULL"),
    )
    op.drop_table("token_un_uso")
    op.drop_index("ix_sesion_familia", table_name="sesion")
    op.drop_index(
        "ix_sesion_activas",
        table_name="sesion",
        postgresql_where=sa.text("revocada_en IS NULL AND usada_en IS NULL"),
    )
    op.drop_table("sesion")
    op.drop_index("ix_servicio_especialidad_activo", table_name="servicio")
    op.drop_table("servicio")
    op.drop_table("rol_permiso")
    op.drop_index("ix_profesional_especialidad", table_name="profesional")
    op.drop_index("ix_profesional_clinica_activo", table_name="profesional")
    op.drop_table("profesional")
    op.drop_index(
        "ix_contacto_emergencia",
        table_name="paciente_contacto",
        postgresql_where=sa.text("es_emergencia"),
    )
    op.drop_table("paciente_contacto")
    op.drop_index("ix_historial_acceso_usuario", table_name="historial_acceso")
    op.drop_index("ix_historial_acceso_ip", table_name="historial_acceso")
    op.drop_index("ix_historial_acceso_correo", table_name="historial_acceso")
    op.drop_table("historial_acceso")
    op.drop_index("ix_feriado_clinica_fecha", table_name="feriado")
    op.drop_table("feriado")
    op.drop_index("ix_documento_paciente", table_name="documento_paciente")
    op.drop_index("ix_documento_hash", table_name="documento_paciente")
    op.drop_index(
        "ix_documento_escaneo_pendiente",
        table_name="documento_paciente",
        postgresql_where=sa.text("escaneo_antivirus = 'PENDIENTE'"),
    )
    op.drop_table("documento_paciente")
    op.drop_table("consultorio")
    op.drop_index(
        "ix_consentimiento_vigente",
        table_name="consentimiento",
        postgresql_where=sa.text("revocado_en IS NULL"),
    )
    op.drop_table("consentimiento")
    op.drop_index(
        "ix_codigo_recuperacion_disponibles",
        table_name="codigo_recuperacion_2fa",
        postgresql_where=sa.text("usado_en IS NULL"),
    )
    op.drop_table("codigo_recuperacion_2fa")
    op.drop_index("ix_usuario_clinica_activo", table_name="usuario")
    op.drop_table("usuario")
    op.drop_index("ix_sede_clinica_activa", table_name="sede")
    op.drop_table("sede")
    op.drop_index(
        "ix_rol_sistema_codigo", table_name="rol", postgresql_where=sa.text("clinica_id IS NULL")
    )
    op.drop_index(
        "ix_rol_clinica_codigo",
        table_name="rol",
        postgresql_where=sa.text("clinica_id IS NOT NULL"),
    )
    op.drop_table("rol")
    op.drop_index(
        "ix_recordatorio_entidad",
        table_name="recordatorio",
        postgresql_where=sa.text("estado = 'PROGRAMADO'"),
    )
    op.drop_index(
        "ix_recordatorio_a_encolar",
        table_name="recordatorio",
        postgresql_where=sa.text("estado = 'PROGRAMADO'"),
    )
    op.drop_table("recordatorio")
    op.drop_index("ix_paciente_whatsapp", table_name="paciente")
    op.drop_index(
        "ix_paciente_documento",
        table_name="paciente",
        postgresql_where=sa.text("numero_documento IS NOT NULL"),
    )
    op.drop_index("ix_paciente_apellido", table_name="paciente")
    op.drop_table("paciente")
    op.drop_table("especialidad")
    op.drop_table("descanso")
    op.drop_index(
        "ix_configuracion_una_vigente_por_clave",
        table_name="configuracion_clinica",
        postgresql_where=sa.text("vigente"),
    )
    op.drop_table("configuracion_clinica")
    op.drop_table("permiso")
    op.drop_index("ix_outbox_referencia_externa", table_name="outbox_mensaje")
    op.drop_index(
        "ix_outbox_pendientes",
        table_name="outbox_mensaje",
        postgresql_where=sa.text("estado = 'PENDIENTE'"),
    )
    op.drop_index("ix_outbox_origen", table_name="outbox_mensaje")
    op.drop_index(
        "ix_outbox_fallidos",
        table_name="outbox_mensaje",
        postgresql_where=sa.text("estado = 'FALLIDO'"),
    )
    op.drop_index(
        "ix_outbox_en_proceso",
        table_name="outbox_mensaje",
        postgresql_where=sa.text("estado = 'EN_PROCESO'"),
    )
    op.drop_table("outbox_mensaje")
    op.drop_index("ix_horario_propietario", table_name="horario_atencion")
    op.drop_table("horario_atencion")
    op.drop_table("clinica")
    op.drop_index("ix_clave_idempotencia_expiracion", table_name="clave_idempotencia")
    op.drop_table("clave_idempotencia")
    op.drop_index(
        "ix_auditoria_revision_seguridad",
        table_name="auditoria",
        postgresql_where=sa.text("resultado = 'DENEGADO' OR nivel_sensibilidad = 'N3'"),
    )
    op.drop_index("ix_auditoria_paciente", table_name="auditoria")
    op.drop_index("ix_auditoria_entidad", table_name="auditoria")
    op.drop_index("ix_auditoria_correlacion", table_name="auditoria")
    op.drop_index("ix_auditoria_actor", table_name="auditoria")
    op.drop_index("ix_auditoria_accion", table_name="auditoria")
    op.drop_table("auditoria")
    # ### end Alembic commands ###
