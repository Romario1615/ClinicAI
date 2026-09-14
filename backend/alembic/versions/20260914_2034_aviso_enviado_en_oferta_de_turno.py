"""Marca si una oferta de turno llego a comunicarse al paciente.

Por que hace falta
------------------
La oferta se creaba y **nadie le decia nada al paciente**: la plantilla
`OFERTA_TURNO` existia y ningun codigo la encolaba.  Quince minutos despues la
oferta vencia sola, sumaba una a `ofertas_vencidas`, y a la tercera la entrada
pasaba a `EXPIRADA` -- el paciente quedaba fuera de la lista de espera sin haber
hecho nada mal y sin enterarse de nada.

La solucion tiene dos mitades, y esta columna es la segunda:

1. Se encola el aviso al crear la oferta.
2. Una oferta que **no** se pudo comunicar no cuenta en contra al vencer.

La oferta se sigue creando aunque no haya consentimiento para mensajes
automaticos: recepcion puede llamar por telefono, y bloquearla dejaria a ese
paciente fuera de la lista de espera para siempre.

El valor de las filas existentes
--------------------------------
`false`, y es el valor honesto: ninguna oferta anterior a este cambio se
comunico nunca.  Marcarlas como avisadas las haria contar contra pacientes que
no recibieron nada.

`server_default` es imprescindible: la columna es `NOT NULL` y la tabla puede
tener filas.  Se conserva en el esquema para que un `INSERT` que no mencione la
columna siga siendo valido.

Revision ID: 751245a5a937
Revises: 7af9728c1c2e
Fecha: 2026-09-14 20:34:59.871811+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "751245a5a937"
down_revision: str | None = "7af9728c1c2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "oferta_turno",
        sa.Column(
            "aviso_enviado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("oferta_turno", "aviso_enviado")
