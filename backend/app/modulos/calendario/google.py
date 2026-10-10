"""Google Calendar v3. HTTP acotado, errores sin cuerpo y eventos sin pacientes.

Los IDs deterministas permiten repetir una insercion tras perder la respuesta.
Un evento borrado usa la siguiente generacion determinista, nunca un ID al azar.
La agenda interna permanece independiente de la disponibilidad del proveedor.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from app.modulos.calendario.adaptadores import (
    Credenciales,
    EstadoRemoto,
    RenovacionToken,
    RespuestaCalendario,
    ResultadoCalendario,
)
from app.modulos.calendario.eventos import EventoExterno, verificar
from app.modulos.calendario.oauth import URL_TOKEN_GOOGLE

URL_API = "https://www.googleapis.com/calendar/v3/calendars"
MAXIMO_GENERACIONES = 5
RAZONES_REINTENTABLES = frozenset(
    {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "backendError"}
)


def _datos(respuesta: httpx.Response) -> dict[str, Any]:
    try:
        valor = respuesta.json()
    except ValueError:
        return {}
    return valor if isinstance(valor, dict) else {}


def _fallo(respuesta: httpx.Response) -> ResultadoCalendario:
    codigo = respuesta.status_code
    if codigo == httpx.codes.UNAUTHORIZED:
        return ResultadoCalendario.TOKEN_VENCIDO
    if codigo in {httpx.codes.NOT_FOUND, httpx.codes.GONE}:
        return ResultadoCalendario.NO_ENCONTRADO
    if codigo in {httpx.codes.CONFLICT, httpx.codes.PRECONDITION_FAILED}:
        return ResultadoCalendario.CONFLICTO
    error = _datos(respuesta).get("error")
    errores = error.get("errors", []) if isinstance(error, dict) else []
    cuota = isinstance(errores, list) and any(
        isinstance(e, dict) and e.get("reason") in RAZONES_REINTENTABLES for e in errores
    )
    if (
        codigo == httpx.codes.TOO_MANY_REQUESTS
        or codigo >= httpx.codes.INTERNAL_SERVER_ERROR
        or cuota
    ):
        return ResultadoCalendario.FALLO_TEMPORAL
    return ResultadoCalendario.FALLO_PERMANENTE


def _fecha(valor: Any) -> datetime | None:
    if not isinstance(valor, dict) or not isinstance(valor.get("dateTime"), str):
        return None
    try:
        fecha = datetime.fromisoformat(valor["dateTime"].replace("Z", "+00:00"))
    except ValueError:
        return None
    return fecha if fecha.tzinfo is not None else None


def _propiedades(datos: dict[str, Any]) -> dict[str, Any]:
    extendidas = datos.get("extendedProperties")
    privadas = extendidas.get("private") if isinstance(extendidas, dict) else None
    return privadas if isinstance(privadas, dict) else {}


def _es_propio(datos: dict[str, Any], referencia: str | None = None) -> bool:
    privadas = _propiedades(datos)
    ref = privadas.get("clinicai_referencia")
    if privadas.get("clinicai_origen") != "sistema-clinica" or not isinstance(ref, str):
        return False
    try:
        if not ref.startswith("cita:"):
            return False
        uuid.UUID(ref.removeprefix("cita:"))
    except ValueError:
        return False
    return referencia is None or ref == referencia


def _payload(evento: EventoExterno) -> dict[str, Any]:
    verificar(evento)
    try:
        if evento.etiqueta_origen != "sistema-clinica" or not evento.referencia_interna.startswith(
            "cita:"
        ):
            raise ValueError("Origen invalido.")
        referencia = uuid.UUID(evento.referencia_interna.removeprefix("cita:"))
        if evento.referencia_interna != f"cita:{referencia}":
            raise ValueError("Referencia invalida.")
    except (ValueError, AttributeError) as exc:
        raise ValueError("El evento exige una referencia de cita y el origen de ClinicAI.") from exc
    if evento.inicio.tzinfo is None or evento.fin.tzinfo is None or evento.fin <= evento.inicio:
        raise ValueError("El evento exige horas con zona y un intervalo positivo.")
    return {
        "summary": evento.titulo,
        "description": evento.descripcion,
        "location": evento.ubicacion or "",
        "start": {"dateTime": evento.inicio.isoformat()},
        "end": {"dateTime": evento.fin.isoformat()},
        "visibility": "private",
        "transparency": "opaque",
        "extendedProperties": {
            "private": {
                "clinicai_origen": evento.etiqueta_origen,
                "clinicai_referencia": evento.referencia_interna,
            }
        },
    }


class AdaptadorGoogleCalendario:
    nombre = "google"

    def __init__(self, *, cliente: httpx.AsyncClient | None = None) -> None:
        self._cliente = cliente

    async def _http(self, metodo: str, url: str, **opciones: Any) -> httpx.Response | None:
        # Sin redirecciones: un destino no esperado no recibe el bearer ni el secreto.
        try:
            if self._cliente is not None:
                return await self._cliente.request(metodo, url, follow_redirects=False, **opciones)
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as cliente:
                return await cliente.request(metodo, url, **opciones)
        except httpx.HTTPError:
            return None

    async def _pedir(
        self,
        metodo: str,
        credenciales: Credenciales,
        evento_id: str | None = None,
        **opciones: Any,
    ) -> httpx.Response | None:
        url = f"{URL_API}/{quote(credenciales.calendar_id, safe='')}/events"
        if evento_id is not None:
            url += f"/{quote(evento_id, safe='')}"
        cabeceras = dict(opciones.pop("headers", {}))
        cabeceras["Authorization"] = f"Bearer {credenciales.token_acceso}"
        return await self._http(metodo, url, headers=cabeceras, **opciones)

    @staticmethod
    def _error(respuesta: httpx.Response | None) -> RespuestaCalendario:
        if respuesta is None:
            return RespuestaCalendario(
                ResultadoCalendario.FALLO_TEMPORAL,
                detalle="No se pudo contactar con Google Calendar.",
            )
        return RespuestaCalendario(
            _fallo(respuesta),
            detalle=f"Google Calendar rechazo la operacion (HTTP {respuesta.status_code}).",
        )

    @staticmethod
    def _exito(datos: dict[str, Any], esperado: str) -> RespuestaCalendario:
        if (
            datos.get("id") != esperado
            or not isinstance(datos.get("etag"), str)
            or not datos["etag"]
        ):
            return RespuestaCalendario(
                ResultadoCalendario.FALLO_TEMPORAL, detalle="Google devolvio un evento incompleto."
            )
        return RespuestaCalendario(ResultadoCalendario.OK, esperado, datos["etag"])

    async def crear(self, credenciales: Credenciales, evento: EventoExterno) -> RespuestaCalendario:  # noqa: PLR0911
        cuerpo = _payload(evento)
        identificador = uuid.uuid5(uuid.NAMESPACE_URL, "clinicai:" + evento.referencia_interna).hex
        for _ in range(MAXIMO_GENERACIONES):
            respuesta = await self._pedir(
                "POST",
                credenciales,
                json={**cuerpo, "id": identificador},
                params={"sendUpdates": "none"},
            )
            if respuesta is None:
                return self._error(None)
            if respuesta.status_code == httpx.codes.CONFLICT:
                existente = await self._pedir("GET", credenciales, identificador)
                if existente is not None and existente.status_code == httpx.codes.GONE:
                    identificador = hashlib.sha256(identificador.encode()).hexdigest()
                    continue
                if existente is not None and existente.status_code not in {
                    httpx.codes.OK,
                    httpx.codes.NOT_FOUND,
                }:
                    return self._error(existente)
                if existente is None or existente.status_code != httpx.codes.OK:
                    # 409 + 404 es una lectura incierta: no saltar a otra generacion.
                    return RespuestaCalendario(
                        ResultadoCalendario.FALLO_TEMPORAL,
                        detalle="No se pudo verificar el evento existente.",
                    )
                datos = _datos(existente)
                if datos.get("status") == "cancelled":
                    identificador = hashlib.sha256(identificador.encode()).hexdigest()
                    continue
                coincide = (
                    _es_propio(datos, evento.referencia_interna)
                    and _fecha(datos.get("start")) == evento.inicio
                    and _fecha(datos.get("end")) == evento.fin
                    and all(
                        datos.get(k, "") == cuerpo[k]
                        for k in ("summary", "description", "location")
                    )
                )
                if not coincide:
                    return RespuestaCalendario(
                        ResultadoCalendario.CONFLICTO,
                        detalle="El evento existente requiere revision humana.",
                    )
                return self._exito(datos, identificador)
            if respuesta.status_code not in {httpx.codes.OK, httpx.codes.CREATED}:
                # Un 404 del calendario no significa que falte un evento.
                error = self._error(respuesta)
                if error.resultado is ResultadoCalendario.NO_ENCONTRADO:
                    return RespuestaCalendario(
                        ResultadoCalendario.FALLO_PERMANENTE,
                        detalle="El calendario no esta disponible para esta cuenta.",
                    )
                return error
            return self._exito(_datos(respuesta), identificador)
        return RespuestaCalendario(
            ResultadoCalendario.FALLO_PERMANENTE,
            detalle="Se agoto el limite de recreaciones; revise el calendario.",
        )

    async def actualizar(
        self,
        credenciales: Credenciales,
        external_event_id: str,
        evento: EventoExterno,
        *,
        etag: str | None,
    ) -> RespuestaCalendario:
        cuerpo = _payload(evento)
        if not etag:
            return RespuestaCalendario(
                ResultadoCalendario.CONFLICTO,
                detalle="Falta la revision del evento; requiere conciliacion.",
            )
        previo = await self._pedir("GET", credenciales, external_event_id)
        if previo is None or previo.status_code != httpx.codes.OK:
            return self._error(previo)
        datos = _datos(previo)
        if datos.get("status") == "cancelled":
            return RespuestaCalendario(ResultadoCalendario.NO_ENCONTRADO)
        if not _es_propio(datos, evento.referencia_interna) or datos.get("etag") != etag:
            return RespuestaCalendario(
                ResultadoCalendario.CONFLICTO, detalle="El evento cambio fuera de ClinicAI."
            )
        respuesta = await self._pedir(
            "PATCH",
            credenciales,
            external_event_id,
            json=cuerpo,
            headers={"If-Match": etag},
            params={"sendUpdates": "none"},
        )
        if respuesta is None or respuesta.status_code != httpx.codes.OK:
            return self._error(respuesta)
        return self._exito(_datos(respuesta), external_event_id)

    async def eliminar(  # noqa: PLR0911
        self, credenciales: Credenciales, external_event_id: str
    ) -> RespuestaCalendario:
        previo = await self._pedir("GET", credenciales, external_event_id)
        if previo is None:
            return self._error(None)
        if previo.status_code in {httpx.codes.NOT_FOUND, httpx.codes.GONE}:
            return RespuestaCalendario(ResultadoCalendario.OK)
        if previo.status_code != httpx.codes.OK:
            return self._error(previo)
        datos = _datos(previo)
        if datos.get("status") == "cancelled":
            return RespuestaCalendario(ResultadoCalendario.OK)
        if not _es_propio(datos) or not isinstance(datos.get("etag"), str) or not datos["etag"]:
            return RespuestaCalendario(
                ResultadoCalendario.CONFLICTO, detalle="El evento no conserva su origen o revision."
            )
        respuesta = await self._pedir(
            "DELETE",
            credenciales,
            external_event_id,
            headers={"If-Match": datos["etag"]},
            params={"sendUpdates": "none"},
        )
        if respuesta is not None and respuesta.status_code in {
            httpx.codes.NO_CONTENT,
            httpx.codes.NOT_FOUND,
            httpx.codes.GONE,
        }:
            return RespuestaCalendario(ResultadoCalendario.OK)
        return self._error(respuesta)

    async def consultar(self, credenciales: Credenciales, external_event_id: str) -> EstadoRemoto:
        respuesta = await self._pedir("GET", credenciales, external_event_id)
        if respuesta is not None and respuesta.status_code in {
            httpx.codes.NOT_FOUND,
            httpx.codes.GONE,
        }:
            return EstadoRemoto(existe=False)
        if respuesta is None or respuesta.status_code != httpx.codes.OK:
            error = self._error(respuesta)
            return EstadoRemoto(existe=True, resultado=error.resultado, detalle=error.detalle)
        datos = _datos(respuesta)
        if datos.get("status") == "cancelled":
            return EstadoRemoto(existe=False)
        if (
            datos.get("id") != external_event_id
            or not isinstance(datos.get("etag"), str)
            or not datos["etag"]
        ):
            return EstadoRemoto(
                existe=True,
                resultado=ResultadoCalendario.FALLO_TEMPORAL,
                detalle="Google devolvio un evento incompleto.",
            )
        return EstadoRemoto(
            existe=True,
            etag=datos["etag"],
            inicio=_fecha(datos.get("start")),
            fin=_fecha(datos.get("end")),
            es_nuestro=_es_propio(datos),
        )

    async def renovar_token(
        self,
        credenciales: Credenciales,
        *,
        client_id: str,
        client_secret: str,
        ahora: datetime,
    ) -> RenovacionToken:
        if not client_id or not client_secret:
            return RenovacionToken(
                ResultadoCalendario.FALLO_PERMANENTE,
                detalle="Configure la aplicacion OAuth de Google.",
            )
        respuesta = await self._http(
            "POST",
            URL_TOKEN_GOOGLE,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": credenciales.token_refresco,
                "grant_type": "refresh_token",
            },
        )
        if respuesta is None:
            return RenovacionToken(
                ResultadoCalendario.FALLO_TEMPORAL,
                detalle="No se pudo renovar la conexion con Google.",
            )
        datos = _datos(respuesta)
        if respuesta.status_code != httpx.codes.OK:
            resultado = _fallo(respuesta)
            if datos.get("error") == "invalid_grant":
                resultado = ResultadoCalendario.TOKEN_VENCIDO
            return RenovacionToken(
                resultado,
                detalle="Google rechazo la renovacion; revise la conexion y configuracion.",
            )
        acceso = datos.get("access_token")
        duracion = datos.get("expires_in")
        refresco = datos.get("refresh_token", credenciales.token_refresco)
        if (
            not isinstance(acceso, str)
            or not acceso.strip()
            or not isinstance(refresco, str)
            or not refresco.strip()
            or isinstance(duracion, bool)
            or not isinstance(duracion, int)
            or duracion <= 0
            or not isinstance(datos.get("token_type", "Bearer"), str)
            or datos.get("token_type", "Bearer").lower() != "bearer"
        ):
            return RenovacionToken(
                ResultadoCalendario.FALLO_TEMPORAL,
                detalle="Google devolvio credenciales incompletas.",
            )
        try:
            vence = ahora + timedelta(seconds=duracion)
        except OverflowError:
            return RenovacionToken(
                ResultadoCalendario.FALLO_TEMPORAL,
                detalle="Google devolvio una caducidad invalida.",
            )
        return RenovacionToken(
            ResultadoCalendario.OK,
            acceso,
            refresco,
            vence,
            datos.get("scope") if isinstance(datos.get("scope"), str) else None,
        )
