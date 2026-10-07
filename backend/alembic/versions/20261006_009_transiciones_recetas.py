"""Restringe transiciones y firma de recetas al flujo clinico valido.

Revision ID: 20261006_009
Revises: 20261006_008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261006_009"
down_revision: str | None = "20261006_008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRANSICIONES_VALIDAS = """
CREATE OR REPLACE FUNCTION receta_solo_transiciones() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Una receta no se elimina: se suspende o se sustituye por una versión nueva.'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.estado IS DISTINCT FROM OLD.estado AND NOT (
        (OLD.estado = 'BORRADOR' AND NEW.estado IN ('CONFIRMADA', 'SUSPENDIDA'))
        OR (OLD.estado = 'CONFIRMADA' AND NEW.estado = 'SUSPENDIDA')
    ) THEN
        RAISE EXCEPTION 'estado_receta_transicion_invalida: solo se permite borrador → confirmada/suspendida o confirmada → suspendida.'
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

    IF (
        (OLD.confirmada_en IS NULL AND NEW.confirmada_en IS NOT NULL)
        OR (OLD.confirmada_por IS NULL AND NEW.confirmada_por IS NOT NULL)
    ) AND NOT (OLD.estado = 'BORRADOR' AND NEW.estado = 'CONFIRMADA') THEN
        RAISE EXCEPTION 'receta_firma_fuera_de_transicion: la firma solo se establece al confirmar.'
            USING ERRCODE = '23514';
    END IF;

    IF (
        (OLD.suspendida_en IS NULL AND NEW.suspendida_en IS NOT NULL)
        OR (OLD.motivo_suspension IS NULL AND NEW.motivo_suspension IS NOT NULL)
    ) AND NOT (
        NEW.estado = 'SUSPENDIDA' AND OLD.estado IN ('BORRADOR', 'CONFIRMADA')
    ) THEN
        RAISE EXCEPTION 'receta_suspension_fuera_de_transicion: la suspensión solo se registra al suspender.'
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
"""

# Restauracion exacta del comportamiento anterior de 008 para que el downgrade
# revierta solo esta revision y deje intactas las protecciones ya instaladas.
TRANSICIONES_008 = """
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
"""


def upgrade() -> None:
    op.execute(TRANSICIONES_VALIDAS)
    op.create_check_constraint(
        "borrador_sin_firma",
        "receta",
        "estado <> 'BORRADOR' OR (confirmada_en IS NULL AND confirmada_por IS NULL)",
    )
    op.create_check_constraint(
        "suspension_exige_instante",
        "receta",
        "estado <> 'SUSPENDIDA' OR suspendida_en IS NOT NULL",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE receta DROP CONSTRAINT IF EXISTS suspension_exige_instante")
    op.execute("ALTER TABLE receta DROP CONSTRAINT IF EXISTS borrador_sin_firma")
    op.execute(TRANSICIONES_008)
