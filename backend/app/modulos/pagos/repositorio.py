import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Select, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente
from app.modulos.pagos.modelos import CargoPago, Pago, PagoComprobante, PagoHistorial
from app.nucleo.autorizacion import Principal


class RepositorioPagos:
    def __init__(self, sesion: AsyncSession) -> None:
        self.sesion = sesion

    def consulta(self, principal: Principal) -> Select[Any]:
        citas = RepositorioAgenda(self.sesion).consulta_autorizada(principal).subquery()
        return select(Pago).where(
            Pago.clinica_id == principal.clinica_id, Pago.cita_id.in_(select(citas.c.id))
        )

    async def obtener(self, pago_id: uuid.UUID, principal: Principal) -> Pago | None:
        return (
            await self.sesion.execute(
                self.consulta(principal).where(Pago.id == pago_id).with_for_update()
            )
        ).scalar_one_or_none()

    async def listar(
        self, principal: Principal, limite: int, desplazamiento: int
    ) -> tuple[list[Pago], int]:
        consulta = self.consulta(principal)
        total = int(
            (
                await self.sesion.execute(select(func.count()).select_from(consulta.subquery()))
            ).scalar_one()
        )
        filas = await self.sesion.execute(
            consulta.order_by(Pago.creado_en.desc(), Pago.id).limit(limite).offset(desplazamiento)
        )
        return list(filas.scalars()), total

    async def visible(self, pago_id: uuid.UUID, principal: Principal) -> Pago | None:
        """Busca dentro del ámbito sin tomar el bloqueo reservado a cambios."""
        return (
            await self.sesion.execute(self.consulta(principal).where(Pago.id == pago_id))
        ).scalar_one_or_none()

    async def cargo_por_cita(
        self, cita_id: uuid.UUID, clinica_id: uuid.UUID, *, bloquear: bool = False
    ) -> CargoPago | None:
        consulta = select(CargoPago).where(
            CargoPago.cita_id == cita_id, CargoPago.clinica_id == clinica_id
        )
        if bloquear:
            consulta = consulta.with_for_update()
        return (await self.sesion.execute(consulta)).scalar_one_or_none()

    async def cargo_visible(
        self, cargo_id: uuid.UUID, principal: Principal, *, bloquear: bool = False
    ) -> CargoPago | None:
        citas = RepositorioAgenda(self.sesion).consulta_autorizada(principal).subquery()
        consulta = select(CargoPago).where(
            CargoPago.id == cargo_id,
            CargoPago.clinica_id == principal.clinica_id,
            CargoPago.cita_id.in_(select(citas.c.id)),
        )
        if bloquear:
            consulta = consulta.with_for_update()
        return (await self.sesion.execute(consulta)).scalar_one_or_none()

    async def total_comprometido(self, cargo_id: uuid.UUID) -> Decimal:
        total = await self.sesion.scalar(
            select(func.coalesce(func.sum(Pago.importe), 0)).where(
                Pago.cargo_id == cargo_id, Pago.estado != "REJECTED"
            )
        )
        return Decimal("0") if total is None else total

    async def totales_cargo(self, cargo_id: uuid.UUID) -> tuple[Decimal, Decimal]:
        fila = await self.sesion.execute(
            select(
                func.coalesce(
                    func.sum(case((Pago.estado == "CONFIRMED", Pago.importe), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((Pago.estado != "REJECTED", Pago.importe), else_=0)), 0
                ),
            ).where(Pago.cargo_id == cargo_id)
        )
        confirmado, comprometido = fila.one()
        return Decimal(confirmado), Decimal(comprometido)

    async def historial(self, pago_id: uuid.UUID) -> list[PagoHistorial]:
        filas = await self.sesion.execute(
            select(PagoHistorial)
            .where(PagoHistorial.pago_id == pago_id)
            .order_by(PagoHistorial.secuencia)
        )
        return list(filas.scalars())

    async def comprobantes(self, pago_id: uuid.UUID) -> list[PagoComprobante]:
        filas = await self.sesion.execute(
            select(PagoComprobante)
            .where(PagoComprobante.pago_id == pago_id)
            .order_by(PagoComprobante.cargado_en, PagoComprobante.id)
        )
        return list(filas.scalars())

    async def comprobante_visible(
        self, comprobante_id: uuid.UUID, principal: Principal
    ) -> PagoComprobante | None:
        pago_visible = self.consulta(principal).with_only_columns(Pago.id).subquery()
        return (
            await self.sesion.execute(
                select(PagoComprobante)
                .join(pago_visible, pago_visible.c.id == PagoComprobante.pago_id)
                .where(PagoComprobante.id == comprobante_id)
            )
        ).scalar_one_or_none()

    async def proxima_secuencia_historial(self, pago_id: uuid.UUID) -> int:
        ultima = await self.sesion.scalar(
            select(func.max(PagoHistorial.secuencia)).where(PagoHistorial.pago_id == pago_id)
        )
        return (ultima or 0) + 1

    async def listar_detallado(
        self,
        principal: Principal,
        limite: int,
        desplazamiento: int,
        estado: str | None = None,
    ) -> tuple[list[tuple[Pago, str, datetime, Decimal | None, Decimal, Decimal]], int]:
        """Pagos con el nombre del paciente y la fecha de la cita, dentro del ámbito."""
        consulta = self.consulta(principal)
        if estado is not None:
            consulta = consulta.where(Pago.estado == estado)
        total = int(
            (
                await self.sesion.execute(select(func.count()).select_from(consulta.subquery()))
            ).scalar_one()
        )
        cargos_visibles = (
            self.consulta(principal)
            .with_only_columns(Pago.cargo_id)
            .where(Pago.cargo_id.is_not(None))
        )
        agregados = (
            select(
                Pago.cargo_id.label("cargo_id"),
                func.sum(case((Pago.estado == "CONFIRMED", Pago.importe), else_=0)).label(
                    "total_confirmado"
                ),
                func.sum(case((Pago.estado != "REJECTED", Pago.importe), else_=0)).label(
                    "total_comprometido"
                ),
            )
            .where(Pago.cargo_id.in_(select(cargos_visibles.subquery().c.cargo_id)))
            .group_by(Pago.cargo_id)
            .subquery()
        )
        filas = await self.sesion.execute(
            consulta.add_columns(
                Paciente.nombre,
                Paciente.apellido,
                Cita.inicio,
                CargoPago.total_acordado,
                func.coalesce(agregados.c.total_confirmado, 0),
                func.coalesce(agregados.c.total_comprometido, 0),
            )
            .join(Cita, Cita.id == Pago.cita_id)
            .join(Paciente, Paciente.id == Cita.paciente_id)
            .outerjoin(CargoPago, CargoPago.id == Pago.cargo_id)
            .outerjoin(agregados, agregados.c.cargo_id == Pago.cargo_id)
            .order_by(Pago.creado_en.desc(), Pago.id)
            .limit(limite)
            .offset(desplazamiento)
        )
        return [
            (f[0], f"{f[1]} {f[2]}".strip(), f[3], f[4], Decimal(f[5]), Decimal(f[6]))
            for f in filas.all()
        ], total

    async def listar_cargos(
        self,
        principal: Principal,
        limite: int,
        desplazamiento: int,
        cita_id: uuid.UUID | None = None,
        vencidos: bool = False,
    ) -> tuple[list[tuple[CargoPago, str, datetime, Decimal, Decimal, bool]], int]:
        citas = RepositorioAgenda(self.sesion).consulta_autorizada(principal).subquery()
        ids_en_ambito = select(CargoPago.id).where(
            CargoPago.clinica_id == principal.clinica_id,
            CargoPago.cita_id.in_(select(citas.c.id)),
        )
        if cita_id is not None:
            ids_en_ambito = ids_en_ambito.where(CargoPago.cita_id == cita_id)
        pagos = (
            select(
                Pago.cargo_id.label("cargo_id"),
                func.sum(case((Pago.estado == "CONFIRMED", Pago.importe), else_=0)).label(
                    "total_confirmado"
                ),
                func.sum(case((Pago.estado != "REJECTED", Pago.importe), else_=0)).label(
                    "total_comprometido"
                ),
            )
            .where(Pago.cargo_id.in_(ids_en_ambito))
            .group_by(Pago.cargo_id)
            .subquery()
        )
        fecha_local = cast(
            func.timezone(func.coalesce(Sede.zona_horaria, Clinica.zona_horaria), func.now()),
            Date,
        )
        total_confirmado = func.coalesce(pagos.c.total_confirmado, 0)
        vencido = and_(
            CargoPago.fecha_vencimiento.is_not(None),
            CargoPago.fecha_vencimiento < fecha_local,
            CargoPago.total_acordado.is_not(None),
            CargoPago.total_acordado > total_confirmado,
        )
        consulta = (
            select(
                CargoPago,
                Paciente.nombre,
                Paciente.apellido,
                Cita.inicio,
                total_confirmado,
                func.coalesce(pagos.c.total_comprometido, 0),
                vencido,
            )
            .join(Cita, Cita.id == CargoPago.cita_id)
            .join(Paciente, Paciente.id == Cita.paciente_id)
            .join(Clinica, Clinica.id == CargoPago.clinica_id)
            .outerjoin(Sede, Sede.id == Cita.sede_id)
            .outerjoin(pagos, pagos.c.cargo_id == CargoPago.id)
            .where(CargoPago.id.in_(ids_en_ambito))
        )
        if vencidos:
            consulta = consulta.where(vencido)
        total = int(
            (
                await self.sesion.execute(
                    select(func.count()).select_from(
                        consulta.with_only_columns(CargoPago.id).order_by(None).subquery()
                    )
                )
            ).scalar_one()
        )
        filas = await self.sesion.execute(
            consulta.order_by(CargoPago.fecha_vencimiento.asc().nulls_last(), CargoPago.id)
            .limit(limite)
            .offset(desplazamiento)
        )
        return [
            (
                fila[0],
                f"{fila[1]} {fila[2]}".strip(),
                fila[3],
                Decimal(fila[4]),
                Decimal(fila[5]),
                bool(fila[6]),
            )
            for fila in filas.all()
        ], total

    async def resumen(self, principal: Principal) -> dict[str, Decimal]:
        pagos = self.consulta(principal).subquery()
        filas = await self.sesion.execute(
            select(pagos.c.estado, func.sum(pagos.c.importe)).group_by(pagos.c.estado)
        )
        return {str(estado): Decimal(importe) for estado, importe in filas}

    async def resumen_diario_exportable(
        self,
        principal: Principal,
        desde: date,
        hasta: date,
        sede_id: uuid.UUID | None = None,
    ) -> list[tuple[date, str, str, str, int, Decimal, Decimal]]:
        """Agregados diarios de pagos en hora local, sin datos de pacientes."""
        citas = RepositorioAgenda(self.sesion).consulta_autorizada(principal).subquery()
        fecha_local = cast(
            func.timezone(func.coalesce(Sede.zona_horaria, Clinica.zona_horaria), Pago.creado_en),
            Date,
        )
        consulta = (
            select(
                fecha_local.label("fecha_local"),
                Pago.estado,
                Pago.metodo,
                Pago.moneda,
                func.count(Pago.id),
                func.sum(Pago.importe),
                func.sum(case((Pago.estado == "CONFIRMED", Pago.importe), else_=0)),
            )
            .join(Cita, Cita.id == Pago.cita_id)
            .join(Clinica, Clinica.id == Pago.clinica_id)
            .outerjoin(Sede, Sede.id == Cita.sede_id)
            .where(
                Pago.clinica_id == principal.clinica_id,
                Pago.cita_id.in_(select(citas.c.id)),
                fecha_local >= desde,
                fecha_local < hasta,
            )
        )
        if sede_id is not None:
            consulta = consulta.where(Cita.sede_id == sede_id)
        consulta = consulta.group_by(fecha_local, Pago.estado, Pago.metodo, Pago.moneda).order_by(
            fecha_local, Pago.estado, Pago.metodo, Pago.moneda
        )
        filas = (await self.sesion.execute(consulta)).all()
        return [
            (
                fecha,
                estado,
                metodo,
                moneda,
                int(cantidad),
                Decimal(registrado),
                Decimal(confirmado),
            )
            for fecha, estado, metodo, moneda, cantidad, registrado, confirmado in filas
        ]

    async def abiertos_de_paciente(
        self, principal: Principal, paciente_id: uuid.UUID, estados: tuple[str, ...]
    ) -> list[tuple[Decimal, str, str, Any]]:
        """Pagos sin cerrar de un paciente, dentro del ambito del principal."""
        pagos = self.consulta(principal).where(Pago.estado.in_(estados)).subquery()
        filas = await self.sesion.execute(
            select(pagos.c.importe, pagos.c.moneda, pagos.c.estado, Cita.inicio)
            .join(Cita, Cita.id == pagos.c.cita_id)
            .where(Cita.paciente_id == paciente_id)
            .order_by(Cita.inicio)
        )
        return [(importe, moneda, estado, inicio) for importe, moneda, estado, inicio in filas]
