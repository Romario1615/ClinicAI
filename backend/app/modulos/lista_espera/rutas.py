import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.modulos.lista_espera import panel
from app.modulos.lista_espera.esquemas import (
    AccionEspera,
    DatosEspera,
    PaginaEspera,
    RespuestaEspera,
)
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import RelojActual, Sesion, exige_permiso

enrutador = APIRouter(prefix="/lista-espera", tags=["lista de espera"])
PuedeGestionar = Annotated[Principal, Depends(exige_permiso("lista_espera.gestionar"))]
Clave = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


@enrutador.get("/", response_model=PaginaEspera)
async def listar(
    principal: PuedeGestionar,
    sesion: Sesion,
    limite: Annotated[int, Query(ge=1, le=100)] = 25,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaEspera:
    return await panel.listar_espera(sesion, principal, limite, desplazamiento)


@enrutador.post("/", response_model=RespuestaEspera, status_code=201)
async def anotar(
    datos: DatosEspera,
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaEspera:
    resultado = await panel.anotar(sesion, principal, reloj, datos, clave)
    await sesion.commit()
    return resultado


@enrutador.post("/{entrada_id}/resolver", response_model=RespuestaEspera)
async def resolver(
    entrada_id: uuid.UUID,
    datos: AccionEspera,
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    clave: Clave,
) -> RespuestaEspera:
    resultado = await panel.resolver(sesion, principal, reloj, entrada_id, datos, clave)
    await sesion.commit()
    return resultado
