"""Texto del agente por WhatsApp: legible y sin datos clinicos."""

import pytest

from app.ia.herramientas.contrato import ResultadoHerramienta
from app.modulos.conversaciones.redaccion_whatsapp import redactar

pytestmark = pytest.mark.unitaria

ZONA = "America/Guayaquil"


def test_los_horarios_se_numeran_en_la_hora_local() -> None:
    resultado = ResultadoHerramienta(
        exito=True,
        mensaje="Hay 2 horarios disponibles.",
        datos={
            "turnos": [
                {"inicio": "2026-04-16T14:00:00+00:00"},
                {"inicio": "2026-04-16T14:30:00+00:00"},
            ],
            "zona_horaria": ZONA,
        },
    )

    texto = redactar(resultado, ZONA)

    assert texto.splitlines() == [
        "Hay 2 horarios disponibles.",
        "1) jue 16/04 09:00",
        "2) jue 16/04 09:30",
        "Responda con el número del horario que prefiera.",
    ]


def test_citas_y_pagos_solo_llevan_fecha_estado_e_importe() -> None:
    citas = ResultadoHerramienta(
        exito=True,
        mensaje="Tiene 1 cita(s) proxima(s).",
        datos={
            "citas": [
                {"cita_id": "x", "inicio": "2026-04-17T15:30:00+00:00", "estado": "CONFIRMED"}
            ]
        },
    )
    pagos = ResultadoHerramienta(
        exito=True,
        mensaje="Tiene 1 pago(s) sin cerrar.",
        datos={
            "pagos": [
                {
                    "importe": "25.50",
                    "moneda": "USD",
                    "estado": "Pendiente",
                    "cita": "2026-04-17T15:30:00+00:00",
                }
            ]
        },
    )

    assert "• vie 17/04 10:30 — confirmada" in redactar(citas, ZONA)
    assert "• 25.50 USD — pendiente — cita del vie 17/04" in redactar(pagos, ZONA)


def test_el_horario_apartado_dice_hasta_cuando_y_como_confirmar() -> None:
    resultado = ResultadoHerramienta(
        exito=True,
        mensaje="He apartado ese horario.",
        datos={
            "cita_id": "x",
            "inicio": "2026-04-16T14:00:00+00:00",
            "expira_en": "2026-04-15T14:15:00+00:00",
        },
    )

    texto = redactar(resultado, ZONA)

    assert "Horario: jue 16/04 09:00." in texto
    assert "hasta las 09:15" in texto and "«confirmar»" in texto


def test_sin_datos_es_solo_el_titular() -> None:
    assert redactar(ResultadoHerramienta(exito=True, mensaje="Hola."), ZONA) == "Hola."
