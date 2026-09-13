"""El limite clinico del agente (CLAUDE.md, regla 5).

Como estan elegidos los casos
-----------------------------
Los mensajes de aqui estan escritos como los escribe la gente por WhatsApp:
en minusculas, sin tildes, con faltas y sin puntuacion. Probar con prosa
correcta daria una falsa sensacion de cobertura, porque la prosa correcta es
justo lo que no llega por ese canal.

Las dos mitades importan igual. Que derive lo clinico protege al paciente;
que **no** derive lo administrativo es lo que hace que el agente sirva de
algo. Un clasificador que deriva todo es seguro y es inutil.
"""

from __future__ import annotations

import pytest

from app.ia.herramientas.limites import (
    SENALES,
    MotivoDerivacion,
    evaluar,
    explicar,
)

pytestmark = pytest.mark.unitaria


# ---------------------------------------------------------------------------
#  Lo que tiene que salir del agente
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("mensaje", "motivo"),
    [
        # --- Medicacion ---
        ("quiero cambiar la dosis", MotivoDerivacion.MEDICACION),
        ("puedo subir a 2 pastillas", MotivoDerivacion.MEDICACION),
        ("me bajan la dosis a 5 mg?", MotivoDerivacion.MEDICACION),
        ("puedo dejar de tomar el medicamento", MotivoDerivacion.MEDICACION),
        ("quiero suspender el tratamiento", MotivoDerivacion.MEDICACION),
        ("se me olvido la toma de anoche", MotivoDerivacion.MEDICACION),
        ("no tome la pastilla de ayer", MotivoDerivacion.MEDICACION),
        ("me pueden recetar un antibiotico", MotivoDerivacion.MEDICACION),
        # --- Reaccion adversa ---
        ("me cayo mal el medicamento", MotivoDerivacion.REACCION_ADVERSA),
        ("creo que tengo una reaccion", MotivoDerivacion.REACCION_ADVERSA),
        ("me salio un sarpullido", MotivoDerivacion.REACCION_ADVERSA),
        ("es un efecto secundario?", MotivoDerivacion.REACCION_ADVERSA),
        # --- Sintomas y diagnostico ---
        ("me duele el pecho", MotivoDerivacion.SINTOMA_O_DIAGNOSTICO),
        ("tengo fiebre desde ayer", MotivoDerivacion.SINTOMA_O_DIAGNOSTICO),
        ("que tengo doctor", MotivoDerivacion.SINTOMA_O_DIAGNOSTICO),
        ("esto es grave?", MotivoDerivacion.SINTOMA_O_DIAGNOSTICO),
        ("no puedo respirar bien", MotivoDerivacion.SINTOMA_O_DIAGNOSTICO),
        # --- Urgencia ---
        ("es urgente por favor", MotivoDerivacion.URGENCIA_DECLARADA),
        ("tengo una emergencia", MotivoDerivacion.URGENCIA_DECLARADA),
        # --- Terceros ---
        ("quiero una cita para mi madre", MotivoDerivacion.DATOS_DE_TERCERO),
        ("la cita de mi hijo", MotivoDerivacion.DATOS_DE_TERCERO),
        ("es para un familiar", MotivoDerivacion.DATOS_DE_TERCERO),
    ],
)
def test_lo_clinico_sale_del_agente(mensaje: str, motivo: MotivoDerivacion) -> None:
    evaluacion = evaluar(mensaje)
    assert evaluacion.deriva, f"No derivo: {mensaje!r}"
    assert evaluacion.motivo is motivo


# ---------------------------------------------------------------------------
#  Lo que el agente si puede atender
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mensaje",
    [
        "quiero una cita para el martes",
        "tienen hora el jueves por la tarde",
        "a que hora abren",
        "donde quedan ustedes",
        "cuanto cuesta la consulta",
        "confirmar",
        "cancelar",
        "quiero cambiar mi cita de hora",
        "necesito reprogramar para la semana que viene",
        "cual es mi proxima cita",
        "aceptan tarjeta",
        "gracias",
    ],
)
def test_lo_administrativo_se_queda_en_el_agente(mensaje: str) -> None:
    """Si esto derivara, el agente no serviria para nada.

    «quiero cambiar mi cita de hora» merece atencion especial: contiene
    «cambiar», que tambien aparece en el patron de cambio de dosis. Que no
    derive demuestra que el patron exige ademas una palabra de medicacion.
    """
    assert not evaluar(mensaje).deriva, f"Derivo sin necesidad: {mensaje!r}"


# ---------------------------------------------------------------------------
#  Propiedades del catalogo
# ---------------------------------------------------------------------------
def test_el_texto_vacio_no_deriva() -> None:
    """Un mensaje vacio es un mensaje sin contenido, no una urgencia."""
    assert not evaluar(None).deriva
    assert not evaluar("").deriva
    assert not evaluar("   ").deriva


def test_las_tildes_no_evitan_la_deteccion() -> None:
    """La evasion mas barata es escribir con o sin tilde.

    El texto se normaliza antes de buscar, asi que las dos formas caen igual.
    """
    assert evaluar("me duele el estómago").deriva
    assert evaluar("me duele el estomago").deriva


def test_las_mayusculas_no_evitan_la_deteccion() -> None:
    assert evaluar("ES URGENTE").deriva


def test_todo_motivo_tiene_texto_para_el_paciente() -> None:
    """Derivar sin decir nada deja a alguien esperando una respuesta que no llega."""
    for motivo in MotivoDerivacion:
        texto = explicar(motivo)
        assert texto and len(texto) > 20


def test_ningun_texto_de_derivacion_menciona_contenido_clinico() -> None:
    """Regla 10: estos textos salen por WhatsApp.

    Un mensaje que diga «sobre su reaccion al medicamento X» revela la
    condicion de quien lo recibe a cualquiera que mire el telefono.
    """
    prohibidas = (
        "diagnostic",
        "medicament",
        "dosis",
        "receta",
        "sintoma",
        "enfermedad",
        "pastilla",
    )
    for motivo in MotivoDerivacion:
        texto = explicar(motivo).lower()
        encontradas = [p for p in prohibidas if p in texto]
        assert not encontradas, f"{motivo.value} menciona {encontradas}"


def test_cada_senal_declara_por_que_existe() -> None:
    """La razon se lee cuando alguien quiere quitar una senal.

    Sin ella, la lista se convierte en una acumulacion que nadie se atreve a
    tocar ni sabe justificar.
    """
    for senal in SENALES:
        assert len(senal.razon) > 30, f"{senal.nombre} no explica por que esta."


def test_los_nombres_de_senal_no_se_repiten() -> None:
    """Un nombre duplicado haria ambiguo el registro de auditoria."""
    nombres = [s.nombre for s in SENALES]
    assert len(nombres) == len(set(nombres))


def test_la_medicacion_gana_al_sintoma_cuando_aparecen_juntos() -> None:
    """El orden del catalogo no es casual.

    «me duele desde que tomo la pastilla nueva, puedo dejar de tomar el
    medicamento» es las dos cosas. Atenderlo como asunto de medicacion lleva
    a quien corresponde antes.
    """
    mensaje = "me duele todo desde que empece, puedo dejar de tomar el medicamento"
    assert evaluar(mensaje).motivo is MotivoDerivacion.MEDICACION
