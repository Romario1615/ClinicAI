"""Reconocimiento de intencion: lo que se reconoce y, sobre todo, lo que no.

Las pruebas que mas importan de este archivo son las del segundo bloque: las
que comprueban que un mensaje clinico, ambiguo o negado **no** se reconoce y
acaba en `DESCONOCIDA`, es decir, en manos de una persona.

Una falsa aceptacion aqui cancela la cita de alguien que no queria cancelarla.
"""

from __future__ import annotations

import pytest

from app.modulos.conversaciones.intenciones import FRASES, normalizar, reconocer
from app.modulos.conversaciones.modelos import IntencionEntrante

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]


# ---------------------------------------------------------------------------
#  Lo que se reconoce
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("CONFIRMAR", IntencionEntrante.CONFIRMAR),
        ("confirmar", IntencionEntrante.CONFIRMAR),
        ("Confirmo", IntencionEntrante.CONFIRMAR),
        ("asistiré", IntencionEntrante.CONFIRMAR),
        ("CANCELAR", IntencionEntrante.CANCELAR),
        ("no puedo asistir", IntencionEntrante.CANCELAR),
        ("SI", IntencionEntrante.ACEPTAR_OFERTA),
        ("Sí", IntencionEntrante.ACEPTAR_OFERTA),
        ("acepto", IntencionEntrante.ACEPTAR_OFERTA),
        ("TOMADA", IntencionEntrante.REGISTRAR_TOMA),
        ("ya tomé", IntencionEntrante.REGISTRAR_TOMA),
        ("recordarme después", IntencionEntrante.RECORDAR_TOMA_DESPUES),
        ("recordatorio en 30 minutos", IntencionEntrante.RECORDAR_TOMA_DESPUES),
        ("no pude tomarla", IntencionEntrante.NO_PUDO_TOMAR),
        ("no pude hacer la toma", IntencionEntrante.NO_PUDO_TOMAR),
        ("tengo un problema con mi medicamento", IntencionEntrante.PROBLEMA_TRATAMIENTO),
        ("me sienta mal la medicina", IntencionEntrante.PROBLEMA_TRATAMIENTO),
        ("hablar con la clínica", IntencionEntrante.AYUDA),
        ("BAJA", IntencionEntrante.BAJA),
        ("stop", IntencionEntrante.BAJA),
        ("STOP", IntencionEntrante.BAJA),
        ("no molestar", IntencionEntrante.BAJA),
        ("AYUDA", IntencionEntrante.AYUDA),
    ],
)
def test_frases_del_catalogo_se_reconocen(texto: str, esperada: IntencionEntrante) -> None:
    assert reconocer(texto) is esperada


@pytest.mark.parametrize(
    "texto",
    ["confirmar.", "¡CONFIRMAR!", "  confirmar  ", "Confirmar,", "confirmar\n"],
)
def test_la_puntuacion_y_los_espacios_no_impiden_el_reconocimiento(texto: str) -> None:
    """El paciente escribe en un teclado de telefono, con autocorrector.

    Exigir el texto exacto haria que «CONFIRMAR!» se derivara a una persona.
    """
    assert reconocer(texto) is IntencionEntrante.CONFIRMAR


def test_las_tildes_no_cambian_la_intencion() -> None:
    """«asistiré» y «asistire» son la misma respuesta.

    Distinguirlas convertiria un acento en la diferencia entre confirmar una
    cita y no confirmarla.
    """
    assert reconocer("asistiré") is reconocer("asistire")


