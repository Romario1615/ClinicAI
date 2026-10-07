import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, cast, func, select
from sqlalchemy.dialects.postgresql import DATE
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.dashboard.esquemas import FiltroDashboard, ResumenAdherencia, ResumenDashboard
from app.modulos.historia.modelos import (
    AlertaAdherencia,
    NotaEvolucion,
    Receta,
    RecetaMedicamento,
    Toma,
)
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.lista_espera.modelos import EstadoOferta, OfertaTurno
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pagos.modelos import Pago
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.autorizacion import Principal


async def _resumir_recuperacion_turnos(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> tuple[int, int, int | None]:
    """Cuenta liberaciones y ofertas aceptadas dentro del ámbito autorizado."""
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.cancelada_en.is_not(None))
    )
    consulta = _aplicar_filtros(
        consulta,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=None,
    )
    cancelaciones = consulta.subquery()
    liberados = int(
        (
            await sesion.execute(
                select(func.count())
                .select_from(cancelaciones)
                .where(
                    cancelaciones.c.cancelada_en >= filtro.desde,
                    cancelaciones.c.cancelada_en < filtro.hasta,
                )
            )
        ).scalar_one()
    )

    consulta_liberadas = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.cancelada_en.is_not(None))
    )
    consulta_liberadas = _aplicar_filtros(
        consulta_liberadas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=None,
    )
    citas_liberadas = consulta_liberadas.subquery()
    demora_minutos = (
        func.extract("epoch", OfertaTurno.respondida_en - citas_liberadas.c.cancelada_en) / 60
    )
    filas = await sesion.execute(
        select(func.count(OfertaTurno.id), func.floor(func.avg(demora_minutos)))
        .select_from(
            citas_liberadas.join(
                OfertaTurno,
                OfertaTurno.cita_liberada_id == citas_liberadas.c.id,
            )
        )
        .where(
            OfertaTurno.estado == EstadoOferta.ACEPTADA.value,
            OfertaTurno.respondida_en >= filtro.desde,
            OfertaTurno.respondida_en < filtro.hasta,
            OfertaTurno.respondida_en >= citas_liberadas.c.cancelada_en,
        )
    )
    recuperados, promedio = filas.one()
    return int(liberados), int(recuperados), int(promedio) if promedio is not None else None


