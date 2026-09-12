"""Adaptadores de canal saliente.

Alcance honesto de estas pruebas
--------------------------------
El adaptador de la Cloud API **no se ha ejecutado contra Meta**: no hay
credenciales y no se inventan (CLAUDE.md, regla 3).  Lo que se verifica aqui
es lo unico verificable sin ellas, y no es poco:

* Que el cuerpo que se construye tiene la forma que documenta la Cloud API.
* Que la clasificacion de errores es correcta -- que decide bien cuando
  reintentar y cuando no.

Lo que **no** demuestra: que Meta acepte ese cuerpo, ni que sus codigos de
error sean los que esta lista supone.  Queda declarado como limitacion E-1.
Se usa `httpx.MockTransport`, que responde sin abrir un socket: ninguna prueba
de esta suite puede salir a la red.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.mensajeria.adaptadores import (
    CODIGOS_PERMANENTES,
    AdaptadorSandbox,
    AdaptadorWhatsAppCloud,
    CredencialesWhatsApp,
    MensajeSaliente,
    RegistroCanales,
    ResultadoEnvio,
)
from app.modulos.outbox.modelos import CanalOutbox
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import ProveedorExternoNoDisponible
from app.tareas.outbox import construir_canales

pytestmark = pytest.mark.unitaria

# Credenciales sinteticas. No son ni se parecen a credenciales reales.
CREDENCIALES = CredencialesWhatsApp(
    id_numero_telefono="000000000000000",
    token_acceso="token-sintetico-de-prueba",
    version_api="v21.0",
)

MENSAJE = MensajeSaliente(
    destino="593999000111",
    nombre_plantilla="cita_recordatorio_dia",
    variables=("16 de abril", "09:30", "Paciente", "Profesional", "Sede"),
    texto="Le recordamos su cita.",
)


def _adaptador(manejador: Any) -> AdaptadorWhatsAppCloud:
    """Adaptador sobre un transporte que no abre ningun socket."""
    return AdaptadorWhatsAppCloud(
        CREDENCIALES, cliente=httpx.AsyncClient(transport=httpx.MockTransport(manejador))
    )


# ---------------------------------------------------------------------------
#  Sandbox
# ---------------------------------------------------------------------------
async def test_el_sandbox_registra_el_envio_y_no_sale_a_la_red() -> None:
    canal = AdaptadorSandbox()
    respuesta = await canal.enviar(MENSAJE)

    assert respuesta.resultado is ResultadoEnvio.ENTREGADO
    assert respuesta.referencia_externa is not None
    assert len(canal.enviados) == 1
    assert canal.enviados[0].mensaje is MENSAJE


async def test_el_sandbox_consume_los_fallos_programados_en_orden() -> None:
    """Permite ejercer los reintentos sin depender de que el proveedor falle."""
    canal = AdaptadorSandbox()
    canal.programar_fallo(ResultadoEnvio.FALLO_TEMPORAL, "primero")
    canal.programar_fallo(ResultadoEnvio.FALLO_PERMANENTE, "segundo")

    assert (await canal.enviar(MENSAJE)).detalle == "primero"
    assert (await canal.enviar(MENSAJE)).detalle == "segundo"
    # Agotados los fallos, vuelve a entregar.
    assert (await canal.enviar(MENSAJE)).resultado is ResultadoEnvio.ENTREGADO
    # Y solo el ultimo se registro como enviado de verdad.
    assert len(canal.enviados) == 1


# ---------------------------------------------------------------------------
#  Construccion del cuerpo
# ---------------------------------------------------------------------------
async def test_el_cuerpo_usa_plantilla_y_no_texto_libre() -> None:
    """La Cloud API no admite texto libre para iniciar conversacion.

    Fuera de la ventana de 24 horas exige la plantilla aprobada con sus
    parametros posicionales. Enviar `type: text` se rechaza con el codigo
    131047, que aparece como fallo sin explicacion util.
    """
    capturado: dict[str, Any] = {}

    def manejador(peticion: httpx.Request) -> httpx.Response:
        capturado.update(json.loads(peticion.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.ACEPTADO"}]})

    await _adaptador(manejador).enviar(MENSAJE)

    assert capturado["messaging_product"] == "whatsapp"
    assert capturado["type"] == "template"
    assert capturado["to"] == "593999000111"
    assert capturado["template"]["name"] == "cita_recordatorio_dia"
    assert capturado["template"]["language"]["code"] == "es"

    parametros = capturado["template"]["components"][0]["parameters"]
    assert [p["text"] for p in parametros] == list(MENSAJE.variables)


async def test_la_url_incluye_version_y_numero() -> None:
    capturado: dict[str, str] = {}

    def manejador(peticion: httpx.Request) -> httpx.Response:
        capturado["url"] = str(peticion.url)
        capturado["autorizacion"] = peticion.headers.get("Authorization", "")
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    await _adaptador(manejador).enviar(MENSAJE)

    assert capturado["url"] == ("https://graph.facebook.com/v21.0/000000000000000/messages")
    assert capturado["autorizacion"] == "Bearer token-sintetico-de-prueba"


# ---------------------------------------------------------------------------
#  Clasificacion de respuestas
# ---------------------------------------------------------------------------
async def test_una_respuesta_aceptada_devuelve_la_referencia() -> None:
    """La referencia es lo que permite conciliar el estado de entrega."""

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": [{"id": "wamid.REFERENCIA"}]})

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.ENTREGADO
    assert respuesta.referencia_externa == "wamid.REFERENCIA"


async def test_un_2xx_sin_identificador_se_considera_entregado() -> None:
    """El proveedor lo acepto; sin referencia no habra conciliacion.

    Marcarlo fallido haria que se reenviara un mensaje que el paciente ya
    recibio.
    """

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"algo": "inesperado"})

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.ENTREGADO
    assert respuesta.referencia_externa is None


@pytest.mark.parametrize("codigo_http", [500, 502, 503, 504])
async def test_un_error_del_servidor_es_temporal(codigo_http: int) -> None:
    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(codigo_http, json={"error": {"code": 1}})

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_TEMPORAL


async def test_el_limite_de_tasa_es_temporal() -> None:
    """Un 429 es lo que el retroceso exponencial existe para resolver."""

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": 130429}})

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_TEMPORAL


@pytest.mark.parametrize("codigo", sorted(CODIGOS_PERMANENTES))
async def test_los_codigos_permanentes_no_se_reintentan(codigo: int) -> None:
    """Reintentar un numero inexistente gasta cuota y retrasa lo demas."""

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": codigo, "message": "rechazado"}})

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_PERMANENTE


async def test_un_4xx_con_codigo_desconocido_se_reintenta() -> None:
    """La eleccion deliberada ante lo desconocido.

    Descartar un recordatorio por un error que era temporal es peor que un
    reintento de mas.
    """

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 999999}})

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_TEMPORAL


async def test_un_4xx_sin_cuerpo_json_se_reintenta() -> None:
    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b"<html>error</html>")

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_TEMPORAL


async def test_un_timeout_se_reintenta() -> None:
    """Un timeout es ambiguo: el mensaje pudo entregarse.

    Se reintenta, y la deduplicacion del outbox evita el duplicado. La
    alternativa -- darlo por fallido -- perderia recordatorios que si
    salieron.
    """

    def manejador(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("agotado", request=peticion)

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_TEMPORAL
    assert "espera" in (respuesta.detalle or "").lower()


async def test_un_error_de_red_se_reintenta() -> None:
    def manejador(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta", request=peticion)

    respuesta = await _adaptador(manejador).enviar(MENSAJE)
    assert respuesta.resultado is ResultadoEnvio.FALLO_TEMPORAL


async def test_el_adaptador_nunca_lanza_por_un_fallo_del_proveedor() -> None:
    """Quien decide si se reintenta es el outbox, que sabe los intentos.

    Si el adaptador lanzara, el procesador tendria que adivinar la
    clasificacion a partir del tipo de excepcion.
    """

    def manejador(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin ruta", request=peticion)

    # No hay `pytest.raises`: la ausencia de excepcion es la afirmacion.
    await _adaptador(manejador).enviar(MENSAJE)


# ---------------------------------------------------------------------------
#  Configuracion
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("id_numero", "token"),
    [("", "token-sintetico"), ("000000000000000", ""), ("", "")],
)
def test_sin_credenciales_falla_al_construirlo(id_numero: str, token: str) -> None:
    """Falla al construirlo, no al primer envio.

    Arrancar con el adaptador real mal configurado significa descubrirlo
    cuando un paciente no recibio su recordatorio.
    """
    with pytest.raises(ProveedorExternoNoDisponible, match="MODO_WHATSAPP=sandbox"):
        AdaptadorWhatsAppCloud(
            CredencialesWhatsApp(id_numero_telefono=id_numero, token_acceso=token)
        )


def test_un_canal_sin_registrar_devuelve_none() -> None:
    """Un canal sin adaptador no impide arrancar la aplicacion.

    Exigir los cuatro canales impediria levantar el backend para trabajar en
    la agenda.
    """
    assert RegistroCanales().obtener("WHATSAPP") is None


# ---------------------------------------------------------------------------
#  Seleccion de adaptador por entorno
# ---------------------------------------------------------------------------
def test_en_modo_sandbox_no_se_construye_el_adaptador_real() -> None:
    """Garantia de que ninguna prueba puede salir a la red.

    Y de que un entorno sin credenciales no intente hablar con Meta: el
    adaptador real falla al construirse si faltan, y eso tumbaria el worker.
    """
    canales = construir_canales(Configuracion(modo_whatsapp="sandbox"))
    canal = canales.obtener(CanalOutbox.WHATSAPP.value)
    assert isinstance(canal, AdaptadorSandbox)
    assert not isinstance(canal, AdaptadorWhatsAppCloud)


def test_en_modo_cloud_api_se_construye_el_adaptador_real() -> None:
    """Con credenciales sinteticas, para comprobar solo la seleccion.

    No se envia nada: construir el adaptador no abre ninguna conexion.
    """
    canales = construir_canales(
        Configuracion(
            modo_whatsapp="cloud_api",
            whatsapp_id_numero_telefono="000000000000000",
            whatsapp_token_acceso=SecretStr("token-sintetico"),
        )
    )
    assert isinstance(canales.obtener(CanalOutbox.WHATSAPP.value), AdaptadorWhatsAppCloud)


def test_los_canales_sin_adaptador_propio_reciben_el_sandbox() -> None:
    """Correo e interno todavia no tienen adaptador propio.

    Se registra el sandbox y se avisa: sin entrada, el procesador devolveria
    esos mensajes a la cola indefinidamente diciendo solo «no hay adaptador».
    """
    canales = construir_canales(Configuracion(modo_whatsapp="sandbox"))
    assert canales.obtener(CanalOutbox.CORREO.value) is not None
    assert canales.obtener(CanalOutbox.INTERNO.value) is not None
