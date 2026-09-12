"""Conversaciones y mensajes entrantes de WhatsApp.

Dos tablas y dos garantias en el motor:

1. `uq_mensaje_entrante_external_id` es LA deduplicacion del webhook.  Meta
   entrega al menos una vez y reintenta ante cualquier duda; sin esta
   restriccion, un reintento volveria a ejecutar el efecto del mensaje, y el
   efecto puede ser revocar el consentimiento de un paciente.  Vive en la base
   de datos y no en Redis porque debe durar lo mismo que el dato de negocio.

2. `ix_conversacion_activa_unica` es un indice unico **parcial**: un solo hilo
   no cerrado por numero y canal, pero tantos hilos cerrados en el historico
   como haga falta.  Sin la clausula parcial no se podria conservar el
   historico, que es justo lo que hay que conservar.

El `CHECK` de `intencion` mantiene el catalogo cerrado en el motor.  Anadir
una intencion exige migracion, y eso es deliberado: cada intencion nueva es
una decision que el sistema toma sin preguntar a una persona.

Revision ID: 490988d20cbd
Revises: ca0c0c08ad86
Fecha: 2026-09-12 16:47:11.378508+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "490988d20cbd"
down_revision: str | None = "ca0c0c08ad86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversacion",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("canal", sa.String(length=16), nullable=False),
        sa.Column("telefono", sa.String(length=32), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=True),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("ventana_expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asignado_a_usuario_id", sa.Uuid(), nullable=True),
        sa.Column("motivo_handoff", sa.String(length=255), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "ultima_actividad_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint("canal IN ('WHATSAPP')", name=op.f("ck_conversacion_canal_valido")),
        sa.CheckConstraint(
            "estado <> 'EN_HANDOFF' OR motivo_handoff IS NOT NULL",
            name=op.f("ck_conversacion_handoff_con_motivo"),
        ),
        sa.CheckConstraint(
            "estado IN ('ABIERTA', 'EN_HANDOFF', 'CERRADA')",
            name=op.f("ck_conversacion_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["asignado_a_usuario_id"],
            ["usuario.id"],
            name=op.f("fk_conversacion_asignado_a_usuario_id_usuario"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_conversacion_clinica_id_clinica"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_conversacion_paciente_id_paciente"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversacion")),
    )
    op.create_index(
        "ix_conversacion_activa_unica",
        "conversacion",
        ["clinica_id", "canal", "telefono"],
        unique=True,
        postgresql_where=sa.text("estado <> 'CERRADA'"),
    )
    op.create_index(
        "ix_conversacion_en_handoff",
        "conversacion",
        ["clinica_id", "ultima_actividad_en"],
        unique=False,
        postgresql_where=sa.text("estado = 'EN_HANDOFF'"),
    )
    op.create_table(
        "mensaje_entrante",
        sa.Column("conversacion_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("telefono_origen", sa.String(length=32), nullable=False),
        sa.Column("tipo", sa.String(length=24), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("carga_util", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("intencion", sa.String(length=24), nullable=False),
        sa.Column("recibido_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("procesado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', 'BAJA', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
            name=op.f("ck_mensaje_entrante_intencion_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["conversacion_id"],
            ["conversacion.id"],
            name=op.f("fk_mensaje_entrante_conversacion_id_conversacion"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mensaje_entrante")),
        sa.UniqueConstraint("external_id", name="uq_mensaje_entrante_external_id"),
    )
    op.create_index(
        "ix_mensaje_entrante_conversacion",
        "mensaje_entrante",
        ["conversacion_id", "recibido_en"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mensaje_entrante_conversacion", table_name="mensaje_entrante")
    op.drop_table("mensaje_entrante")
    op.drop_index(
        "ix_conversacion_en_handoff",
        table_name="conversacion",
        postgresql_where=sa.text("estado = 'EN_HANDOFF'"),
    )
    op.drop_index(
        "ix_conversacion_activa_unica",
        table_name="conversacion",
        postgresql_where=sa.text("estado <> 'CERRADA'"),
    )
    op.drop_table("conversacion")
