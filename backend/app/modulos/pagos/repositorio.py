import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.pagos.modelos import Pago
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

    async def resumen(self, principal: Principal) -> dict[str, Decimal]:
        pagos = self.consulta(principal).subquery()
        filas = await self.sesion.execute(
            select(pagos.c.estado, func.sum(pagos.c.importe)).group_by(pagos.c.estado)
        )
        return {str(estado): Decimal(importe) for estado, importe in filas}
