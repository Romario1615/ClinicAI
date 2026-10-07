"""Protege el contenido de recetas firmadas y sus versiones.

Revision ID: 20261006_008
Revises: 20261006_007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_008"
down_revision: str | None = "20261006_007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RECETA_INMUTABLE = """
CREATE OR REPLACE FUNCTION receta_solo_transiciones() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Una receta no se elimina: se suspende o se sustituye por una versión nueva.'
            USING ERRCODE = '23514';
    END IF;

    IF (OLD.estado <> 'BORRADOR' OR NEW.estado <> 'BORRADOR') AND (
        NEW.clinica_id IS DISTINCT FROM OLD.clinica_id
        OR NEW.paciente_id IS DISTINCT FROM OLD.paciente_id
        OR NEW.profesional_id IS DISTINCT FROM OLD.profesional_id
        OR NEW.nota_id IS DISTINCT FROM OLD.nota_id
        OR NEW.receta_anterior_id IS DISTINCT FROM OLD.receta_anterior_id
        OR NEW.indicaciones_generales IS DISTINCT FROM OLD.indicaciones_generales
        OR NEW.vigente_desde IS DISTINCT FROM OLD.vigente_desde
        OR NEW.vigente_hasta IS DISTINCT FROM OLD.vigente_hasta
        OR NEW.creado_en IS DISTINCT FROM OLD.creado_en
        OR NEW.creado_por IS DISTINCT FROM OLD.creado_por
    ) THEN
        RAISE EXCEPTION 'El contenido de una receta firmada es inmutable; cree una nueva versión.'
            USING ERRCODE = '23514';
    END IF;

    IF (OLD.confirmada_en IS NOT NULL AND NEW.confirmada_en IS DISTINCT FROM OLD.confirmada_en)
       OR (OLD.confirmada_por IS NOT NULL AND NEW.confirmada_por IS DISTINCT FROM OLD.confirmada_por)
       OR (OLD.suspendida_en IS NOT NULL AND NEW.suspendida_en IS DISTINCT FROM OLD.suspendida_en)
       OR (OLD.motivo_suspension IS NOT NULL
           AND NEW.motivo_suspension IS DISTINCT FROM OLD.motivo_suspension) THEN
        RAISE EXCEPTION 'La firma y la suspensión de una receta no se reescriben.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER receta_solo_transiciones
  BEFORE UPDATE OR DELETE ON receta
  FOR EACH ROW EXECUTE FUNCTION receta_solo_transiciones();
"""

LINEA_RECETA_SOLO_BORRADOR = """
CREATE OR REPLACE FUNCTION linea_receta_solo_borrador() RETURNS trigger AS $$
DECLARE
    estado_receta text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT estado INTO estado_receta
          FROM receta WHERE id = OLD.receta_id FOR UPDATE;
        IF estado_receta IS DISTINCT FROM 'BORRADOR' THEN
            RAISE EXCEPTION 'La línea de una receta firmada no se edita ni se elimina; cree una versión nueva.'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT estado INTO estado_receta
          FROM receta WHERE id = NEW.receta_id FOR UPDATE;
        IF estado_receta IS DISTINCT FROM 'BORRADOR' THEN
            RAISE EXCEPTION 'Las líneas solo se agregan a recetas en borrador.'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER linea_receta_solo_borrador
  BEFORE INSERT OR UPDATE OR DELETE ON receta_medicamento
  FOR EACH ROW EXECUTE FUNCTION linea_receta_solo_borrador();
"""


def upgrade() -> None:
    op.execute(RECETA_INMUTABLE)
    op.execute(LINEA_RECETA_SOLO_BORRADOR)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS linea_receta_solo_borrador ON receta_medicamento")
    op.execute("DROP FUNCTION IF EXISTS linea_receta_solo_borrador()")
    op.execute("DROP TRIGGER IF EXISTS receta_solo_transiciones ON receta")
    op.execute("DROP FUNCTION IF EXISTS receta_solo_transiciones()")
