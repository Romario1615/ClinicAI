"""Indice funcional del telefono de WhatsApp normalizado.

Corrige un fallo real, no anade una optimizacion.

El problema
-----------
`paciente.telefono_whatsapp` guarda el numero como lo escribio el personal
(«+593 99 900 0333»), porque es lo legible en un panel.  El webhook de WhatsApp
entrega solo digitos («593999000333»).  Comparar las dos formas literalmente no
encuentra al paciente.

La consecuencia era que **un paciente que respondia BAJA no quedaba dado de
baja**: la revocacion de consentimiento no encontraba a quien revocar, y el
sistema le seguia escribiendo.  Es el fallo exacto que ADR-0017 dice que no
puede ocurrir, y se descubrio ejerciendo el sistema con las semillas reales,
con 891 pruebas en verde.

La correccion
-------------
El servicio normaliza la columna en el `WHERE` con
`regexp_replace(telefono_whatsapp, '\D', '', 'g')`.  Este indice es lo que
impide que esa normalizacion obligue a recorrer la tabla `paciente` en cada
mensaje entrante: `regexp_replace` es IMMUTABLE y por tanto indexable.

La expresion debe coincidir **estructuralmente** con la de la consulta -- de ahi
que ambas se construyan desde `telefono_normalizado()` en el modelo, y que los
argumentos del patron vayan como literales y no como parametros enlazados.

Es parcial sobre los que tienen numero: un indice sobre los nulos no se
consulta nunca.

Revision ID: c8c4f1a49870
Revises: 490988d20cbd
Fecha: 2026-09-12 17:31:06.481885+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8c4f1a49870"
down_revision: str | None = "490988d20cbd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_paciente_whatsapp_normalizado",
        "paciente",
        ["clinica_id", sa.literal_column("regexp_replace(telefono_whatsapp, '\\D', '', 'g')")],
        unique=False,
        postgresql_where=sa.text("telefono_whatsapp IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_paciente_whatsapp_normalizado",
        table_name="paciente",
        postgresql_where=sa.text("telefono_whatsapp IS NOT NULL"),
    )
