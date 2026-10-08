"""Consulta y cálculo del indicador agregado de ocupación de agenda.

El indicador compara el tiempo reservado con el tiempo que la agenda ofrecía
en el periodo.  Las reglas de capacidad (horario, plantilla, pausas, feriados
y bloqueos) son las mismas que aplica el motor de disponibilidad: si el panel
contara como capacidad minutos que el motor no deja reservar, la ocupación
saldría más baja que la real sin que nadie pudiera explicar por qué.
"""

from __future__ import annotations

import uuid
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
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
from app.modulos.agenda.repositorio import (
    RepositorioAgenda,
    _a_fecha,
    _a_hora,
    condicion_bloqueos_aplicables,
)
from app.modulos.dashboard.esquemas import FiltroDashboard, ResumenOcupacionAgenda
from app.modulos.dashboard.ocupacion import resumir_intervalos_ocupacion, unir_intervalos
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

# Estados cuyo tiempo cuenta como agenda consumida en este indicador.
#
# No es `_ESTADOS_QUE_OCUPAN`, y no debe serlo: ese conjunto responde a «¿puede
# otra reserva usar este hueco?» (motor de disponibilidad y restricción de
# exclusión), por eso deja fuera lo ya terminado.  El indicador responde a
# «¿cuánto del horario se reservó?»: una consulta atendida (COMPLETED) o a la
# que el paciente no acudió (NO_SHOW) consumió ese tiempo igual que una
# confirmada.  Sin ellas, cualquier periodo pasado saldría cerca del 0 %,
# porque cerrar cada consulta es justo pasarla a uno de esos dos estados.
# CANCELLED y PENDING no consumen tiempo: el motor tampoco los trata como
# ocupados y el hueco queda libre para otra reserva.
ESTADOS_OCUPACION_PANEL: frozenset[EstadoCita] = _ESTADOS_QUE_OCUPAN | {
    EstadoCita.COMPLETED,
    EstadoCita.NO_SHOW,
}

