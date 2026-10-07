"""Administración de la disponibilidad semanal individual del equipo."""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import select

from app.modulos.organizacion.modelos import Sede
from app.modulos.profesionales.esquemas import DatosAgendaPlantilla, RespuestaAgendaPlantilla
from app.modulos.profesionales.modelos import AgendaPlantilla, Profesional, ProfesionalSede
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, RecursoNoEncontrado

enrutador = APIRouter(
    prefix="/profesionales/{profesional_id}/agenda",
    tags=["agenda del equipo"],
)
PuedeVerAgendaProfesional = Annotated[
    Principal,
    Depends(
        exige_permiso(
            "agenda.leer", "agenda.configurar", "profesional.leer", "profesional.gestionar"
        )
    ),
]
PuedeConfigurarAgendaProfesional = Annotated[
    Principal, Depends(exige_permiso("agenda.configurar", "profesional.gestionar"))
]


def _hora_modelo(valor: time | str) -> time:
    if isinstance(valor, time):
        return valor
    return time.fromisoformat(valor)


def _respuesta(plantilla: AgendaPlantilla) -> RespuestaAgendaPlantilla:
    return RespuestaAgendaPlantilla(
        id=plantilla.id,
        profesional_id=plantilla.profesional_id,
        sede_id=plantilla.sede_id,
        dia_semana=plantilla.dia_semana,
        hora_inicio=_hora_modelo(plantilla.hora_inicio),
        hora_fin=_hora_modelo(plantilla.hora_fin),
        granularidad_minutos=plantilla.granularidad_minutos,
        vigente_desde=date.fromisoformat(plantilla.vigente_desde)
        if isinstance(plantilla.vigente_desde, str)
        else plantilla.vigente_desde,
        vigente_hasta=date.fromisoformat(plantilla.vigente_hasta)
        if isinstance(plantilla.vigente_hasta, str)
        else plantilla.vigente_hasta,
    )


async def _destino_autorizado(
    profesional_id: uuid.UUID,
    sede_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
    *,
    bloquear: bool = False,
) -> tuple[Profesional, Sede]:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("No se encontró el equipo dentro de su ámbito.")
    if not principal.ambito.cubre_sede(sede_id):
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    if not principal.ambito.cubre_profesional(profesional_id):
        raise RecursoNoEncontrado("No se encontró el profesional dentro de su ámbito.")
    consulta = (
        select(Profesional, Sede)
        .join(
            ProfesionalSede,
            ProfesionalSede.profesional_id == Profesional.id,
        )
        .join(Sede, Sede.id == ProfesionalSede.sede_id)
        .where(
            Profesional.id == profesional_id,
            Profesional.clinica_id == principal.clinica_id,
            Profesional.activo.is_(True),
            Profesional.anulado_en.is_(None),
            Sede.id == sede_id,
            Sede.clinica_id == principal.clinica_id,
            Sede.activa.is_(True),
            Sede.anulado_en.is_(None),
        )
    )
    if bloquear:
        consulta = consulta.with_for_update(of=Profesional)
    fila = (await sesion.execute(consulta)).first()
    if fila is None:
        raise RecursoNoEncontrado("No se encontró el equipo dentro de su ámbito.")
    profesional, sede = fila
    if not principal.ambito.cubre_especialidad(profesional.especialidad_id):
        raise RecursoNoEncontrado("No se encontró el profesional dentro de su ámbito.")
    return profesional, sede


async def _validar_sin_solapamiento(
    sesion: Sesion,
    profesional_id: uuid.UUID,
    sede_id: uuid.UUID,
    datos: DatosAgendaPlantilla,
    *,
    excluir_id: uuid.UUID | None = None,
) -> None:
    consulta = select(AgendaPlantilla).where(
        AgendaPlantilla.profesional_id == profesional_id,
        AgendaPlantilla.sede_id == sede_id,
        AgendaPlantilla.dia_semana == datos.dia_semana,
    )
    if excluir_id is not None:
        consulta = consulta.where(AgendaPlantilla.id != excluir_id)
    inicio_nuevo = datos.vigente_desde or date.min
    fin_nuevo = datos.vigente_hasta or date.max
    existentes = (await sesion.execute(consulta.with_for_update())).scalars()
    for actual in existentes:
        inicio_actual = date.fromisoformat(actual.vigente_desde) if actual.vigente_desde else None
        fin_actual = date.fromisoformat(actual.vigente_hasta) if actual.vigente_hasta else None
        if (
            datos.hora_inicio < _hora_modelo(actual.hora_fin)
            and _hora_modelo(actual.hora_inicio) < datos.hora_fin
            and (inicio_actual or date.min) <= fin_nuevo
            and inicio_nuevo <= (fin_actual or date.max)
        ):
            raise ConflictoEstado("La disponibilidad se solapa con otra franja del profesional.")


