"""Reglas del libro de gastos y del flujo de caja.

Es la unica via de escritura (CLAUDE.md, seccion 4): valida la sede y la
fecha, aplica la idempotencia, escribe y audita en la misma transaccion.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.gastos.esquemas import (
    AnulacionGasto,
    CategoriaFlujo,
    DatosGasto,
    DiaFlujo,
    FlujoCaja,
)
from app.modulos.gastos.modelos import Gasto
from app.modulos.gastos.repositorio import RepositorioGastos
from app.modulos.pagos.repositorio import RepositorioPagos
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PermisoDenegado,
    RecursoNoEncontrado,
)
from app.nucleo.operaciones import completar_operacion, iniciar_operacion
from app.nucleo.reloj import Reloj

DIAS_MAXIMOS_FLUJO = 366
BASE_DEL_FLUJO = (
    "Base de caja: ingresos son los pagos confirmados según la fecha local en que se "
    "registraron; gastos, los registrados y no anulados según su fecha. No incluye "
    "devengos, depreciaciones ni impuestos: no es un estado de resultados."
)
CENTAVO = Decimal("0.01")


class ServicioGastos:
    def __init__(self, sesion: AsyncSession, reloj: Reloj) -> None:
        self.sesion = sesion
        self.reloj = reloj
        self.repo = RepositorioGastos(sesion)

    async def listar(
        self, principal: Principal, *, limite: int, desplazamiento: int, **filtros: Any
    ) -> tuple[list[Gasto], int, Decimal]:
        """Pagina del libro dentro del ambito, con el total no anulado del filtro."""
        return await self.repo.listar(
            principal, limite=limite, desplazamiento=desplazamiento, **filtros
        )

    async def registrar(self, datos: DatosGasto, principal: Principal, clave: str) -> Gasto:
        if not principal.tiene_permiso("gasto.registrar"):
            raise PermisoDenegado("No puede registrar gastos.")
        if datos.sede_id is not None:
            if await self.repo.sede_de_la_clinica(principal, datos.sede_id) is None:
                raise RecursoNoEncontrado("La sede indicada no existe.")
        elif not principal.ambito.todas_las_sedes:
            # Un gasto de toda la clinica solo lo registra quien la ve entera.
            raise DatosInvalidos("Indique la sede del gasto.")
        zona = await self.repo.zona_horaria(principal, datos.sede_id)
        if datos.fecha > self.reloj.ahora_en(zona).date():
            raise DatosInvalidos("La fecha del gasto no puede ser futura.")

        operacion = await iniciar_operacion(
            self.sesion,
            principal,
            self.reloj,
            "gasto.registrar",
            clave,
            datos.model_dump(mode="json"),
        )
        if operacion.respuesta:
            existente = await self.sesion.get(Gasto, uuid.UUID(str(operacion.respuesta["id"])))
            if existente is None:  # pragma: sin cobertura - la clave apunta a un gasto creado
                raise RecursoNoEncontrado("El gasto registrado ya no existe.")
            return existente

        gasto = Gasto(
            clinica_id=principal.clinica_id,
            creado_por=principal.actor_id,
            creado_en=self.reloj.ahora(),
            **datos.model_dump(),
        )
        self.sesion.add(gasto)
        await self.sesion.flush()
        await self._auditar(gasto, principal, AccionAuditada.GASTO_REGISTRADO)
        completar_operacion(operacion, {"id": str(gasto.id)}, self.reloj)
        return gasto

    async def anular(
        self, gasto_id: uuid.UUID, datos: AnulacionGasto, principal: Principal
    ) -> Gasto:
        if not principal.tiene_permiso("gasto.registrar"):
            raise PermisoDenegado("No puede anular gastos.")
        gasto = await self.repo.obtener_para_anular(principal, gasto_id)
        if gasto is None:
            raise RecursoNoEncontrado("El gasto indicado no existe.")
        if gasto.estado == "ANULADO":
            raise ConflictoEstado("El gasto ya estaba anulado.")
        gasto.estado = "ANULADO"
        gasto.anulado_por = principal.actor_id
        gasto.anulado_en = self.reloj.ahora()
        gasto.motivo_anulacion = datos.motivo
        await self.sesion.flush()
        await self._auditar(gasto, principal, AccionAuditada.GASTO_ANULADO, motivo=datos.motivo)
        return gasto

    async def flujo(
        self, principal: Principal, desde: date, hasta: date, sede_id: uuid.UUID | None
    ) -> FlujoCaja:
        dias = (hasta - desde).days
        if dias < 1 or dias > DIAS_MAXIMOS_FLUJO:
            raise DatosInvalidos("El periodo debe ser de 1 a 366 días; hasta es exclusivo.")
        if sede_id is not None and await self.repo.sede_de_la_clinica(principal, sede_id) is None:
            raise RecursoNoEncontrado("La sede indicada no existe.")

        ingresos_por_dia: dict[date, Decimal] = defaultdict(Decimal)
        for (
            fecha,
            _estado,
            _metodo,
            _moneda,
            _cantidad,
            _registrado,
            confirmado,
        ) in await RepositorioPagos(self.sesion).resumen_diario_exportable(
            principal, desde, hasta, sede_id
        ):
            ingresos_por_dia[fecha] += confirmado
        gastos_por_dia = dict(await self.repo.totales_por_dia(principal, desde, hasta, sede_id))
        categorias = await self.repo.totales_por_categoria(principal, desde, hasta, sede_id)

        ingresos = sum(ingresos_por_dia.values(), Decimal(0))
        gastos = sum(gastos_por_dia.values(), Decimal(0))
        resultado = ingresos - gastos
        margen = (
            (resultado * 100 / ingresos).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if ingresos > 0
            else None
        )
        fechas = sorted(set(ingresos_por_dia) | set(gastos_por_dia))
        return FlujoCaja(
            desde=desde,
            hasta=hasta,
            moneda="USD",
            ingresos=ingresos.quantize(CENTAVO),
            gastos=gastos.quantize(CENTAVO),
            resultado=resultado.quantize(CENTAVO),
            margen_porcentaje=margen,
            por_dia=[
                DiaFlujo(
                    fecha=fecha,
                    ingresos=ingresos_por_dia.get(fecha, Decimal(0)).quantize(CENTAVO),
                    gastos=gastos_por_dia.get(fecha, Decimal(0)).quantize(CENTAVO),
                    resultado=(
                        ingresos_por_dia.get(fecha, Decimal(0))
                        - gastos_por_dia.get(fecha, Decimal(0))
                    ).quantize(CENTAVO),
                )
                for fecha in fechas
            ],
            por_categoria=[
                CategoriaFlujo.model_validate(
                    {"categoria": categoria, "total": total.quantize(CENTAVO), "cantidad": cantidad}
                )
                for categoria, total, cantidad in categorias
            ],
            base=BASE_DEL_FLUJO,
        )

    async def _auditar(
        self,
        gasto: Gasto,
        principal: Principal,
        accion: AccionAuditada,
        *,
        motivo: str | None = None,
    ) -> None:
        await RepositorioAuditoria(self.sesion).registrar(
            [
                construir_entrada(
                    accion=accion,
                    principal=principal,
                    ahora=self.reloj.ahora(),
                    entidad_tipo="gasto",
                    entidad_id=gasto.id,
                    sede_id=gasto.sede_id,
                    motivo=motivo,
                    categoria=gasto.categoria,
                    importe=str(gasto.importe),
                    estado_nuevo=gasto.estado,
                )
            ]
        )
