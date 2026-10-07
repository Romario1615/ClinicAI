"""Endpoints del ciclo de vida de los planes de tratamiento.

Borrador -> propuesto -> aceptado (con constancia) -> completado, o
cancelado con motivo. Toda lectura y todo cambio quedan en auditoria. Solo el
profesional responsable cambia el estado del plan; completar un
procedimiento con hallazgo genera una version nueva del odontograma.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import exists, select

from app.modulos.historia.especialidades import exige_modulo
from app.modulos.odontologia.modelos import PlantillaPlan, PlanTratamiento, ProcedimientoPlan
from app.modulos.odontologia.planes_esquemas import (
    AceptacionPlan,
    AtencionControl,
    Cancelacion,
    CompletarProcedimiento,
    PlanNuevo,
    PlanSalida,
    PlantillaNueva,
    PlantillaSalida,
    ProcedimientoNuevo,
    ProcedimientoPlanSalida,
)
from app.modulos.odontologia.planes_servicios import ServicioPlanesTratamiento
from app.nucleo.auditoria import AccionAuditada, EntradaAuditoria, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion

enrutador_planes = APIRouter(prefix="/odontologia", tags=["planes de tratamiento"])
PuedeLeer = Annotated[Principal, Depends(exige_modulo("planes", "plan_tratamiento.leer"))]
PuedeEscribir = Annotated[Principal, Depends(exige_modulo("planes", "plan_tratamiento.escribir"))]


def _salida(plan: PlanTratamiento, procedimientos: list[ProcedimientoPlan]) -> PlanSalida:
    return PlanSalida(
        id=plan.id,
        paciente_id=plan.paciente_id,
        profesional_id=plan.profesional_id,
        titulo=plan.titulo,
        estado=plan.estado,
        moneda=plan.moneda,
        observaciones=plan.observaciones,
        nivel_sensibilidad=plan.nivel_sensibilidad,
        propuesto_en=plan.propuesto_en,
        aceptado_en=plan.aceptado_en,
        aceptacion_medio=plan.aceptacion_medio,
        aceptacion_referencia=plan.aceptacion_referencia,
        completado_en=plan.completado_en,
        cancelado_en=plan.cancelado_en,
        motivo_cancelacion=plan.motivo_cancelacion,
        creado_en=plan.creado_en,
        procedimientos=[
            ProcedimientoPlanSalida(
                id=item.id,
                fase=item.fase,
                orden=item.orden,
                pieza=item.pieza,
                caras=item.caras,
                servicio_id=item.servicio_id,
                descripcion=item.descripcion,
                precio=item.precio,
                estado=item.estado,
                hallazgo_resultante=item.hallazgo_resultante,
                cita_id=item.cita_id,
                completado_en=item.completado_en,
                control_recomendado_en=item.control_recomendado_en,
                control_atendido_en=item.control_atendido_en,
                control_nota=item.control_nota,
                cancelado_en=item.cancelado_en,
                motivo_cancelacion=item.motivo_cancelacion,
            )
            for item in procedimientos
        ],
    )


@enrutador_planes.get(
    "/pacientes/{paciente_id}/planes-tratamiento",
    response_model=list[PlanSalida],
    summary="Consultar planes de tratamiento de un paciente",
)
async def listar_planes(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> list[PlanSalida]:
    filas = await ServicioPlanesTratamiento(sesion, reloj).listar(paciente_id, principal=principal)
    hay_n3_oculto = False
    if not principal.tiene_permiso("historia_clinica.leer_sensible"):
        hay_n3_oculto = bool(
            await sesion.scalar(
                select(
                    exists().where(
                        PlanTratamiento.paciente_id == paciente_id,
                        PlanTratamiento.clinica_id == principal.clinica_id,
                        PlanTratamiento.nivel_sensibilidad == "N3",
                    )
                )
            )
        )
    entradas = [
        construir_entrada(
            accion=AccionAuditada.PLAN_CONSULTADO,
            principal=principal,
            ahora=reloj.ahora(),
            entidad_tipo="plan_tratamiento",
            entidad_id=plan.id,
            paciente_id=paciente_id,
            nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
            estado=plan.estado,
        )
        for plan, _ in filas
    ]
    if hay_n3_oculto:
        entradas.append(
            construir_entrada(
                accion=AccionAuditada.PLAN_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="paciente",
                entidad_id=paciente_id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO_SENSIBLE,
                planes_sensibles_filtrados=True,
            )
        )
    if not entradas:
        entradas.append(
            construir_entrada(
                accion=AccionAuditada.PLAN_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="paciente",
                entidad_id=paciente_id,
                paciente_id=paciente_id,
                nivel_sensibilidad=(
                    NivelSensibilidad.CLINICO_SENSIBLE
                    if hay_n3_oculto
                    else NivelSensibilidad.CLINICO
                ),
                planes_devueltos=0,
            )
        )
    await auditor.registrar(entradas)
    await sesion.commit()
    return [_salida(plan, procedimientos) for plan, procedimientos in filas]


@enrutador_planes.post(
    "/pacientes/{paciente_id}/planes-tratamiento",
    response_model=PlanSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un borrador de plan de tratamiento",
)
async def crear_plan(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: PlanNuevo,
) -> PlanSalida:
    plan, procedimientos = await ServicioPlanesTratamiento(sesion, reloj).crear(
        paciente_id, datos, principal=principal
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PLAN_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="plan_tratamiento",
                entidad_id=plan.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
                procedimientos=len(procedimientos),
            )
        ]
    )
    await sesion.commit()
    return _salida(plan, procedimientos)


@enrutador_planes.post(
    "/planes-tratamiento/{plan_id}/propuesta",
    response_model=PlanSalida,
    summary="Proponer al paciente un borrador de plan",
)
async def proponer_plan(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    plan_id: Annotated[uuid.UUID, Path()],
) -> PlanSalida:
    plan, procedimientos = await ServicioPlanesTratamiento(sesion, reloj).proponer(
        plan_id, principal=principal
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PLAN_ESTADO_CAMBIADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="plan_tratamiento",
                entidad_id=plan.id,
                paciente_id=plan.paciente_id,
                nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
                estado=plan.estado,
            )
        ]
    )
    await sesion.commit()
    return _salida(plan, procedimientos)


def _plantilla(plantilla: PlantillaPlan) -> PlantillaSalida:
    return PlantillaSalida(
        id=plantilla.id,
        nombre=plantilla.nombre,
        descripcion=plantilla.descripcion,
        procedimientos=[
            ProcedimientoNuevo.model_validate(item) for item in plantilla.procedimientos
        ],
        creado_en=plantilla.creado_en,
    )


@enrutador_planes.get(
    "/plantillas-plan",
    response_model=list[PlantillaSalida],
    summary="Plantillas de planes de la clinica",
)
async def listar_plantillas(
    principal: PuedeLeer, sesion: Sesion, reloj: RelojActual
) -> list[PlantillaSalida]:
    filas = await ServicioPlanesTratamiento(sesion, reloj).plantillas(principal=principal)
    return [_plantilla(fila) for fila in filas]


@enrutador_planes.post(
    "/plantillas-plan",
    response_model=PlantillaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar una plantilla de plan",
    responses={409: {"description": "Ya existe una plantilla con ese nombre"}},
)
async def crear_plantilla(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    datos: PlantillaNueva,
) -> PlantillaSalida:
    plantilla = await ServicioPlanesTratamiento(sesion, reloj).crear_plantilla(
        datos, principal=principal
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PLANTILLA_PLAN_CREADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="plantilla_plan",
                entidad_id=plantilla.id,
                procedimientos=len(plantilla.procedimientos),
            )
        ]
    )
    await sesion.commit()
    return _plantilla(plantilla)


@enrutador_planes.post(
    "/plantillas-plan/{plantilla_id}/retiro",
    response_model=PlantillaSalida,
    summary="Retirar una plantilla (no se borra)",
)
async def retirar_plantilla(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    plantilla_id: Annotated[uuid.UUID, Path()],
    datos: Cancelacion,
) -> PlantillaSalida:
    plantilla = await ServicioPlanesTratamiento(sesion, reloj).retirar_plantilla(
        plantilla_id, datos.motivo, principal=principal
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PLANTILLA_PLAN_RETIRADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="plantilla_plan",
                entidad_id=plantilla.id,
                motivo=datos.motivo,
            )
        ]
    )
    await sesion.commit()
    return _plantilla(plantilla)


def _entrada_estado(
    principal: Principal, ahora: datetime, plan: PlanTratamiento, **extra: Any
) -> EntradaAuditoria:
    return construir_entrada(
        accion=AccionAuditada.PLAN_ESTADO_CAMBIADO,
        principal=principal,
        ahora=ahora,
        entidad_tipo="plan_tratamiento",
        entidad_id=plan.id,
        paciente_id=plan.paciente_id,
        nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
        estado=plan.estado,
        **extra,
    )


@enrutador_planes.post(
    "/planes-tratamiento/{plan_id}/aceptacion",
    response_model=PlanSalida,
    summary="Registrar la constancia de aceptacion del paciente",
    responses={409: {"description": "El plan no esta propuesto"}},
)
async def aceptar_plan(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    plan_id: Annotated[uuid.UUID, Path()],
    datos: AceptacionPlan,
) -> PlanSalida:
    """Registra una aceptacion que ocurrio fuera del sistema (documento firmado).

    No es una firma digital del paciente: deja constancia de quien la registro
    y de la referencia del documento archivado.
    """
    plan, procedimientos = await ServicioPlanesTratamiento(sesion, reloj).aceptar(
        plan_id, datos, principal=principal
    )
    await auditor.registrar(
        [_entrada_estado(principal, reloj.ahora(), plan, medio=datos.medio.value)]
    )
    await sesion.commit()
    return _salida(plan, procedimientos)


@enrutador_planes.post(
    "/planes-tratamiento/{plan_id}/cancelacion",
    response_model=PlanSalida,
    summary="Cancelar un plan; lo ya hecho se conserva",
)
async def cancelar_plan(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    plan_id: Annotated[uuid.UUID, Path()],
    datos: Cancelacion,
) -> PlanSalida:
    plan, procedimientos = await ServicioPlanesTratamiento(sesion, reloj).cancelar(
        plan_id, datos.motivo, principal=principal
    )
    entrada = _entrada_estado(principal, reloj.ahora(), plan)
    entrada.motivo = datos.motivo
    await auditor.registrar([entrada])
    await sesion.commit()
    return _salida(plan, procedimientos)


@enrutador_planes.post(
    "/procedimientos/{procedimiento_id}/completado",
    response_model=PlanSalida,
    summary="Completar un procedimiento del plan",
    responses={409: {"description": "El plan no esta aceptado o el procedimiento ya se cerro"}},
)
async def completar_procedimiento(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    procedimiento_id: Annotated[uuid.UUID, Path()],
    datos: CompletarProcedimiento,
) -> PlanSalida:
    plan, procedimientos, version = await ServicioPlanesTratamiento(
        sesion, reloj
    ).completar_procedimiento(procedimiento_id, datos, principal=principal)
    ahora = reloj.ahora()
    entradas = [
        construir_entrada(
            accion=AccionAuditada.PROCEDIMIENTO_COMPLETADO,
            principal=principal,
            ahora=ahora,
            entidad_tipo="procedimiento_plan",
            entidad_id=procedimiento_id,
            paciente_id=plan.paciente_id,
            nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
            plan_id=str(plan.id),
            estado_plan=plan.estado,
        )
    ]
    if version is not None:
        entradas.append(
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_VERSIONADO,
                principal=principal,
                ahora=ahora,
                entidad_tipo="odontograma",
                entidad_id=version.id,
                paciente_id=plan.paciente_id,
                nivel_sensibilidad=NivelSensibilidad(version.nivel_sensibilidad),
                version=version.version,
                origen_cambio="procedimiento",
            )
        )
    await auditor.registrar(entradas)
    await sesion.commit()
    return _salida(plan, procedimientos)


@enrutador_planes.post(
    "/procedimientos/{procedimiento_id}/control/atencion",
    response_model=PlanSalida,
    summary="Registrar que se realizó el control posterior del procedimiento",
    responses={409: {"description": "No hay un control pendiente de atención"}},
)
async def atender_control_procedimiento(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    procedimiento_id: Annotated[uuid.UUID, Path()],
    datos: AtencionControl,
) -> PlanSalida:
    plan, procedimientos = await ServicioPlanesTratamiento(sesion, reloj).atender_control(
        procedimiento_id, datos.nota, principal=principal
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONTROL_TRATAMIENTO_ATENDIDO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="procedimiento_plan",
                entidad_id=procedimiento_id,
                paciente_id=plan.paciente_id,
                nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
                plan_id=str(plan.id),
            )
        ]
    )
    await sesion.commit()
    return _salida(plan, procedimientos)


@enrutador_planes.post(
    "/procedimientos/{procedimiento_id}/cancelacion",
    response_model=PlanSalida,
    summary="Cancelar un procedimiento pendiente",
)
async def cancelar_procedimiento(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    procedimiento_id: Annotated[uuid.UUID, Path()],
    datos: Cancelacion,
) -> PlanSalida:
    plan, procedimientos = await ServicioPlanesTratamiento(sesion, reloj).cancelar_procedimiento(
        procedimiento_id, datos.motivo, principal=principal
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PLAN_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="procedimiento_plan",
                entidad_id=procedimiento_id,
                paciente_id=plan.paciente_id,
                nivel_sensibilidad=NivelSensibilidad(plan.nivel_sensibilidad),
                motivo=datos.motivo,
                operacion="procedimiento_cancelado",
                estado_plan=plan.estado,
            )
        ]
    )
    await sesion.commit()
    return _salida(plan, procedimientos)


__all__ = ["enrutador_planes"]
