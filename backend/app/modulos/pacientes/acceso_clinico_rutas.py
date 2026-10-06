"""¿Puede quien pregunta ver los datos clínicos de este paciente?

La ficha muestra al paciente a quien tiene `paciente.leer_administrativo`, pero sus datos
clínicos exigen además relación asistencial vigente si quien pregunta es
profesional (`GuardiaClinica`). Sin esta consulta, la ficha pedía notas,
odontograma, planes e imágenes y recibía cuatro 404 seguidos.

No revela nada nuevo: solo responde por un paciente que ya está en el ámbito
del solicitante (fuera de él, 404 como siempre) y solo dice sí o no, sin
contenido clínico. Por eso no se audita como lectura clínica.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel

from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import RelojActual, Sesion, exige_permiso
from app.nucleo.errores import RecursoNoEncontrado, RelacionAsistencialRequerida

enrutador = APIRouter(prefix="/pacientes", tags=["pacientes"])

PuedeLeerPaciente = Annotated[Principal, Depends(exige_permiso("paciente.leer_administrativo"))]


class AccesoClinico(BaseModel):
    acceso_clinico: bool


@enrutador.get(
    "/{paciente_id}/acceso-clinico",
    response_model=AccesoClinico,
    summary="Saber si se pueden pedir los datos clínicos del paciente",
    responses={404: {"description": "No existe o está fuera de ámbito"}},
)
async def consultar_acceso_clinico(
    principal: PuedeLeerPaciente,
    sesion: Sesion,
    reloj: RelojActual,
    paciente_id: Annotated[uuid.UUID, Path(description="Identificador del paciente.")],
) -> AccesoClinico:
    guardia = GuardiaClinica(sesion)
    await guardia.paciente(principal, paciente_id)
    if principal.es_agente:
        return AccesoClinico(acceso_clinico=False)
    try:
        await guardia.exigir_relacion(principal, paciente_id, reloj.ahora())
    # La guardia ha señalado la falta de relación con 403 o con 404 indistinguible.
    except (RecursoNoEncontrado, RelacionAsistencialRequerida):
        return AccesoClinico(acceso_clinico=False)
    return AccesoClinico(acceso_clinico=True)


__all__ = ["enrutador"]
