"""Agente conversacional en WhatsApp (ADR-0025).

* `conversacion.agente`: memoria y contexto del agente que atiende el hilo.
* El outbox admite el destino `CONVERSACION`: las respuestas dentro de un hilo
  abierto por el paciente van al telefono de ese hilo, no al de la ficha.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261009_037"
down_revision: str | None = "20261008_036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DESTINOS_ANTES = "destino_tipo IN ('PACIENTE', 'PROFESIONAL', 'USUARIO', 'CLINICA')"
_DESTINOS_DESPUES = (
    "destino_tipo IN ('PACIENTE', 'PROFESIONAL', 'USUARIO', 'CLINICA', 'CONVERSACION')"
)


def upgrade() -> None:
    op.add_column(
        "conversacion",
        sa.Column("agente", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_constraint("destino_tipo_valido", "outbox_mensaje", type_="check")
    op.create_check_constraint("destino_tipo_valido", "outbox_mensaje", _DESTINOS_DESPUES)


def downgrade() -> None:
    # Las respuestas a conversaciones no caben en la restriccion anterior: se
    # descartan antes de restaurarla (solo existen si el agente estuvo activo).
    op.execute("DELETE FROM outbox_mensaje WHERE destino_tipo = 'CONVERSACION'")
    op.drop_constraint("destino_tipo_valido", "outbox_mensaje", type_="check")
    op.create_check_constraint("destino_tipo_valido", "outbox_mensaje", _DESTINOS_ANTES)
    op.drop_column("conversacion", "agente")
