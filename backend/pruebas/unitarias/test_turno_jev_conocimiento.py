"""Cómo usa el agente lo que decide JEV y la base de conocimiento.

* Confianza baja de JEV: pregunta con opciones, no adivina.
* Pregunta de información: responde desde documentos publicados; sin LLM
  cita, con LLM redacta solo con las fuentes, sin fuente lo dice.
* Ollama: solo herramientas del catálogo, URL local y, ante fallo, derivación.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.ia.conversacion import (
    MENSAJE_ACLARACION,
    MENSAJE_SIN_FUENTE,
    Decision,
    ProveedorConversacional,
    ProveedorDemostracion,
    ejecutar_turno,
)
from app.ia.decisiones import DecisionTipada, Intencion
from app.ia.herramientas.contrato import ResultadoHerramienta
from app.ia.proveedor_ollama import ProveedorOllama

pytestmark = pytest.mark.unitaria


class _Clasificador:
    def __init__(self, decision: DecisionTipada) -> None:
        self._decision = decision
        self.nombre = decision.proveedor

    async def clasificar(self, texto: str) -> DecisionTipada:
        return self._decision


class _LLM(ProveedorConversacional):
    def __init__(self, mensaje: str) -> None:
        self.memoria: dict[str, Any] = {}
        self._mensaje = mensaje

    async def decidir(self, **datos: Any) -> Decision:
        self.memoria = datos["memoria"]
        return Decision(mensaje=self._mensaje)


async def _fuentes(texto: str) -> list[tuple[str, str]]:
    return [("Horarios", "Atendemos de lunes a viernes de 8:00 a 17:00.")]


async def _sin_fuentes(texto: str) -> list[tuple[str, str]]:
    return []


async def _turno(
    proveedor: ProveedorConversacional, decision: DecisionTipada, buscador: Any
) -> ResultadoHerramienta:
    resultado, herramientas = await ejecutar_turno(
        proveedor,
        "¿a qué hora atienden?",
        {},
        {},
        None,  # type: ignore[arg-type]
        clasificador=_Clasificador(decision),
        buscar_conocimiento=buscador,
    )
    assert herramientas == []
    return resultado


async def test_confianza_baja_de_jev_pregunta_con_opciones() -> None:
    dudosa = DecisionTipada(Intencion.CANCELAR, 0.4, 0.0, 0.0, "jev")
    resultado = await _turno(ProveedorDemostracion(), dudosa, _fuentes)
    assert resultado.mensaje == MENSAJE_ACLARACION


@pytest.mark.parametrize("texto", ["confirmar", "Confirmar cita", "sí confirmo"])
@pytest.mark.parametrize("confianza", [0.4, 0.95])
@pytest.mark.parametrize("configurado", [False, True])
async def test_confirmacion_explicita_usa_solo_la_reserva_de_memoria(texto, confianza, configurado):
    llamadas = []

    async def invocar(nombre, argumentos, contexto):
        llamadas.append((nombre, argumentos))
        return ResultadoHerramienta(exito=True, mensaje="Cita confirmada.")

    resultado, herramientas = await ejecutar_turno(
        _LLM("No debe decidir la confirmación.") if configurado else ProveedorDemostracion(),
        texto,
        {"cita_id": "reserva-del-canal"},
        dict.fromkeys(
            ("profesional_id", "servicio_id", "sede_id", "desde", "hasta"), "dato-del-canal"
        ),
        None,  # type: ignore[arg-type]
        clasificador=_Clasificador(
            DecisionTipada(Intencion.BUSCAR_HORARIOS, confianza, 0, 0, "jev")
        ),
        invocar=invocar,
    )
    assert herramientas == ["confirm_appointment"]
    assert llamadas == [("confirm_appointment", {"cita_id": "reserva-del-canal"})]
    assert resultado.exito


async def test_confirmacion_sin_reserva_no_inventa_cita():
    async def invocar(nombre, argumentos, contexto):
        pytest.fail("Sin una reserva no se debe invocar una herramienta.")

    resultado, herramientas = await ejecutar_turno(
        ProveedorDemostracion(),
        "Confirmar cita",
        {},
        {},
        None,  # type: ignore[arg-type]
        clasificador=_Clasificador(DecisionTipada(Intencion.BUSCAR_HORARIOS, 0.95, 0, 0, "jev")),
        invocar=invocar,
    )
    assert herramientas == []
    assert "Primero busque horarios" in resultado.mensaje


@pytest.mark.parametrize("clinica, urgencia", [(0.9, 0), (0, 0.9)])
async def test_confirmacion_no_omite_la_barrera_clinica(clinica, urgencia):
    async def invocar(nombre, argumentos, contexto):
        assert nombre == "handoff_to_human"
        return ResultadoHerramienta(
            exito=False, mensaje="Atención del personal.", requiere_humano=True
        )

    resultado, herramientas = await ejecutar_turno(
        ProveedorDemostracion(),
        "Confirmar cita",
        {"cita_id": "reserva"},
        {},
        None,  # type: ignore[arg-type]
        clasificador=_Clasificador(
            DecisionTipada(Intencion.BUSCAR_HORARIOS, 0.95, clinica, urgencia, "jev")
        ),
        invocar=invocar,
    )
    assert herramientas == ["handoff_to_human"]
    assert resultado.requiere_humano


async def test_informacion_sin_llm_cita_y_sin_fuente_lo_dice() -> None:
    info = DecisionTipada(Intencion.INFORMACION, 0.95, 0.0, 0.0, "jev")
    citada = await _turno(ProveedorDemostracion(), info, _fuentes)
    assert citada.mensaje.startswith("Segun «Horarios»")
    assert citada.codigo == "FUENTE_CITADA"
    vacia = await _turno(ProveedorDemostracion(), info, _sin_fuentes)
    assert vacia.mensaje == MENSAJE_SIN_FUENTE


async def test_con_llm_redacta_solo_con_las_fuentes() -> None:
    info = DecisionTipada(Intencion.INFORMACION, 0.95, 0.0, 0.0, "jev")
    llm = _LLM("De lunes a viernes, de 8 a 17.")
    redactada = await _turno(llm, info, _fuentes)
    assert redactada.codigo == "FUENTE_REDACTADA"
    assert redactada.mensaje.endswith("Fuente: Horarios")
    assert llm.memoria["fuentes_aprobadas"][0]["titulo"] == "Horarios"
    callado = await _turno(_LLM("   "), info, _fuentes)
    assert callado.codigo == "FUENTE_CITADA"


def _ollama(respuesta: dict[str, Any] | None, estado: int = 200) -> ProveedorOllama:
    def manejador(peticion: httpx.Request) -> httpx.Response:
        assert peticion.url.path == "/api/chat"
        if respuesta is None:
            return httpx.Response(estado)
        return httpx.Response(estado, json={"message": {"content": json.dumps(respuesta)}})

    cliente = httpx.AsyncClient(transport=httpx.MockTransport(manejador))
    return ProveedorOllama(cliente, url="http://127.0.0.1:11434", modelo="llama3")


async def _decidir(proveedor: ProveedorOllama) -> Decision:
    return await proveedor.decidir(
        sistema="s", texto="hola", memoria={}, negocio={"paciente_id": "x"}, resultado=None
    )


async def test_ollama_solo_catalogo_y_deriva_ante_fallo() -> None:
    permitida = await _decidir(
        _ollama({"herramienta": "get_patient_appointments", "argumentos": {}, "mensaje": ""})
    )
    assert permitida.herramienta == "get_patient_appointments"
    inventada = await _decidir(
        _ollama({"herramienta": "borrar_historia", "argumentos": {}, "mensaje": ""})
    )
    assert inventada.herramienta == "handoff_to_human"
    texto = await _decidir(_ollama({"herramienta": None, "argumentos": {}, "mensaje": "Hola"}))
    assert texto.mensaje == "Hola" and texto.herramienta is None
    caido = await _decidir(_ollama(None, 500))
    assert caido.herramienta == "handoff_to_human"
    with pytest.raises(ValueError, match="local"):
        ProveedorOllama(httpx.AsyncClient(), url="https://ollama.ejemplo.com", modelo="x")
