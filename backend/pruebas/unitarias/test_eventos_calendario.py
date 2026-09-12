"""Verificacion de RF-I09: el evento externo no lleva datos clinicos.

El calendario de Google es un tercero. Lo que se escribe ahi sale del sistema:
deja de estar bajo su control de acceso, su auditoria y su politica de
retencion, y queda en la cuenta personal del profesional y en cualquier
dispositivo donde la tenga sincronizada.

La prueba mas importante de este archivo es
`test_no_se_puede_colar_nada_del_paciente_ni_del_servicio`: comprueba que la
funcion **no admite** esos datos, no que los filtre. No se puede filtrar lo
que no llega.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modulos.calendario.eventos import (
    PALABRAS_PROHIBIDAS,
    TITULO_EVENTO,
    ContenidoNoPermitido,
    EventoExterno,
    construir_evento,
    verificar,
)

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]

INICIO = datetime(2026, 4, 16, 14, 0, tzinfo=UTC)
FIN = INICIO + timedelta(minutes=30)
URL = "https://clinica.example.invalid"


def _evento(**cambios: object) -> EventoExterno:
    argumentos: dict[str, object] = {
        "cita_id": uuid.uuid4(),
        "inicio": INICIO,
        "fin": FIN,
        "consultorio": "Consultorio 3",
        "sede": "Sede Norte",
        "url_sistema": URL,
    }
    argumentos.update(cambios)
    return construir_evento(**argumentos)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
#  La frontera
# ---------------------------------------------------------------------------
def test_no_se_puede_colar_nada_del_paciente_ni_del_servicio() -> None:
    """La firma de la funcion no acepta esos datos.

    Es la comprobacion estructural, y vale mas que cualquier asercion sobre el
    resultado: mientras la funcion no reciba el paciente ni el servicio, no
    hay forma de que aparezcan en el evento.
    """
    parametros = set(inspect.signature(construir_evento).parameters)
    prohibidos = {
        "paciente",
        "paciente_id",
        "paciente_nombre",
        "servicio",
        "servicio_id",
        "especialidad",
        "motivo",
        "diagnostico",
        "notas",
    }
    assert not (parametros & prohibidos), (
        f"`construir_evento` acepta {sorted(parametros & prohibidos)}. El evento "
        "externo no puede recibir datos del paciente ni clinicos (RF-I09)."
    )


def test_el_evento_no_menciona_ninguna_palabra_prohibida() -> None:
    evento = _evento()
    texto = evento.texto_completo().lower()
    # La descripcion explica que NO hay motivo ni paciente; esa frase concreta
    # es la unica excepcion y `verificar` la conoce.
    texto = texto.replace("no incluye el paciente ni el motivo de la consulta", "")
    encontradas = [palabra for palabra in PALABRAS_PROHIBIDAS if palabra in texto]
    assert not encontradas, f"El evento menciona {encontradas}."


def test_el_titulo_es_fijo_y_no_revela_nada() -> None:
    """Un titulo parametrizable acabaria llevando el servicio.

    «Consulta oncologia» en el calendario del profesional exporta a Google la
    especialidad de quien va a esa cita.
    """
    assert _evento().titulo == TITULO_EVENTO
    assert "consulta" not in TITULO_EVENTO.lower()


def test_la_descripcion_explica_por_que_no_hay_mas() -> None:
    """Sin la explicacion, el primero que abra su calendario creera que falla.

    Y pedira que se anada el paciente, que es justo lo que no debe pasar.
    """
    descripcion = _evento().descripcion
    assert "proteccion de datos" in descripcion.lower()
    assert URL in descripcion


def test_el_evento_lleva_un_enlace_al_sistema() -> None:
    """Quien necesite saber de quien es la cita entra al sistema.

    Ahi si hay control de acceso, y la lectura queda auditada.
    """
    cita_id = uuid.uuid4()
    evento = _evento(cita_id=cita_id)
    assert f"/agenda/citas/{cita_id}" in evento.descripcion


def test_una_sede_con_nombre_clinico_se_rechaza() -> None:
    """La sede es el unico texto libre que el operador controla.

    Una sede llamada «Centro de Tratamiento» revelaria lo mismo que un titulo
    con el servicio, y por una via que las demas comprobaciones no cubren.
    """
    with pytest.raises(ContenidoNoPermitido):
        _evento(sede="Centro de Tratamiento Oncologico")


def test_un_consultorio_con_nombre_clinico_se_rechaza() -> None:
    with pytest.raises(ContenidoNoPermitido):
        _evento(consultorio="Sala de diagnostico")


def test_verificar_rechaza_un_evento_construido_a_mano() -> None:
    """La ultima barrera, para el codigo que no pase por `construir_evento`.

    Un modulo futuro, o una prueba, podria armar el objeto directamente;
    `verificar` se sigue aplicando en el adaptador antes de publicar.
    """
    a_mano = EventoExterno(
        titulo="Cita de oncologia",
        descripcion="Paciente: Maria Torres. Diagnostico confirmado.",
        inicio=INICIO,
        fin=FIN,
        ubicacion=None,
        referencia_interna="cita:0",
    )
    with pytest.raises(ContenidoNoPermitido):
        verificar(a_mano)


# ---------------------------------------------------------------------------
#  Forma del evento
# ---------------------------------------------------------------------------
def test_la_ubicacion_combina_sede_y_consultorio() -> None:
    """La ubicacion fisica no es dato clinico, y al profesional le sirve."""
    evento = _evento(sede="Sede Norte", consultorio="Consultorio 3")
    assert evento.ubicacion == "Sede Norte · Consultorio 3"


def test_sin_ubicacion_queda_en_nulo_y_no_en_cadena_vacia() -> None:
    """Una cadena vacia aparece como ubicacion en blanco en el calendario."""
    assert _evento(sede=None, consultorio=None).ubicacion is None


def test_la_ubicacion_no_admite_saltos_de_linea() -> None:
    """Un salto de linea en un campo de ubicacion rompe formatos de calendario.

    Y es la via por la que se inyectaria texto adicional en un ICS.
    """
    evento = _evento(sede="Sede\nNorte", consultorio=None)
    assert evento.ubicacion is not None
    assert "\n" not in evento.ubicacion


def test_la_referencia_interna_identifica_la_cita() -> None:
    """Permite reconciliar sin depender de que el proveedor conserve nada."""
    cita_id = uuid.uuid4()
    assert _evento(cita_id=cita_id).referencia_interna == f"cita:{cita_id}"


def test_un_instante_sin_zona_se_rechaza() -> None:
    """ADR-0010: un instante sin zona en una agenda medica desplaza citas."""
    with pytest.raises(ValueError, match="zona horaria"):
        _evento(inicio=datetime(2026, 4, 16, 14, 0))


def test_un_fin_anterior_al_inicio_se_rechaza() -> None:
    with pytest.raises(ValueError, match="posterior"):
        _evento(fin=INICIO - timedelta(minutes=1))


def test_un_fin_igual_al_inicio_se_rechaza() -> None:
    """Un evento de duracion cero no bloquea el hueco, que es su unico fin."""
    with pytest.raises(ValueError, match="posterior"):
        _evento(fin=INICIO)


def test_el_evento_no_admite_campos_libres() -> None:
    """El conjunto de campos es cerrado.

    Un diccionario de «extras» seria donde acabaria el dato que este modulo
    existe para impedir.
    """
    campos = set(EventoExterno.__slots__)
    assert campos == {
        "titulo",
        "descripcion",
        "inicio",
        "fin",
        "ubicacion",
        "referencia_interna",
        "etiqueta_origen",
    }