# ---------------------------------------------------------------------------
#  Lo que NO se reconoce: el bloque que protege al paciente
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto",
    [
        # Negaciones y matices que un modelo probabilistico interpretaria, y
        # que aqui van a una persona por diseno.
        "no confirmar",
        "creo que no puedo ir",
        "confirmar? no se",
        "quizas cancele",
        "puede que confirme manana",
        # Contenido clinico. Nada de esto lo decide una maquina
        # (CLAUDE.md, regla 5).
        "me duele el pecho",
        "la pastilla me da nauseas",
        "puedo tomar doble dosis?",
        "dejo el tratamiento",
        "tengo fiebre desde ayer",
        # Peticiones administrativas que exigen a una persona.
        "quiero cambiar de doctor",
        "cuanto cuesta la consulta",
        "",
    ],
)
def test_lo_que_no_esta_en_el_catalogo_se_deriva(texto: str) -> None:
    assert reconocer(texto) is IntencionEntrante.DESCONOCIDA


def test_ningun_mensaje_clinico_produce_una_intencion_de_accion() -> None:
    """Refuerzo explicito de la regla 5, con el caso mas peligroso.

    «no puedo tomar la pastilla» **no** es un registro de toma, ni una
    cancelacion, ni una baja. Es un mensaje para un profesional.
    """
    for texto in (
        "se me olvido la pastilla, tomo dos?",
        "la medicina me hace mal",
        "no pude tomar una decisión",
    ):
        assert reconocer(texto) is IntencionEntrante.DESCONOCIDA, texto
    assert reconocer("no puedo tomar la pastilla") is IntencionEntrante.PROBLEMA_TRATAMIENTO


def test_solo_el_reporte_explicito_recibe_etiqueta_de_revision_clinica() -> None:
    """La etiqueta deriva a una persona; no clasifica sintomas ni gravedad."""
    assert reconocer("no me sienta mal la medicina") is IntencionEntrante.DESCONOCIDA
    assert reconocer("la pastilla me da nauseas") is IntencionEntrante.DESCONOCIDA


def test_un_mensaje_largo_se_deriva_sin_buscar_palabras_clave() -> None:
    """Un parrafo que contiene «cancelar» no es una orden de cancelar.

    Buscar la palabra dentro del texto haria que «no quiero cancelar, solo
    preguntaba» cancelara la cita.
    """
    largo = (
        "buenas tardes, no quiero cancelar la cita pero necesito saber si puedo "
        "llegar quince minutos tarde"
    )
    assert reconocer(largo) is IntencionEntrante.DESCONOCIDA


def test_none_se_deriva() -> None:
    """Un audio o una imagen llegan sin texto. Van a una persona."""
    assert reconocer(None) is IntencionEntrante.DESCONOCIDA


# ---------------------------------------------------------------------------
#  Invariantes del catalogo
# ---------------------------------------------------------------------------
def test_ninguna_frase_pertenece_a_dos_intenciones() -> None:
    """Una frase ambigua haria que el orden de iteracion decidiera.

    El modulo ya lo comprueba al importarse; la prueba lo deja explicito para
    que se lea como un requisito y no como un detalle de implementacion.
    """
    vistas: dict[str, IntencionEntrante] = {}
    for intencion, frases in FRASES.items():
        for frase in frases:
            assert frase not in vistas, f"«{frase}» esta en {vistas.get(frase)} y en {intencion}"
            vistas[frase] = intencion


def test_toda_frase_del_catalogo_esta_normalizada() -> None:
    """Una frase con mayuscula o tilde en el catalogo nunca coincidiria.

    El texto entrante se normaliza antes de comparar, asi que una frase
    guardada como «Confirmar» seria codigo muerto: parece cubrir un caso y no
    lo cubre.
    """
    for intencion, frases in FRASES.items():
        for frase in frases:
            assert normalizar(frase) == frase, f"«{frase}» de {intencion} no esta normalizada"


def test_no_existe_intencion_de_contenido_clinico() -> None:
    """El catalogo no admite intenciones clinicas.

    Si alguien anade «CAMBIAR_DOSIS» o «REPORTAR_REACCION», esta prueba falla.
    """
    prohibidas = {"DOSIS", "RECETA", "MEDICAMENTO", "SINTOMA", "DIAGNOSTICO", "REACCION"}
    nombres = {intencion.name for intencion in IntencionEntrante}
    assert not (nombres & prohibidas)