async def _plantilla_en_ambito(
    plantilla_id: uuid.UUID,
    profesional_id: uuid.UUID,
    sede_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
) -> AgendaPlantilla:
    await _destino_autorizado(profesional_id, sede_id, principal, sesion, bloquear=True)
    plantilla = (
        await sesion.execute(
            select(AgendaPlantilla)
            .where(
                AgendaPlantilla.id == plantilla_id,
                AgendaPlantilla.profesional_id == profesional_id,
                AgendaPlantilla.sede_id == sede_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if plantilla is None:
        raise RecursoNoEncontrado("No se encontró la franja dentro de su ámbito.")
    return plantilla


@enrutador.get("", response_model=list[RespuestaAgendaPlantilla])
async def listar_agenda_profesional(
    profesional_id: Annotated[uuid.UUID, Path()],
    principal: PuedeVerAgendaProfesional,
    sesion: Sesion,
    sede_id: Annotated[uuid.UUID, Query()],
) -> list[RespuestaAgendaPlantilla]:
    await _destino_autorizado(profesional_id, sede_id, principal, sesion)
    filas = (
        await sesion.execute(
            select(AgendaPlantilla)
            .where(
                AgendaPlantilla.profesional_id == profesional_id,
                AgendaPlantilla.sede_id == sede_id,
            )
            .order_by(
                AgendaPlantilla.dia_semana,
                AgendaPlantilla.hora_inicio,
                AgendaPlantilla.vigente_desde,
            )
        )
    ).scalars()
    return [_respuesta(fila) for fila in filas]


@enrutador.post("", response_model=RespuestaAgendaPlantilla, status_code=status.HTTP_201_CREATED)
async def crear_franja_profesional(
    profesional_id: Annotated[uuid.UUID, Path()],
    datos: DatosAgendaPlantilla,
    principal: PuedeConfigurarAgendaProfesional,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    sede_id: Annotated[uuid.UUID, Query()],
) -> RespuestaAgendaPlantilla:
    await _destino_autorizado(profesional_id, sede_id, principal, sesion, bloquear=True)
    await _validar_sin_solapamiento(sesion, profesional_id, sede_id, datos)
    plantilla = AgendaPlantilla(
        profesional_id=profesional_id,
        sede_id=sede_id,
        dia_semana=datos.dia_semana,
        hora_inicio=datos.hora_inicio.strftime("%H:%M:%S"),
        hora_fin=datos.hora_fin.strftime("%H:%M:%S"),
        granularidad_minutos=datos.granularidad_minutos,
        vigente_desde=datos.vigente_desde.isoformat() if datos.vigente_desde else None,
        vigente_hasta=datos.vigente_hasta.isoformat() if datos.vigente_hasta else None,
    )
    sesion.add(plantilla)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.AGENDA_PROFESIONAL_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="agenda_profesional",
                entidad_id=plantilla.id,
                sede_id=sede_id,
                profesional_id=str(profesional_id),
                operacion="creada",
                dia_semana=datos.dia_semana,
            )
        ]
    )
    await sesion.commit()
    return _respuesta(plantilla)


@enrutador.put("/{plantilla_id}", response_model=RespuestaAgendaPlantilla)
async def actualizar_franja_profesional(
    profesional_id: Annotated[uuid.UUID, Path()],
    plantilla_id: Annotated[uuid.UUID, Path()],
    datos: DatosAgendaPlantilla,
    principal: PuedeConfigurarAgendaProfesional,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    sede_id: Annotated[uuid.UUID, Query()],
) -> RespuestaAgendaPlantilla:
    plantilla = await _plantilla_en_ambito(plantilla_id, profesional_id, sede_id, principal, sesion)
    await _validar_sin_solapamiento(sesion, profesional_id, sede_id, datos, excluir_id=plantilla.id)
    plantilla.dia_semana = datos.dia_semana
    plantilla.hora_inicio = datos.hora_inicio.strftime("%H:%M:%S")
    plantilla.hora_fin = datos.hora_fin.strftime("%H:%M:%S")
    plantilla.granularidad_minutos = datos.granularidad_minutos
    plantilla.vigente_desde = datos.vigente_desde.isoformat() if datos.vigente_desde else None
    plantilla.vigente_hasta = datos.vigente_hasta.isoformat() if datos.vigente_hasta else None
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.AGENDA_PROFESIONAL_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="agenda_profesional",
                entidad_id=plantilla.id,
                sede_id=sede_id,
                profesional_id=str(profesional_id),
                operacion="modificada",
                dia_semana=datos.dia_semana,
            )
        ]
    )
    await sesion.commit()
    return _respuesta(plantilla)


@enrutador.delete("/{plantilla_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_franja_profesional(
    profesional_id: Annotated[uuid.UUID, Path()],
    plantilla_id: Annotated[uuid.UUID, Path()],
    principal: PuedeConfigurarAgendaProfesional,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    sede_id: Annotated[uuid.UUID, Query()],
) -> Response:
    plantilla = await _plantilla_en_ambito(plantilla_id, profesional_id, sede_id, principal, sesion)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.AGENDA_PROFESIONAL_MODIFICADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="agenda_profesional",
                entidad_id=plantilla.id,
                sede_id=sede_id,
                profesional_id=str(profesional_id),
                operacion="eliminada",
                dia_semana=plantilla.dia_semana,
            )
        ]
    )
    await sesion.delete(plantilla)
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["enrutador"]
