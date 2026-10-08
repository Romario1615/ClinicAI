from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.modulos.historia.especialidades import exige_modulo
from app.modulos.odontologia.periodontograma_esquemas import (
    PeriodontogramaNuevo,
    PeriodontogramaSalida,
)
from app.modulos.odontologia.periodontograma_servicios import ServicioPeriodontograma
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion

enrutador = APIRouter(
    prefix="/odontologia/pacientes/{paciente_id}/periodontogramas", tags=["periodoncia"]
)
PuedeLeer = Annotated[Principal, Depends(exige_modulo("periodoncia", "odontograma.leer"))]
PuedeEscribir = Annotated[Principal, Depends(exige_modulo("periodoncia", "odontograma.escribir"))]


async def auditar(
    principal: Principal,
    paciente_id: uuid.UUID,
    id_registro: uuid.UUID,
    nivel: str,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    escribir: bool = False,
) -> None:
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_VERSIONADO
                if escribir
                else AccionAuditada.ODONTOGRAMA_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="periodontograma",
                entidad_id=id_registro,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad(nivel),
            )
        ]
    )
    await sesion.commit()


@enrutador.get("", response_model=list[PeriodontogramaSalida])
async def listar(
    principal: PuedeLeer,
    paciente_id: uuid.UUID,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> list[PeriodontogramaSalida]:
    filas = await ServicioPeriodontograma(sesion, reloj).listar(principal, paciente_id)
    await auditar(
        principal,
        paciente_id,
        paciente_id,
        "N3" if any(f.nivel_sensibilidad == "N3" for f in filas) else "N2",
        sesion,
        reloj,
        auditor,
    )
    return filas


@enrutador.post("", response_model=PeriodontogramaSalida, status_code=status.HTTP_201_CREATED)
async def crear(
    principal: PuedeEscribir,
    paciente_id: uuid.UUID,
    datos: PeriodontogramaNuevo,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> PeriodontogramaSalida:
    fila = await ServicioPeriodontograma(sesion, reloj).crear(principal, paciente_id, datos)
    await auditar(
        principal, paciente_id, fila.id, fila.nivel_sensibilidad, sesion, reloj, auditor, True
    )
    return fila


@enrutador.get("/{id_registro}/pdf", response_class=Response)
async def pdf(
    principal: PuedeLeer,
    paciente_id: uuid.UUID,
    id_registro: uuid.UUID,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> Response:
    servicio = ServicioPeriodontograma(sesion, reloj)
    fila = await servicio.obtener(principal, paciente_id, id_registro)
    contenido = await servicio.pdf(principal, paciente_id, id_registro)
    await auditar(
        principal, paciente_id, id_registro, fila.nivel_sensibilidad, sesion, reloj, auditor
    )
    return Response(
        contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="periodontograma.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
