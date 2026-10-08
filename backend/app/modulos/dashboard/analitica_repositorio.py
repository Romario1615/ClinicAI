"""Solo agregados del ámbito; el reloj y la zona de clínica fijan el corte."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import DATE, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.dashboard.repositorio import _aplicar_filtros
from app.modulos.gastos.repositorio import RepositorioGastos
from app.modulos.organizacion.modelos import Clinica
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.modulos.pagos.modelos import Pago
from app.nucleo.autorizacion import Principal


class RepositorioAnalitica:
    def __init__(self, sesion: AsyncSession):
        self.sesion = sesion

    async def zona(self, principal: Principal) -> str:
        return str(
            await self.sesion.scalar(
                select(Clinica.zona_horaria).where(Clinica.id == principal.clinica_id)
            )
            or "America/Guayaquil"
        )

    async def series(
        self,
        principal: Principal,
        desde: date,
        hasta: date,
        zona: str,
        sede_id: uuid.UUID | None = None,
        profesional_id: uuid.UUID | None = None,
        especialidad_id: uuid.UUID | None = None,
        servicio_id: uuid.UUID | None = None,
    ) -> dict[str, dict[date, tuple[float, int]]]:
        salida: dict[str, dict[date, tuple[float, int]]] = {}
        inicio = datetime.combine(desde, time.min, ZoneInfo(zona))
        fin = datetime.combine(hasta, time.min, ZoneInfo(zona))
        base = _aplicar_filtros(
            RepositorioAgenda(self.sesion).consulta_autorizada(principal),
            sede_id=sede_id,
            profesional_id=profesional_id,
            especialidad_id=especialidad_id,
            servicio_id=servicio_id,
            estado=None,
        ).subquery()
        fecha = cast(func.timezone(zona, base.c.inicio), DATE)
        if principal.tiene_permiso("agenda.leer"):
            filas = await self.sesion.execute(
                select(
                    fecha,
                    base.c.estado,
                    func.count(),
                    func.count(func.distinct(base.c.paciente_id)),
                    func.sum(base.c.duracion_minutos),
                )
                .where(base.c.inicio >= inicio, base.c.inicio < fin, base.c.creado_en < fin)
                .group_by(fecha, base.c.estado)
            )
            claves = (
                "citas",
                "atenciones",
                "inasistencias",
                "cancelaciones",
                "pendientes",
                "minutos_atendidos",
            )
            for c in claves:
                salida[c] = {}
            for dia, estado, total, _pacientes, minutos in filas:
                _sumar(salida["citas"], dia, total, total)
                clave = {
                    "COMPLETED": "atenciones",
                    "NO_SHOW": "inasistencias",
                    "CANCELLED": "cancelaciones",
                    "PENDING": "pendientes",
                    "HELD": "pendientes",
                }.get(estado)
                if clave:
                    _sumar(salida[clave], dia, total, total)
                if estado == "COMPLETED":
                    _sumar(salida["minutos_atendidos"], dia, minutos, total)
            # Personas únicas por día, no suma de subconjuntos por estado.
            salida["pacientes_dia"] = {
                d: (float(n), int(n))
                for d, n in (
                    await self.sesion.execute(
                        select(fecha, func.count(func.distinct(base.c.paciente_id)))
                        .where(base.c.inicio >= inicio, base.c.inicio < fin, base.c.creado_en < fin)
                        .group_by(fecha)
                    )
                ).all()
            }
            espera_dia = cast(func.timezone(zona, base.c.atencion_iniciada_en), DATE)
            espera = func.extract("epoch", base.c.atencion_iniciada_en - base.c.llegada_en) / 60
            salida["espera"] = {
                d: (float(v), int(n))
                for d, v, n in (
                    await self.sesion.execute(
                        select(espera_dia, func.avg(espera), func.count())
                        .where(
                            base.c.atencion_iniciada_en >= inicio,
                            base.c.atencion_iniciada_en < fin,
                            base.c.llegada_en.is_not(None),
                            base.c.atencion_iniciada_en >= base.c.llegada_en,
                        )
                        .group_by(espera_dia)
                    )
                ).all()
            }
        if principal.tiene_permiso("pago.leer"):
            dia_pago = cast(func.timezone(zona, Pago.validado_en), DATE)
            salida["cobros"] = {
                d: (float(v), int(n))
                for d, v, n in (
                    await self.sesion.execute(
                        select(dia_pago, func.sum(Pago.importe), func.count())
                        .where(
                            Pago.clinica_id == principal.clinica_id,
                            Pago.cita_id.in_(select(base.c.id)),
                            Pago.estado == "CONFIRMED",
                            Pago.validado_en >= inicio,
                            Pago.validado_en < fin,
                        )
                        .group_by(dia_pago)
                    )
                ).all()
            }
        if (
            principal.tiene_permiso("gasto.leer")
            and profesional_id is None
            and especialidad_id is None
            and servicio_id is None
        ):
            gastos = (
                RepositorioGastos(self.sesion)
                .consulta(principal, desde=desde, hasta=hasta, sede_id=sede_id)
                .subquery()
            )
            salida["gastos"] = {
                d: (float(v), int(n))
                for d, v, n in (
                    await self.sesion.execute(
                        select(gastos.c.fecha, func.sum(gastos.c.importe), func.count())
                        .where(gastos.c.creado_en < fin)
                        .group_by(gastos.c.fecha)
                    )
                ).all()
            }
        if (
            principal.tiene_permiso("paciente.leer_administrativo")
            and sede_id is None
            and profesional_id is None
            and especialidad_id is None
            and servicio_id is None
        ):
            pacientes = RepositorioPacientes(self.sesion).consulta_autorizada(principal).subquery()
            dia_registro = cast(func.timezone(zona, pacientes.c.creado_en), DATE)
            salida["registros_pacientes"] = {
                d: (float(n), int(n))
                for d, n in (
                    await self.sesion.execute(
                        select(dia_registro, func.count())
                        .where(pacientes.c.creado_en >= inicio, pacientes.c.creado_en < fin)
                        .group_by(dia_registro)
                    )
                ).all()
            }
        return salida


def _sumar(datos: dict[date, tuple[float, int]], dia: date, valor: float, muestras: int) -> None:
    anterior = datos.get(dia, (0, 0))
    datos[dia] = anterior[0] + float(valor), anterior[1] + int(muestras)
