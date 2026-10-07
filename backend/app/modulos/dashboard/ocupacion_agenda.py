"""Consulta y cálculo del indicador agregado de ocupación de agenda."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.disponibilidad import (
    DescansoLocal,
    FeriadoLocal,
    FranjaLocal,
    Intervalo,
    proyectar_descansos,
    proyectar_feriados,
    proyectar_franjas,
    restar,
)
from app.modulos.agenda.modelos import _ESTADOS_QUE_OCUPAN, BloqueoAgenda, Cita, EstadoCita
from app.modulos.agenda.repositorio import RepositorioAgenda, _a_fecha, _a_hora
from app.modulos.dashboard.esquemas import FiltroDashboard, ResumenOcupacionAgenda
from app.modulos.dashboard.ocupacion import resumir_intervalos_ocupacion
from app.modulos.organizacion.modelos import (
    Clinica,
    Descanso,
    Feriado,
    HorarioAtencion,
    Sede,
    Servicio,
)
from app.modulos.profesionales.modelos import (
    AgendaPlantilla,
    Profesional,
    ProfesionalSede,
    ProfesionalServicio,
)
from app.nucleo.autorizacion import Principal

ParAgenda = tuple[uuid.UUID, uuid.UUID]
_NINGUNO = uuid.UUID(int=0)


def _filtrar_ambito(
    consulta: Select[Any],
    columna: Any,
    acceso_completo: bool,
    identificadores: frozenset[uuid.UUID],
) -> Select[Any]:
    if acceso_completo:
        return consulta
    return (
        consulta.where(columna.in_(identificadores))
        if identificadores
        else consulta.where(columna == _NINGUNO)
    )


async def _consultar_pares_agenda(
    sesion: AsyncSession,
    principal: Principal,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> dict[ParAgenda, str]:
    # La zona horaria efectiva se consulta sin cargar objetos completos.
    consulta = (
        select(
            Profesional.id,
            Profesional.especialidad_id,
            ProfesionalSede.sede_id,
            Sede.zona_horaria,
            Clinica.zona_horaria,
        )
        .join(ProfesionalSede, ProfesionalSede.profesional_id == Profesional.id)
        .join(Sede, Sede.id == ProfesionalSede.sede_id)
        .join(Clinica, Clinica.id == Profesional.clinica_id)
        .where(
            Profesional.clinica_id == principal.clinica_id,
            Profesional.activo.is_(True),
            Sede.activa.is_(True),
        )
    )
    consulta = _filtrar_ambito(
        consulta,
        Profesional.id,
        principal.ambito.todos_los_profesionales,
        principal.ambito.profesionales,
    )
    consulta = _filtrar_ambito(
        consulta,
        ProfesionalSede.sede_id,
        principal.ambito.todas_las_sedes,
        principal.ambito.sedes,
    )
    if servicio_id is None:
        consulta = _filtrar_ambito(
            consulta,
            Profesional.especialidad_id,
            principal.ambito.todas_las_especialidades,
            principal.ambito.especialidades,
        )
    if sede_id is not None:
        consulta = consulta.where(ProfesionalSede.sede_id == sede_id)
    if profesional_id is not None:
        consulta = consulta.where(Profesional.id == profesional_id)
    if especialidad_id is not None and servicio_id is None:
        consulta = consulta.where(Profesional.especialidad_id == especialidad_id)
    if servicio_id is not None:
        consulta = (
            consulta.join(ProfesionalServicio, ProfesionalServicio.profesional_id == Profesional.id)
            .join(Servicio, Servicio.id == ProfesionalServicio.servicio_id)
            .where(
                ProfesionalServicio.servicio_id == servicio_id,
                Servicio.clinica_id == principal.clinica_id,
            )
        )
        if especialidad_id is not None:
            consulta = consulta.where(Servicio.especialidad_id == especialidad_id)
        consulta = _filtrar_ambito(
            consulta,
            Servicio.especialidad_id,
            principal.ambito.todas_las_especialidades,
            principal.ambito.especialidades,
        )

    filas = (await sesion.execute(consulta)).all()
    return {
        (id_profesional, id_sede): str(zona_sede or zona_clinica)
        for id_profesional, _especialidad, id_sede, zona_sede, zona_clinica in filas
    }


async def _consultar_horarios(
    sesion: AsyncSession, pares: set[ParAgenda]
) -> tuple[
    dict[ParAgenda, list[FranjaLocal]],
    dict[uuid.UUID, list[FranjaLocal]],
    dict[uuid.UUID, list[DescansoLocal]],
]:
    profesionales = {profesional for profesional, _sede in pares}
    sedes = {sede for _profesional, sede in pares}
    plantillas: dict[ParAgenda, list[FranjaLocal]] = defaultdict(list)
    horarios_sede: dict[uuid.UUID, list[FranjaLocal]] = defaultdict(list)
    descansos_sede: dict[uuid.UUID, list[DescansoLocal]] = defaultdict(list)

    filas_plantilla = (
        await sesion.execute(
            select(AgendaPlantilla).where(
                AgendaPlantilla.profesional_id.in_(profesionales),
                AgendaPlantilla.sede_id.in_(sedes),
            )
        )
    ).scalars()
    for plantilla in filas_plantilla:
        clave = (plantilla.profesional_id, plantilla.sede_id)
        if clave in pares:
            plantillas[clave].append(
                FranjaLocal(
                    dia_semana=plantilla.dia_semana,
                    hora_inicio=_a_hora(plantilla.hora_inicio),
                    hora_fin=_a_hora(plantilla.hora_fin),
                    granularidad_minutos=plantilla.granularidad_minutos,
                    vigente_desde=_a_fecha(plantilla.vigente_desde),
                    vigente_hasta=_a_fecha(plantilla.vigente_hasta),
                )
            )

    filas_horarios = (
        await sesion.execute(
            select(HorarioAtencion).where(
                HorarioAtencion.propietario_tipo == "SEDE",
                HorarioAtencion.propietario_id.in_(sedes),
            )
        )
    ).scalars()
    for horario in filas_horarios:
        horarios_sede[horario.propietario_id].append(
            FranjaLocal(
                dia_semana=horario.dia_semana,
                hora_inicio=horario.hora_inicio,
                hora_fin=horario.hora_fin,
                granularidad_minutos=horario.granularidad_minutos,
                vigente_desde=horario.vigente_desde,
                vigente_hasta=horario.vigente_hasta,
            )
        )

    filas_descansos = (
        await sesion.execute(
            select(Descanso, HorarioAtencion.propietario_id, HorarioAtencion.dia_semana)
            .join(HorarioAtencion, HorarioAtencion.id == Descanso.horario_atencion_id)
            .where(
                HorarioAtencion.propietario_tipo == "SEDE",
                HorarioAtencion.propietario_id.in_(sedes),
            )
        )
    ).all()
    for descanso, id_sede, dia_semana in filas_descansos:
        descansos_sede[id_sede].append(
            DescansoLocal(
                dia_semana=dia_semana,
                hora_inicio=descanso.hora_inicio,
                hora_fin=descanso.hora_fin,
                motivo=descanso.motivo,
            )
        )
    return plantillas, horarios_sede, descansos_sede


async def _consultar_feriados(
    sesion: AsyncSession,
    principal: Principal,
    sedes: set[uuid.UUID],
    filtro: FiltroDashboard,
) -> tuple[list[FeriadoLocal], dict[uuid.UUID, list[FeriadoLocal]]]:
    filas = list(
        (
            await sesion.execute(
                select(Feriado).where(
                    Feriado.clinica_id == principal.clinica_id,
                    or_(Feriado.sede_id.is_(None), Feriado.sede_id.in_(sedes)),
                    or_(
                        Feriado.recurrente_anual.is_(True),
                        and_(
                            Feriado.fecha >= filtro.desde.date() - timedelta(days=2),
                            Feriado.fecha <= filtro.hasta.date() + timedelta(days=2),
                        ),
                    ),
                )
            )
        ).scalars()
    )
    generales: list[FeriadoLocal] = []
    por_sede: dict[uuid.UUID, list[FeriadoLocal]] = defaultdict(list)
    for fila in filas:
        feriado = FeriadoLocal(
            fecha=fila.fecha,
            nombre=fila.nombre,
            recurrente_anual=fila.recurrente_anual,
            hora_inicio=fila.hora_inicio,
            hora_fin=fila.hora_fin,
        )
        if fila.sede_id is None:
            generales.append(feriado)
        else:
            por_sede[fila.sede_id].append(feriado)
    return generales, por_sede


async def _consultar_bloqueos(
    sesion: AsyncSession,
    principal: Principal,
    profesionales: set[uuid.UUID],
    sedes: set[uuid.UUID],
    filtro: FiltroDashboard,
) -> list[BloqueoAgenda]:
    filas = await sesion.execute(
        select(BloqueoAgenda).where(
            BloqueoAgenda.clinica_id == principal.clinica_id,
            BloqueoAgenda.inicio < filtro.hasta,
            BloqueoAgenda.fin > filtro.desde,
            or_(
                BloqueoAgenda.profesional_id.in_(profesionales),
                and_(
                    BloqueoAgenda.profesional_id.is_(None),
                    BloqueoAgenda.sede_id.in_(sedes),
                ),
            ),
        )
    )
    return list(filas.scalars())


async def _consultar_reservas(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    pares: set[ParAgenda],
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> dict[uuid.UUID, list[Intervalo]]:
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(
            Cita.estado.in_(tuple(estado.value for estado in _ESTADOS_QUE_OCUPAN)),
            Cita.inicio < filtro.hasta,
            Cita.fin > filtro.desde,
        )
    )
    if sede_id is not None:
        consulta = consulta.where(Cita.sede_id == sede_id)
    if profesional_id is not None:
        consulta = consulta.where(Cita.profesional_id == profesional_id)
    if especialidad_id is not None or servicio_id is not None:
        consulta = consulta.join(Servicio, Servicio.id == Cita.servicio_id)
        if especialidad_id is not None:
            consulta = consulta.where(Servicio.especialidad_id == especialidad_id)
        if servicio_id is not None:
            consulta = consulta.where(Cita.servicio_id == servicio_id)
    reservas: dict[uuid.UUID, list[Intervalo]] = defaultdict(list)
    for cita in (await sesion.execute(consulta)).scalars():
        if (cita.profesional_id, cita.sede_id) in pares:
            reservas[cita.profesional_id].append(Intervalo(cita.inicio, cita.fin))
    return reservas


def _recortar(intervalo: Intervalo, rango: Intervalo) -> Intervalo | None:
    inicio = max(intervalo.inicio, rango.inicio)
    fin = min(intervalo.fin, rango.fin)
    return Intervalo(inicio, fin) if fin > inicio else None


def _cierres_del_dia(
    *,
    dia: date,
    zona: str,
    id_profesional: uuid.UUID,
    id_sede: uuid.UUID,
    descansos: list[DescansoLocal],
    feriados: list[FeriadoLocal],
    bloqueos: list[BloqueoAgenda],
) -> list[Intervalo]:
    cierres = [
        ocupacion.intervalo for ocupacion in proyectar_descansos(descansos, dia=dia, zona=zona)
    ]
    cierres.extend(
        ocupacion.intervalo for ocupacion in proyectar_feriados(feriados, dia=dia, zona=zona)
    )
    cierres.extend(
        Intervalo(bloqueo.inicio, bloqueo.fin)
        for bloqueo in bloqueos
        if bloqueo.profesional_id == id_profesional
        or (bloqueo.profesional_id is None and bloqueo.sede_id == id_sede)
    )
    return cierres


def _disponibles_por_profesional(
    *,
    pares: dict[ParAgenda, str],
    plantillas: dict[ParAgenda, list[FranjaLocal]],
    horarios_sede: dict[uuid.UUID, list[FranjaLocal]],
    descansos_sede: dict[uuid.UUID, list[DescansoLocal]],
    feriados_clinica: list[FeriadoLocal],
    feriados_sede: dict[uuid.UUID, list[FeriadoLocal]],
    bloqueos: list[BloqueoAgenda],
    filtro: FiltroDashboard,
) -> dict[uuid.UUID, list[Intervalo]]:
    disponibles: dict[uuid.UUID, list[Intervalo]] = defaultdict(list)
    rango = Intervalo(filtro.desde, filtro.hasta)
    for (id_profesional, id_sede), zona in pares.items():
        franjas = plantillas.get((id_profesional, id_sede)) or horarios_sede.get(id_sede, [])
        if not franjas:
            continue
        zona_info = ZoneInfo(zona)
        dia = filtro.desde.astimezone(zona_info).date() - timedelta(days=1)
        ultimo_dia = filtro.hasta.astimezone(zona_info).date() + timedelta(days=1)
        while dia <= ultimo_dia:
            base = [
                recortado
                for intervalo in proyectar_franjas(franjas, dia=dia, zona=zona)
                if (recortado := _recortar(intervalo, rango)) is not None
            ]
            if base:
                feriados = [*feriados_clinica, *feriados_sede.get(id_sede, [])]
                cierres = _cierres_del_dia(
                    dia=dia,
                    zona=zona,
                    id_profesional=id_profesional,
                    id_sede=id_sede,
                    descansos=descansos_sede.get(id_sede, []),
                    feriados=feriados,
                    bloqueos=bloqueos,
                )
                disponibles[id_profesional].extend(restar(base, cierres))
            dia += timedelta(days=1)
    return disponibles


async def resumir_ocupacion_agenda(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
    estado: EstadoCita | None,
) -> ResumenOcupacionAgenda:
    """Compara reservas activas y minutos de agenda disponibles."""
    if estado is not None:
        return ResumenOcupacionAgenda(
            minutos_disponibles=None,
            minutos_ocupados=None,
            porcentaje=None,
            detalle="Selecciona todos los estados para obtener una ocupación comparable.",
        )
    if principal.clinica_id is None or not principal.ambito.todos_los_pacientes:
        return ResumenOcupacionAgenda(
            minutos_disponibles=None,
            minutos_ocupados=None,
            porcentaje=None,
            detalle="La ocupación se muestra a roles con acceso al agregado completo de agenda.",
        )

    pares = await _consultar_pares_agenda(
        sesion,
        principal,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
    )
    if not pares:
        return ResumenOcupacionAgenda(
            minutos_disponibles=0,
            minutos_ocupados=0,
            porcentaje=None,
            detalle="No hay profesionales con horario dentro del ámbito y filtros elegidos.",
        )

    profesionales = {profesional for profesional, _sede in pares}
    sedes = {sede for _profesional, sede in pares}
    plantillas, horarios_sede, descansos_sede = await _consultar_horarios(sesion, set(pares))
    feriados_clinica, feriados_sede = await _consultar_feriados(sesion, principal, sedes, filtro)
    bloqueos = await _consultar_bloqueos(sesion, principal, profesionales, sedes, filtro)
    reservas = await _consultar_reservas(
        sesion,
        principal,
        filtro,
        set(pares),
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
    )
    disponibles = _disponibles_por_profesional(
        pares=pares,
        plantillas=plantillas,
        horarios_sede=horarios_sede,
        descansos_sede=descansos_sede,
        feriados_clinica=feriados_clinica,
        feriados_sede=feriados_sede,
        bloqueos=bloqueos,
        filtro=filtro,
    )
    resultados = [
        resumir_intervalos_ocupacion(franjas, reservas.get(id_profesional, ()))
        for id_profesional, franjas in disponibles.items()
    ]
    capacidad = sum(resultado[0] for resultado in resultados)
    ocupados = sum(resultado[1] for resultado in resultados)
    porcentaje = round(ocupados * 100 / capacidad, 1) if capacidad else None
    detalle = (
        "Sin horarios configurados para calcular capacidad en este periodo."
        if capacidad == 0
        else "Reservas activas frente al horario disponible; incluye pausas, feriados y bloqueos."
    )
    return ResumenOcupacionAgenda(
        minutos_disponibles=capacidad,
        minutos_ocupados=ocupados,
        porcentaje=porcentaje,
        detalle=detalle,
    )
