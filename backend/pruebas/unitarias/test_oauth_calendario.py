"""El parametro `state` de OAuth como control de seguridad.

El ataque que esto detiene
--------------------------
Si `state` fuera un campo informativo -- el identificador del profesional
puesto ahi y leido tal cual al volver --, un tercero podria preparar una URL
de callback con el `state` de **otra** persona y conseguir que el sistema
asocie su propio calendario de Google a la cuenta de esa persona, o al
contrario: quedarse con el calendario de un companero.

Por eso `state` va firmado, caduca y es de un solo uso. Estas pruebas
comprueban las tres cosas.

El secreto es sintetico y vive solo en este archivo (CLAUDE.md, regla 2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.modulos.calendario import oauth
from app.nucleo.errores import FirmaInvalida, ProveedorExternoNoDisponible

pytestmark = [pytest.mark.unitaria, pytest.mark.seguridad]

SECRETO = "secreto-sintetico-de-firma-para-pruebas"
AHORA = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
PROFESIONAL = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _firmado(*, profesional: uuid.UUID = PROFESIONAL, ahora: datetime = AHORA) -> str:
    return oauth.firmar_estado(oauth.nuevo_estado(profesional, ahora=ahora), SECRETO)


# ---------------------------------------------------------------------------
#  Firma
# ---------------------------------------------------------------------------
def test_un_estado_valido_se_verifica_y_devuelve_el_profesional() -> None:
    verificado = oauth.verificar_estado(_firmado(), SECRETO, ahora=AHORA)
    assert verificado.profesional_id == PROFESIONAL


def test_un_estado_firmado_con_otro_secreto_se_rechaza() -> None:
    ajeno = oauth.firmar_estado(oauth.nuevo_estado(PROFESIONAL, ahora=AHORA), "otro-secreto")
    with pytest.raises(FirmaInvalida, match="no coincide"):
        oauth.verificar_estado(ajeno, SECRETO, ahora=AHORA)


def test_cambiar_el_profesional_invalida_la_firma() -> None:
    """El ataque concreto: apropiarse del calendario de otra persona.

    Se toma un `state` valido y se sustituye el cuerpo por uno que nombra a
    otro profesional, conservando la firma original.
    """
    valido = _firmado()
    cuerpo_ajeno = oauth.firmar_estado(
        oauth.nuevo_estado(uuid.uuid4(), ahora=AHORA), "cualquier-otro-secreto"
    ).split(".")[0]
    manipulado = f"{cuerpo_ajeno}.{valido.split('.')[1]}"

    with pytest.raises(FirmaInvalida):
        oauth.verificar_estado(manipulado, SECRETO, ahora=AHORA)


@pytest.mark.parametrize(
    "valor",
    ["", "sin-punto", "a.b.c", ".", "x.", ".y", "no-base64!.firma"],
)
def test_un_estado_deforme_se_rechaza(valor: str) -> None:
    with pytest.raises(FirmaInvalida):
        oauth.verificar_estado(valor, SECRETO, ahora=AHORA)


def test_sin_secreto_no_se_firma_ni_se_verifica() -> None:
    """Un `state` sin firmar es un vale de autorizacion en blanco.

    Se falla de forma explicita en lugar de aceptar cualquier valor cuando
    falta la configuracion.
    """
    with pytest.raises(FirmaInvalida, match="secreto"):
        oauth.firmar_estado(oauth.nuevo_estado(PROFESIONAL, ahora=AHORA), "")
    with pytest.raises(FirmaInvalida, match="secreto"):
        oauth.verificar_estado(_firmado(), "", ahora=AHORA)


# ---------------------------------------------------------------------------
#  Vigencia
# ---------------------------------------------------------------------------
def test_un_estado_dentro_de_su_vigencia_se_acepta() -> None:
    valido = _firmado()
    oauth.verificar_estado(valido, SECRETO, ahora=AHORA + timedelta(minutes=14))


def test_un_estado_caducado_se_rechaza() -> None:
    """Un `state` eterno es un vale de autorizacion reutilizable."""
    valido = _firmado()
    with pytest.raises(FirmaInvalida, match="caduco"):
        oauth.verificar_estado(
            valido, SECRETO, ahora=AHORA + oauth.VIGENCIA_ESTADO + timedelta(seconds=1)
        )


def test_el_limite_exacto_de_vigencia_se_acepta() -> None:
    """El limite no se cuenta como caducado.

    Se fija porque un «mayor o igual» aqui rechazaria un flujo legitimo que
    tardo exactamente lo permitido.
    """
    oauth.verificar_estado(_firmado(), SECRETO, ahora=AHORA + oauth.VIGENCIA_ESTADO)


def test_un_estado_emitido_en_el_futuro_se_rechaza() -> None:
    """Indica manipulacion o un reloj desincronizado. En ambos casos, no."""
    futuro = _firmado(ahora=AHORA + timedelta(hours=1))
    with pytest.raises(FirmaInvalida, match="emision"):
        oauth.verificar_estado(futuro, SECRETO, ahora=AHORA)


def test_dos_estados_seguidos_son_distintos() -> None:
    """El valor aleatorio es lo que hace posible el control de un solo uso.

    Si dos emisiones para el mismo profesional produjeran el mismo `state`, el
    segundo flujo legitimo se rechazaria como reutilizado.
    """
    assert _firmado() != _firmado()


# ---------------------------------------------------------------------------
#  URL de autorizacion
# ---------------------------------------------------------------------------
def test_la_url_pide_acceso_offline_y_consentimiento() -> None:
    """Sin `access_type=offline` no llega token de refresco.

    Y sin `prompt=consent`, Google no lo vuelve a entregar a quien ya
    autorizo antes -- que es el caso en el que la conexion se rompe a la hora
    y nadie entiende por que.
    """
    url = oauth.url_autorizacion(
        client_id="cliente-sintetico",
        redirect_uri="https://clinica.example.invalid/callback",
        scopes="https://www.googleapis.com/auth/calendar.events",
        estado_firmado=_firmado(),
    )
    assert url.startswith(oauth.URL_AUTORIZACION_GOOGLE)
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=" in url


def test_sin_client_id_no_se_construye_la_url() -> None:
    """Falla de forma explicita y dice que usar en su lugar."""
    with pytest.raises(ProveedorExternoNoDisponible, match="MODO_CALENDARIO=sandbox"):
        oauth.url_autorizacion(
            client_id="",
            redirect_uri="https://clinica.example.invalid/callback",
            scopes="scope",
            estado_firmado=_firmado(),
        )


# ---------------------------------------------------------------------------
#  Intercambio del codigo
# ---------------------------------------------------------------------------
async def test_el_intercambio_devuelve_los_tokens() -> None:
    """Con transporte simulado: ninguna prueba sale a la red."""

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "acceso-sintetico",
                "refresh_token": "refresco-sintetico",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/calendar.events",
            },
        )

    tokens = await oauth.intercambiar_codigo(
        codigo="codigo-sintetico",
        client_id="cliente",
        client_secret="secreto",
        redirect_uri="https://clinica.example.invalid/callback",
        ahora=AHORA,
        cliente=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
    )
    assert tokens.token_acceso == "acceso-sintetico"
    assert tokens.token_refresco == "refresco-sintetico"
    assert tokens.expira_en == AHORA + timedelta(seconds=3600)


async def test_una_respuesta_sin_token_de_refresco_falla() -> None:
    """Guardar solo el de acceso produce una conexion que se rompe a la hora.

    Y el sintoma -- «la sincronizacion dejo de ir» -- no apunta a su causa.
    """

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "solo-acceso", "expires_in": 3600})

    with pytest.raises(ProveedorExternoNoDisponible, match="token de refresco"):
        await oauth.intercambiar_codigo(
            codigo="codigo",
            client_id="cliente",
            client_secret="secreto",
            redirect_uri="https://clinica.example.invalid/callback",
            ahora=AHORA,
            cliente=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
        )


async def test_el_error_del_proveedor_no_filtra_su_cuerpo() -> None:
    """El cuerpo puede contener fragmentos del codigo de autorizacion."""
    secreto_en_respuesta = "codigo-de-autorizacion-filtrado"

    def manejador(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "code": secreto_en_respuesta})

    with pytest.raises(ProveedorExternoNoDisponible) as fallo:
        await oauth.intercambiar_codigo(
            codigo="codigo",
            client_id="cliente",
            client_secret="secreto",
            redirect_uri="https://clinica.example.invalid/callback",
            ahora=AHORA,
            cliente=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
        )
    assert secreto_en_respuesta not in str(fallo.value)


async def test_sin_credenciales_no_se_intenta_el_intercambio() -> None:
    with pytest.raises(ProveedorExternoNoDisponible, match="MODO_CALENDARIO=sandbox"):
        await oauth.intercambiar_codigo(
            codigo="codigo",
            client_id="",
            client_secret="",
            redirect_uri="https://clinica.example.invalid/callback",
            ahora=AHORA,
        )


def test_los_tokens_no_aparecen_en_su_repr() -> None:
    """Un `repr` accidental -- en un traceback, en un log -- no los vuelca."""
    tokens = oauth.TokensObtenidos(
        token_acceso="acceso-secreto",
        token_refresco="refresco-secreto",
        expira_en=AHORA,
        alcances=None,
    )
    texto = repr(tokens)
    assert "acceso-secreto" not in texto
    assert "refresco-secreto" not in texto
    assert "oculto" in texto
