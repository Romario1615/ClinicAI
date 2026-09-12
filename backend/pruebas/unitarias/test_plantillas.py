"""Verificacion de la regla 10: ninguna notificacion lleva datos clinicos.

La prueba central de este archivo es `test_ninguna_plantilla_admite_variables_clinicas`,
que recorre **todas** las plantillas del catalogo.  Es la que hace cumplir el
requisito RF-K07 y la regla 10 de CLAUDE.md, y no se desactiva.

El resto comprueba que el mecanismo que la sostiene funciona: que declarar una
variable clinica falla al construir la plantilla, que redactar con una
variable no declarada falla, y que las plantillas que existen cubren los tipos
de mensaje que el sistema encola.
"""

from __future__ import annotations

import re

import pytest

from app.mensajeria import plantillas
from app.mensajeria.plantillas import (
    PLANTILLAS,
    VARIABLES_PROHIBIDAS,
    Plantilla,
)
from app.modulos.outbox.modelos import TipoMensajeOutbox

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]

# Orden estable para que el informe de pruebas sea comparable entre
# ejecuciones; el diccionario no garantiza orden entre versiones.
TIPOS_CON_PLANTILLA: list[TipoMensajeOutbox] = sorted(PLANTILLAS, key=lambda t: t.value)

# Palabras que no pueden aparecer en el TEXTO de una plantilla, ni siquiera
# fuera de un hueco.  Cubre el caso que la comprobacion de variables no ve:
# escribir el dato clinico directamente en el texto fijo.
PALABRAS_CLINICAS_PROHIBIDAS = (
    "diagnostic",
    "diagnóstic",
    "medicament",
    "farmac",
    "fármac",
    "dosis",
    "miligramo",
    " mg ",
    "tratamiento",
    "sintoma",
    "síntoma",
    "alergia",
    "patolog",
)

# Excepciones razonadas. «receta» y «medicacion» aparecen en textos que hablan
# de la existencia de una indicacion sin decir cual: «una de las tomas que le
# indico su profesional». Se permiten como palabras del idioma, y la prueba de
# variables garantiza que no se pueda rellenar con el nombre del medicamento.
_PERMITIDAS_EN_TEXTO = ("medicacion",)


@pytest.mark.parametrize("tipo", TIPOS_CON_PLANTILLA)
def test_ninguna_plantilla_admite_variables_clinicas(tipo: TipoMensajeOutbox) -> None:
    """Ninguna plantilla declara un hueco de contenido clinico.

    Es la comprobacion que impide que un recordatorio diga «su cita de
    oncologia» o «es hora de su metformina». La pantalla de bloqueo de un
    telefono es un canal publico.
    """
    plantilla = PLANTILLAS[tipo]
    assert not (set(plantilla.variables_permitidas) & VARIABLES_PROHIBIDAS), (
        f"La plantilla {tipo.value} admite variables clinicas: "
        f"{sorted(set(plantilla.variables_permitidas) & VARIABLES_PROHIBIDAS)}"
    )


@pytest.mark.parametrize("tipo", TIPOS_CON_PLANTILLA)
def test_ningun_texto_de_plantilla_menciona_contenido_clinico(
    tipo: TipoMensajeOutbox,
) -> None:
    """El texto fijo tampoco nombra diagnosticos, medicamentos ni dosis.

    Complementa la prueba anterior: se podria cumplir la regla de variables y
    aun asi escribir «recuerde tomar su medicamento para la diabetes» en el
    texto literal.
    """
    texto = PLANTILLAS[tipo].texto.lower()
    for permitida in _PERMITIDAS_EN_TEXTO:
        texto = texto.replace(permitida, "")

    encontradas = [palabra for palabra in PALABRAS_CLINICAS_PROHIBIDAS if palabra in texto]
    assert not encontradas, (
        f"El texto de la plantilla {tipo.value} menciona {encontradas}. "
        "Ninguna notificacion puede incluir diagnostico, medicamento ni motivo "
        "de consulta (CLAUDE.md, regla 10)."
    )


def test_el_recordatorio_de_toma_no_nombra_el_medicamento() -> None:
    """Caso concreto y mas tentador de todos.

    Un recordatorio de medicacion seria mas util si dijera que tomar.  No lo
    dice: el nombre de un medicamento en una pantalla de bloqueo revela la
    condicion de quien lo toma.
    """
    plantilla = PLANTILLAS[TipoMensajeOutbox.TOMA_RECORDATORIO]
    assert plantilla.variables_permitidas == frozenset({"nombre", "enlace"})

    redactado = plantilla.redactar(nombre="Ana", enlace="https://ejemplo.invalid/t")
    assert "Ana" in redactado
    # Ni el nombre del farmaco ni la dosis: solo la existencia de la toma.
    assert "toma" in redactado.lower()


def test_declarar_una_variable_clinica_falla_al_construir() -> None:
    """El mecanismo falla al definir la plantilla, no al enviarla.

    Importa el momento: si fallara al enviar, el error apareceria cuando un
    paciente ya no recibio su recordatorio. Aqui rompe al importar el modulo.
    """
    with pytest.raises(ValueError, match="variables clinicas"):
        Plantilla(
            tipo=TipoMensajeOutbox.CITA_CONFIRMACION,
            nombre_meta="prueba",
            texto="Su cita es por {diagnostico}.",
            variables_permitidas=frozenset({"diagnostico"}),
        )


