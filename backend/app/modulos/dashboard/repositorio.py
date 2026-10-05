import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.dashboard.esquemas import FiltroDashboard, ResumenDashboard
from app.modulos.pagos.modelos import Pago
from app.nucleo.autorizacion import Principal


async def resumir(
    sesion: AsyncSession,
    principal: Principal,
    filtro: FiltroDashboard,
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
) -> ResumenDashboard:
    consulta = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.inicio >= filtro.desde, Cita.inicio < filtro.hasta)
    )
    if sede_id:
        consulta = consulta.where(Cita.sede_id == sede_id)
    if profesional_id:
        consulta = consulta.where(Cita.profesional_id == profesional_id)
    citas = consulta.subquery()
    filas = await sesion.execute(select(citas.c.estado, func.count()).group_by(citas.c.estado))
    estados = {str(estado): int(cantidad) for estado, cantidad in filas}
    pacientes = (
        await sesion.execute(select(func.count(func.distinct(citas.c.paciente_id))))
    ).scalar_one()
    consulta_esperas = (
        RepositorioAgenda(sesion)
        .consulta_autorizada(principal)
        .where(Cita.llegada_en >= filtro.desde, Cita.llegada_en < filtro.hasta)
    )
    if sede_id:
        consulta_esperas = consulta_esperas.where(Cita.sede_id == sede_id)
    if profesional_id:
        consulta_esperas = consulta_esperas.where(Cita.profesional_id == profesional_id)
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
        espera={
            "promedio_minutos": int(promedio_espera) if promedio_espera is not None else None,
            "personas_en_espera": int(personas_en_espera),
            "espera_mayor_15_minutos": int(espera_mayor_15),
        },
        pagos=pagos,
    )
