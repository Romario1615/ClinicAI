"""Guarda la lista de pacientes ofrecida cuando un telefono es ambiguo.

Un telefono no identifica a una persona: una madre gestiona las citas de sus
tres hijos desde el mismo numero.  Cuando ocurre, el sistema ofrece la lista
numerada y espera a que quien escribe elija.

La lista se guarda **con su orden** en lugar de reconstruirse al recibir la
respuesta: entre la oferta y el «2» puede haberse creado una ficha nueva con
ese mismo telefono, y entonces la segunda opcion seria otra persona.

El JSON lleva su propia caducidad.  Una lista ofrecida ayer y respondida hoy es
una respuesta a una pregunta que quien escribe ya no recuerda.

Columna anulable y sin valor por defecto: una conversacion sin ambiguedad no
tiene nada pendiente, y `NULL` lo dice mejor que un objeto vacio.


Revision ID: 7af9728c1c2e
Revises: 7c1d9a4b2f38
Fecha: 2026-09-14 04:29:43.019681+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7af9728c1c2e"
down_revision: str | None = "7c1d9a4b2f38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversacion",
        sa.Column("seleccion_pendiente", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversacion", "seleccion_pendiente")