def test_hueco_no_declarado_falla_al_construir() -> None:
    with pytest.raises(ValueError, match="huecos no declarados"):
        Plantilla(
            tipo=TipoMensajeOutbox.ALERTA_PERSONAL,
            nombre_meta="",
            texto="Hola {nombre}, su cita es el {fecha}.",
            variables_permitidas=frozenset({"nombre"}),
        )


def test_variable_declarada_y_no_usada_falla_al_construir() -> None:
    """Una variable declarada y no usada suele ser un renombrado a medias.

    Deja la plantilla aceptando un dato que no muestra, que es justo la
    situacion en que alguien cree que el mensaje lleva algo y no lo lleva.
    """
    with pytest.raises(ValueError, match="huecos que no usa"):
        Plantilla(
            tipo=TipoMensajeOutbox.ALERTA_PERSONAL,
            nombre_meta="",
            texto="Hola {nombre}.",
            variables_permitidas=frozenset({"nombre", "sede"}),
        )


def test_redactar_rechaza_una_variable_no_declarada() -> None:
    """Pasar un dato clinico al redactar es un error, no se ignora.

    Ignorarlo en silencio permitiria creer que se esta enviando -- o que se
    enviaria si alguien anade el hueco despues.
    """
    plantilla = PLANTILLAS[TipoMensajeOutbox.OFERTA_EXPIRADA]
    with pytest.raises(ValueError, match="no admite estas variables"):
        plantilla.redactar(nombre="Ana", diagnostico="algo")


def test_redactar_exige_todas_las_variables() -> None:
    """Un hueco sin rellenar produciria «Hola {nombre}» en el telefono."""
    plantilla = PLANTILLAS[TipoMensajeOutbox.CITA_CONFIRMACION]
    with pytest.raises(ValueError, match="Faltan variables"):
        plantilla.redactar(nombre="Ana")


def test_redactar_no_deja_huecos_sin_sustituir() -> None:
    plantilla = PLANTILLAS[TipoMensajeOutbox.CITA_CONFIRMACION]
    redactado = plantilla.redactar(
        nombre="Ana",
        clinica="Clinica de Prueba",
        fecha="16 de abril",
        hora="09:30",
        sede="Sede Norte",
        profesional="Dra. Ficticia",
        telefono_clinica="00-000-0000",
    )
    assert not re.search(r"\{\w+\}", redactado)


def test_los_tipos_de_calendario_no_necesitan_plantilla() -> None:
    """Los mensajes de calendario no son texto para una persona.

    Llevan una operacion sobre un evento, no un mensaje.  Se comprueba de
    forma explicita para que la ausencia sea una decision visible y no un
    hueco olvidado.
    """
    sin_plantilla = set(plantillas.tipos_sin_plantilla())
    assert sin_plantilla == {
        TipoMensajeOutbox.CALENDARIO_CREAR_EVENTO,
        TipoMensajeOutbox.CALENDARIO_ACTUALIZAR_EVENTO,
        TipoMensajeOutbox.CALENDARIO_ELIMINAR_EVENTO,
    }


def test_obtener_un_tipo_sin_plantilla_lanza() -> None:
    """No hay plantilla generica de reserva.

    Enviar un mensaje con la plantilla equivocada es peor que no enviarlo: el
    paciente recibe informacion que no encaja con su situacion.
    """
    with pytest.raises(KeyError, match="No hay plantilla"):
        plantillas.obtener(TipoMensajeOutbox.CALENDARIO_CREAR_EVENTO)


def test_toda_plantilla_de_whatsapp_declara_su_nombre_en_meta() -> None:
    """La Cloud API exige plantilla aprobada para iniciar conversacion.

    Sin `nombre_meta` el envio se rechaza con «template does not exist», que
    aparece como fallo de entrega sin explicacion util.
    """
    tipos_whatsapp = {
        TipoMensajeOutbox.CITA_CONFIRMACION,
        TipoMensajeOutbox.CITA_RECORDATORIO_DIA_ANTES,
        TipoMensajeOutbox.CITA_RECORDATORIO_HORAS_ANTES,
        TipoMensajeOutbox.CITA_CANCELACION,
        TipoMensajeOutbox.CITA_REPROGRAMACION,
        TipoMensajeOutbox.OFERTA_TURNO,
        TipoMensajeOutbox.OFERTA_EXPIRADA,
        TipoMensajeOutbox.OFERTA_PERDIDA,
        TipoMensajeOutbox.TOMA_RECORDATORIO,
        TipoMensajeOutbox.TOMA_SEGUIMIENTO,
    }
    sin_nombre = [tipo.value for tipo in tipos_whatsapp if not PLANTILLAS[tipo].nombre_meta]
    assert not sin_nombre, f"Plantillas de WhatsApp sin nombre aprobado: {sin_nombre}"
