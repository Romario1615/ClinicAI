"""Admite el canal DEMO en conversacion y el origen DEMO_LOCAL en auditoria.

Por que un canal propio y no reutilizar WHATSAPP
------------------------------------------------
Un hilo de simulacion no puede ser indistinguible de uno real.  Si la
demostracion abriera conversaciones con `canal = 'WHATSAPP'`, cualquier
consulta que busque hilos pendientes -- la cola del personal, un futuro
recordatorio, el outbox -- los trataria como un paciente al que se le puede
escribir.  Marcarlo por el formato del telefono no sirve: bastaria con que una
sola consulta olvidara ese detalle.

El indice unico de hilo activo incluye `canal`, asi que una conversacion de
demostracion y una real sobre el mismo numero no se estorban.

Por el mismo motivo se admite `DEMO_LOCAL` como origen de auditoria: sin el,
una revision no podria distinguir una reserva simulada de una real, que es
justo para lo que existe ese campo.

Revision ID: 7c1d9a4b2f38
Revises: c6cb53c8c608
Create Date: 2026-09-14 09:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7c1d9a4b2f38"
down_revision: str | None = "c6cb53c8c608"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Nombre desnudo: la convencion de nombres del proyecto antepone
# `ck_conversacion_` por su cuenta. Pasarlo ya prefijado lo duplica.
_RESTRICCION = "canal_valido"
_ORIGEN = "origen_valido"


def upgrade() -> None:
    op.drop_constraint(_RESTRICCION, "conversacion", type_="check")
    op.create_check_constraint(
        _RESTRICCION,
        "conversacion",
        "canal IN ('WHATSAPP', 'DEMO')",
    )
    op.drop_constraint(_ORIGEN, "auditoria", type_="check")
    op.create_check_constraint(
        _ORIGEN,
        "auditoria",
        "origen IN ('WEB', 'API', 'WHATSAPP', 'WORKER', 'DEMO_LOCAL')",
    )


def downgrade() -> None:
    """Vuelve a restringir el canal a WHATSAPP.

    Las conversaciones de demostracion existentes **se eliminan**: con ellas
    presentes la restriccion no se puede volver a crear.  Es aceptable porque
    la demostracion solo existe en el entorno local y sus hilos no contienen
    texto del paciente; la auditoria de las herramientas invocadas si queda,
    porque vive en `auditoria` y no se borra aqui.

    Se eliminan primero las sesiones, que referencian la conversacion.
    """
    op.execute("DELETE FROM sesion_agente_demo")
    op.execute("DELETE FROM conversacion WHERE canal = 'DEMO'")
    # La auditoria no se borra: se reetiqueta como API, que es el origen mas
    # cercano. Perder el rastro de lo que hizo el agente seria peor que
    # perder la etiqueta que lo distinguia.
    op.execute("UPDATE auditoria SET origen = 'API' WHERE origen = 'DEMO_LOCAL'")
    op.drop_constraint(_ORIGEN, "auditoria", type_="check")
    op.create_check_constraint(
        _ORIGEN,
        "auditoria",
        "origen IN ('WEB', 'API', 'WHATSAPP', 'WORKER')",
    )
    op.drop_constraint(_RESTRICCION, "conversacion", type_="check")
    op.create_check_constraint(
        _RESTRICCION,
        "conversacion",
        "canal IN ('WHATSAPP')",
    )
