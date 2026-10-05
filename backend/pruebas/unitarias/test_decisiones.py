"""Pruebas del modelo de decision tipada (Jev) y su respaldo por reglas.

* La peticion a Jev tiene la forma documentada (`state` + `questions` con
  `choice` y `noul`) y **no** lleva identificadores del paciente.
* La respuesta se interpreta y se valida; una respuesta fuera de esquema o
  un fallo de red caen al respaldo por reglas, nunca rompen el chat.
* La barrera clinica gana a cualquier intencion: con probabilidad clinica alta
  se deriva aunque el mensaje "parezca" una reserva.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.ia.conversacion import decision_determinista
from app.ia.decisiones import (
    ClasificadorJev,
    ClasificadorReglas,
    DecisionTipada,
    Intencion,
)

pytestmark = [pytest.mark.unitaria, pytest.mark.asyncio]

NEGOCIO = {
    "paciente_id": "p-1",
    "profesional_id": "pr-1",
    "servicio_id": "s-1",
    "sede_id": "se-1",
    "desde": "2026-10-06T00:00:00Z",
    "hasta": "2026-10-07T00:00:00Z",
}


def _respuesta_jev(
    intencion: str, confianza: float, clinica: float, urgencia: float
) -> dict[str, Any]:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "intencion": {
                "type": "choice",
                "choice": intencion,
                "confidence": confianza,
                "probabilities": {intencion: confianza},
            },
            "pregunta_clinica": {"type": "noul", "noul": clinica},
            "urgencia": {"type": "noul", "noul": urgencia},
        },
        "usage": {"input_tokens": 120, "output_tokens": 10},
    }


def _cliente(manejador: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(manejador))


async def test_peticion_a_jev_tiene_la_forma_documentada() -> None:
    capturada: dict[str, Any] = {}

    def manejador(peticion: httpx.Request) -> httpx.Response:
        capturada["url"] = str(peticion.url)
        capturada["auth"] = peticion.headers["Authorization"]
        capturada["cuerpo"] = json.loads(peticion.content)
        return httpx.Response(200, json=_respuesta_jev("consultar_citas", 0.95, 0.01, 0.0))

    jev = ClasificadorJev(clave="clave-sintetica", cliente=_cliente(manejador))
    decision = await jev.clasificar("¿Tengo cita mañana?")

    assert capturada["url"] == "https://api.typesafe.ai/v1/systemone"
    assert capturada["auth"] == "Bearer clave-sintetica"
    cuerpo = capturada["cuerpo"]
    assert cuerpo["model"] == "jev-latest"
    assert cuerpo["state"] == "¿Tengo cita mañana?"
    assert cuerpo["questions"]["intencion"]["type"] == "choice"
    assert set(cuerpo["questions"]["intencion"]["criteria"]) == {i.value for i in Intencion}
    assert cuerpo["questions"]["pregunta_clinica"]["type"] == "noul"
    assert decision == DecisionTipada(Intencion.CONSULTAR_CITAS, 0.95, 0.01, 0.0, "jev")


async def test_el_texto_enviado_no_lleva_identificadores() -> None:
    """Solo viaja el texto del mensaje: ni telefono, ni id, ni nombre."""
    enviado: dict[str, Any] = {}

    def manejador(peticion: httpx.Request) -> httpx.Response:
        enviado.update(json.loads(peticion.content))
        return httpx.Response(200, json=_respuesta_jev("otro", 0.6, 0.0, 0.0))

    await ClasificadorJev(clave="k", cliente=_cliente(manejador)).clasificar("hola")
    assert set(enviado) == {"model", "state", "questions"}


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(500),
        httpx.Response(200, json={"answers": {}}),
        httpx.Response(200, json=_respuesta_jev("borrar_base_de_datos", 0.99, 0.0, 0.0)),
        httpx.Response(200, json=_respuesta_jev("otro", 1.7, 0.0, 0.0)),
    ],
)
async def test_fallo_o_respuesta_fuera_de_esquema_cae_al_respaldo(
    respuesta: httpx.Response,
) -> None:
    jev = ClasificadorJev(clave="k", cliente=_cliente(lambda _peticion: respuesta))
    decision = await jev.clasificar("quiero reservar una cita")
    assert decision.proveedor == "reglas"
    assert decision.intencion is Intencion.BUSCAR_HORARIOS


async def test_reglas_detectan_lo_clinico_y_lo_urgente() -> None:
    reglas = ClasificadorReglas()
    assert (await reglas.clasificar("me duele mucho la muela")).pregunta_clinica == 1.0
    assert (await reglas.clasificar("es urgente")).urgencia == 1.0
    assert (await reglas.clasificar("mis citas")).intencion is Intencion.CONSULTAR_CITAS


# ===========================================================================
#  Del valor tipado a la accion
# ===========================================================================
def _decidir(decision: DecisionTipada) -> Any:
    return decision_determinista(decision, NEGOCIO, umbral_clinico=0.35, umbral_intencion=0.85)


async def test_la_barrera_clinica_gana_a_la_intencion() -> None:
    """Parece una reserva, pero describe un sintoma: va a una persona."""
    resultado = _decidir(DecisionTipada(Intencion.BUSCAR_HORARIOS, 0.99, 0.6, 0.0, "jev"))
    assert resultado.herramienta == "handoff_to_human"
    assert resultado.argumentos["motivo"] == "SINTOMA_O_DIAGNOSTICO"


async def test_la_urgencia_deriva_con_su_motivo() -> None:
    resultado = _decidir(DecisionTipada(Intencion.OTRO, 0.9, 0.1, 0.8, "jev"))
    assert resultado.argumentos["motivo"] == "URGENCIA_DECLARADA"


async def test_intencion_segura_con_confianza_alta_no_usa_el_llm() -> None:
    resultado = _decidir(DecisionTipada(Intencion.CONSULTAR_CITAS, 0.95, 0.0, 0.0, "jev"))
    assert resultado.herramienta == "get_patient_appointments"


async def test_confianza_baja_sigue_al_proveedor() -> None:
    assert _decidir(DecisionTipada(Intencion.CONSULTAR_CITAS, 0.6, 0.0, 0.0, "jev")) is None


async def test_cancelar_nunca_se_resuelve_por_probabilidad() -> None:
    """Cancelar cambia estado: no hay atajo, decide el flujo con confirmacion."""
    assert _decidir(DecisionTipada(Intencion.CANCELAR, 0.99, 0.0, 0.0, "jev")) is None
