"""Periodontograma de seis sitios; correcciones y anulaciones inmutables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_032"
down_revision: str | None = "20261007_031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "periodontograma",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "clinica_id",
            sa.Uuid(),
            sa.ForeignKey("clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "paciente_id",
            sa.Uuid(),
            sa.ForeignKey("paciente.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profesional_id",
            sa.Uuid(),
            sa.ForeignKey("profesional.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "especialidad_id",
            sa.Uuid(),
            sa.ForeignKey("especialidad.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sede_id", sa.Uuid(), sa.ForeignKey("sede.id", ondelete="RESTRICT")),
        sa.Column("cita_id", sa.Uuid(), sa.ForeignKey("cita.id", ondelete="RESTRICT")),
        sa.Column("raiz_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fecha_examen", sa.Date(), nullable=False),
        sa.Column("piezas", postgresql.JSONB(), nullable=False),
        sa.Column("observaciones", sa.Text()),
        sa.Column("motivo", sa.String(500), nullable=False),
        sa.Column("nivel_sensibilidad", sa.String(2), nullable=False),
        sa.Column("anulado", sa.Boolean(), nullable=False),
        sa.Column("solicitud_hash", sa.String(64), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True)),
        sa.Column("actualizado_por", sa.Uuid()),
        sa.UniqueConstraint("raiz_id", "version"),
        sa.CheckConstraint("version >= 1", name="version_positiva"),
        sa.CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        sa.CheckConstraint("length(trim(motivo)) >= 8", name="motivo_obligatorio"),
    )
    op.create_index(
        "ix_periodontograma_ambito",
        "periodontograma",
        ["clinica_id", "paciente_id", "profesional_id"],
    )
    op.execute("""CREATE FUNCTION proteger_periodontograma() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'El periodontograma es inmutable; cree una corrección o anulación'; END; $$""")
    op.execute("""CREATE TRIGGER periodontograma_inmutable BEFORE UPDATE OR DELETE OR TRUNCATE
        ON periodontograma FOR EACH STATEMENT EXECUTE FUNCTION proteger_periodontograma()""")


def downgrade() -> None:
    op.drop_table("periodontograma")
    op.execute("DROP FUNCTION proteger_periodontograma()")
