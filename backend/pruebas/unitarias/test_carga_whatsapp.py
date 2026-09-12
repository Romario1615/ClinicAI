"""Lectura del cuerpo del webhook.

El requisito de este modulo es asimetrico: debe extraer lo que entiende y
**no romper nunca** con lo que no entiende.  Un error aqui hace que el webhook
devuelva 5xx, y Meta responde a los errores persistentes deshabilitando la
suscripcion -- lo que deja al sistema sin recibir las respuestas de ningun
paciente.

Por eso la mitad de las pruebas son formas deformes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.mensajeria.carga_whatsapp import interpretar

pytestmark = pytest.mark.unitaria

# Numero sintetico de la documentacion de formato, no un numero real
# (CLAUDE.md, regla 3).
TELEFONO = "593999000111"
ID_NUMERO = "000000000000000"


def _cuerpo(
    *, mensajes: list[dict[str, Any]] | None = None, estados: list[Any] | None = None
) -> dict[str, Any]:
    valor: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "0", "phone_number_id": ID_NUMERO},
    }
    if mensajes is not None:
        valor["messages"] = mensajes
    if estados is not None:
        valor["statuses"] = estados
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "0", "changes": [{"field": "messages", "value": valor}]}],
    }


# ---------------------------------------------------------------------------
#  Mensajes
# ---------------------------------------------------------------------------
def test_un_mensaje_de_texto_se_lee_completo() -> None:
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": "wamid.SINTETICO1",
                    "from": TELEFONO,
                    "timestamp": "1776268800",
                    "type": "text",
                    "text": {"body": "CONFIRMAR"},
                }
            ]
        )
    )
    assert len(carga.mensajes) == 1
    mensaje = carga.mensajes[0]
    assert mensaje.external_id == "wamid.SINTETICO1"
    assert mensaje.telefono == TELEFONO
    assert mensaje.texto == "CONFIRMAR"
    assert mensaje.recibido_en == datetime(2026, 4, 15, 16, 0, tzinfo=UTC)
    assert carga.id_numero_telefono == ID_NUMERO


def test_la_respuesta_de_un_boton_se_lee_como_texto() -> None:
    """Un boton no trae `text.body`.

    Tratarlo como mensaje sin texto haria que un «CONFIRMAR» pulsado en un
    boton -- el camino que el sistema ofrece al paciente -- se derivara a una
    persona.
    """
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": "wamid.SINTETICO2",
                    "from": TELEFONO,
                    "timestamp": "1776268800",
                    "type": "button",
                    "button": {"payload": "CONFIRMAR", "text": "Confirmar asistencia"},
                }
            ]
        )
    )
    assert carga.mensajes[0].texto == "CONFIRMAR"


def test_la_respuesta_de_una_lista_interactiva_se_lee() -> None:
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": "wamid.SINTETICO3",
                    "from": TELEFONO,
                    "timestamp": "1776268800",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "CANCELAR", "title": "Cancelar cita"},
                    },
                }
            ]
        )
    )
    assert carga.mensajes[0].texto == "CANCELAR"


def test_un_audio_se_registra_sin_texto() -> None:
    """Este modulo no transcribe audio.

    Se registra el mensaje con `texto` nulo, lo que lo lleva a una persona.
    Fingir una transcripcion produciria decisiones sobre contenido que nadie
    leyo.
    """
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": "wamid.SINTETICO4",
                    "from": TELEFONO,
                    "timestamp": "1776268800",
                    "type": "audio",
                    "audio": {"id": "media-sintetico", "mime_type": "audio/ogg"},
                }
            ]
        )
    )
    assert carga.mensajes[0].tipo == "audio"
    assert carga.mensajes[0].texto is None


def test_un_mensaje_sin_identificador_se_descarta() -> None:
    """Sin `id` no hay deduplicacion posible.

    Procesar un mensaje que no se puede deduplicar es peor que descartarlo: un
    reintento de Meta volveria a ejecutar su efecto.
    """
    carga = interpretar(
        _cuerpo(mensajes=[{"from": TELEFONO, "type": "text", "text": {"body": "hola"}}])
    )
    assert carga.mensajes == []


def test_varios_mensajes_en_una_sola_peticion() -> None:
    """Meta agrupa. Procesar solo el primero perderia los demas."""
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": f"wamid.LOTE{indice}",
                    "from": TELEFONO,
                    "timestamp": "1776268800",
                    "type": "text",
                    "text": {"body": "hola"},
                }
                for indice in range(3)
            ]
        )
    )
    assert len(carga.mensajes) == 3


# ---------------------------------------------------------------------------
#  Estados de entrega
# ---------------------------------------------------------------------------
def test_un_estado_de_entrega_se_lee() -> None:
    carga = interpretar(
        _cuerpo(
            estados=[
                {
                    "id": "wamid.ENVIADO1",
                    "status": "delivered",
                    "timestamp": "1776268800",
                    "recipient_id": TELEFONO,
                }
            ]
        )
    )
    assert len(carga.estados) == 1
    assert carga.estados[0].external_id == "wamid.ENVIADO1"
    assert carga.estados[0].estado == "delivered"
    assert carga.estados[0].detalle is None


def test_un_fallo_de_entrega_trae_su_detalle() -> None:
    """El detalle es lo que permite diagnosticar por que no llego.

    Sin el, la cola de fallidos dice que fallo pero no por que, y nadie puede
    actuar.
    """
    carga = interpretar(
        _cuerpo(
            estados=[
                {
                    "id": "wamid.FALLIDO1",
                    "status": "failed",
                    "timestamp": "1776268800",
                    "errors": [
                        {
                            "code": 131026,
                            "title": "Message undeliverable",
                            "message": "Receiver is incapable of receiving this message",
                        }
                    ],
                }
            ]
        )
    )
    detalle = carga.estados[0].detalle
    assert detalle is not None
    assert "131026" in detalle


def test_mensajes_y_estados_en_la_misma_peticion() -> None:
    cuerpo = _cuerpo(
        mensajes=[
            {
                "id": "wamid.MIXTO",
                "from": TELEFONO,
                "timestamp": "1776268800",
                "type": "text",
                "text": {"body": "SI"},
            }
        ],
        estados=[{"id": "wamid.ENVIADO2", "status": "read", "timestamp": "1776268800"}],
    )
    carga = interpretar(cuerpo)
    assert len(carga.mensajes) == 1
    assert len(carga.estados) == 1
    assert not carga.vacia


# ---------------------------------------------------------------------------
#  Formas inesperadas: ninguna puede lanzar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cuerpo",
    [
        None,
        "una cadena",
        42,
        [],
        {},
        {"entry": None},
        {"entry": "no es una lista"},
        {"entry": [None, 3, "x"]},
        {"entry": [{"changes": None}]},
        {"entry": [{"changes": [{"value": None}]}]},
        {"entry": [{"changes": [{"value": {"messages": "no es lista"}}]}]},
        {"entry": [{"changes": [{"value": {"messages": [None, 1]}}]}]},
        {"entry": [{"changes": [{"value": {"statuses": {"id": "x"}}}]}]},
        {"entry": [{"changes": [{"value": {"metadata": "no es dict"}}]}]},
    ],
)
def test_ninguna_forma_inesperada_lanza(cuerpo: Any) -> None:
    """Meta anade campos y tipos sin aviso; un 5xx cuesta la suscripcion."""
    carga = interpretar(cuerpo)
    assert carga.vacia


def test_una_notificacion_sin_mensajes_ni_estados_esta_vacia() -> None:
    """Meta notifica tambien cambios de plantilla y de cuenta. No es un error."""
    assert interpretar(_cuerpo()).vacia


def test_una_marca_de_tiempo_ilegible_no_pierde_el_mensaje() -> None:
    """Una fecha de 1970 es un sintoma visible; perder el mensaje no lo es.

    La hora exacta de recepcion es informativa: descartar el mensaje entero
    por una marca mal formada seria desproporcionado.
    """
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": "wamid.SINFECHA",
                    "from": TELEFONO,
                    "timestamp": "no es un numero",
                    "type": "text",
                    "text": {"body": "hola"},
                }
            ]
        )
    )
    assert len(carga.mensajes) == 1
    assert carga.mensajes[0].recibido_en.year == 1970


def test_un_texto_con_forma_inesperada_no_lanza() -> None:
    carga = interpretar(
        _cuerpo(
            mensajes=[
                {
                    "id": "wamid.RARO",
                    "from": TELEFONO,
                    "timestamp": "1776268800",
                    "type": "text",
                    "text": "no es un diccionario",
                }
            ]
        )
    )
    assert carga.mensajes[0].texto is None
