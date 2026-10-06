"""Recorrido del paciente dentro de la clínica, derivación interna y prolongación.

Qué resuelve
------------
* **Recorrido.** Desde que el paciente llega hasta que se va: a qué hora
  llegó, en qué consultorio estuvo, quién le atendió, si le derivaron a otra
  área, si la atención se alargó y cuándo salió. Se construye sobre
  `cita_historial`, que ya es append-only: cada hecho es una fila nueva y
  nada se corrige ni se borra.
* **Derivación interna.** El profesional manda al paciente, que ya está en la
  clínica, a otra área o especialista. Se crea una cita confirmada con la
  llegada ya registrada y la relación asistencial con el profesional de
  destino, para que pueda abrir la historia.
* **Prolongación.** El profesional pide más tiempo. Si no pisa a nadie se
  aplica; si pisa al siguiente paciente, queda pendiente y recepción decide:
  pasarlo a otro profesional libre, moverlo a más tarde, o derivar al
  paciente en atención. Nunca se resuelve sola.

Lo que **no** guarda
--------------------
El motivo clínico de una derivación no se pide aquí: el recorrido lo ve
recepción. El motivo va a la historia como nota de interconsulta, que tiene
sus propios permisos y su relación asistencial.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita, CitaHistorial, EstadoCita
from app.modulos.agenda.recorrido_repositorio import RepositorioRecorrido
from app.modulos.agenda.servicios import ResultadoOperacion, ServicioAgenda, SolicitudReserva
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.pacientes.modelos import RelacionAsistencial
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import (
    ConflictoEstado,
    ConsentimientoRequerido,
    PermisoDenegado,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
)
from app.nucleo.errores_bd import traducir_o_propagar
from app.nucleo.idempotencia import calcular_clave_deduplicacion
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj

logger = obtener_logger(__name__)

MINUTOS_MINIMOS = 5
MINUTOS_MAXIMOS = 120
MOTIVO_MINIMO = 3
MOTIVO_MOVIDA = "Movida por la prolongación de otra atención"


class Evento(StrEnum):
    """Tipos de paso, en el orden natural en que ocurren."""

    CREADA = "CREADA"
    REPROGRAMADA = "REPROGRAMADA"
    CAMBIO = "CAMBIO"
    LLEGADA = "LLEGADA"
    INGRESO_CONSULTORIO = "INGRESO_CONSULTORIO"
    ATENCION_INICIADA = "ATENCION_INICIADA"
    PROLONGACION_SOLICITADA = "PROLONGACION_SOLICITADA"
    PROLONGACION_APLICADA = "PROLONGACION_APLICADA"
    PROLONGACION_RECHAZADA = "PROLONGACION_RECHAZADA"
    DERIVACION_INTERNA = "DERIVACION_INTERNA"
    DERIVADA_DESDE = "DERIVADA_DESDE"
    COMPLETADA = "COMPLETADA"
    INASISTENCIA = "INASISTENCIA"
    CANCELADA = "CANCELADA"
    SALIDA = "SALIDA"


TITULOS: dict[Evento, str] = {
    Evento.CREADA: "Cita agendada",
    Evento.LLEGADA: "Llegó a la clínica",
    Evento.ATENCION_INICIADA: "Empezó la atención",
    Evento.INGRESO_CONSULTORIO: "Pasó a consultorio",
    Evento.DERIVACION_INTERNA: "Derivado a otra área",
    Evento.DERIVADA_DESDE: "Recibido por derivación",
    Evento.PROLONGACION_SOLICITADA: "Se pidió más tiempo",
    Evento.PROLONGACION_APLICADA: "Atención prolongada",
    Evento.PROLONGACION_RECHAZADA: "Prolongación no aplicada",
    Evento.REPROGRAMADA: "Cita movida",
    Evento.CANCELADA: "Cita cancelada",
    Evento.COMPLETADA: "Atención completada",
    Evento.INASISTENCIA: "No se presentó",
    Evento.SALIDA: "Salió de la clínica",
    Evento.CAMBIO: "Cambio en la cita",
}


def evento_de(fila: CitaHistorial) -> Evento:
    """Tipo de evento de una fila del historial.

    Las filas nuevas lo llevan en `metadatos.evento`; las de cambio de estado
    se deducen del estado, que es como siempre se han escrito.
    """
    marcado = (fila.metadatos or {}).get("evento")
    if isinstance(marcado, str) and marcado in Evento.__members__:
        return Evento(marcado)
    if fila.estado_anterior is None:
        return Evento.CREADA
    return {
        EstadoCita.COMPLETED.value: Evento.COMPLETADA,
        EstadoCita.NO_SHOW.value: Evento.INASISTENCIA,
        EstadoCita.CANCELLED.value: Evento.CANCELADA,
        EstadoCita.RESCHEDULED.value: Evento.REPROGRAMADA,
    }.get(fila.estado_nuevo, Evento.CAMBIO)


@dataclass(frozen=True, slots=True)
class PasoRecorrido:
    ocurrido_en: datetime
    evento: Evento
    titulo: str
    detalle: str | None
    cita_id: uuid.UUID
    servicio: str | None
    profesional: str | None
    consultorio: str | None
    sede: str | None
    registrado_por: str | None


@dataclass(frozen=True, slots=True)
class Alternativa:
    """Una forma de liberar el turno de una cita que choca."""

    profesional_id: uuid.UUID
    profesional: str
    inicio: datetime
    mismo_profesional: bool


@dataclass(frozen=True, slots=True)
class Conflicto:
    cita: Cita
    paciente: str
    alternativas: tuple[Alternativa, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoProlongacion:
    cita: Cita
    aplicada: bool
    minutos: int
    conflictos: tuple[Conflicto, ...]
    auditoria: tuple[EntradaAuditoria, ...] = ()


@dataclass(frozen=True, slots=True)
class SolicitudPendiente:
    cita: Cita
    paciente: str
    profesional: str
    minutos: int
    solicitada_en: datetime
    conflictos: tuple[Conflicto, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OpcionDerivacion:
    profesional_id: uuid.UUID
    profesional: str
    servicio_id: uuid.UUID
    servicio: str
    especialidad: str
    libre_ahora: bool
    proximo_turno: datetime | None


@dataclass(frozen=True, slots=True)
class Resolucion:
    cita_id: uuid.UUID
    inicio: datetime
    profesional_id: uuid.UUID | None = None


class ServicioRecorrido:
    def __init__(
        self,
        sesion: AsyncSession,
        repositorio: RepositorioRecorrido,
        agenda: ServicioAgenda,
        reloj: Reloj,
    ) -> None:
        self._sesion = sesion
        self._repo = repositorio
        self._agenda = agenda
        self._reloj = reloj

    # ==================================================================
    #  Recorrido
    # ==================================================================
    async def recorrido(
        self, paciente_id: uuid.UUID, *, principal: Principal, dias: int = 365
    ) -> tuple[list[PasoRecorrido], EntradaAuditoria]:
        if not principal.tiene_permiso("agenda.leer") or principal.es_agente:
            raise PermisoDenegado("No tiene permiso para ver el recorrido del paciente.")
        ahora = self._reloj.ahora()
        filas = await self._repo.historial_de_paciente(
            paciente_id, principal=principal, desde=ahora - timedelta(days=max(1, min(dias, 3650)))
        )
        profesionales: set[uuid.UUID] = set()
        consultorios: set[uuid.UUID] = set()
        sedes: set[uuid.UUID] = set()
        servicios: set[uuid.UUID] = set()
        usuarios: set[uuid.UUID] = set()
        for fila, cita in filas:
            profesionales.add(fila.profesional_nuevo_id or cita.profesional_id)
            destino = _uuid((fila.metadatos or {}).get("profesional_destino_id"))
            if destino:
                profesionales.add(destino)
            consultorio = _uuid((fila.metadatos or {}).get("consultorio_id")) or cita.consultorio_id
            if consultorio:
                consultorios.add(consultorio)
            sedes.add(cita.sede_id)
            servicios.add(cita.servicio_id)
            if fila.actor_id and fila.actor_tipo == "USUARIO":
                usuarios.add(fila.actor_id)
        nombres = await self._repo.nombres(
            profesionales=profesionales,
            consultorios=consultorios,
            sedes=sedes,
            servicios=servicios,
            usuarios=usuarios,
        )
        # Varias filas pueden compartir instante (misma transacción) o venir de
        # relojes distintos (base de datos y aplicación): dentro del mismo
        # minuto manda el orden natural de los hechos.
        orden = {evento: posicion for posicion, evento in enumerate(Evento)}
        filas.sort(
            key=lambda par: (
                par[0].ocurrido_en.replace(second=0, microsecond=0),
                orden[evento_de(par[0])],
                par[0].ocurrido_en,
            )
        )
        pasos = [self._paso(fila, cita, nombres) for fila, cita in filas]
        entrada = construir_entrada(
            accion=AccionAuditada.RECORRIDO_CONSULTADO,
            principal=principal,
            ahora=ahora,
            entidad_tipo="paciente",
            entidad_id=paciente_id,
            paciente_id=paciente_id,
            pasos_devueltos=len(pasos),
        )
        return pasos, entrada

    @staticmethod
    def _paso(fila: CitaHistorial, cita: Cita, nombres: dict[uuid.UUID, str]) -> PasoRecorrido:
        evento = evento_de(fila)
        metadatos = fila.metadatos or {}
        consultorio = _uuid(metadatos.get("consultorio_id")) or cita.consultorio_id
        detalle: str | None = None
        if evento is Evento.DERIVACION_INTERNA:
            destino = _uuid(metadatos.get("profesional_destino_id"))
            partes = [
                str(metadatos.get("especialidad") or ""),
                nombres.get(destino, "") if destino else "",
            ]
            detalle = " · ".join(p for p in partes if p) or None
        elif evento in (Evento.PROLONGACION_SOLICITADA, Evento.PROLONGACION_APLICADA):
            detalle = f"+{metadatos.get('minutos')} min"
        elif evento in (Evento.REPROGRAMADA, Evento.CANCELADA, Evento.PROLONGACION_RECHAZADA):
            detalle = fila.motivo
        if fila.actor_tipo == "USUARIO" and fila.actor_id:
            registrado_por = nombres.get(fila.actor_id)
        else:
            registrado_por = {
                "AGENTE": "Asistente",
                "PACIENTE": "Paciente",
                "SISTEMA": "Sistema",
            }.get(fila.actor_tipo)
        return PasoRecorrido(
            ocurrido_en=fila.ocurrido_en,
            evento=evento,
            titulo=TITULOS[evento],
            detalle=detalle,
            cita_id=cita.id,
            servicio=nombres.get(cita.servicio_id),
            profesional=nombres.get(fila.profesional_nuevo_id or cita.profesional_id),
            consultorio=nombres.get(consultorio) if consultorio else None,
            sede=nombres.get(cita.sede_id),
            registrado_por=registrado_por,
        )

    # ==================================================================
    #  Movimientos dentro de la clínica
    # ==================================================================
    async def ingreso_consultorio(
        self, cita_id: uuid.UUID, consultorio_id: uuid.UUID, *, principal: Principal
    ) -> ResultadoOperacion:
        self._exigir(principal, "cita.registrar_llegada", "registrar movimientos del paciente")
        cita = await self._cita_en_clinica(cita_id, principal)
        consultorio = await self._repo.obtener_consultorio(consultorio_id)
        if consultorio is None or consultorio.sede_id != cita.sede_id or consultorio.esta_anulado:
            raise RecursoNoEncontrado("El consultorio solicitado no existe en esta sede.")
        if not consultorio.activo:
            raise ReglaNegocioViolada("El consultorio seleccionado no está disponible.")
        anterior = cita.consultorio_id
        cita.consultorio_id = consultorio_id
        cita.actualizado_por = principal.actor_id
        await self._flush()
        self._evento(
            cita,
            principal,
            Evento.INGRESO_CONSULTORIO,
            "Ingreso a consultorio",
            consultorio_id=str(consultorio_id),
            consultorio_anterior_id=str(anterior) if anterior else None,
        )
        return ResultadoOperacion(
            cita, (self._auditoria(cita, principal, AccionAuditada.CITA_CONSULTORIO_ASIGNADO),)
        )

    async def salida(self, cita_id: uuid.UUID, *, principal: Principal) -> ResultadoOperacion:
        self._exigir(principal, "cita.registrar_llegada", "registrar la salida")
        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        if cita.llegada_en is None:
            raise ConflictoEstado("No se registró la llegada de este paciente.")
        if any(evento_de(f) is Evento.SALIDA for f in await self._repo.eventos_de_cita(cita.id)):
            raise ConflictoEstado("La salida de este paciente ya está registrada.")
        self._evento(cita, principal, Evento.SALIDA, "Salida de la clínica")
        return ResultadoOperacion(
            cita, (self._auditoria(cita, principal, AccionAuditada.CITA_SALIDA_REGISTRADA),)
        )

    # ==================================================================
    #  Derivación interna
    # ==================================================================
    async def opciones_derivacion(
        self, cita_id: uuid.UUID, *, principal: Principal
    ) -> list[OpcionDerivacion]:
        self._exigir_derivacion(principal)
        cita = await self._repo.obtener_cita(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        ahora = self._reloj.ahora()
        opciones: list[OpcionDerivacion] = []
        for servicio, especialidad in await self._repo.servicios_de_sede(
            cita.sede_id, cita.clinica_id
        ):
            for profesional in await self._repo.profesionales_del_servicio(
                servicio.id, cita.sede_id, cita.clinica_id
            ):
                if profesional.id == cita.profesional_id:
                    continue
                proximo = await self._proximo_turno(
                    principal,
                    profesional.id,
                    servicio.id,
                    cita.sede_id,
                    ahora,
                    ahora + timedelta(hours=12),
                )
                opciones.append(
                    OpcionDerivacion(
                        profesional_id=profesional.id,
                        profesional=f"{profesional.nombre} {profesional.apellido}".strip(),
                        servicio_id=servicio.id,
                        servicio=servicio.nombre,
                        especialidad=especialidad,
                        libre_ahora=proximo is not None
                        and proximo - ahora <= timedelta(minutes=15),
                        proximo_turno=proximo,
                    )
                )
        return opciones

    async def derivar(
        self,
        cita_id: uuid.UUID,
        *,
        principal: Principal,
        profesional_id: uuid.UUID,
        servicio_id: uuid.UUID,
        inicio: datetime | None = None,
        consultorio_id: uuid.UUID | None = None,
    ) -> ResultadoOperacion:
        """Crea la atención en el área de destino, con el paciente ya presente."""
        self._exigir_derivacion(principal)
        origen = await self._cita_en_clinica(cita_id, principal)
        if profesional_id == origen.profesional_id:
            raise ReglaNegocioViolada("Elija un profesional distinto al que ya le atiende.")
        if principal.profesional_id is not None and not await self._repo.relacion_vigente(
            origen.paciente_id, principal.profesional_id, self._reloj.ahora()
        ):
            raise PermisoDenegado("Solo deriva quien tiene relación asistencial con el paciente.")
        ahora = self._reloj.ahora()
        resultado = await self._agenda.crear_cita_confirmada(
            SolicitudReserva(
                paciente_id=origen.paciente_id,
                profesional_id=profesional_id,
                servicio_id=servicio_id,
                sede_id=origen.sede_id,
                inicio=(inicio or ahora).replace(second=0, microsecond=0),
                consultorio_id=consultorio_id,
                notas_recepcion="Derivación interna",
            ),
            principal=principal,
        )
        destino = resultado.cita
        # Ya está en la clínica: el área de destino puede empezar sin volver a
        # registrar la llegada en recepción.
        destino.llegada_en = ahora
        await self._flush()
        if not await self._repo.relacion_vigente(origen.paciente_id, profesional_id, ahora):
            self._sesion.add(
                RelacionAsistencial(
                    paciente_id=origen.paciente_id,
                    profesional_id=profesional_id,
                    origen="DERIVACION",
                    cita_id=destino.id,
                )
            )
        especialidad = await self._repo.especialidad_de_servicio(servicio_id)
        self._evento(
            origen,
            principal,
            Evento.DERIVACION_INTERNA,
            "Derivación interna",
            cita_destino_id=str(destino.id),
            profesional_destino_id=str(profesional_id),
            especialidad=especialidad,
        )
        self._evento(
            destino,
            principal,
            Evento.DERIVADA_DESDE,
            "Recibido por derivación interna",
            cita_origen_id=str(origen.id),
        )
        entrada = construir_entrada(
            accion=AccionAuditada.CITA_DERIVADA,
            principal=principal,
            ahora=ahora,
            entidad_tipo="cita",
            entidad_id=origen.id,
            sede_id=origen.sede_id,
            paciente_id=origen.paciente_id,
            cita_destino_id=str(destino.id),
            profesional_destino_id=str(profesional_id),
        )
        return ResultadoOperacion(destino, (*resultado.auditoria, entrada))

    # ==================================================================
    #  Prolongación
    # ==================================================================
    async def solicitar_prolongacion(
        self, cita_id: uuid.UUID, minutos: int, *, principal: Principal
    ) -> ResultadoProlongacion:
        self._exigir(principal, "cita.iniciar_atencion", "pedir más tiempo para una atención")
        if not MINUTOS_MINIMOS <= minutos <= MINUTOS_MAXIMOS:
            raise ReglaNegocioViolada(
                f"Pida entre {MINUTOS_MINIMOS} y {MINUTOS_MAXIMOS} minutos más."
            )
        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        if cita.atencion_iniciada_en is None or cita.estado_enum.es_terminal:
            raise ConflictoEstado("Solo se prolonga una atención en curso.")
        if await self._minutos_pendientes(cita.id) is not None:
            raise ConflictoEstado("Ya hay una petición de más tiempo esperando a recepción.")

        conflictos = await self._repo.citas_que_chocan(cita, minutos)
        if not conflictos:
            await self._alargar(cita, minutos, principal)
            self._evento(
                cita,
                principal,
                Evento.PROLONGACION_APLICADA,
                "Atención prolongada",
                minutos=minutos,
                directa=True,
            )
            auditoria = self._auditoria(
                cita, principal, AccionAuditada.CITA_PROLONGADA, minutos=minutos
            )
            return ResultadoProlongacion(cita, True, minutos, (), (auditoria,))

        self._evento(
            cita,
            principal,
            Evento.PROLONGACION_SOLICITADA,
            "Más tiempo solicitado",
            minutos=minutos,
            citas_afectadas=[str(c.id) for c in conflictos],
        )
        auditoria = self._auditoria(
            cita, principal, AccionAuditada.CITA_PROLONGACION_SOLICITADA, minutos=minutos
        )
        afectadas = tuple(
            [Conflicto(c, await self._repo.nombre_de_paciente(c.paciente_id)) for c in conflictos]
        )
        return ResultadoProlongacion(cita, False, minutos, afectadas, (auditoria,))

    async def pendientes(self, *, principal: Principal) -> list[SolicitudPendiente]:
        self._exigir(principal, "cita.reprogramar", "resolver peticiones de más tiempo")
        ahora = self._reloj.ahora()
        filas = await self._repo.solicitudes_de_prolongacion(
            principal=principal, desde=ahora - timedelta(hours=12)
        )
        por_cita: dict[uuid.UUID, tuple[list[CitaHistorial], Cita]] = {}
        for fila, cita in filas:
            por_cita.setdefault(cita.id, ([], cita))[0].append(fila)
        abiertas = [
            (filas_cita, cita)
            for filas_cita, cita in por_cita.values()
            if _pendiente(filas_cita) is not None
        ]
        resultado = []
        for filas_cita, cita in abiertas:
            if cita.estado_enum.es_terminal:
                continue
            minutos = _pendiente(filas_cita) or 0
            fila = _ultima_solicitud(filas_cita)
            choques = await self._repo.citas_que_chocan(cita, minutos)
            nombres = await self._repo.nombres(
                profesionales={cita.profesional_id},
                consultorios=set(),
                sedes=set(),
                servicios=set(),
                usuarios=set(),
            )
            resultado.append(
                SolicitudPendiente(
                    cita=cita,
                    paciente=await self._repo.nombre_de_paciente(cita.paciente_id),
                    profesional=nombres.get(cita.profesional_id, ""),
                    minutos=minutos,
                    solicitada_en=fila.ocurrido_en,
                    conflictos=tuple(
                        [
                            Conflicto(c, await self._repo.nombre_de_paciente(c.paciente_id))
                            for c in choques
                        ]
                    ),
                )
            )
        return resultado

    async def opciones_prolongacion(
        self, cita_id: uuid.UUID, *, principal: Principal
    ) -> SolicitudPendiente:
        """Para cada paciente afectado: otros profesionales libres o un turno más tarde."""
        self._exigir(principal, "cita.reprogramar", "resolver peticiones de más tiempo")
        cita = await self._repo.obtener_cita(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        minutos = await self._minutos_pendientes(cita.id)
        if minutos is None:
            raise ConflictoEstado("Esta atención no tiene una petición de más tiempo pendiente.")
        nuevo_fin = cita.fin + timedelta(minutes=minutos)
        conflictos = []
        for afectada in await self._repo.citas_que_chocan(cita, minutos):
            alternativas = await self._alternativas(
                principal, afectada, cita.profesional_id, nuevo_fin
            )
            conflictos.append(
                Conflicto(
                    afectada,
                    await self._repo.nombre_de_paciente(afectada.paciente_id),
                    alternativas,
                )
            )
        nombres = await self._repo.nombres(
            profesionales={cita.profesional_id},
            consultorios=set(),
            sedes=set(),
            servicios=set(),
            usuarios=set(),
        )
        historial = await self._repo.eventos_de_cita(cita.id)
        solicitada = next(
            (
                f.ocurrido_en
                for f in reversed(historial)
                if evento_de(f) is Evento.PROLONGACION_SOLICITADA
            ),
            self._reloj.ahora(),
        )
        return SolicitudPendiente(
            cita=cita,
            paciente=await self._repo.nombre_de_paciente(cita.paciente_id),
            profesional=nombres.get(cita.profesional_id, ""),
            minutos=minutos,
            solicitada_en=solicitada,
            conflictos=tuple(conflictos),
        )

    async def resolver_prolongacion(
        self,
        cita_id: uuid.UUID,
        *,
        principal: Principal,
        aprobar: bool,
        resoluciones: list[Resolucion],
        motivo_rechazo: str | None = None,
    ) -> ResultadoProlongacion:
        self._exigir(principal, "cita.reprogramar", "resolver peticiones de más tiempo")
        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        minutos = await self._minutos_pendientes(cita.id)
        if minutos is None:
            raise ConflictoEstado("Esta atención no tiene una petición de más tiempo pendiente.")

        if not aprobar:
            motivo = (motivo_rechazo or "").strip()
            if len(motivo) < MOTIVO_MINIMO:
                raise ReglaNegocioViolada("Indique por qué no se aplica la prolongación.")
            self._evento(cita, principal, Evento.PROLONGACION_RECHAZADA, motivo, minutos=minutos)
            rechazo = self._auditoria(
                cita,
                principal,
                AccionAuditada.CITA_PROLONGACION_RECHAZADA,
                minutos=minutos,
                motivo=motivo,
            )
            return ResultadoProlongacion(cita, False, minutos, (), (rechazo,))

        choques = await self._repo.citas_que_chocan(cita, minutos)
        por_cita = {r.cita_id: r for r in resoluciones}
        faltan = [c for c in choques if c.id not in por_cita]
        if faltan:
            raise ReglaNegocioViolada(
                "Decida qué pasa con cada paciente afectado antes de aplicar la prolongación.",
                detalles={"citas_sin_decision": [str(c.id) for c in faltan]},
            )
        auditoria: list[EntradaAuditoria] = []
        movidas: list[Cita] = []
        for afectada in choques:
            decision = por_cita[afectada.id]
            cambio = await self._agenda.reprogramar_cita(
                afectada.id,
                principal=principal,
                nuevo_inicio=decision.inicio,
                motivo=MOTIVO_MOVIDA,
                nuevo_profesional_id=decision.profesional_id,
            )
            auditoria.extend(cambio.auditoria)
            movidas.append(cambio.cita)
        await self._alargar(cita, minutos, principal)
        self._evento(
            cita,
            principal,
            Evento.PROLONGACION_APLICADA,
            "Atención prolongada",
            minutos=minutos,
            citas_movidas=[str(c.id) for c in movidas],
        )
        auditoria.append(
            self._auditoria(cita, principal, AccionAuditada.CITA_PROLONGADA, minutos=minutos)
        )
        for movida in movidas:
            await self._avisar_movida(movida)
        return ResultadoProlongacion(cita, True, minutos, (), tuple(auditoria))

    # ==================================================================
    #  Auxiliares
    # ==================================================================
    async def _alternativas(
        self,
        principal: Principal,
        afectada: Cita,
        profesional_actual: uuid.UUID,
        nuevo_fin: datetime,
    ) -> tuple[Alternativa, ...]:
        alternativas: list[Alternativa] = []
        # Otro profesional que preste el servicio, a la misma hora o lo más cerca.
        for profesional in await self._repo.profesionales_del_servicio(
            afectada.servicio_id, afectada.sede_id, afectada.clinica_id
        ):
            if profesional.id == profesional_actual:
                continue
            turno = await self._proximo_turno(
                principal,
                profesional.id,
                afectada.servicio_id,
                afectada.sede_id,
                afectada.inicio - timedelta(minutes=10),
                afectada.inicio + timedelta(hours=2),
            )
            if turno is not None:
                alternativas.append(
                    Alternativa(
                        profesional_id=profesional.id,
                        profesional=f"{profesional.nombre} {profesional.apellido}".strip(),
                        inicio=max(turno, afectada.inicio) if turno <= afectada.inicio else turno,
                        mismo_profesional=False,
                    )
                )
        # El mismo profesional, después de la atención prolongada.
        resultado = await self._agenda.consultar_disponibilidad(
            principal=principal,
            profesional_id=profesional_actual,
            servicio_id=afectada.servicio_id,
            sede_id=afectada.sede_id,
            desde=nuevo_fin,
            hasta=nuevo_fin + timedelta(hours=10),
        )
        nombre = (
            await self._repo.nombres(
                profesionales={profesional_actual},
                consultorios=set(),
                sedes=set(),
                servicios=set(),
                usuarios=set(),
            )
        ).get(profesional_actual, "")
        for turno_libre in [t for t in resultado.turnos if t.intervalo.inicio >= nuevo_fin][:3]:
            alternativas.append(
                Alternativa(
                    profesional_id=profesional_actual,
                    profesional=nombre,
                    inicio=turno_libre.intervalo.inicio,
                    mismo_profesional=True,
                )
            )
        return tuple(alternativas)

    async def _proximo_turno(
        self,
        principal: Principal,
        profesional_id: uuid.UUID,
        servicio_id: uuid.UUID,
        sede_id: uuid.UUID,
        desde: datetime,
        hasta: datetime,
    ) -> datetime | None:
        try:
            resultado = await self._agenda.consultar_disponibilidad(
                principal=principal,
                profesional_id=profesional_id,
                servicio_id=servicio_id,
                sede_id=sede_id,
                desde=desde,
                hasta=hasta,
            )
        except (RecursoNoEncontrado, ReglaNegocioViolada):
            return None
        return resultado.turnos[0].intervalo.inicio if resultado.turnos else None

    async def _minutos_pendientes(self, cita_id: uuid.UUID) -> int | None:
        return _pendiente(await self._repo.eventos_de_cita(cita_id))

    async def _alargar(self, cita: Cita, minutos: int, principal: Principal) -> None:
        cita.duracion_minutos = cita.duracion_minutos + minutos
        # El disparador recalcula `fin`; se asigna también para que la
        # respuesta salga bien sin volver a leer la fila.
        cita.fin = cita.fin + timedelta(minutes=minutos)
        cita.actualizado_por = principal.actor_id
        await self._flush()

    async def _avisar_movida(self, cita: Cita) -> None:
        """WhatsApp genérico al paciente movido: hora, sede y profesional, nada clínico."""
        datos = await self._repo.datos_aviso(cita)
        if datos is None:
            return
        nombre, sede, zona, profesional = datos
        local = cita.inicio.astimezone(ZoneInfo(zona))
        try:
            await ServicioOutbox(self._sesion, self._reloj, RegistroCanales()).encolar(
                SolicitudEnvio(
                    tipo=TipoMensajeOutbox.CITA_REPROGRAMACION,
                    canal=CanalOutbox.WHATSAPP,
                    destino_tipo="PACIENTE",
                    destino_id=cita.paciente_id,
                    clave_deduplicacion=calcular_clave_deduplicacion(
                        "cita_movida", str(cita.id), cita.inicio.isoformat()
                    ),
                    variables={
                        "nombre": nombre.split(" ")[0],
                        "fecha": local.strftime("%d/%m/%Y"),
                        "hora": local.strftime("%H:%M"),
                        "sede": sede,
                        "profesional": profesional,
                    },
                    clinica_id=cita.clinica_id,
                    entidad_origen_tipo="cita",
                    entidad_origen_id=cita.id,
                )
            )
        except ConsentimientoRequerido:
            logger.info("recorrido.aviso_sin_consentimiento", cita_id=str(cita.id))

    async def _cita_en_clinica(self, cita_id: uuid.UUID, principal: Principal) -> Cita:
        cita = await self._repo.obtener_cita_para_actualizar(cita_id, principal=principal)
        if cita is None:
            raise RecursoNoEncontrado("La cita solicitada no existe.")
        if cita.estado_enum.es_terminal:
            raise ConflictoEstado("La cita ya está cerrada.")
        if cita.llegada_en is None:
            raise ConflictoEstado("Registre primero la llegada del paciente.")
        return cita

    async def _flush(self) -> None:
        try:
            await self._sesion.flush()
        except SQLAlchemyError as exc:
            await self._sesion.rollback()
            raise traducir_o_propagar(exc) from exc

    def _evento(
        self, cita: Cita, principal: Principal, evento: Evento, motivo: str, **metadatos: object
    ) -> None:
        self._sesion.add(
            CitaHistorial(
                cita_id=cita.id,
                estado_anterior=cita.estado,
                estado_nuevo=cita.estado,
                actor_tipo=principal.actor_tipo.value,
                actor_id=principal.actor_id,
                motivo=motivo,
                ocurrido_en=self._reloj.ahora(),
                metadatos={
                    "evento": evento.value,
                    **{k: v for k, v in metadatos.items() if v is not None},
                },
            )
        )

    def _auditoria(
        self,
        cita: Cita,
        principal: Principal,
        accion: AccionAuditada,
        *,
        minutos: int | None = None,
        motivo: str | None = None,
    ) -> EntradaAuditoria:
        return construir_entrada(
            accion=accion,
            principal=principal,
            ahora=self._reloj.ahora(),
            entidad_tipo="cita",
            entidad_id=cita.id,
            sede_id=cita.sede_id,
            paciente_id=cita.paciente_id,
            motivo=motivo,
            minutos=minutos,
        )

    @staticmethod
    def _exigir(principal: Principal, permiso: str, que: str) -> None:
        if principal.es_agente or not principal.tiene_permiso(permiso):
            raise PermisoDenegado(f"No tiene permiso para {que}.")

    @staticmethod
    def _exigir_derivacion(principal: Principal) -> None:
        if principal.es_agente or not (
            principal.tiene_permiso("historia_clinica.escribir")
            and principal.tiene_permiso("cita.crear")
        ):
            raise PermisoDenegado(
                "Derivar a otra área es una decisión del profesional que atiende."
            )


def _ultima_solicitud(filas: list[CitaHistorial]) -> CitaHistorial:
    solicitudes = [f for f in filas if evento_de(f) is Evento.PROLONGACION_SOLICITADA]
    return max(solicitudes, key=lambda f: f.ocurrido_en)


def _pendiente(filas: list[CitaHistorial]) -> int | None:
    """Minutos de la petición sin resolver, si la hay.

    Se cuenta en lugar de mirar el orden: varias filas pueden compartir
    instante (misma transacción, o reloj fijo en pruebas) y el orden entre
    ellas no es fiable. Cada solicitud se cierra con una aplicación o un
    rechazo; las prolongaciones directas, sin solicitud, no cuentan.
    """
    solicitudes = [f for f in filas if evento_de(f) is Evento.PROLONGACION_SOLICITADA]
    resueltas = sum(
        1
        for f in filas
        if evento_de(f) is Evento.PROLONGACION_RECHAZADA
        or (evento_de(f) is Evento.PROLONGACION_APLICADA and not (f.metadatos or {}).get("directa"))
    )
    if len(solicitudes) <= resueltas:
        return None
    return int(str((_ultima_solicitud(filas).metadatos or {}).get("minutos") or 0))


def _uuid(valor: object) -> uuid.UUID | None:
    if not valor:
        return None
    try:
        return uuid.UUID(str(valor))
    except ValueError:
        return None


__all__ = [
    "Alternativa",
    "Conflicto",
    "Evento",
    "OpcionDerivacion",
    "PasoRecorrido",
    "Resolucion",
    "ResultadoProlongacion",
    "ServicioRecorrido",
    "SolicitudPendiente",
    "evento_de",
]
