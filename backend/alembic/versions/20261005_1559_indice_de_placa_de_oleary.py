"""Indice de placa de O'Leary (periodoncia).

Registros inmutables: un disparador rechaza UPDATE y DELETE. La serie temporal
es la historia de higiene del paciente.

Revision ID: 20261005_007
Revises: 20261005_006
Fecha: 2026-10-05 15:59:56.375651+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261005_007"
down_revision: str | None = "20261005_006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REGISTRO_PLACA_INMUTABLE = """
CREATE OR REPLACE FUNCTION registro_placa_inmutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Un control de placa no se modifica ni se borra: registre uno nuevo.'
        USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER registro_placa_inmutable
  BEFORE UPDATE OR DELETE ON registro_placa
  FOR EACH ROW EXECUTE FUNCTION registro_placa_inmutable();
"""


def upgrade() -> None:
    op.create_table(
        "registro_placa",
        sa.Column("clinica_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), nullable=False),
        sa.Column("profesional_id", sa.Uuid(), nullable=False),
        sa.Column("piezas_evaluadas", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("superficies_con_placa", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_superficies", sa.Integer(), nullable=False),
        sa.Column("total_con_placa", sa.Integer(), nullable=False),
        sa.Column("porcentaje", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "porcentaje >= 0 AND porcentaje <= 100",
            name=op.f("ck_registro_placa_porcentaje_valido"),
        ),
        sa.CheckConstraint(
            "total_con_placa >= 0 AND total_con_placa <= total_superficies",
            name=op.f("ck_registro_placa_conteo_coherente"),
        ),
        sa.CheckConstraint("total_superficies > 0", name=op.f("ck_registro_placa_con_superficies")),
        sa.ForeignKeyConstraint(
            ["clinica_id"],
            ["clinica.id"],
            name=op.f("fk_registro_placa_clinica_id_clinica"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["paciente_id"],
            ["paciente.id"],
            name=op.f("fk_registro_placa_paciente_id_paciente"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profesional_id"],
            ["profesional.id"],
            name=op.f("fk_registro_placa_profesional_id_profesional"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registro_placa")),
    )
    op.create_index(
        "ix_registro_placa_paciente", "registro_placa", ["paciente_id", "creado_en"], unique=False
    )
    op.execute(REGISTRO_PLACA_INMUTABLE)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS registro_placa_inmutable ON registro_placa")
    op.execute("DROP FUNCTION IF EXISTS registro_placa_inmutable()")
    op.drop_index("ix_registro_placa_paciente", table_name="registro_placa")
    op.drop_table("registro_placa")