def _aplicar_filtros_receta(
    consulta: Select[Any],
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> Select[Any]:
    if especialidad_id:
        consulta = consulta.join(Profesional, Profesional.id == Receta.profesional_id)
        consulta = consulta.where(Profesional.especialidad_id == especialidad_id)
    if profesional_id:
        consulta = consulta.where(Receta.profesional_id == profesional_id)
    if sede_id or servicio_id:
        consulta = consulta.join(NotaEvolucion, NotaEvolucion.id == Receta.nota_id).join(
            Cita, Cita.id == NotaEvolucion.cita_id
        )
    if sede_id:
        consulta = consulta.where(Cita.sede_id == sede_id)
    if servicio_id:
        consulta = consulta.where(Cita.servicio_id == servicio_id)
    return consulta


async def _resumir_adherencia(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    ahora: datetime,
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
) -> ResumenAdherencia:
    """Agrega estados de dosis sin devolver identidad, medicamento ni nota clínica."""
    repositorio = RepositorioHistoria(sesion)
    consulta_tomas = (
        select(Toma.estado)
        .join(RecetaMedicamento, RecetaMedicamento.id == Toma.receta_medicamento_id)
        .join(Receta, Receta.id == RecetaMedicamento.receta_id)
        .where(Toma.programada_en >= filtro.desde, Toma.programada_en < filtro.hasta)
    )
    consulta_tomas = repositorio.consulta_receta_autorizada(
        consulta_tomas, principal=principal, ahora=ahora
    )
    consulta_tomas = _aplicar_filtros_receta(
        consulta_tomas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
    )
    tomas = consulta_tomas.subquery()
    conteos = await sesion.execute(
        select(
            func.count().filter(tomas.c.estado == "TOMADA"),
            func.count().filter(tomas.c.estado == "OMITIDA"),
        )
    )
    tomadas, omitidas = (int(valor) for valor in conteos.one())

    consulta_alertas = (
        select(AlertaAdherencia.id)
        .join(Receta, Receta.id == AlertaAdherencia.receta_id)
        .where(AlertaAdherencia.atendida_en.is_(None))
    )
    consulta_alertas = repositorio.consulta_receta_autorizada(
        consulta_alertas, principal=principal, ahora=ahora
    )
    consulta_alertas = _aplicar_filtros_receta(
        consulta_alertas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
    )
    alertas = consulta_alertas.subquery()
    pendientes = int((await sesion.execute(select(func.count()).select_from(alertas))).scalar_one())
    registradas = tomadas + omitidas
    porcentaje = round(tomadas * 100 / registradas, 1) if registradas else None
    return ResumenAdherencia(
        tomas_confirmadas=tomadas,
        tomas_omitidas=omitidas,
        porcentaje_registro_positivo=porcentaje,
        seguimientos_pendientes=pendientes,
    )


def _aplicar_filtros(
    consulta: Select[tuple[Cita]],
    *,
    sede_id: uuid.UUID | None,
    profesional_id: uuid.UUID | None,
    especialidad_id: uuid.UUID | None,
    servicio_id: uuid.UUID | None,
    estado: EstadoCita | None,
) -> Select[tuple[Cita]]:
    if sede_id:
        consulta = consulta.where(Cita.sede_id == sede_id)
    if profesional_id:
        consulta = consulta.where(Cita.profesional_id == profesional_id)
    if especialidad_id is not None or servicio_id is not None:
        consulta = consulta.join(Servicio, Servicio.id == Cita.servicio_id)
    if especialidad_id:
        consulta = consulta.where(Servicio.especialidad_id == especialidad_id)
    if servicio_id:
        consulta = consulta.where(Cita.servicio_id == servicio_id)
    if estado:
        consulta = consulta.where(Cita.estado == estado.value)
    return consulta


async def resumir(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
    especialidad_id: uuid.UUID | None = None,
    servicio_id: uuid.UUID | None = None,
    estado: EstadoCita | None = None,
    *,
    ahora: datetime,
) -> ResumenDashboard:
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.inicio >= filtro.desde, Cita.inicio < filtro.hasta)
    )
    consulta = _aplicar_filtros(
        consulta,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=estado,
    )
    citas = consulta.subquery()
    filas = await sesion.execute(select(citas.c.estado, func.count()).group_by(citas.c.estado))
    estados = {str(estado): int(cantidad) for estado, cantidad in filas}
    zona_local = func.coalesce(Sede.zona_horaria, Clinica.zona_horaria)
    inicio_local = func.timezone(zona_local, citas.c.inicio)
    agrupacion_local = (
        select(
            cast(inicio_local, DATE).label("fecha"),
            func.extract("hour", inicio_local).label("hora"),
            func.extract("dow", inicio_local).label("dia_postgres"),
            func.count().label("total"),
        )
        .select_from(citas)
        .join(Sede, Sede.id == citas.c.sede_id)
        .join(Clinica, Clinica.id == citas.c.clinica_id)
        .group_by(
            cast(inicio_local, DATE),
            func.extract("hour", inicio_local),
            func.extract("dow", inicio_local),
        )
        .subquery()
    )
    grupos_locales = await sesion.execute(
        select(
            agrupacion_local.c.fecha,
            agrupacion_local.c.hora,
            agrupacion_local.c.dia_postgres,
            agrupacion_local.c.total,
        )
    )
    tendencia: dict[date, int] = {}
    por_hora: dict[int, int] = {}
    por_dia: dict[int, int] = {}
    for fecha_local, hora, dia_postgres, total in grupos_locales:
        tendencia[fecha_local] = tendencia.get(fecha_local, 0) + int(total)
        hora_local = int(hora)
        dia_iso = ((int(dia_postgres) + 6) % 7) + 1
        por_hora[hora_local] = por_hora.get(hora_local, 0) + int(total)
        por_dia[dia_iso] = por_dia.get(dia_iso, 0) + int(total)
    pacientes = (
        await sesion.execute(select(func.count(func.distinct(citas.c.paciente_id))))
    ).scalar_one()
    pacientes_nuevos: int | None = None
    pacientes_recurrentes: int | None = None
    if estado is None:
        consulta_atenciones = (
            RepositorioAgenda(sesion)
            .consulta_autorizada(principal)
            .where(Cita.estado == EstadoCita.COMPLETED.value)
        )
        consulta_atenciones = _aplicar_filtros(
            consulta_atenciones,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
            estado=None,
        )
        atenciones = consulta_atenciones.subquery()
        primeras_atenciones = (
            select(atenciones.c.paciente_id, func.min(atenciones.c.inicio).label("primera"))
            .group_by(atenciones.c.paciente_id)
            .subquery()
        )
        pacientes_atendidos_en_periodo = (
            select(atenciones.c.paciente_id)
            .where(atenciones.c.inicio >= filtro.desde, atenciones.c.inicio < filtro.hasta)
            .distinct()
            .subquery()
        )
        conteo_pacientes = await sesion.execute(
            select(
                func.count().filter(primeras_atenciones.c.primera >= filtro.desde),
                func.count().filter(primeras_atenciones.c.primera < filtro.desde),
            ).select_from(
                primeras_atenciones.join(
                    pacientes_atendidos_en_periodo,
                    pacientes_atendidos_en_periodo.c.paciente_id
                    == primeras_atenciones.c.paciente_id,
                )
            )
        )
        pacientes_nuevos, pacientes_recurrentes = (int(valor) for valor in conteo_pacientes.one())
    adherencia: ResumenAdherencia | None = None
    if estado is None and principal.tiene_permiso("adherencia.leer"):
        adherencia = await _resumir_adherencia(
            sesion,
            principal,
            filtro,
            ahora,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
        )
    consulta_esperas = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.llegada_en >= filtro.desde, Cita.llegada_en < filtro.hasta)
    )
    consulta_esperas = _aplicar_filtros(
        consulta_esperas,
        sede_id=sede_id,
        profesional_id=profesional_id,
        especialidad_id=especialidad_id,
        servicio_id=servicio_id,
        estado=estado,
    )
    esperas = consulta_esperas.subquery()
    espera_minutos = func.floor(
        func.extract("epoch", esperas.c.atencion_iniciada_en - esperas.c.llegada_en) / 60
    )
    promedio_espera = (
        await sesion.execute(
            select(func.floor(func.avg(espera_minutos))).where(
                esperas.c.atencion_iniciada_en.is_not(None)
            )
        )
    ).scalar_one()
    en_espera = esperas.c.atencion_iniciada_en.is_(None)
    conteos_espera = await sesion.execute(
        select(
            func.count().filter(en_espera),
            func.count().filter(
                en_espera & (func.now() - esperas.c.llegada_en >= timedelta(minutes=15))
            ),
        )
    )
    personas_en_espera, espera_mayor_15 = conteos_espera.one()
    recuperacion: tuple[int | None, int | None, int | None] = (None, None, None)
    if estado is None:
        recuperacion = await _resumir_recuperacion_turnos(
            sesion,
            principal,
            filtro,
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
        )
    pagos = None
    # Ver indicadores de agenda no concede acceso a importes.
    if principal.tiene_permiso("pago.leer"):
        cobros = await sesion.execute(
            select(Pago.estado, func.sum(Pago.importe))
            .where(Pago.cita_id.in_(select(citas.c.id)), Pago.clinica_id == principal.clinica_id)
            .group_by(Pago.estado)
        )
        pagos = {str(estado): importe for estado, importe in cobros}
    return ResumenDashboard(
        desde=filtro.desde,
        hasta=filtro.hasta,
        citas=estados,
        total_citas=sum(estados.values()),
        pacientes=pacientes,
        pacientes_nuevos=pacientes_nuevos,
        pacientes_recurrentes=pacientes_recurrentes,
        espera={
            "promedio_minutos": int(promedio_espera) if promedio_espera is not None else None,
            "personas_en_espera": int(personas_en_espera),
            "espera_mayor_15_minutos": int(espera_mayor_15),
        },
        recuperacion_turnos={
            "turnos_liberados": recuperacion[0],
            "turnos_recuperados": recuperacion[1],
            "promedio_minutos_para_recuperar": recuperacion[2],
        },
        adherencia=adherencia,
        pagos=pagos,
        tendencia_diaria=[
            {"fecha": fecha, "total": total}
            for fecha, total in sorted(tendencia.items(), key=lambda par: par[0])
        ],
        por_hora=[{"hora": hora, "total": total} for hora, total in sorted(por_hora.items())],
        por_dia_semana=[{"dia": dia, "total": total} for dia, total in sorted(por_dia.items())],
    )
