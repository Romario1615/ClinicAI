"""Rutas del calendario externo.

Quien puede conectar un calendario, y sobre quien
-------------------------------------------------
Solo el profesional, y **solo el suyo**. El permiso
`profesional.conectar_calendario` lo tiene unicamente el rol profesional, y
todas las rutas de aqui derivan el profesional del **principal**, nunca de un
parametro de la peticion.

Esa decision es lo que cierra el agujero obvio: si el identificador del
profesional viniera en el cuerpo, un profesional podria conectar su propio
calendario de Google a la agenda de un companero y quedarse con una copia
permanente de sus horarios de trabajo.

El callback de OAuth
--------------------
`GET /calendario/oauth/callback` lo llama el navegador del profesional
redirigido por Google, sin cabecera de autorizacion. Lo que lo autoriza es el
`state` firmado: lleva dentro el profesional, se verifica con HMAC en tiempo
constante, caduca en 15 minutos y **se consume** (un solo uso, registrado en
`clave_idempotencia`).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modulos.agenda.modelos import ClaveIdempotencia
from app.modulos.calendario import oauth
from app.modulos.calendario.adaptadores import RegistroCalendarios
from app.modulos.calendario.configuracion import parametros_google
from app.modulos.calendario.esquemas import (
    PaginaConexiones,
    PaginaEventos,
    RespuestaConexion,
    RespuestaEventoCalendario,
    RespuestaInicioOauth,
    RespuestaSincronizacion,
    SolicitudDesconexion,
    SolicitudInicioOauth,
)
from app.modulos.calendario.servicios import ServicioCalendario
from app.modulos.profesionales.modelos import CalendarioConexion, CalendarioEvento, Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal, principal_sistema
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import (
    FirmaInvalida,
    PermisoDenegado,
    ProveedorExternoNoDisponible,
    RecursoNoEncontrado,
)
from app.nucleo.idempotencia import AlcanceIdempotencia
from app.nucleo.registro import obtener_logger
from app.nucleo.seguridad import CifradorDatos

logger = obtener_logger(__name__)

enrutador = APIRouter(prefix="/calendario", tags=["calendario"])

PuedeConectar = Annotated[Principal, Depends(exige_permiso("profesional.conectar_calendario"))]

IdConexion = Annotated[uuid.UUID, Path(description="Identificador de la conexion.")]


def _profesional_del_principal(principal: Principal) -> uuid.UUID:
    """Profesional al que pertenece el principal, o error.

    Un usuario con el permiso pero sin ficha de profesional no tiene
    calendario que conectar. Se rechaza de forma explicita en lugar de
    devolver una lista vacia: el mensaje dice que falta la ficha, que es lo
    que hay que corregir.
    """
    if principal.profesional_id is None:
        raise PermisoDenegado(
            "Esta cuenta no esta asociada a una ficha de profesional, asi que no "
            "tiene calendario propio que conectar."
        )
    return principal.profesional_id


def _a_respuesta(conexion: CalendarioConexion) -> RespuestaConexion:
    return RespuestaConexion(
        id=conexion.id,
        proveedor=conexion.proveedor,
        calendar_id=conexion.calendar_id,
        estado_sincronizacion=conexion.estado_sincronizacion,
        ultima_sincronizacion_en=conexion.ultima_sincronizacion_en,
        expira_en=conexion.expira_en,
        alcances=conexion.alcances,
        ultimo_error=conexion.ultimo_error,
    )


# ---------------------------------------------------------------------------
#  Conexiones
# ---------------------------------------------------------------------------
@enrutador.get(
    "/conexiones",
    response_model=PaginaConexiones,
    summary="Conexiones de calendario propias",
    responses={403: {"description": "Sin permiso, o cuenta sin ficha de profesional"}},
)
async def listar_conexiones(principal: PuedeConectar, sesion: Sesion) -> PaginaConexiones:
    """Solo las del profesional que consulta.

    El filtro es por `principal.profesional_id`, no por un parametro: no hay
    forma de pedir las de otro.
    """
    profesional_id = _profesional_del_principal(principal)
    filas = (
        (
            await sesion.execute(
                select(CalendarioConexion)
                .where(CalendarioConexion.profesional_id == profesional_id)
                .order_by(CalendarioConexion.creado_en)
            )
        )
        .scalars()
        .all()
    )
    return PaginaConexiones(elementos=[_a_respuesta(fila) for fila in filas], total=len(filas))


@enrutador.post(
    "/oauth/inicio",
    response_model=RespuestaInicioOauth,
    summary="Iniciar la autorizacion del calendario",
    responses={
        403: {"description": "Sin permiso, o cuenta sin ficha de profesional"},
        503: {"description": "Faltan credenciales de Google (modo sandbox)"},
    },
)
async def iniciar_oauth(
    principal: PuedeConectar,
    configuracion: ConfiguracionActual,
    reloj: RelojActual,
    sesion: Sesion,
    peticion: SolicitudInicioOauth | None = None,
) -> RespuestaInicioOauth:
    """Devuelve la URL de consentimiento con un `state` firmado de un solo uso."""
    profesional_id = _profesional_del_principal(principal)
    solicitud = peticion or SolicitudInicioOauth()
    ahora = reloj.ahora()
    if configuracion.modo_calendario == "sandbox":
        raise ProveedorExternoNoDisponible(
            "Google Calendar sigue en modo de prueba. Pida al administrador configurar Integraciones y habilitar la conexion externa."
        )
    if principal.clinica_id is None:
        raise PermisoDenegado("Esta cuenta no tiene una clinica asignada.")
    parametros = await parametros_google(
        sesion,
        principal.clinica_id,
        configuracion,
        CifradorDatos(configuracion.clave_cifrado_datos.get_secret_value()),
    )
    estado = oauth.nuevo_estado(profesional_id, ahora=ahora, calendar_id=solicitud.calendar_id)
    firmado = oauth.firmar_estado(estado, configuracion.clave_secreta.get_secret_value())
    url = oauth.url_autorizacion(
        client_id=parametros.client_id,
        redirect_uri=parametros.redirect_uri,
        scopes=parametros.scopes,
        estado_firmado=firmado,
    )
    logger.info(
        "calendario.oauth.iniciado",
        profesional_id=str(profesional_id),
        calendar_id=solicitud.calendar_id,
    )
    return RespuestaInicioOauth(url_autorizacion=url, expira_en=ahora + oauth.VIGENCIA_ESTADO)


@enrutador.get(
    "/oauth/callback",
    response_model=RespuestaConexion,
    summary="Retorno de la autorizacion de Google",
    responses={
        403: {"description": "Estado invalido, caducado o ya usado"},
        503: {"description": "El proveedor de OAuth no respondio"},
    },
)
async def retorno_oauth(
    solicitud: Request,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    codigo: Annotated[str, Query(alias="code", min_length=1, max_length=2048)],
    estado: Annotated[str, Query(alias="state", min_length=1, max_length=2048)],
) -> RespuestaConexion | Response:
    """Consume el `state`, canjea el codigo y guarda los tokens cifrados.

    No lleva autenticacion de sesion: lo llama el navegador redirigido por
    Google. Lo que autoriza es el `state` firmado.

    El orden importa: **primero** se consume el `state` y **despues** se canjea
    el codigo. Al contrario, un `state` reutilizado gastaria una llamada al
    proveedor antes de rechazarse, y dos pestanas abiertas del mismo flujo
    crearian dos conexiones.
    """
    ahora = reloj.ahora()
    verificado = oauth.verificar_estado(
        estado, configuracion.clave_secreta.get_secret_value(), ahora=ahora
    )
    await _consumir_estado(sesion, verificado.identificador, ahora=ahora)
    profesional = await sesion.get(Profesional, verificado.profesional_id)
    if profesional is None or not profesional.activo:
        raise FirmaInvalida("La autorizacion de calendario ya no esta vigente.")
    parametros = await parametros_google(
        sesion, profesional.clinica_id, configuracion, _cifrador(solicitud)
    )
    if configuracion.modo_calendario == "sandbox":
        raise ProveedorExternoNoDisponible("La conexion real requiere MODO_CALENDARIO=google.")
    tokens = await oauth.intercambiar_codigo(
        codigo=codigo,
        client_id=parametros.client_id,
        client_secret=parametros.client_secret,
        redirect_uri=parametros.redirect_uri,
        ahora=ahora,
    )

    servicio = ServicioCalendario(
        sesion,
        reloj,
        _cifrador(solicitud),
        _proveedores(solicitud),
        url_sistema=configuracion.api_url,
        configuracion=configuracion,
    )
    conexion = await servicio.conectar(
        profesional_id=verificado.profesional_id,
        proveedor="google",
        calendar_id=verificado.calendar_id,
        token_acceso=tokens.token_acceso,
        token_refresco=tokens.token_refresco,
        expira_en=tokens.expira_en,
        alcances=tokens.alcances,
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CALENDARIO_CONECTADO,
                principal=principal_sistema(profesional.clinica_id),
                ahora=ahora,
                entidad_tipo="calendario_conexion",
                entidad_id=conexion.id,
                profesional_id=str(profesional.id),
            )
        ]
    )
    await sesion.commit()
    if "text/html" in solicitud.headers.get("accept", ""):
        return HTMLResponse(
            '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Calendario conectado · ClinicAI</title></head><body><main><h1>Google Calendar conectado</h1><p>Vuelve a la pestaña de ClinicAI y pulsa Actualizar estado en Mi Google Calendar.</p><p>Puedes cerrar esta pestaña. La sesión de ClinicAI permanece en la ventana original.</p></main></body></html>',
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
    return _a_respuesta(conexion)


@enrutador.post(
    "/conexiones/{conexion_id}/desconexion",
    response_model=RespuestaConexion,
    summary="Desconectar un calendario",
    responses={404: {"description": "La conexion no existe o es de otro profesional"}},
)
async def desconectar(
    principal: PuedeConectar,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    auditor: Auditor,
    solicitud_http: Request,
    conexion_id: IdConexion,
    peticion: SolicitudDesconexion,
) -> RespuestaConexion:
    """Borra los tokens. No toca los eventos ya creados en el calendario.

    Es el calendario del profesional: borrar de golpe meses de su agenda al
    desconectar una integracion es una sorpresa desagradable y no reversible.
    """
    await _exigir_propia(sesion, conexion_id, principal)

    servicio = ServicioCalendario(
        sesion,
        reloj,
        _cifrador(solicitud_http),
        _proveedores(solicitud_http),
        url_sistema=configuracion.api_url,
        configuracion=configuracion,
    )
    conexion = await servicio.desconectar(conexion_id=conexion_id, motivo=peticion.motivo)

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CALENDARIO_DESCONECTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="calendario_conexion",
                entidad_id=conexion_id,
                motivo=peticion.motivo,
            )
        ]
    )
    await sesion.commit()
    return _a_respuesta(conexion)


@enrutador.post(
    "/conexiones/{conexion_id}/sincronizacion",
    response_model=RespuestaSincronizacion,
    status_code=status.HTTP_200_OK,
    summary="Forzar una sincronizacion",
    responses={404: {"description": "La conexion no existe o es de otro profesional"}},
)
async def sincronizar(
    principal: PuedeConectar,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    solicitud_http: Request,
    conexion_id: IdConexion,
    auditor: Auditor,
) -> RespuestaSincronizacion:
    """Publica ahora los eventos pendientes.

    Existe porque el barrido periodico puede tardar, y un profesional que
    acaba de conectar su calendario espera verlo poblado, no enterarse en el
    proximo ciclo.
    """
    await _exigir_propia(sesion, conexion_id, principal)

    servicio = ServicioCalendario(
        sesion,
        reloj,
        _cifrador(solicitud_http),
        _proveedores(solicitud_http),
        url_sistema=configuracion.api_url,
        configuracion=configuracion,
    )
    await servicio.detectar_citas_sin_reflejo(conexion_id=conexion_id)
    resumen = await servicio.sincronizar_pendientes(
        conexion_id=conexion_id, reintentar_errores=True
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CALENDARIO_SINCRONIZADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="calendario_conexion",
                entidad_id=conexion_id,
            )
        ]
    )
    await sesion.commit()
    return RespuestaSincronizacion(
        creados=resumen.creados,
        actualizados=resumen.actualizados,
        eliminados=resumen.eliminados,
        recreados=resumen.recreados,
        conflictos=resumen.conflictos,
        reintentables=resumen.reintentables,
        errores=resumen.errores,
        sin_conexion=resumen.sin_conexion,
        token_vencido=resumen.token_vencido,
    )


@enrutador.get(
    "/conexiones/{conexion_id}/eventos",
    response_model=PaginaEventos,
    summary="Estado de sincronizacion de los eventos",
    responses={404: {"description": "La conexion no existe o es de otro profesional"}},
)
async def listar_eventos(
    principal: PuedeConectar,
    sesion: Sesion,
    conexion_id: IdConexion,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PaginaEventos:
    """Diagnostico de la sincronizacion.

    Devuelve estados, no contenido de citas: ni paciente, ni servicio, ni
    motivo (RF-I09).
    """
    await _exigir_propia(sesion, conexion_id, principal)

    total = await sesion.scalar(
        select(func.count())
        .select_from(CalendarioEvento)
        .where(CalendarioEvento.calendario_conexion_id == conexion_id)
    )
    filas = (
        (
            await sesion.execute(
                select(CalendarioEvento)
                .where(CalendarioEvento.calendario_conexion_id == conexion_id)
                .order_by(CalendarioEvento.creado_en.desc())
                .limit(limite)
            )
        )
        .scalars()
        .all()
    )
    return PaginaEventos(
        elementos=[
            RespuestaEventoCalendario(
                id=fila.id,
                cita_id=fila.cita_id,
                estado=fila.estado,
                external_event_id=fila.external_event_id,
                sincronizado_en=fila.sincronizado_en,
                intentos=fila.intentos,
                ultimo_error=fila.ultimo_error,
            )
            for fila in filas
        ],
        total=total or 0,
    )


# ---------------------------------------------------------------------------
#  Auxiliares
# ---------------------------------------------------------------------------
async def _exigir_propia(
    sesion: Sesion, conexion_id: uuid.UUID, principal: Principal
) -> CalendarioConexion:
    """Comprueba que la conexion sea del profesional del principal.

    Devuelve **404** y no 403 cuando es de otro: un 403 confirmaria que la
    conexion existe, y eso permite enumerar los calendarios de los companeros
    probando identificadores.
    """
    profesional_id = _profesional_del_principal(principal)
    conexion = await sesion.get(CalendarioConexion, conexion_id)
    if conexion is None or conexion.profesional_id != profesional_id:
        raise RecursoNoEncontrado("La conexion de calendario no existe.")
    return conexion


async def _consumir_estado(sesion: Sesion, identificador: str, *, ahora: datetime) -> None:
    """Registra el `state` como usado. Un segundo intento falla.

    La garantia es la restriccion unica `(alcance, clave)` de
    `clave_idempotencia`, no una comprobacion previa en Python: dos pestanas
    del mismo flujo pueden llegar a la vez, y un `SELECT` antes del `INSERT`
    dejaria pasar las dos.
    """
    sesion.add(
        ClaveIdempotencia(
            clave=hashlib.sha256(identificador.encode("utf-8")).hexdigest(),
            alcance=AlcanceIdempotencia.CALENDARIO_OAUTH.value,
            hash_peticion=hashlib.sha256(identificador.encode("utf-8")).hexdigest(),
            estado="COMPLETADA",
            completado_en=ahora,
            expira_en=ahora + timedelta(days=1),
        )
    )
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        logger.warning("calendario.oauth.estado_reutilizado")
        raise FirmaInvalida("El estado de OAuth ya se uso.") from exc


def _cifrador(peticion: Request) -> CifradorDatos:
    cifrador: CifradorDatos = peticion.app.state.cifrador
    return cifrador


def _proveedores(peticion: Request) -> RegistroCalendarios:
    """Registro de adaptadores de calendario, guardado en `app.state`.

    Vive en `app.state` y no como global del modulo para que la suite pueda
    levantar varias aplicaciones con adaptadores distintos en el mismo
    proceso.
    """
    registro: RegistroCalendarios = peticion.app.state.proveedores_calendario
    return registro


__all__ = ["enrutador"]
