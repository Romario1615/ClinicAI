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
    solo_sin_avisar: Annotated[
        bool,
        Query(
            description=(
                "Solo las entradas con una oferta activa que no se pudo comunicar. "
                "Es la cola de llamadas pendientes de recepcion."
            )
        ),
    ] = False,
) -> PaginaEspera:
    """Lista la cola de espera.

    `solo_sin_avisar` existe porque una oferta que no se pudo comunicar
    **retiene el turno y no la ve nadie**: el paciente no recibio nada -- no
    tiene consentimiento para mensajes automaticos -- y sin este filtro hay que
    rebuscarla entre las demas. Con el, es una lista de llamadas por hacer.
    """
    return await panel.listar_espera(
        sesion, principal, limite, desplazamiento, solo_sin_avisar=solo_sin_avisar
    )


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
