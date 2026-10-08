"""Fotografías privadas de registros, con retirada lógica y trazabilidad."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_033"
down_revision: str | None = "20261008_032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "foto_registro",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "clinica_id",
            sa.Uuid(),
            sa.ForeignKey("clinica.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tipo_registro", sa.String(32), nullable=False),
        sa.Column("registro_id", sa.Uuid(), nullable=False),
        sa.Column("paciente_id", sa.Uuid(), sa.ForeignKey("paciente.id", ondelete="RESTRICT")),
        sa.Column("nivel_sensibilidad", sa.String(2), nullable=False),
        sa.Column("clave_objeto", sa.String(300), nullable=False, unique=True),
        sa.Column("tipo_mime", sa.String(32), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("descripcion", sa.String(500)),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("creado_por", sa.Uuid()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True)),
        sa.Column("actualizado_por", sa.Uuid()),
        sa.Column("anulado_en", sa.DateTime(timezone=True)),
        sa.Column("anulado_por", sa.Uuid()),
        sa.Column("motivo_anulacion", sa.String()),
        sa.CheckConstraint(
            "nivel_sensibilidad IN ('N1','N2','N3') OR (tipo_registro = 'conocimiento' AND nivel_sensibilidad = 'N0')",
            name="sensibilidad_valida",
        ),
        sa.CheckConstraint("tamano_bytes > 0", name="tamano_positivo"),
    )
    op.create_index(
        "ix_foto_registro_destino", "foto_registro", ["clinica_id", "tipo_registro", "registro_id"]
    )
    op.execute("""CREATE FUNCTION proteger_foto_registro() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP <> 'UPDATE' THEN RAISE EXCEPTION 'Solo se permite retirar fotos con motivo'; END IF;
          IF OLD.anulado_en IS NOT NULL OR NEW.anulado_en IS NULL OR NEW.anulado_por IS NULL
            OR length(trim(NEW.motivo_anulacion)) < 8
            OR (to_jsonb(OLD) - ARRAY['anulado_en','anulado_por','motivo_anulacion','actualizado_en','actualizado_por'])
              IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['anulado_en','anulado_por','motivo_anulacion','actualizado_en','actualizado_por'])
          THEN RAISE EXCEPTION 'La fotografía es inmutable; solo retirada con motivo'; END IF;
          RETURN NEW;
        END; $$""")
    op.execute(
        "CREATE TRIGGER foto_registro_inmutable BEFORE UPDATE OR DELETE ON foto_registro FOR EACH ROW EXECUTE FUNCTION proteger_foto_registro()"
    )
    op.execute(
        "CREATE TRIGGER foto_registro_no_truncate BEFORE TRUNCATE ON foto_registro FOR EACH STATEMENT EXECUTE FUNCTION proteger_foto_registro()"
    )


def downgrade() -> None:
    op.drop_table("foto_registro")
    op.execute("DROP FUNCTION proteger_foto_registro()")
