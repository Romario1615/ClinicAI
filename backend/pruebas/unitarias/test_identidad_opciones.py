"""Lectura de la eleccion y resolucion contra la lista guardada.

Sin base de datos: lo que se comprueba aqui es la logica de decidir **a quien
se refiere** un «2», y esa decision no consulta nada.

Vive en unitarias y no junto a las pruebas de integracion porque aquellas
llevan un `pytestmark` con `asyncio` a nivel de modulo, y una prueba `def`
sincrona bajo ese marcador falla.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modulos.conversaciones.identificacion import (
    MINUTOS_VIGENCIA_SELECCION,
    Candidato,
    Opciones,
    leer_eleccion,
    texto_de_opciones,
)

pytestmark = pytest.mark.unitaria

AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)


def _opciones(cuantas: int = 2, minutos: int = 5) -> Opciones:
    return Opciones(
        candidatos=tuple(Candidato(uuid.uuid4(), f"Nombre{i} A.") for i in range(1, cuantas + 1)),
        expira_en=AHORA + timedelta(minutes=minutos),
    )


# ---------------------------------------------------------------------------
#  Leer la respuesta
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("texto", ["1", " 2 ", "3", "\t4\n"])
def test_un_digito_suelto_es_una_eleccion(texto: str) -> None:
    assert leer_eleccion(texto) is not None


@pytest.mark.parametrize(
    "texto",
    ["el segundo", "opcion 2", "2 por favor", "", "   ", "cancelar", "12", "2.", "0"],
)
def test_lo_demas_no_cuenta_como_eleccion(texto: str) -> None:
    """Coincidencia exacta, igual que el resto del reconocimiento de intencion.

    Una interpretacion probabilistica de «el segundo creo» no es base para
    decidir sobre quien se actua. El coste es que a veces hay que repetir; el
    beneficio es que nunca se actua sobre la persona equivocada por haber
    entendido de mas.
    """
    assert leer_eleccion(texto) is None


def test_el_texto_nulo_no_es_una_eleccion() -> None:
    """Un mensaje sin texto -- una imagen, un audio -- no elige nada."""
    assert leer_eleccion(None) is None


# ---------------------------------------------------------------------------
#  Resolver contra lo guardado
# ---------------------------------------------------------------------------
def test_la_posicion_resuelve_al_candidato_guardado() -> None:
    opciones = _opciones(3)
    assert opciones.elegir(1) == opciones.candidatos[0].paciente_id
    assert opciones.elegir(3) == opciones.candidatos[2].paciente_id


@pytest.mark.parametrize("numero", [0, -1, 4, 99])
def test_una_posicion_fuera_de_rango_no_resuelve(numero: int) -> None:
    """Y no se aproxima al mas cercano.

    Redondear un «4» a la tercera opcion seria elegir por el paciente.
    """
    assert _opciones(3).elegir(numero) is None


def test_la_lista_se_reconstruye_con_su_orden_original() -> None:
    """Guardar y volver a leer no puede reordenar nada.

    Si el orden cambiara, el «2» de quien escribe seleccionaria a otra persona
    de la misma familia.
    """
    original = _opciones(3)
    recuperada = Opciones.desde_json(original.a_json())

    assert recuperada is not None
    assert [c.paciente_id for c in recuperada.candidatos] == [
        c.paciente_id for c in original.candidatos
    ]


def test_una_lista_vacia_no_se_reconstruye() -> None:
    assert Opciones.desde_json(None) is None
    assert Opciones.desde_json({}) is None
    assert Opciones.desde_json({"candidatos": [], "expira_en": AHORA.isoformat()}) is None


# ---------------------------------------------------------------------------
#  Vigencia
# ---------------------------------------------------------------------------
def test_una_lista_recien_ofrecida_esta_vigente() -> None:
    assert _opciones(minutos=MINUTOS_VIGENCIA_SELECCION).vigente(AHORA)


def test_una_lista_pasada_su_plazo_no_lo_esta() -> None:
    """Un «2» de mañana responde a una pregunta que ya nadie recuerda."""
    opciones = _opciones(minutos=MINUTOS_VIGENCIA_SELECCION)
    assert not opciones.vigente(AHORA + timedelta(minutes=MINUTOS_VIGENCIA_SELECCION + 1))


def test_el_limite_de_vigencia_es_estricto() -> None:
    """Justo en el instante de caducidad ya no vale.

    Es el borde que decide si una respuesta a tiempo cuenta; dejarlo ambiguo
    haria que el comportamiento dependiera de milisegundos.
    """
    opciones = Opciones(candidatos=(Candidato(uuid.uuid4(), "Ana A."),), expira_en=AHORA)
    assert not opciones.vigente(AHORA)


# ---------------------------------------------------------------------------
#  Lo que se muestra
# ---------------------------------------------------------------------------
def test_el_texto_numera_las_opciones_desde_uno() -> None:
    """Desde uno y no desde cero: se lo lee una persona, no un programa."""
    texto = texto_de_opciones(_opciones(3))
    assert "1. Nombre1 A." in texto
    assert "3. Nombre3 A." in texto
    assert "0." not in texto


def test_el_texto_pide_responder_con_el_numero() -> None:
    """Sin la instruccion, quien recibe la lista responde con un nombre."""
    assert "numero" in texto_de_opciones(_opciones(2)).lower()
