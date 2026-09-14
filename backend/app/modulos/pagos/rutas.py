import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.modulos.pagos.esquemas import CambioPago, DatosPago, PaginaPagos, RespuestaPago
from app.modulos.pagos.repositorio import RepositorioPagos
from app.modulos.pagos.servicios import ServicioPagos
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import RelojActual, Sesion, exige_permiso

enrutador = APIRouter(prefix="/pagos", tags=["pagos"])
PuedeLeer = Annotated[Principal, Depends(exige_permiso("pago.leer"))]
PuedeRegistrar = Annotated[Principal, Depends(exige_permiso("pago.registrar"))]
PuedeValidar = Annotated[Principal, Depends(exige_permiso("pago.validar"))]
Clave = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


@enrutador.get("/", response_model=PaginaPagos)
async def listar(
    principal: PuedeLeer,
    sesion: Sesion,
    limite: Annotated[int, Query(ge=1, le=100)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaPagos:
    filas, total = await RepositorioPagos(sesion).listar(principal, limite, desplazamiento)
    return PaginaPagos(elementos=[RespuestaPago.model_validate(f) for f in filas], total=total)


@enrutador.post("/", response_model=RespuestaPago, status_code=201)
async def registrar(
    datos: DatosPago,
    principal: PuedeRegistrar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaPago:
    pago = await ServicioPagos(sesion, reloj).registrar(datos, principal, clave)
    await sesion.commit()
    return RespuestaPago.model_validate(pago)


@enrutador.post("/{pago_id}/estado", response_model=RespuestaPago)
async def cambiar(
    pago_id: uuid.UUID,
    datos: CambioPago,
    principal: PuedeValidar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaPago:
    pago = await ServicioPagos(sesion, reloj).cambiar(pago_id, datos, principal, clave)
    await sesion.commit()
    return RespuestaPago.model_validate(pago)
