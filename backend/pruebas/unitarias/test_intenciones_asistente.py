"""El asistente interno decide qué datos tocar por reglas, no por un modelo."""

from __future__ import annotations

import pytest

from app.modulos.asistente.intenciones import Intencion, interpretar

pytestmark = pytest.mark.unitaria


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("¿Qué puedes hacer?", Intencion.AYUDA),
        ("Mi agenda de hoy", Intencion.AGENDA),
        ("¿Quién sigue?", Intencion.SIGUIENTE),
        ("Resumen del paciente", Intencion.RESUMEN),
        ("¿Tiene alergias?", Intencion.RESUMEN),
        ("Peticiones de más tiempo", Intencion.PROLONGACIONES),
        ("¿Qué le receto?", Intencion.DECISION_CLINICA),
        ("Dame el diagnóstico", Intencion.DECISION_CLINICA),
        ("¿Cambio la dosis?", Intencion.DECISION_CLINICA),
        ("Agrega al conocimiento: los sábados abrimos a las 8", Intencion.BORRADOR_CONOCIMIENTO),
        ("conocimiento: el parqueo es gratuito", Intencion.BORRADOR_CONOCIMIENTO),
        ("Crea una promoción: limpieza con descuento", Intencion.BORRADOR_PROMOCION),
        ("¿Cuál es el horario del sábado?", Intencion.PREGUNTA),
    ],
)
def test_intencion(texto: str, esperada: Intencion) -> None:
    assert interpretar(texto).intencion is esperada


def test_el_borrador_lleva_solo_lo_que_va_despues_de_los_dos_puntos() -> None:
    resultado = interpretar("Agrega a la base de conocimiento: Atendemos sábados de 8 a 13")
    assert resultado.contenido == "Atendemos sábados de 8 a 13"


def test_una_decision_clinica_gana_aunque_mencione_la_historia() -> None:
    assert interpretar("según su historia, ¿qué le receto?").intencion is Intencion.DECISION_CLINICA
