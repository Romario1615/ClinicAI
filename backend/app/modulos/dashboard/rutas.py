import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, ValidationError

from app.modulos.dashboard.esquemas import FiltroDashboard, ResumenDashboard
from app.modulos.dashboard.repositorio import resumir
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Sesion, exige_permiso
from app.nucleo.errores import DatosInvalidos

enrutador = APIRouter(prefix="/dashboard", tags=["dashboard"])
PuedeLeer = Annotated[Principal, Depends(exige_permiso("dashboard.leer"))]


def filtro_dashboard(desde: AwareDatetime, hasta: AwareDatetime) -> FiltroDashboard:
    """Construye el filtro traduciendo el fallo de validacion a `DatosInvalidos`.

    No se declara el modelo como `Depends()` directamente: cuando su
    `model_validator` rechaza el rango, FastAPI **no** convierte esa excepcion
    en un 422 -- solo traduce los fallos de su propio analisis de la peticion --
    y el error escapa como un 500. Un rango invertido es entrada invalida del
    cliente, no una averia del servidor, y tiene que salir con el contrato de
    error del proyecto como el resto de los endpoints.
    """
    try:
        return FiltroDashboard(desde=desde, hasta=hasta)
    except ValidationError as exc:
        primero = exc.errors()[0]
        raise DatosInvalidos(str(primero.get("msg", "Rango de fechas invalido."))) from exc


@enrutador.get("/", response_model=ResumenDashboard)
async def resumen(
    principal: PuedeLeer,
    sesion: Sesion,
    filtro: Annotated[FiltroDashboard, Depends(filtro_dashboard)],
    sede_id: uuid.UUID | None = None,
    profesional_id: uuid.UUID | None = None,
) -> ResumenDashboard:
    return await resumir(sesion, principal, filtro, sede_id, profesional_id)
