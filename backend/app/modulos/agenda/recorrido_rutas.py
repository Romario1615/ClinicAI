"""Rutas del recorrido del paciente, la derivación interna y la prolongación.

Cada ruta declara su permiso y el servicio lo vuelve a comprobar; el ámbito lo
aplica el repositorio en el `WHERE`. La auditoría se confirma en la misma
transacción que el cambio.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from app.modulos.agenda.esquemas import RespuestaCita
from app.modulos.agenda.recorrido_repositorio import RepositorioRecorrido
from app.modulos.agenda.recorrido_servicios import (
    MINUTOS_MAXIMOS,
    MINUTOS_MINIMOS,
    Conflicto,
    Resolucion,
    ServicioRecorrido,
    SolicitudPendiente,
)
from app.modulos.agenda.rutas import _a_respuesta
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    RelojActual,
    ServicioDeAgenda,
    Sesion,
    exige_permiso,
)

enrutador = APIRouter(prefix="/agenda", tags=["agenda"])

PuedeLeer = Annotated[Principal, Depends(exige_permiso("agenda.leer"))]
PuedeMover = Annotated[Principal, Depends(exige_permiso("cita.registrar_llegada"))]
PuedeDerivar = Annotated[
    Principal, Depends(exige_permiso("historia_clinica.escribir", "cita.crear", exigir_todos=True))
]
PuedePedirTiempo = Annotated[Principal, Depends(exige_permiso("cita.iniciar_atencion"))]
PuedeResolver = Annotated[Principal, Depends(exige_permiso("cita.reprogramar"))]


def obtener_servicio_recorrido(
    sesion: Sesion, reloj: RelojActual, agenda: ServicioDeAgenda
) -> ServicioRecorrido:
    return ServicioRecorrido(sesion, RepositorioRecorrido(sesion), agenda, reloj)


RecorridoActual = Annotated[ServicioRecorrido, Depends(obtener_servicio_recorrido)]


# ---------------------------------------------------------------------------
#  Esquemas
# ---------------------------------------------------------------------------
class PasoSalida(BaseModel):
    ocurrido_en: datetime
    evento: str
    titulo: str
    detalle: str | None
    cita_id: uuid.UUID
    servicio: str | None
    profesional: str | None
    consultorio: str | None
    sede: str | None
    registrado_por: str | None


class IngresoConsultorio(BaseModel):
    consultorio_id: uuid.UUID


class OpcionDerivacionSalida(BaseModel):
    profesional_id: uuid.UUID
    profesional: str
    servicio_id: uuid.UUID
    servicio: str
    especialidad: str
    libre_ahora: bool
    proximo_turno: datetime | None


class PeticionDerivacion(BaseModel):
    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    inicio: datetime | None = None
    consultorio_id: uuid.UUID | None = None


class PeticionProlongacion(BaseModel):
    minutos: int = Field(ge=MINUTOS_MINIMOS, le=MINUTOS_MAXIMOS)


class AlternativaSalida(BaseModel):
    profesional_id: uuid.UUID
    profesional: str
    inicio: datetime
    mismo_profesional: bool


class ConflictoSalida(BaseModel):
    cita_id: uuid.UUID
    paciente: str
    inicio: datetime
    llego: bool
    alternativas: list[AlternativaSalida]


class ProlongacionSalida(BaseModel):
    cita_id: uuid.UUID
    aplicada: bool
    minutos: int
    fin: datetime
    conflictos: list[ConflictoSalida]


class SolicitudSalida(BaseModel):
    cita_id: uuid.UUID
    paciente: str
    profesional: str
    minutos: int
    solicitada_en: datetime
    fin_actual: datetime
    conflictos: list[ConflictoSalida]


class DecisionAfectada(BaseModel):
    cita_id: uuid.UUID
    inicio: datetime
    profesional_id: uuid.UUID | None = None


class ResolucionProlongacion(BaseModel):
    aprobar: bool
    resoluciones: list[DecisionAfectada] = Field(default_factory=list, max_length=10)
    motivo_rechazo: str | None = Field(default=None, max_length=300)


def _conflicto(conflicto: Conflicto) -> ConflictoSalida:
    return ConflictoSalida(
        cita_id=conflicto.cita.id,
        paciente=conflicto.paciente,
        inicio=conflicto.cita.inicio,
        llego=conflicto.cita.llegada_en is not None,
        alternativas=[
            AlternativaSalida(
                profesional_id=a.profesional_id,
                profesional=a.profesional,
                inicio=a.inicio,
                mismo_profesional=a.mismo_profesional,
            )
            for a in conflicto.alternativas
        ],
    )


def _solicitud(solicitud: SolicitudPendiente) -> SolicitudSalida:
    return SolicitudSalida(
        cita_id=solicitud.cita.id,
        paciente=solicitud.paciente,
        profesional=solicitud.profesional,
        minutos=solicitud.minutos,
        solicitada_en=solicitud.solicitada_en,
        fin_actual=solicitud.cita.fin,
        conflictos=[_conflicto(c) for c in solicitud.conflictos],
    )


# ---------------------------------------------------------------------------
#  Recorrido
# ---------------------------------------------------------------------------
@enrutador.get("/pacientes/{paciente_id}/recorrido", response_model=list[PasoSalida])
async def ver_recorrido(
    principal: PuedeLeer,
    servicio: RecorridoActual,
    sesion: Sesion,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    dias: Annotated[int, Query(ge=1, le=3650)] = 365,
) -> list[PasoSalida]:
    """Todo lo que pasó con el paciente en la clínica, en orden."""
    pasos, entrada = await servicio.recorrido(paciente_id, principal=principal, dias=dias)
    await auditor.registrar([entrada])
    await sesion.commit()
    return [
        PasoSalida(
            ocurrido_en=p.ocurrido_en,
            evento=p.evento.value,
            titulo=p.titulo,
            detalle=p.detalle,
            cita_id=p.cita_id,
            servicio=p.servicio,
            profesional=p.profesional,
            consultorio=p.consultorio,
            sede=p.sede,
            registrado_por=p.registrado_por,
        )
        for p in pasos
    ]


@enrutador.post("/citas/{cita_id}/consultorio", response_model=RespuestaCita)
async def ingresar_consultorio(
    principal: PuedeMover,
    servicio: RecorridoActual,
    sesion: Sesion,
    auditor: Auditor,
    datos: IngresoConsultorio,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    resultado = await servicio.ingreso_consultorio(
        cita_id, datos.consultorio_id, principal=principal
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return _a_respuesta(resultado.cita)


@enrutador.post("/citas/{cita_id}/salida", response_model=RespuestaCita)
async def registrar_salida(
    principal: PuedeMover,
    servicio: RecorridoActual,
    sesion: Sesion,
    auditor: Auditor,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    resultado = await servicio.salida(cita_id, principal=principal)
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return _a_respuesta(resultado.cita)


# ---------------------------------------------------------------------------
#  Derivación interna
# ---------------------------------------------------------------------------
@enrutador.get("/citas/{cita_id}/derivacion/opciones", response_model=list[OpcionDerivacionSalida])
async def opciones_derivacion(
    principal: PuedeDerivar,
    servicio: RecorridoActual,
    cita_id: Annotated[uuid.UUID, Path()],
) -> list[OpcionDerivacionSalida]:
    return [
        OpcionDerivacionSalida(
            profesional_id=o.profesional_id,
            profesional=o.profesional,
            servicio_id=o.servicio_id,
            servicio=o.servicio,
            especialidad=o.especialidad,
            libre_ahora=o.libre_ahora,
            proximo_turno=o.proximo_turno,
        )
        for o in await servicio.opciones_derivacion(cita_id, principal=principal)
    ]


@enrutador.post("/citas/{cita_id}/derivacion", response_model=RespuestaCita, status_code=201)
async def derivar(
    principal: PuedeDerivar,
    servicio: RecorridoActual,
    sesion: Sesion,
    auditor: Auditor,
    datos: PeticionDerivacion,
    cita_id: Annotated[uuid.UUID, Path()],
) -> RespuestaCita:
    """Crea la atención en el área de destino; devuelve la cita nueva."""
    resultado = await servicio.derivar(
        cita_id,
        principal=principal,
        profesional_id=datos.profesional_id,
        servicio_id=datos.servicio_id,
        inicio=datos.inicio,
        consultorio_id=datos.consultorio_id,
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return _a_respuesta(resultado.cita)


# ---------------------------------------------------------------------------
#  Prolongación
# ---------------------------------------------------------------------------
@enrutador.post("/citas/{cita_id}/prolongacion", response_model=ProlongacionSalida)
async def pedir_prolongacion(
    principal: PuedePedirTiempo,
    servicio: RecorridoActual,
    sesion: Sesion,
    auditor: Auditor,
    datos: PeticionProlongacion,
    cita_id: Annotated[uuid.UUID, Path()],
) -> ProlongacionSalida:
    """Sin choque se aplica; con choque queda pendiente para recepción."""
    resultado = await servicio.solicitar_prolongacion(cita_id, datos.minutos, principal=principal)
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return ProlongacionSalida(
        cita_id=resultado.cita.id,
        aplicada=resultado.aplicada,
        minutos=resultado.minutos,
        fin=resultado.cita.fin,
        conflictos=[_conflicto(c) for c in resultado.conflictos],
    )


@enrutador.get("/prolongaciones", response_model=list[SolicitudSalida])
async def prolongaciones_pendientes(
    principal: PuedeResolver, servicio: RecorridoActual
) -> list[SolicitudSalida]:
    return [_solicitud(s) for s in await servicio.pendientes(principal=principal)]


@enrutador.get("/citas/{cita_id}/prolongacion/opciones", response_model=SolicitudSalida)
async def opciones_prolongacion(
    principal: PuedeResolver,
    servicio: RecorridoActual,
    cita_id: Annotated[uuid.UUID, Path()],
) -> SolicitudSalida:
    return _solicitud(await servicio.opciones_prolongacion(cita_id, principal=principal))


@enrutador.post("/citas/{cita_id}/prolongacion/resolucion", response_model=ProlongacionSalida)
async def resolver_prolongacion(
    principal: PuedeResolver,
    servicio: RecorridoActual,
    sesion: Sesion,
    auditor: Auditor,
    datos: ResolucionProlongacion,
    cita_id: Annotated[uuid.UUID, Path()],
) -> ProlongacionSalida:
    resultado = await servicio.resolver_prolongacion(
        cita_id,
        principal=principal,
        aprobar=datos.aprobar,
        resoluciones=[
            Resolucion(cita_id=r.cita_id, inicio=r.inicio, profesional_id=r.profesional_id)
            for r in datos.resoluciones
        ],
        motivo_rechazo=datos.motivo_rechazo,
    )
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return ProlongacionSalida(
        cita_id=resultado.cita.id,
        aplicada=resultado.aplicada,
        minutos=resultado.minutos,
        fin=resultado.cita.fin,
        conflictos=[],
    )


__all__ = ["enrutador"]
