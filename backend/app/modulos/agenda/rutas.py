"""Rutas de la agenda.

Sin logica de negocio y sin SQL: validan, invocan el servicio, persisten la
auditoria que este devuelve y confirman la transaccion.

Dos capas de autorizacion, y ninguna sustituye a la otra
--------------------------------------------------------
1. `exige_permiso(...)` en la declaracion del endpoint responde «esta persona
   puede ejecutar esta operacion».
2. El repositorio aplica el filtro de ambito en el `WHERE` de cada consulta, y
   responde «sobre estos datos».

Un endpoint con el permiso correcto y sin filtro de ambito tiene un IDOR: el
recepcionista de la sede Norte podria leer y cancelar las citas de la sede
Sur con solo cambiar un identificador en la URL. Por eso una cita fuera de
ambito devuelve **404 y no 403**: un 403 confirmaria que ese identificador
existe, y con eso se enumeran las citas de la clinica entera.

Idempotencia
------------
Crear una cita acepta la cabecera `Idempotency-Key`. Repetir la peticion con
la misma clave devuelve la cita ya creada en lugar de crear otra. Es lo que
hace seguro que el cliente reintente cuando la red corta la respuesta, y lo
que evita que pulsar dos veces «Reservar» produzca dos citas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, status

from app.modulos.agenda.disponibilidad import ResultadoDisponibilidad
from app.modulos.agenda.esquemas import (
    DIAS_MAXIMOS_CONSULTA,
    EstadoFiltro,
    PaginaCitas,
    PeticionCancelacion,
    PeticionReprogramacion,
    PeticionReserva,
    RespuestaCita,
    RespuestaCitaDetalle,
    RespuestaDisponibilidad,
    TurnoDisponible,
)
from app.modulos.agenda.modelos import Cita, EstadoCita, OrigenCita
from app.modulos.agenda.servicios import ResultadoOperacion, SolicitudReserva
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    RepoAgenda,
    ServicioDeAgenda,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import DatosInvalidos, RecursoNoEncontrado
from app.nucleo.idempotencia import validar_clave_cliente

enrutador = APIRouter(prefix="/agenda", tags=["agenda"])

# Permisos declarados una sola vez, para que la ruta y la tabla de
# `docs/security.md` no puedan divergir por un error de copia.
PuedeLeerAgenda = Annotated[Principal, Depends(exige_permiso("agenda.leer"))]
PuedeCrearCita = Annotated[Principal, Depends(exige_permiso("cita.crear"))]
PuedeCancelar = Annotated[Principal, Depends(exige_permiso("cita.cancelar"))]
PuedeReprogramar = Annotated[Principal, Depends(exige_permiso("cita.reprogramar"))]
PuedeCompletar = Annotated[Principal, Depends(exige_permiso("cita.completar"))]
PuedeMarcarInasistencia = Annotated[Principal, Depends(exige_permiso("cita.marcar_inasistencia"))]

ClaveIdempotencia = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description=(
            "Repetir la peticion con la misma clave devuelve la cita ya creada "
            "en lugar de crear otra."
        ),
    ),
]

LIMITE_MAXIMO_PAGINA = 200


def _a_respuesta(cita: Cita) -> RespuestaCita:
    return RespuestaCita(
        id=cita.id,
        paciente_id=cita.paciente_id,
        profesional_id=cita.profesional_id,
        servicio_id=cita.servicio_id,
        sede_id=cita.sede_id,
        consultorio_id=cita.consultorio_id,
        inicio=cita.inicio,
        fin=cita.fin,
        duracion_minutos=cita.duracion_minutos,
        minutos_preparacion=cita.minutos_preparacion,
        estado=EstadoCita(cita.estado),
        origen=OrigenCita(cita.origen),
        expira_en=cita.expira_en,
        confirmada_en=cita.confirmada_en,
        cancelada_en=cita.cancelada_en,
        motivo_cancelacion=cita.motivo_cancelacion,
    )


def _a_detalle(cita: Cita) -> RespuestaCitaDetalle:
    return RespuestaCitaDetalle(
        **_a_respuesta(cita).model_dump(),
        notas_recepcion=cita.notas_recepcion,
    )


def _clave_validada(clave: str | None) -> str | None:
    if clave is None:
        return None
    try:
        return validar_clave_cliente(clave)
    except ValueError as exc:
        raise DatosInvalidos(str(exc)) from exc


async def _persistir(
    resultado: ResultadoOperacion, sesion: Sesion, auditor: Auditor
) -> RespuestaCita:
    """Escribe la auditoria y confirma, en una sola transaccion.

    El cambio de estado de la cita y el registro de que ocurrio se confirman
    juntos. Separarlos permitiria una cita cancelada sin constancia de quien
    la cancelo, que es justo lo que se pregunta ante una reclamacion.
    """
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return _a_respuesta(resultado.cita)


# ===========================================================================
#  Disponibilidad
# ===========================================================================
@enrutador.get(
    "/disponibilidad",
    response_model=RespuestaDisponibilidad,
    summary="Turnos libres de un profesional",
    responses={
        403: {"description": "Sin permiso para consultar la agenda"},
        404: {"description": "Profesional, servicio o sede fuera de alcance"},
        422: {"description": "Rango invalido o instantes sin zona horaria"},
    },
)
async def consultar_disponibilidad(
    principal: PuedeLeerAgenda,
    servicio_agenda: ServicioDeAgenda,
    repo: RepoAgenda,
    profesional_id: Annotated[uuid.UUID, Query()],
    servicio_id: Annotated[uuid.UUID, Query()],
    sede_id: Annotated[uuid.UUID, Query()],
    desde: Annotated[datetime, Query(description="ISO-8601 con desplazamiento.")],
    hasta: Annotated[datetime, Query(description="ISO-8601 con desplazamiento.")],
    consultorio_id: Annotated[uuid.UUID | None, Query()] = None,
    explicar: Annotated[
        bool,
        Query(description="Incluye el recuento de motivos por los que no hay turnos."),
    ] = False,
) -> RespuestaDisponibilidad:
    """Calcula los turnos ofrecibles en una ventana.

    Es una lectura y aun asi exige permiso: la disponibilidad de un
    profesional revela su carga de trabajo y sus ausencias, que no es
    informacion publica dentro de la clinica.
    """
    _validar_ventana(desde, hasta)

    resultado: ResultadoDisponibilidad = await servicio_agenda.consultar_disponibilidad(
        principal=principal,
        profesional_id=profesional_id,
        servicio_id=servicio_id,
        sede_id=sede_id,
        desde=desde,
        hasta=hasta,
        consultorio_id=consultorio_id,
        registrar_descartes=explicar,
    )

    zona = await repo.obtener_zona_horaria(sede_id)
    return RespuestaDisponibilidad(
        profesional_id=profesional_id,
        servicio_id=servicio_id,
        sede_id=sede_id,
        zona_horaria=zona,
        desde=desde,
        hasta=hasta,
        turnos=[
            TurnoDisponible(
                inicio=turno.inicio,
                fin_consulta=turno.fin_consulta,
                fin_bloque=turno.fin,
                duracion_minutos=int((turno.fin_consulta - turno.inicio).total_seconds() // 60),
                minutos_preparacion=int((turno.fin - turno.fin_consulta).total_seconds() // 60),
            )
            for turno in resultado.turnos
        ],
        motivos_sin_turno={
            motivo.value: cantidad for motivo, cantidad in resultado.motivos_de_descarte().items()
        },
    )


def _validar_ventana(desde: datetime, hasta: datetime) -> None:
    """Comprueba el rango antes de tocar la base de datos.

    El servicio lo vuelve a comprobar -- tambien lo llaman el worker y el
    agente de IA, que no pasan por aqui --, pero rechazarlo en el borde evita
    cargar franjas, feriados y ocupaciones de una ventana que se iba a
    rechazar igualmente.
    """
    if desde.tzinfo is None or hasta.tzinfo is None:
        raise DatosInvalidos(
            "Las fechas deben incluir zona horaria (por ejemplo "
            "2026-04-16T09:00:00-05:00). Un instante sin zona es ambiguo."
        )
    if hasta <= desde:
        raise DatosInvalidos("El fin de la ventana debe ser posterior al inicio.")
    if (hasta - desde).days > DIAS_MAXIMOS_CONSULTA:
        raise DatosInvalidos(
            f"La ventana consultada no puede exceder {DIAS_MAXIMOS_CONSULTA} dias."
        )


# ===========================================================================
#  Consulta de citas
# ===========================================================================
@enrutador.get(
    "/citas",
    response_model=PaginaCitas,
    summary="Listar citas dentro del ambito del solicitante",
)
async def listar_citas(
    principal: PuedeLeerAgenda,
    repo: RepoAgenda,
    desde: Annotated[datetime | None, Query()] = None,
    hasta: Annotated[datetime | None, Query()] = None,
    profesional_id: Annotated[uuid.UUID | None, Query()] = None,
    paciente_id: Annotated[uuid.UUID | None, Query()] = None,
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
    estado: Annotated[list[EstadoFiltro] | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO_PAGINA)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaCitas:
    """Lista citas.

    El filtro de ambito lo aplica el repositorio en SQL, no este endpoint: un
    filtro en Python sobre filas ya traidas seria un post-filtro, y basta con
    olvidarlo en una rama para exponer la agenda de otra sede.

    El total se cuenta con **los mismos filtros** que el listado. Con filtros
    distintos, un listado de tres citas mostraria «1 de 340» y la paginacion
    pediria paginas que siempre vuelven vacias.
    """
    estados = list(estado) if estado else None

    elementos = await repo.listar_citas(
        principal=principal,
        desde=desde,
        hasta=hasta,
        profesional_id=profesional_id,
        paciente_id=paciente_id,
        sede_id=sede_id,
        estados=estados,
        limite=limite,
        desplazamiento=desplazamiento,
    )
    total = await repo.contar_citas(
        principal=principal,
        desde=desde,
        hasta=hasta,
        profesional_id=profesional_id,
        paciente_id=paciente_id,
        sede_id=sede_id,
        estados=estados,
    )

    return PaginaCitas(
        elementos=[_a_respuesta(c) for c in elementos],
        total=total,
        limite=limite,
        desplazamiento=desplazamiento,
    )


@enrutador.get(
    "/citas/{cita_id}",
    response_model=RespuestaCitaDetalle,
    summary="Detalle de una cita",
    responses={404: {"description": "No existe, o esta fuera del ambito del solicitante"}},
)
async def obtener_cita(
    principal: PuedeLeerAgenda,
    repo: RepoAgenda,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCitaDetalle:
    """Devuelve una cita.

    Una cita fuera del ambito responde 404, igual que una inexistente. Un 403
    confirmaria que ese identificador corresponde a una cita real y permitiria
    enumerar la agenda de la clinica probando identificadores.
    """
    cita = await repo.obtener_cita(cita_id, principal=principal)
    if cita is None:
        raise RecursoNoEncontrado("La cita solicitada no existe.")
    return _a_detalle(cita)


# ===========================================================================
#  Creacion
# ===========================================================================
@enrutador.post(
    "/citas",
    response_model=RespuestaCita,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una cita confirmada",
    responses={
        409: {"description": "El turno ya no esta disponible"},
        422: {"description": "Datos invalidos o instante sin zona horaria"},
    },
)
async def crear_cita(
    peticion: Request,
    principal: PuedeCrearCita,
    datos: PeticionReserva,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    clave_idempotencia: ClaveIdempotencia = None,
) -> RespuestaCita:
    """Crea una cita ya confirmada.

    Es el camino del panel: recepcion habla con el paciente por telefono y
    confirma en el acto, sin bloqueo temporal intermedio.

    Si el turno ya esta ocupado, la respuesta es 409. Quien lo decide es la
    restriccion de exclusion de PostgreSQL, no una comprobacion previa: entre
    comprobar y escribir cabe otra reserva, y esa ventana es exactamente donde
    aparece la doble reserva (ADR-0009).
    """
    resultado = await servicio_agenda.crear_cita_confirmada(
        _solicitud(datos, clave_idempotencia, peticion),
        principal=principal,
    )
    return await _persistir(resultado, sesion, auditor)


@enrutador.post(
    "/citas/bloqueos",
    response_model=RespuestaCita,
    status_code=status.HTTP_201_CREATED,
    summary="Bloquear un turno temporalmente",
    responses={409: {"description": "El turno ya no esta disponible"}},
)
async def bloquear_turno(
    peticion: Request,
    principal: PuedeCrearCita,
    datos: PeticionReserva,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    clave_idempotencia: ClaveIdempotencia = None,
) -> RespuestaCita:
    """Reserva un turno en estado `HELD`, con caducidad.

    Existe por el flujo de WhatsApp: entre que el paciente elige una hora y
    confirma pueden pasar minutos, y sin bloqueo otro paciente podria tomar
    el mismo turno en ese intervalo; el primero recibiria un rechazo despues
    de creer que ya habia reservado.

    La caducidad es obligatoria. Un bloqueo sin plazo retendria el turno para
    siempre si el paciente abandona la conversacion a medias.
    """
    resultado = await servicio_agenda.bloquear_turno(
        _solicitud(datos, clave_idempotencia, peticion),
        principal=principal,
    )
    return await _persistir(resultado, sesion, auditor)


def _solicitud(datos: PeticionReserva, clave: str | None, peticion: Request) -> SolicitudReserva:
    """Traduce el cuerpo HTTP a la solicitud del servicio.

    El origen se fija a `PANEL` y **no** se acepta del cliente. Si viniera en
    el cuerpo, cualquiera con permiso para crear citas podria marcarlas como
    procedentes de WhatsApp y falsear las metricas de canal, que es lo que
    despues decide donde invierte la clinica.
    """
    del peticion  # reservado para el origen por canal, cuando exista
    return SolicitudReserva(
        paciente_id=datos.paciente_id,
        profesional_id=datos.profesional_id,
        servicio_id=datos.servicio_id,
        sede_id=datos.sede_id,
        inicio=datos.inicio,
        consultorio_id=datos.consultorio_id,
        origen=OrigenCita.PANEL,
        clave_idempotencia=_clave_validada(clave),
        notas_recepcion=datos.notas_recepcion,
    )


# ===========================================================================
#  Transiciones de estado
# ===========================================================================
@enrutador.post(
    "/citas/{cita_id}/confirmacion",
    response_model=RespuestaCita,
    summary="Confirmar una cita bloqueada o pendiente",
    responses={
        404: {"description": "No existe, o esta fuera del ambito del solicitante"},
        409: {"description": "Transicion invalida, o el bloqueo temporal ya vencio"},
    },
)
async def confirmar_cita(
    principal: PuedeCrearCita,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    """Pasa la cita a `CONFIRMED`.

    Un bloqueo temporal vencido no se confirma: se rechaza. Confirmarlo seria
    peor que rechazarlo, porque ese turno pudo ofrecerse ya a otra persona y
    quedarian dos pacientes citados a la misma hora por un camino que elude
    la restriccion de exclusion.
    """
    resultado = await servicio_agenda.confirmar_cita(cita_id, principal=principal)
    return await _persistir(resultado, sesion, auditor)


@enrutador.post(
    "/citas/{cita_id}/cancelacion",
    response_model=RespuestaCita,
    summary="Cancelar una cita",
    responses={
        404: {"description": "No existe, o esta fuera del ambito del solicitante"},
        409: {"description": "La cita ya esta cerrada"},
        422: {"description": "Falta el motivo, o no se respeta la antelacion minima"},
    },
)
async def cancelar_cita(
    principal: PuedeCancelar,
    datos: PeticionCancelacion,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    """Cancela la cita.

    El motivo es obligatorio, y lo exige tambien la base de datos. Sin el,
    ante una reclamacion no se puede explicar por que un paciente no fue
    atendido, que es exactamente la pregunta que se hace.
    """
    resultado = await servicio_agenda.cancelar_cita(
        cita_id,
        principal=principal,
        motivo=datos.motivo,
        horas_antelacion_minima=datos.horas_antelacion_minima,
    )
    return await _persistir(resultado, sesion, auditor)


@enrutador.post(
    "/citas/{cita_id}/reprogramacion",
    response_model=RespuestaCita,
    summary="Mover una cita a otro horario",
    responses={
        404: {"description": "No existe, o esta fuera del ambito del solicitante"},
        409: {"description": "El nuevo turno ya esta ocupado, o la cita esta cerrada"},
    },
)
async def reprogramar_cita(
    principal: PuedeReprogramar,
    datos: PeticionReprogramacion,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    cita_id: Annotated[uuid.UUID, Path()],
    clave_idempotencia: ClaveIdempotencia = None,
) -> RespuestaCita:
    """Mueve la cita, conservando su identificador.

    Se modifica la cita existente en lugar de crear una nueva y cancelar la
    anterior: un solo identificador simplifica el seguimiento para el
    paciente, para el calendario externo y para los recordatorios ya
    programados. El horario anterior queda en `cita_historial`, que es
    append-only, asi que la trazabilidad no se pierde.
    """
    resultado = await servicio_agenda.reprogramar_cita(
        cita_id,
        principal=principal,
        nuevo_inicio=datos.nuevo_inicio,
        motivo=datos.motivo,
        nuevo_profesional_id=datos.nuevo_profesional_id,
        nuevo_consultorio_id=datos.nuevo_consultorio_id,
        clave_idempotencia=clave_idempotencia,
    )
    return await _persistir(resultado, sesion, auditor)


@enrutador.post(
    "/citas/{cita_id}/completado",
    response_model=RespuestaCita,
    summary="Marcar la cita como atendida",
    responses={404: {"description": "No existe, o esta fuera del ambito"}},
)
async def completar_cita(
    principal: PuedeCompletar,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    resultado = await servicio_agenda.completar_cita(cita_id, principal=principal)
    return await _persistir(resultado, sesion, auditor)


@enrutador.post(
    "/citas/{cita_id}/inasistencia",
    response_model=RespuestaCita,
    summary="Marcar que el paciente no se presento",
    responses={404: {"description": "No existe, o esta fuera del ambito"}},
)
async def marcar_inasistencia(
    principal: PuedeMarcarInasistencia,
    servicio_agenda: ServicioDeAgenda,
    sesion: Sesion,
    auditor: Auditor,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    """Registra la inasistencia como estado propio, no como cancelacion.

    Son hechos distintos: una inasistencia cuenta para la prediccion de
    ausentismo y para las metricas de ocupacion perdida, y confundirla con una
    cancelacion falsearia ambas.
    """
    resultado = await servicio_agenda.marcar_inasistencia(cita_id, principal=principal)
    return await _persistir(resultado, sesion, auditor)


__all__ = ["enrutador"]
