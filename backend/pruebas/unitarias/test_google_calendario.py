"""Contrato HTTP de Google, sin credenciales ni conexiones externas."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from app.modulos.calendario.adaptadores import Credenciales, ResultadoCalendario
from app.modulos.calendario.eventos import ContenidoNoPermitido, EventoExterno, construir_evento
from app.modulos.calendario.google import AdaptadorGoogleCalendario

pytestmark = [pytest.mark.unitaria, pytest.mark.asyncio]
AHORA = datetime(2026, 10, 10, 15, tzinfo=UTC)
CITA = uuid.UUID("7b74d50d-6d52-4129-a17d-9dff5b80cd2e")
CREDENCIALES = Credenciales("acceso-sintetico", "refresco-sintetico", "agenda@example.invalid")
IDENTIFICADOR = uuid.uuid5(uuid.NAMESPACE_URL, f"clinicai:cita:{CITA}").hex


def evento() -> EventoExterno:
    return construir_evento(
        cita_id=CITA,
        inicio=AHORA,
        fin=AHORA + timedelta(minutes=30),
        consultorio="Sala 1",
        sede="Sede norte",
        url_sistema="https://clinica.example.invalid",
    )


def remoto(identificador: str = IDENTIFICADOR) -> dict:
    origen = evento()
    return {
        "id": identificador,
        "etag": '"revision-1"',
        "status": "confirmed",
        "summary": origen.titulo,
        "description": origen.descripcion,
        "location": origen.ubicacion,
        "start": {"dateTime": origen.inicio.isoformat()},
        "end": {"dateTime": origen.fin.isoformat()},
        "extendedProperties": {
            "private": {
                "clinicai_origen": "sistema-clinica",
                "clinicai_referencia": origen.referencia_interna,
            }
        },
    }


async def test_crear_es_idempotente_y_no_exporta_identidad_ni_invitados() -> None:
    solicitudes = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        solicitudes.append(peticion)
        cuerpo = json.loads(peticion.content)
        assert cuerpo["id"] == IDENTIFICADOR
        assert cuerpo["visibility"] == "private"
        assert cuerpo["transparency"] == "opaque"
        assert "attendees" not in cuerpo
        assert peticion.url.params["sendUpdates"] == "none"
        assert peticion.headers["Authorization"] == "Bearer acceso-sintetico"
        assert "agenda%40example.invalid" in str(peticion.url)
        return httpx.Response(200, json=remoto())

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        adaptador = AdaptadorGoogleCalendario(cliente=cliente)
        primero = await adaptador.crear(CREDENCIALES, evento())
        segundo = await adaptador.crear(CREDENCIALES, evento())
    assert primero.external_event_id == segundo.external_event_id == IDENTIFICADOR
    assert len(solicitudes) == 2


async def test_409_verifica_la_insercion_ya_realizada() -> None:
    def manejar(peticion: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(409) if peticion.method == "POST" else httpx.Response(200, json=remoto())
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        respuesta = await AdaptadorGoogleCalendario(cliente=cliente).crear(CREDENCIALES, evento())
    assert respuesta.resultado is ResultadoCalendario.OK


async def test_recreacion_tras_borrado_usa_generacion_estable() -> None:
    siguiente = hashlib.sha256(IDENTIFICADOR.encode()).hexdigest()
    creados = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        if peticion.method == "GET":
            return httpx.Response(200, json={"id": IDENTIFICADOR, "status": "cancelled"})
        identificador = json.loads(peticion.content)["id"]
        if identificador == IDENTIFICADOR:
            return httpx.Response(409)
        creados.append(identificador)
        return httpx.Response(200, json=remoto(identificador))

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        adaptador = AdaptadorGoogleCalendario(cliente=cliente)
        assert (await adaptador.crear(CREDENCIALES, evento())).external_event_id == siguiente
        assert (await adaptador.crear(CREDENCIALES, evento())).external_event_id == siguiente
    assert creados == [siguiente, siguiente]


@pytest.mark.parametrize("cambio", ["fecha", "origen", "referencia"])
async def test_409_no_pisa_evento_ajeno_o_modificado(cambio: str) -> None:
    datos = remoto()
    if cambio == "fecha":
        datos["start"] = {"dateTime": (AHORA + timedelta(hours=1)).isoformat()}
    else:
        datos["extendedProperties"]["private"]["clinicai_" + cambio] = "otro"

    def manejar(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(409) if peticion.method == "POST" else httpx.Response(200, json=datos)

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        respuesta = await AdaptadorGoogleCalendario(cliente=cliente).crear(CREDENCIALES, evento())
    assert respuesta.resultado is ResultadoCalendario.CONFLICTO


async def test_actualizar_exige_revision_y_usa_if_match() -> None:
    metodos = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        metodos.append(peticion.method)
        if peticion.method == "PATCH":
            assert peticion.headers["If-Match"] == '"revision-1"'
            return httpx.Response(412, json={"error": {"message": "contenido-sensible"}})
        return httpx.Response(200, json=remoto())

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        adaptador = AdaptadorGoogleCalendario(cliente=cliente)
        assert (
            await adaptador.actualizar(CREDENCIALES, IDENTIFICADOR, evento(), etag=None)
        ).resultado is ResultadoCalendario.CONFLICTO
        respuesta = await adaptador.actualizar(
            CREDENCIALES, IDENTIFICADOR, evento(), etag='"revision-1"'
        )
    assert metodos == ["GET", "PATCH"]
    assert respuesta.resultado is ResultadoCalendario.CONFLICTO
    assert "contenido-sensible" not in repr(respuesta)


@pytest.mark.parametrize(
    "codigo,razon,esperado",
    [
        (401, "", ResultadoCalendario.TOKEN_VENCIDO),
        (403, "forbidden", ResultadoCalendario.FALLO_PERMANENTE),
        (403, "rateLimitExceeded", ResultadoCalendario.FALLO_TEMPORAL),
        (403, "userRateLimitExceeded", ResultadoCalendario.FALLO_TEMPORAL),
        (429, "", ResultadoCalendario.FALLO_TEMPORAL),
        (503, "", ResultadoCalendario.FALLO_TEMPORAL),
        (302, "", ResultadoCalendario.FALLO_PERMANENTE),
    ],
)
async def test_consulta_fallida_nunca_significa_borrado(
    codigo: int, razon: str, esperado: ResultadoCalendario
) -> None:
    def manejar(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            codigo,
            json={"error": {"errors": [{"reason": razon}], "message": "dato-sensible"}},
            headers={"Location": "https://otro.example.invalid"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        estado = await AdaptadorGoogleCalendario(cliente=cliente).consultar(
            CREDENCIALES, IDENTIFICADOR
        )
    assert estado.existe
    assert estado.resultado is esperado
    assert "dato-sensible" not in repr(estado)


@pytest.mark.parametrize("codigo", [404, 410])
async def test_consulta_borrado_y_eliminacion_idempotente(codigo: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(codigo))
    ) as cliente:
        adaptador = AdaptadorGoogleCalendario(cliente=cliente)
        assert not (await adaptador.consultar(CREDENCIALES, IDENTIFICADOR)).existe
        assert (
            await adaptador.eliminar(CREDENCIALES, IDENTIFICADOR)
        ).resultado is ResultadoCalendario.OK


async def test_no_elimina_eventos_sin_marca_propia() -> None:
    metodos = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        metodos.append(peticion.method)
        return httpx.Response(200, json={"id": IDENTIFICADOR, "etag": '"revision"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        respuesta = await AdaptadorGoogleCalendario(cliente=cliente).eliminar(
            CREDENCIALES, IDENTIFICADOR
        )
    assert respuesta.resultado is ResultadoCalendario.CONFLICTO
    assert metodos == ["GET"]


async def test_renovacion_conserva_refresco_si_google_no_lo_rota() -> None:
    def manejar(peticion: httpx.Request) -> httpx.Response:
        campos = parse_qs(peticion.content.decode())
        assert campos["grant_type"] == ["refresh_token"]
        assert campos["refresh_token"] == ["refresco-sintetico"]
        assert "Authorization" not in peticion.headers
        return httpx.Response(
            200,
            json={"access_token": "nuevo-sintetico", "expires_in": 3600, "token_type": "Bearer"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        renovacion = await AdaptadorGoogleCalendario(cliente=cliente).renovar_token(
            CREDENCIALES, client_id="cliente", client_secret="sintetico", ahora=AHORA
        )
    assert renovacion.token_acceso == "nuevo-sintetico"
    assert renovacion.token_refresco == CREDENCIALES.token_refresco
    assert renovacion.expira_en == AHORA + timedelta(hours=1)
    assert "nuevo-sintetico" not in repr(renovacion)


@pytest.mark.parametrize(
    "datos",
    [
        {},
        {"access_token": None, "expires_in": 3600},
        {"access_token": "", "expires_in": 3600},
        {"access_token": "sintetico", "expires_in": -1},
        {"access_token": "sintetico", "expires_in": True},
        {"access_token": "sintetico", "expires_in": "3600"},
        {"access_token": "sintetico", "expires_in": 3600, "token_type": None},
        {"access_token": "sintetico", "expires_in": 3600, "refresh_token": ""},
    ],
)
async def test_renovacion_rechaza_respuestas_invalidas(datos: dict) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=datos))
    ) as cliente:
        renovacion = await AdaptadorGoogleCalendario(cliente=cliente).renovar_token(
            CREDENCIALES, client_id="cliente", client_secret="sintetico", ahora=AHORA
        )
    assert renovacion.resultado is ResultadoCalendario.FALLO_TEMPORAL


@pytest.mark.parametrize(
    "codigo,error,esperado",
    [
        (400, "invalid_grant", ResultadoCalendario.TOKEN_VENCIDO),
        (400, "invalid_client", ResultadoCalendario.FALLO_PERMANENTE),
        (503, "temporarily_unavailable", ResultadoCalendario.FALLO_TEMPORAL),
    ],
)
async def test_renovacion_distingue_revocacion_y_fallo_temporal(
    codigo: int, error: str, esperado: ResultadoCalendario
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                codigo, json={"error": error, "error_description": "secreto-sintetico"}
            )
        )
    ) as cliente:
        renovacion = await AdaptadorGoogleCalendario(cliente=cliente).renovar_token(
            CREDENCIALES, client_id="cliente", client_secret="sintetico", ahora=AHORA
        )
    assert renovacion.resultado is esperado
    assert "secreto-sintetico" not in repr(renovacion)


async def test_timeout_no_borra_ni_filtra_tokens() -> None:
    def manejar(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("acceso-sintetico", request=peticion)

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        adaptador = AdaptadorGoogleCalendario(cliente=cliente)
        creacion = await adaptador.crear(CREDENCIALES, evento())
        consulta = await adaptador.consultar(CREDENCIALES, IDENTIFICADOR)
    assert creacion.es_reintentable
    assert consulta.existe
    assert consulta.resultado is ResultadoCalendario.FALLO_TEMPORAL
    assert "acceso-sintetico" not in repr(creacion)


async def test_barrera_de_contenido_antes_de_hacer_red() -> None:
    origen = evento()
    peligroso = EventoExterno(
        "paciente: ejemplo",
        origen.descripcion,
        origen.inicio,
        origen.fin,
        None,
        origen.referencia_interna,
    )
    with pytest.raises(ContenidoNoPermitido):
        await AdaptadorGoogleCalendario().crear(CREDENCIALES, peligroso)


@pytest.mark.parametrize(
    "cambio",
    [
        {"referencia_interna": "datos-de-una-persona"},
        {"referencia_interna": "cita:sin-uuid"},
        {"etiqueta_origen": "otro-origen"},
    ],
)
async def test_metadatos_del_evento_no_admiten_texto_libre(cambio: dict) -> None:
    with pytest.raises(ValueError, match="referencia"):
        await AdaptadorGoogleCalendario().crear(CREDENCIALES, replace(evento(), **cambio))


async def test_actualiza_un_evento_propio_con_la_revision_vigente() -> None:
    def manejar(peticion: httpx.Request) -> httpx.Response:
        datos = remoto()
        if peticion.method == "PATCH":
            assert peticion.headers["If-Match"] == '"revision-1"'
            datos["etag"] = '"revision-2"'
        return httpx.Response(200, json=datos)

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        respuesta = await AdaptadorGoogleCalendario(cliente=cliente).actualizar(
            CREDENCIALES, IDENTIFICADOR, evento(), etag='"revision-1"'
        )
    assert respuesta.resultado is ResultadoCalendario.OK
    assert respuesta.etag == '"revision-2"'


async def test_elimina_solo_el_reflejo_y_envia_precondicion() -> None:
    metodos = []

    def manejar(peticion: httpx.Request) -> httpx.Response:
        metodos.append(peticion.method)
        if peticion.method == "DELETE":
            assert peticion.headers["If-Match"] == '"revision-1"'
            return httpx.Response(204)
        return httpx.Response(200, json=remoto())

    async with httpx.AsyncClient(transport=httpx.MockTransport(manejar)) as cliente:
        respuesta = await AdaptadorGoogleCalendario(cliente=cliente).eliminar(
            CREDENCIALES, IDENTIFICADOR
        )
    assert respuesta.resultado is ResultadoCalendario.OK
    assert metodos == ["GET", "DELETE"]


async def test_consulta_conserva_los_instantes_y_el_origen() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=remoto()))
    ) as cliente:
        estado = await AdaptadorGoogleCalendario(cliente=cliente).consultar(
            CREDENCIALES, IDENTIFICADOR
        )
    assert estado.existe and estado.es_nuestro
    assert estado.inicio == AHORA
    assert estado.fin == AHORA + timedelta(minutes=30)


@pytest.mark.parametrize(
    "datos",
    [
        {},
        {"id": IDENTIFICADOR},
        {"id": IDENTIFICADOR, "etag": None},
        {"id": "otro", "etag": "revision"},
    ],
)
async def test_respuesta_incompleta_no_se_declara_sincronizada(datos: dict) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=datos))
    ) as cliente:
        adaptador = AdaptadorGoogleCalendario(cliente=cliente)
        assert (
            await adaptador.crear(CREDENCIALES, evento())
        ).resultado is ResultadoCalendario.FALLO_TEMPORAL
        assert (
            await adaptador.consultar(CREDENCIALES, IDENTIFICADOR)
        ).resultado is ResultadoCalendario.FALLO_TEMPORAL
