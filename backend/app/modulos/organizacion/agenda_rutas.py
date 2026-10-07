"""Configuración de horarios de sede y feriados.

Los horarios se almacenan como horas locales de la sede; la zona horaria se
resuelve al consultar disponibilidad. El acceso a cualquier horario parte de
la clínica del principal y se limita a las sedes que tenga asignadas.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import and_, extract, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.modulos.organizacion.esquemas import (
    DatosFeriado,
    DatosHorarioSede,
    RespuestaDescansoHorario,
    RespuestaFeriado,
    RespuestaHorarioSede,
)
from app.modulos.organizacion.modelos import Clinica, Descanso, Feriado, HorarioAtencion, Sede
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/configuracion/agenda", tags=["configuracion de agenda"])

PuedeVerAgenda = Annotated[Principal, Depends(exige_permiso("agenda.leer", "agenda.configurar"))]
PuedeConfigurarAgenda = Annotated[Principal, Depends(exige_permiso("agenda.configurar"))]
MAX_DIAS_CONSULTA_FERIADOS = 730


async def _sede_autorizada(
    sede_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
    *,
    bloquear: bool = False,
) -> Sede:
    consulta = select(Sede).where(
        Sede.id == sede_id,
        Sede.clinica_id == principal.clinica_id,
        Sede.activa.is_(True),
        Sede.anulado_en.is_(None),
    )
    if not principal.ambito.todas_las_sedes and sede_id not in principal.ambito.sedes:
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    if bloquear:
        consulta = consulta.with_for_update()
    sede = (await sesion.execute(consulta)).scalar_one_or_none()
    if sede is None:
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    return sede


def _respuesta_horario(horario: HorarioAtencion) -> RespuestaHorarioSede:
    return RespuestaHorarioSede(
        id=horario.id,
        dia_semana=horario.dia_semana,
        hora_inicio=horario.hora_inicio,
        hora_fin=horario.hora_fin,
        granularidad_minutos=horario.granularidad_minutos,
        vigente_desde=horario.vigente_desde,
        vigente_hasta=horario.vigente_hasta,
        descansos=[
            RespuestaDescansoHorario(
                id=descanso.id,
                hora_inicio=descanso.hora_inicio,
                hora_fin=descanso.hora_fin,
                motivo=descanso.motivo,
            )
            for descanso in sorted(horario.descansos, key=lambda item: item.hora_inicio)
        ],
    )


def _validar_descansos(datos: DatosHorarioSede) -> None:
    if datos.hora_fin <= datos.hora_inicio:
        raise DatosInvalidos("La hora de cierre debe ser posterior a la hora de apertura.")
    if datos.vigente_desde and datos.vigente_hasta and datos.vigente_hasta < datos.vigente_desde:
        raise DatosInvalidos("La fecha final no puede ser anterior a la fecha inicial.")
    descansos = sorted(datos.descansos, key=lambda item: item.hora_inicio)
    fin_anterior = None
    for descanso in descansos:
        if descanso.hora_fin <= descanso.hora_inicio:
            raise DatosInvalidos("El fin del descanso debe ser posterior a su inicio.")
        if descanso.hora_inicio < datos.hora_inicio or descanso.hora_fin > datos.hora_fin:
            raise DatosInvalidos("Cada descanso debe quedar dentro del horario de atención.")
        if fin_anterior is not None and descanso.hora_inicio < fin_anterior:
            raise DatosInvalidos("Los descansos no pueden solaparse.")
        fin_anterior = descanso.hora_fin


def _periodos_se_solapan(a: HorarioAtencion, b: DatosHorarioSede) -> bool:
    inicio_a = a.vigente_desde or date.min
    fin_a = a.vigente_hasta or date.max
    inicio_b = b.vigente_desde or date.min
    fin_b = b.vigente_hasta or date.max
    return inicio_a <= fin_b and inicio_b <= fin_a


async def _validar_sin_solapamiento(
    sesion: Sesion,
    sede_id: uuid.UUID,
    datos: DatosHorarioSede,
    *,
    excluir_id: uuid.UUID | None = None,
) -> None:
    consulta = select(HorarioAtencion).where(
        HorarioAtencion.propietario_tipo == "SEDE",
        HorarioAtencion.propietario_id == sede_id,
        HorarioAtencion.dia_semana == datos.dia_semana,
    )
    if excluir_id is not None:
        consulta = consulta.where(HorarioAtencion.id != excluir_id)
    existentes = list((await sesion.execute(consulta.with_for_update())).scalars())
    for actual in existentes:
        horas_se_solapan = (
            datos.hora_inicio < actual.hora_fin and actual.hora_inicio < datos.hora_fin
        )
        if horas_se_solapan and _periodos_se_solapan(actual, datos):
            raise ConflictoEstado(
                "Ya existe una franja que se solapa ese día y durante el mismo periodo."
            )


async def _horario_en_ambito(
    horario_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
    *,
    con_descansos: bool = False,
    bloquear: bool = False,
) -> tuple[HorarioAtencion, Sede]:
    consulta = (
        select(HorarioAtencion, Sede)
        .join(
            Sede,
            and_(
                Sede.id == HorarioAtencion.propietario_id,
                HorarioAtencion.propietario_tipo == "SEDE",
            ),
        )
        .where(
            HorarioAtencion.id == horario_id,
            Sede.clinica_id == principal.clinica_id,
            Sede.activa.is_(True),
            Sede.anulado_en.is_(None),
        )
    )
    if not principal.ambito.todas_las_sedes:
        if not principal.ambito.sedes:
            raise RecursoNoEncontrado("No se encontró el horario dentro de su ámbito.")
        consulta = consulta.where(Sede.id.in_(principal.ambito.sedes))
    if con_descansos:
        consulta = consulta.options(selectinload(HorarioAtencion.descansos))
    if bloquear:
        consulta = consulta.with_for_update(of=HorarioAtencion)
    fila = (await sesion.execute(consulta)).first()
    if fila is None:
        raise RecursoNoEncontrado("No se encontró el horario dentro de su ámbito.")
    horario, sede = fila
    return horario, sede


@enrutador.get(
    "/sedes/{sede_id}/horarios",
    response_model=list[RespuestaHorarioSede],
    summary="Horarios y descansos de una sede",
)
async def listar_horarios_sede(
    sede_id: Annotated[uuid.UUID, Path()],
    principal: PuedeVerAgenda,
    sesion: Sesion,
) -> list[RespuestaHorarioSede]:
    await _sede_autorizada(sede_id, principal, sesion)
    horarios = (
        (
            await sesion.execute(
                select(HorarioAtencion)
                .options(selectinload(HorarioAtencion.descansos))
                .where(
                    HorarioAtencion.propietario_tipo == "SEDE",
                    HorarioAtencion.propietario_id == sede_id,
                )
                .order_by(
                    HorarioAtencion.dia_semana,
                    HorarioAtencion.hora_inicio,
                    HorarioAtencion.vigente_desde,
                )
            )
        )
        .scalars()
        .all()
    )
    return [_respuesta_horario(horario) for horario in horarios]


@enrutador.post(
    "/sedes/{sede_id}/horarios",
    response_model=RespuestaHorarioSede,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una franja semanal de sede",
)
async def crear_horario_sede(
    sede_id: Annotated[uuid.UUID, Path()],
    datos: DatosHorarioSede,
    principal: PuedeConfigurarAgenda,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaHorarioSede:
    sede = await _sede_autorizada(sede_id, principal, sesion, bloquear=True)
    _validar_descansos(datos)
    await _validar_sin_solapamiento(sesion, sede.id, datos)
    horario = HorarioAtencion(
        propietario_tipo="SEDE",
        propietario_id=sede.id,
        dia_semana=datos.dia_semana,
        hora_inicio=datos.hora_inicio,
        hora_fin=datos.hora_fin,
        granularidad_minutos=datos.granularidad_minutos,
        vigente_desde=datos.vigente_desde,
        vigente_hasta=datos.vigente_hasta,
        descansos=[
            Descanso(
                hora_inicio=descanso.hora_inicio,
                hora_fin=descanso.hora_fin,
                motivo=descanso.motivo.strip() if descanso.motivo else None,
            )
            for descanso in datos.descansos
        ],
    )
    sesion.add(horario)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado(
            "La franja de atención no se pudo guardar por un conflicto de datos."
        ) from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.HORARIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="horario_sede",
                entidad_id=horario.id,
                sede_id=sede.id,
                operacion="creado",
                descansos=len(datos.descansos),
            )
        ]
    )
    await sesion.commit()
    return _respuesta_horario(horario)


@enrutador.put("/horarios/{horario_id}", response_model=RespuestaHorarioSede)
async def actualizar_horario_sede(
    horario_id: Annotated[uuid.UUID, Path()],
    datos: DatosHorarioSede,
    principal: PuedeConfigurarAgenda,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaHorarioSede:
    horario, sede = await _horario_en_ambito(horario_id, principal, sesion)
    await _sede_autorizada(sede.id, principal, sesion, bloquear=True)
    horario, sede = await _horario_en_ambito(
        horario_id, principal, sesion, con_descansos=True, bloquear=True
    )
    _validar_descansos(datos)
    await _validar_sin_solapamiento(sesion, sede.id, datos, excluir_id=horario.id)
    horario.dia_semana = datos.dia_semana
    horario.hora_inicio = datos.hora_inicio
    horario.hora_fin = datos.hora_fin
    horario.granularidad_minutos = datos.granularidad_minutos
    horario.vigente_desde = datos.vigente_desde
    horario.vigente_hasta = datos.vigente_hasta
    horario.descansos = [
        Descanso(
            hora_inicio=descanso.hora_inicio,
            hora_fin=descanso.hora_fin,
            motivo=descanso.motivo.strip() if descanso.motivo else None,
        )
        for descanso in datos.descansos
    ]
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado(
            "La franja de atención no se pudo guardar por un conflicto de datos."
        ) from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.HORARIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="horario_sede",
                entidad_id=horario.id,
                sede_id=sede.id,
                operacion="modificado",
                descansos=len(datos.descansos),
            )
        ]
    )
    await sesion.commit()
    return _respuesta_horario(horario)


@enrutador.delete("/horarios/{horario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_horario_sede(
    horario_id: Annotated[uuid.UUID, Path()],
    principal: PuedeConfigurarAgenda,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> Response:
    horario, sede = await _horario_en_ambito(horario_id, principal, sesion)
    await _sede_autorizada(sede.id, principal, sesion, bloquear=True)
    horario, sede = await _horario_en_ambito(
        horario_id, principal, sesion, con_descansos=True, bloquear=True
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.HORARIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="horario_sede",
                entidad_id=horario.id,
                sede_id=sede.id,
                operacion="eliminado",
            )
        ]
    )
    await sesion.delete(horario)
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _respuesta_feriado(feriado: Feriado) -> RespuestaFeriado:
    return RespuestaFeriado(
        id=feriado.id,
        sede_id=feriado.sede_id,
        fecha=feriado.fecha,
        nombre=feriado.nombre,
        recurrente_anual=feriado.recurrente_anual,
        hora_inicio=feriado.hora_inicio,
        hora_fin=feriado.hora_fin,
    )


def _validar_feriado(datos: DatosFeriado) -> None:
    if (datos.hora_inicio is None) != (datos.hora_fin is None):
        raise DatosInvalidos(
            "Para un cierre parcial debe indicar tanto la hora de inicio como la de fin."
        )
    if (
        datos.hora_inicio is not None
        and datos.hora_fin is not None
        and datos.hora_fin <= datos.hora_inicio
    ):
        raise DatosInvalidos("La hora de fin del cierre debe ser posterior a la hora de inicio.")
    if not datos.nombre.strip():
        raise DatosInvalidos("El nombre del feriado es obligatorio.")


async def _validar_destino_feriado(
    datos: DatosFeriado,
    principal: Principal,
    sesion: Sesion,
) -> None:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("No se encontró la clínica dentro de su ámbito.")
    clinica = (
        await sesion.execute(
            select(Clinica.id).where(Clinica.id == principal.clinica_id).with_for_update()
        )
    ).scalar_one_or_none()
    if clinica is None:
        raise RecursoNoEncontrado("No se encontró la clínica dentro de su ámbito.")
    if datos.sede_id is None:
        if not principal.ambito.todas_las_sedes:
            raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
        return
    await _sede_autorizada(datos.sede_id, principal, sesion, bloquear=True)


async def _validar_sin_solapamiento_feriado(
    datos: DatosFeriado,
    principal: Principal,
    sesion: Sesion,
    *,
    excluir_id: uuid.UUID | None = None,
) -> None:
    destino = (
        true()
        if datos.sede_id is None
        else or_(Feriado.sede_id.is_(None), Feriado.sede_id == datos.sede_id)
    )
    recurrente_en_el_mismo_dia = (
        true() if datos.recurrente_anual else Feriado.recurrente_anual.is_(True)
    )
    consulta = select(Feriado).where(
        Feriado.clinica_id == principal.clinica_id,
        or_(
            Feriado.fecha == datos.fecha,
            and_(
                recurrente_en_el_mismo_dia,
                extract("month", Feriado.fecha) == datos.fecha.month,
                extract("day", Feriado.fecha) == datos.fecha.day,
            ),
        ),
        destino,
    )
    if excluir_id is not None:
        consulta = consulta.where(Feriado.id != excluir_id)
    for actual in (await sesion.execute(consulta.with_for_update())).scalars():
        # Dos cierres de día completo siempre colisionan. Los cierres parciales
        # pueden coexistir si sus ventanas no se pisan.
        if (
            actual.hora_inicio is None
            or actual.hora_fin is None
            or datos.hora_inicio is None
            or datos.hora_fin is None
        ):
            raise ConflictoEstado("Ya existe un cierre para esa fecha y sede.")
        if datos.hora_inicio < actual.hora_fin and actual.hora_inicio < datos.hora_fin:
            raise ConflictoEstado("El cierre se solapa con otro feriado de esa fecha.")


async def _feriado_en_ambito(
    feriado_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
) -> Feriado:
    consulta = select(Feriado).where(
        Feriado.id == feriado_id,
        Feriado.clinica_id == principal.clinica_id,
    )
    if not principal.ambito.todas_las_sedes:
        sedes = principal.ambito.sedes
        if not sedes:
            raise RecursoNoEncontrado("No se encontró el feriado dentro de su ámbito.")
        consulta = consulta.where(or_(Feriado.sede_id.is_(None), Feriado.sede_id.in_(sedes)))
    consulta = consulta.with_for_update()
    feriado = (await sesion.execute(consulta)).scalar_one_or_none()
    if feriado is None or (feriado.sede_id is None and not principal.ambito.todas_las_sedes):
        raise RecursoNoEncontrado("No se encontró el feriado dentro de su ámbito.")
    return feriado


@enrutador.get("/feriados", response_model=list[RespuestaFeriado])
async def listar_feriados(
    principal: PuedeVerAgenda,
    sesion: Sesion,
    desde: Annotated[date, Query()],
    hasta: Annotated[date, Query()],
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[RespuestaFeriado]:
    if hasta < desde or (hasta - desde).days > MAX_DIAS_CONSULTA_FERIADOS:
        raise DatosInvalidos("El rango de consulta debe ser válido y no superar dos años.")
    if principal.clinica_id is None:
        return []
    consulta = select(Feriado).where(
        Feriado.clinica_id == principal.clinica_id,
        or_(
            Feriado.recurrente_anual.is_(True),
            and_(Feriado.fecha >= desde, Feriado.fecha <= hasta),
        ),
    )
    if sede_id is not None:
        await _sede_autorizada(sede_id, principal, sesion)
        consulta = consulta.where(or_(Feriado.sede_id.is_(None), Feriado.sede_id == sede_id))
    elif not principal.ambito.todas_las_sedes:
        if not principal.ambito.sedes:
            return []
        consulta = consulta.where(
            or_(Feriado.sede_id.is_(None), Feriado.sede_id.in_(principal.ambito.sedes))
        )
    feriados = list(
        (await sesion.execute(consulta.order_by(Feriado.fecha, Feriado.nombre))).scalars()
    )
    return [_respuesta_feriado(feriado) for feriado in feriados]


@enrutador.post("/feriados", response_model=RespuestaFeriado, status_code=status.HTTP_201_CREATED)
async def crear_feriado(
    datos: DatosFeriado,
    principal: PuedeConfigurarAgenda,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaFeriado:
    _validar_feriado(datos)
    await _validar_destino_feriado(datos, principal, sesion)
    await _validar_sin_solapamiento_feriado(datos, principal, sesion)
    feriado = Feriado(
        clinica_id=principal.clinica_id,
        sede_id=datos.sede_id,
        fecha=datos.fecha,
        nombre=datos.nombre.strip(),
        recurrente_anual=datos.recurrente_anual,
        hora_inicio=datos.hora_inicio,
        hora_fin=datos.hora_fin,
    )
    sesion.add(feriado)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FERIADO_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="feriado",
                entidad_id=feriado.id,
                sede_id=feriado.sede_id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_feriado(feriado)


@enrutador.put("/feriados/{feriado_id}", response_model=RespuestaFeriado)
async def actualizar_feriado(
    feriado_id: Annotated[uuid.UUID, Path()],
    datos: DatosFeriado,
    principal: PuedeConfigurarAgenda,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaFeriado:
    feriado = await _feriado_en_ambito(feriado_id, principal, sesion)
    _validar_feriado(datos)
    await _validar_destino_feriado(datos, principal, sesion)
    await _validar_sin_solapamiento_feriado(datos, principal, sesion, excluir_id=feriado.id)
    feriado.sede_id = datos.sede_id
    feriado.fecha = datos.fecha
    feriado.nombre = datos.nombre.strip()
    feriado.recurrente_anual = datos.recurrente_anual
    feriado.hora_inicio = datos.hora_inicio
    feriado.hora_fin = datos.hora_fin
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FERIADO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="feriado",
                entidad_id=feriado.id,
                sede_id=feriado.sede_id,
            )
        ]
    )
    await sesion.commit()
    return _respuesta_feriado(feriado)


@enrutador.delete("/feriados/{feriado_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_feriado(
    feriado_id: Annotated[uuid.UUID, Path()],
    principal: PuedeConfigurarAgenda,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> Response:
    feriado = await _feriado_en_ambito(feriado_id, principal, sesion)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.FERIADO_ELIMINADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="feriado",
                entidad_id=feriado.id,
                sede_id=feriado.sede_id,
            )
        ]
    )
    await sesion.delete(feriado)
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["enrutador"]
