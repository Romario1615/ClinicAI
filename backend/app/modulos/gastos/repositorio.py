"""Acceso a datos del libro de gastos.

El filtro de ambito va en el `WHERE`, siempre:

* Solo la clinica del principal.
* Un gasto de una sede, solo si la sede esta en el ambito.
* Un gasto de toda la clinica (sin sede), solo con ambito de todas las
  sedes: quien trabaja en una sucursal no ve la nomina de la central.
* Ambito vacio, nada (CLAUDE.md, regla 7; `Ambito.esta_vacio`).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, false, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.gastos.modelos import Gasto
from app.modulos.organizacion.modelos import Clinica, Sede
from app.nucleo.autorizacion import Principal


def _filtro_ambito(principal: Principal) -> ColumnElement[bool]:
    if principal.clinica_id is None:
        return false()
    ambito = principal.ambito
    if ambito.todas_las_sedes:
        alcance: ColumnElement[bool] = true()
    elif ambito.sedes:
        alcance = and_(Gasto.sede_id.is_not(None), Gasto.sede_id.in_(ambito.sedes))
    else:
        alcance = false()
    return and_(Gasto.clinica_id == principal.clinica_id, alcance)


class RepositorioGastos:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    def consulta(
        self,
        principal: Principal,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        sede_id: uuid.UUID | None = None,
        categoria: str | None = None,
        incluir_anulados: bool = False,
    ) -> Select[Any]:
        consulta = select(Gasto).where(_filtro_ambito(principal))
        if desde is not None:
            consulta = consulta.where(Gasto.fecha >= desde)
        if hasta is not None:
            consulta = consulta.where(Gasto.fecha < hasta)
        if sede_id is not None:
            consulta = consulta.where(Gasto.sede_id == sede_id)
        if categoria is not None:
            consulta = consulta.where(Gasto.categoria == categoria)
        if not incluir_anulados:
            consulta = consulta.where(Gasto.estado == "REGISTRADO")
        return consulta

    async def listar(
        self,
        principal: Principal,
        *,
        limite: int,
        desplazamiento: int,
        **filtros: Any,
    ) -> tuple[list[Gasto], int, Decimal]:
        base = self.consulta(principal, **filtros).subquery()
        total, importe = (
            await self._sesion.execute(
                select(
                    func.count(base.c.id),
                    func.coalesce(
                        func.sum(base.c.importe).filter(base.c.estado == "REGISTRADO"), 0
                    ),
                )
            )
        ).one()
        filas = (
            (
                await self._sesion.execute(
                    self.consulta(principal, **filtros)
                    .order_by(Gasto.fecha.desc(), Gasto.creado_en.desc(), Gasto.id)
                    .limit(limite)
                    .offset(desplazamiento)
                )
            )
            .scalars()
            .all()
        )
        return list(filas), int(total), Decimal(importe)

    async def obtener_para_anular(self, principal: Principal, gasto_id: uuid.UUID) -> Gasto | None:
        consulta = (
            select(Gasto).where(Gasto.id == gasto_id, _filtro_ambito(principal)).with_for_update()
        )
        return (await self._sesion.execute(consulta)).scalar_one_or_none()

    async def sede_de_la_clinica(self, principal: Principal, sede_id: uuid.UUID) -> Sede | None:
        """La sede, si es de la clinica del principal y esta en su ambito."""
        if principal.clinica_id is None or not principal.ambito.cubre_sede(sede_id):
            return None
        return (
            await self._sesion.execute(
                select(Sede).where(Sede.id == sede_id, Sede.clinica_id == principal.clinica_id)
            )
        ).scalar_one_or_none()

    async def zona_horaria(self, principal: Principal, sede_id: uuid.UUID | None) -> str:
        """Zona de la sede si la tiene; si no, la de la clinica."""
        clinica = (
            await self._sesion.execute(
                select(Clinica.zona_horaria).where(Clinica.id == principal.clinica_id)
            )
        ).scalar_one()
        if sede_id is None:
            return str(clinica)
        propia = (
            await self._sesion.execute(select(Sede.zona_horaria).where(Sede.id == sede_id))
        ).scalar_one_or_none()
        return str(propia or clinica)

    async def totales_por_dia(
        self, principal: Principal, desde: date, hasta: date, sede_id: uuid.UUID | None
    ) -> list[tuple[date, Decimal]]:
        base = self.consulta(principal, desde=desde, hasta=hasta, sede_id=sede_id).subquery()
        filas = await self._sesion.execute(
            select(base.c.fecha, func.sum(base.c.importe))
            .group_by(base.c.fecha)
            .order_by(base.c.fecha)
        )
        return [(fecha, Decimal(total)) for fecha, total in filas]

    async def totales_por_categoria(
        self, principal: Principal, desde: date, hasta: date, sede_id: uuid.UUID | None
    ) -> list[tuple[str, Decimal, int]]:
        base = self.consulta(principal, desde=desde, hasta=hasta, sede_id=sede_id).subquery()
        filas = await self._sesion.execute(
            select(base.c.categoria, func.sum(base.c.importe), func.count(base.c.id))
            .group_by(base.c.categoria)
            .order_by(func.sum(base.c.importe).desc(), base.c.categoria)
        )
        return [(categoria, Decimal(total), int(cantidad)) for categoria, total, cantidad in filas]
