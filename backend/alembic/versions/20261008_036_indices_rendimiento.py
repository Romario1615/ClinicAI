"""Índices de rendimiento: citas del panel y búsqueda de pacientes.

La sala de espera (llegadas sin atender, espera media) y las cancelaciones
del día filtran `cita` por rango de `llegada_en` o `cancelada_en`. Sin índice,
cada carga del panel recorría toda la historia de citas: con 200 000 citas
sintéticas, unos 30 ms por consulta y doce consultas por carga.

Los de llegada y cancelación son parciales (solo filas con valor), así que
ocupan poco. El de `(clinica_id, fin)` sirve a la ocupación del periodo, que
busca citas que se solapan con una ventana (`inicio < hasta AND fin > desde`):
el índice por inicio solo acota por arriba y recorría toda la historia.

En `paciente`, un índice trigram sobre `nombre || ' ' || apellido` sirve a la
búsqueda por nombre (`ILIKE '%termino%'`), que recorría la tabla entera
(40 000 pacientes: 119 ms → 0,9 ms), y `(clinica_id, creado_en)` a las altas
por periodo. Medido sobre una base sintética de 40 000 pacientes y 200 000
citas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_036"
down_revision: str | None = "20261008_035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_cita_llegada",
        "cita",
        ["clinica_id", "llegada_en"],
        postgresql_where=sa.text("llegada_en IS NOT NULL"),
    )
    op.create_index(
        "ix_cita_cancelada",
        "cita",
        ["clinica_id", "cancelada_en"],
        postgresql_where=sa.text("cancelada_en IS NOT NULL"),
    )
    op.create_index("ix_cita_clinica_fin", "cita", ["clinica_id", "fin"])
    # pg_trgm ya está instalada por la migración inicial.
    op.create_index(
        "ix_paciente_nombre_completo_trgm",
        "paciente",
        [sa.literal_column("(nombre || ' ' || apellido) gin_trgm_ops")],
        postgresql_using="gin",
    )
    op.create_index("ix_paciente_creado", "paciente", ["clinica_id", "creado_en"])


def downgrade() -> None:
    op.drop_index("ix_paciente_creado", table_name="paciente")
    op.drop_index("ix_paciente_nombre_completo_trgm", table_name="paciente")
    op.drop_index("ix_cita_clinica_fin", table_name="cita")
    op.drop_index("ix_cita_cancelada", table_name="cita")
    op.drop_index("ix_cita_llegada", table_name="cita")
