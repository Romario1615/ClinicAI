"""API clínica del odontograma; cada lectura y cambio queda auditado."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy import exists, select

from app.modulos.historia.especialidades import exige_modulo
from app.modulos.odontologia.esquemas import (
    NuevaVersionOdontograma,
    OdontogramaInicial,
    OdontogramaSalida,
)
from app.modulos.odontologia.modelos import Odontograma
from app.modulos.odontologia.servicios import ServicioOdontograma
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion

enrutador = APIRouter(prefix="/odontologia", tags=["odontología"])
PuedeLeer = Annotated[Principal, Depends(exige_modulo("odontograma", "odontograma.leer"))]
PuedeEscribir = Annotated[Principal, Depends(exige_modulo("odontograma", "odontograma.escribir"))]


def _salida(fila: Odontograma) -> OdontogramaSalida:
    return OdontogramaSalida(
        id=fila.id,
        paciente_id=fila.paciente_id,
        profesional_id=fila.profesional_id,
        version=fila.version,
        vigente=fila.vigente,
        motivo_modificacion=fila.motivo_modificacion,
        procedimiento_id=fila.procedimiento_id,
        creado_en=fila.creado_en,
        denticion=fila.denticion,
        piezas=fila.piezas,
        nivel_sensibilidad=fila.nivel_sensibilidad,
    )


async def _hay_version_n3(
    sesion: Sesion,
    paciente_id: uuid.UUID,
    principal: Principal,
    version: int | None = None,
    *,
    solo_vigente: bool = True,
) -> bool:
    if principal.tiene_permiso("historia_clinica.leer_sensible"):
        return False
    criterios = [
        Odontograma.paciente_id == paciente_id,
        Odontograma.clinica_id == principal.clinica_id,
        Odontograma.nivel_sensibilidad == "N3",
    ]
    if version is None and solo_vigente:
        criterios.append(Odontograma.vigente.is_(True))
    elif version is not None:
        criterios.append(Odontograma.version == version)
    consulta = select(exists().where(*criterios))
    return bool(await sesion.scalar(consulta))


@enrutador.get(
    "/pacientes/{paciente_id}/odontograma",
    response_model=OdontogramaSalida | None,
    summary="Leer la versión vigente o una versión histórica",
)
async def obtener_odontograma(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> OdontogramaSalida | None:
    servicio = ServicioOdontograma(sesion, reloj)
    fila = await servicio.obtener(paciente_id, principal=principal, version=version)
    nivel_auditoria = (
        NivelSensibilidad(fila.nivel_sensibilidad)
        if fila is not None
        else (
            NivelSensibilidad.CLINICO_SENSIBLE
            if await _hay_version_n3(sesion, paciente_id, principal, version)
            else NivelSensibilidad.CLINICO
        )
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="odontograma",
                entidad_id=fila.id if fila is not None else None,
                paciente_id=paciente_id,
                nivel_sensibilidad=nivel_auditoria,
                version=fila.version if fila is not None else None,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila) if fila is not None else None


@enrutador.get(
    "/pacientes/{paciente_id}/odontograma/versiones",
    response_model=list[OdontogramaSalida],
    summary="Consultar las versiones conservadas del odontograma",
)
async def listar_versiones_odontograma(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> list[OdontogramaSalida]:
    filas = await ServicioOdontograma(sesion, reloj).listar_versiones(
        paciente_id, principal=principal
    )
    nivel_auditoria = (
        NivelSensibilidad.CLINICO_SENSIBLE
        if any(fila.nivel_sensibilidad == "N3" for fila in filas)
        or await _hay_version_n3(sesion, paciente_id, principal, solo_vigente=False)
        else NivelSensibilidad.CLINICO
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="odontograma",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=nivel_auditoria,
                version=fila.version,
            )
            for fila in filas
        ]
        or [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="odontograma",
                paciente_id=paciente_id,
                nivel_sensibilidad=nivel_auditoria,
                versiones=0,
            )
        ]
    )
    await sesion.commit()
    return [_salida(fila) for fila in filas]


@enrutador.post(
    "/pacientes/{paciente_id}/odontograma",
    response_model=OdontogramaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar la primera versión del odontograma",
)
async def crear_odontograma(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: OdontogramaInicial,
) -> OdontogramaSalida:
    fila = await ServicioOdontograma(sesion, reloj).crear(
        paciente_id,
        datos,
        principal=principal,
        nivel_sensibilidad=datos.nivel_sensibilidad,
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_VERSIONADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="odontograma",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad(fila.nivel_sensibilidad),
                version=fila.version,
                denticion=fila.denticion,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


@enrutador.post(
    "/pacientes/{paciente_id}/odontograma/versiones",
    response_model=OdontogramaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una versión nueva sin sobrescribir el historial",
    responses={409: {"description": "La versión base ya no está vigente"}},
)
async def versionar_odontograma(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: NuevaVersionOdontograma,
) -> OdontogramaSalida:
    fila = await ServicioOdontograma(sesion, reloj).versionar(
        paciente_id,
        datos,
        version_base=datos.version_base,
        motivo=datos.motivo,
        principal=principal,
        nivel_sensibilidad=datos.nivel_sensibilidad,
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_VERSIONADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="odontograma",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad(fila.nivel_sensibilidad),
                version=fila.version,
                version_base=datos.version_base,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


__all__ = ["enrutador"]
