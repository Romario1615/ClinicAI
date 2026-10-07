"""Rutas del libro de gastos y del flujo de caja.

* `GET /gastos` y `GET /gastos/flujo` exigen `gasto.leer`; el flujo cruza
  con los pagos, asi que exige ademas `pago.leer`.
* `POST /gastos` y `POST /gastos/{id}/anulacion` exigen `gasto.registrar`;
  el alta lleva `Idempotency-Key` porque un doble clic no puede duplicar un
  egreso.
* Fuera de ambito, 404 (nunca 403): un gasto ajeno no se distingue de uno
  inexistente.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.modulos.gastos.esquemas import (
    AnulacionGasto,
    CategoriaGasto,
    DatosGasto,
    FlujoCaja,
    GastoSalida,
    PaginaGastos,
)
from app.modulos.gastos.servicios import ServicioGastos
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import RelojActual, Sesion, exige_permiso

enrutador = APIRouter(prefix="/gastos", tags=["gastos"])

PuedeLeer = Annotated[Principal, Depends(exige_permiso("gasto.leer"))]
PuedeLeerPagos = Annotated[Principal, Depends(exige_permiso("pago.leer"))]
PuedeRegistrar = Annotated[Principal, Depends(exige_permiso("gasto.registrar"))]
Clave = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


@enrutador.get("", response_model=PaginaGastos, summary="Libro de gastos del ámbito")
async def listar(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    desde: Annotated[date | None, Query(description="Primer día incluido.")] = None,
    hasta: Annotated[date | None, Query(description="Último día, exclusivo.")] = None,
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
    categoria: Annotated[CategoriaGasto | None, Query()] = None,
    incluir_anulados: Annotated[bool, Query()] = False,
    limite: Annotated[int, Query(ge=1, le=100)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaGastos:
    gastos, total, importe = await ServicioGastos(sesion, reloj).listar(
        principal,
        limite=limite,
        desplazamiento=desplazamiento,
        desde=desde,
        hasta=hasta,
        sede_id=sede_id,
        categoria=categoria,
        incluir_anulados=incluir_anulados,
    )
    return PaginaGastos(
        elementos=[GastoSalida.model_validate(gasto) for gasto in gastos],
        total=total,
        importe_total=importe,
    )


@enrutador.get(
    "/flujo",
    response_model=FlujoCaja,
    summary="Flujo de caja del periodo: pagos confirmados menos gastos",
    responses={422: {"description": "El periodo solicitado no es válido"}},
)
async def flujo(
    principal: PuedeLeer,
    _pagos: PuedeLeerPagos,
    sesion: Sesion,
    reloj: RelojActual,
    desde: Annotated[date, Query(description="Primer día local incluido.")],
    hasta: Annotated[date, Query(description="Último día local, exclusivo.")],
    sede_id: Annotated[uuid.UUID | None, Query()] = None,
) -> FlujoCaja:
    return await ServicioGastos(sesion, reloj).flujo(principal, desde, hasta, sede_id)


@enrutador.post("", response_model=GastoSalida, status_code=201, summary="Registrar un gasto")
async def registrar(
    datos: DatosGasto,
    principal: PuedeRegistrar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> GastoSalida:
    gasto = await ServicioGastos(sesion, reloj).registrar(datos, principal, clave)
    respuesta = GastoSalida.model_validate(gasto)
    await sesion.commit()
    return respuesta


@enrutador.post(
    "/{gasto_id}/anulacion",
    response_model=GastoSalida,
    summary="Anular un gasto con motivo (no se borra)",
)
async def anular(
    gasto_id: uuid.UUID,
    datos: AnulacionGasto,
    principal: PuedeRegistrar,
    sesion: Sesion,
    reloj: RelojActual,
) -> GastoSalida:
    gasto = await ServicioGastos(sesion, reloj).anular(gasto_id, datos, principal)
    respuesta = GastoSalida.model_validate(gasto)
    await sesion.commit()
    return respuesta