DETALLE_OCUPACION = (
    "Citas activas, atendidas e inasistencias frente al horario disponible; "
    "descuenta pausas, feriados y bloqueos."
)


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
    # Misma condición que el motor de disponibilidad sin consultorio pedido:
    # el panel no filtra por sala, así que un bloqueo de sala no resta
    # capacidad (el resto de las salas de la sede sigue atendiendo).
    filas = await sesion.execute(
        select(BloqueoAgenda).where(
            BloqueoAgenda.clinica_id == principal.clinica_id,
            BloqueoAgenda.inicio < filtro.hasta,
            BloqueoAgenda.fin > filtro.desde,
            condicion_bloqueos_aplicables(profesionales=profesionales, sedes=sedes),
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
            Cita.estado.in_(tuple(estado.value for estado in ESTADOS_OCUPACION_PANEL)),
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
    # Solo las columnas que hacen falta, leídas de la fila y no del mapa de
    # identidad: `fin` lo calcula un disparador, y una cita ya cargada en la
    # sesión cuyo inicio se cambió conserva el `fin` anterior en memoria.
    columnas = consulta.with_only_columns(
        Cita.profesional_id, Cita.sede_id, Cita.inicio, Cita.fin, maintain_column_froms=True
    )
    reservas: dict[uuid.UUID, list[Intervalo]] = defaultdict(list)
    for id_profesional, id_sede, inicio, fin in (await sesion.execute(columnas)).tuples():
        if (id_profesional, id_sede) in pares:
            reservas[id_profesional].append(Intervalo(inicio, fin))
    return reservas


def _recortar(intervalo: Intervalo, rango: Intervalo) -> Intervalo | None:
    inicio = max(intervalo.inicio, rango.inicio)
    fin = min(intervalo.fin, rango.fin)
    return Intervalo(inicio, fin) if fin > inicio else None


class _BloqueosOrdenados:
    """Bloqueos de una pareja profesional-sede, fusionados y ordenados.

    Al estar fusionados no se solapan, así que tanto los inicios como los
    fines quedan en orden creciente y los que tocan un día se localizan por
    búsqueda binaria.  Recorrer en cada día todos los bloqueos del periodo
    hacía el cálculo proporcional a pares por días por bloqueos, y con un rango
    largo eso bloquea el bucle de eventos durante segundos.
    """

    __slots__ = ("_fines", "_intervalos")

    def __init__(self, intervalos: Iterable[Intervalo]) -> None:
        self._intervalos = unir_intervalos(intervalos)
        self._fines = [intervalo.fin for intervalo in self._intervalos]

    def que_solapan(self, ventana: Intervalo) -> list[Intervalo]:
        indice = bisect_right(self._fines, ventana.inicio)
        resultado: list[Intervalo] = []
        while indice < len(self._intervalos) and self._intervalos[indice].inicio < ventana.fin:
            resultado.append(self._intervalos[indice])
            indice += 1
        return resultado


def _agrupar_bloqueos(
    bloqueos: Iterable[BloqueoAgenda],
) -> tuple[dict[uuid.UUID, list[Intervalo]], dict[uuid.UUID, list[Intervalo]]]:
    """Separa una sola vez los bloqueos de profesional y los de sede completa.

    Replica `condicion_bloqueos_aplicables` sin consultorio pedido: un bloqueo
    de sala no se asigna a nadie, porque el panel no filtra por sala.
    """
    por_profesional: dict[uuid.UUID, list[Intervalo]] = defaultdict(list)
    por_sede: dict[uuid.UUID, list[Intervalo]] = defaultdict(list)
    for bloqueo in bloqueos:
        intervalo = Intervalo(bloqueo.inicio, bloqueo.fin)
        if bloqueo.profesional_id is not None:
            por_profesional[bloqueo.profesional_id].append(intervalo)
        elif bloqueo.consultorio_id is None and bloqueo.sede_id is not None:
            por_sede[bloqueo.sede_id].append(intervalo)
    return por_profesional, por_sede


def _cierres_del_dia(
    *,
    dia: date,
    zona: str,
    ventana: Intervalo,
    descansos: Sequence[DescansoLocal],
    feriados: Sequence[FeriadoLocal],
    bloqueos: _BloqueosOrdenados,
) -> list[Intervalo]:
    cierres = [
        ocupacion.intervalo for ocupacion in proyectar_descansos(descansos, dia=dia, zona=zona)
    ]
    cierres.extend(
        ocupacion.intervalo for ocupacion in proyectar_feriados(feriados, dia=dia, zona=zona)
    )
    cierres.extend(bloqueos.que_solapan(ventana))
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
    bloqueos_profesional, bloqueos_sede = _agrupar_bloqueos(bloqueos)
    for (id_profesional, id_sede), zona in pares.items():
        franjas = plantillas.get((id_profesional, id_sede)) or horarios_sede.get(id_sede, [])
        if not franjas:
            continue
        # Lo que no depende del día se prepara una vez por pareja.
        feriados = [*feriados_clinica, *feriados_sede.get(id_sede, [])]
        descansos = descansos_sede.get(id_sede, [])
        bloqueos_par = _BloqueosOrdenados(
            [*bloqueos_profesional.get(id_profesional, ()), *bloqueos_sede.get(id_sede, ())]
        )
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
                cierres = _cierres_del_dia(
                    dia=dia,
                    zona=zona,
                    ventana=Intervalo(base[0].inicio, base[-1].fin),
                    descansos=descansos,
                    feriados=feriados,
                    bloqueos=bloqueos_par,
                )
                disponibles[id_profesional].extend(restar(base, cierres))
            dia += timedelta(days=1)
    return disponibles


def ocupacion_no_calculada() -> ResumenOcupacionAgenda:
    """Resultado para quien pide el resumen sin necesitar la ocupación.

    Los análisis local y con IA no la leen; calcularla igualmente recorre cada
    día del periodo por profesional sin ningún resultado visible.
    """
    return ResumenOcupacionAgenda(
        minutos_disponibles=None,
        minutos_ocupados=None,
        porcentaje=None,
        detalle="La ocupación no se calcula en este análisis.",
    )


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
    """Compara el tiempo reservado con los minutos de agenda disponibles.

    Cuentan las citas de `ESTADOS_OCUPACION_PANEL` (activas, atendidas e
    inasistencias), recortadas al horario disponible.
    """
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
        else DETALLE_OCUPACION
    )
    return ResumenOcupacionAgenda(
        minutos_disponibles=capacidad,
        minutos_ocupados=ocupados,
        porcentaje=porcentaje,
        detalle=detalle,
    )
