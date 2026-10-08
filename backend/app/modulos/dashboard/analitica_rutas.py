import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modulos.dashboard.analitica_servicios import AnaliticaDashboard, analizar
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import RelojActual, Sesion, exige_permiso

enrutador = APIRouter(prefix="/dashboard", tags=["analítica"])
PuedeLeer = Annotated[Principal, Depends(exige_permiso("dashboard.leer"))]


@enrutador.get("/analitica", response_model=AnaliticaDashboard)
async def analitica(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    dias: Annotated[int, Query(ge=30, le=365)] = 180,
    horizonte: Annotated[int, Query(ge=1, le=30)] = 14,
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
    especialidad_id: uuid.UUID | None = None,
    servicio_id: uuid.UUID | None = None,
) -> AnaliticaDashboard:
    return await analizar(
        sesion,
        principal,
        reloj.ahora(),
        dias,
        horizonte,
        sede_id,
        profesional_id,
        especialidad_id,
        servicio_id,
    )
