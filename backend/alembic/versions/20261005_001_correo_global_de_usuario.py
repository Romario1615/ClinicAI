"""Resuelve las cuentas por correo sin pedir el identificador de clínica.

Revision ID: 20261005_001
Revises: 751245a5a937
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_001"
down_revision: str | None = "751245a5a937"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicado = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT lower(correo) FROM usuario "
                "GROUP BY lower(correo) HAVING count(*) > 1 LIMIT 1"
            )
        )
        .scalar_one_or_none()
    )
    if duplicado is not None:
        raise RuntimeError(
            "No se puede quitar el identificador de clínica del acceso: "
            "hay correos repetidos entre clínicas. Unifique las cuentas antes de migrar."
        )

    op.drop_constraint("uq_usuario_clinica_id_correo", "usuario", type_="unique")
    op.create_index(
        "uq_usuario_correo_normalizado",
        "usuario",
        [sa.text("lower(correo)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_usuario_correo_normalizado", table_name="usuario")
    op.create_unique_constraint("uq_usuario_clinica_id_correo", "usuario", ["clinica_id", "correo"])
