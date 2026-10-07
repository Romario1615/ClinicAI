"""Acceso de emergencia temporal y aviso administrativo sin datos del paciente."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.modulos.historia.esquemas import (
    AccesoEmergenciaCreado,
    AvisoAccesoEmergenciaSalida,
    SolicitudAccesoEmergencia,
)
from app.modulos.pacientes.modelos import AvisoAccesoEmergencia, Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, RepoPacientes, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, PermisoDenegado, RecursoNoEncontrado

enrutador = APIRouter(prefix="/historia", tags=["acceso clínico de emergencia"])
PuedeSolicitar = Annotated[Principal, Depends(exige_permiso("acceso_emergencia.solicitar"))]
PuedeRevisar = Annotated[Principal, Depends(exige_permiso("auditoria.leer"))]
DURACION_MINUTOS = 30


class ConteoAvisosEmergencia(BaseModel):
    cantidad: int


@enrutador.post(
    "/pacientes/{paciente_id}/acceso-emergencia",
    response_model=AccesoEmergenciaCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Conceder acceso clínico temporal por emergencia",
)
async def solicitar_acceso(
    peticion: Request,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: SolicitudAccesoEmergencia,
    principal: PuedeSolicitar,
    repositorio: RepoPacientes,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> AccesoEmergenciaCreado:
    if principal.profesional_id is None or principal.clinica_id is None:
        raise PermisoDenegado("Solo un profesional vinculado puede solicitar este acceso.")

    paciente = await repositorio.obtener(paciente_id, principal)
    if paciente is None or not paciente.activo:
        raise RecursoNoEncontrado("El paciente solicitado no existe.")

    profesional = await sesion.scalar(
        select(Profesional).where(
            Profesional.id == principal.profesional_id,
            Profesional.clinica_id == principal.clinica_id,
            Profesional.usuario_id == principal.actor_id,
            Profesional.activo.is_(True),
        )
    )
    if profesional is None:
        raise PermisoDenegado("La cuenta no tiene un perfil profesional activo.")

    # Serializa solicitudes simultáneas para la misma ficha antes de comprobar
    # vínculos y crear el temporal.
    await sesion.scalar(
        select(Paciente.id)
        .where(Paciente.id == paciente.id, Paciente.clinica_id == principal.clinica_id)
        .with_for_update()
    )
    ahora = reloj.ahora()
    relacion_activa = await sesion.scalar(
        select(RelacionAsistencial.id).where(
            RelacionAsistencial.paciente_id == paciente.id,
            RelacionAsistencial.profesional_id == profesional.id,
            RelacionAsistencial.revocada_en.is_(None),
            or_(
                RelacionAsistencial.vigente_hasta.is_(None),
                RelacionAsistencial.vigente_hasta > ahora,
            ),
        )
    )
    if relacion_activa is not None:
        raise ConflictoEstado("Ya existe una relación asistencial vigente para este paciente.")

    vence_en = ahora + timedelta(minutes=DURACION_MINUTOS)
    relacion = RelacionAsistencial(
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        origen="EMERGENCIA",
        vigente_hasta=vence_en,
        motivo=datos.motivo,
        creado_en=ahora,
        creado_por=principal.actor_id,
    )
    sesion.add(relacion)
    await sesion.flush()
    aviso = AvisoAccesoEmergencia(
        clinica_id=principal.clinica_id,
        relacion_id=relacion.id,
        profesional_id=profesional.id,
        creado_en=ahora,
        creado_por=principal.actor_id,
    )
    sesion.add(aviso)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ACCESO_EMERGENCIA,
                principal=principal,
                ahora=ahora,
                entidad_tipo="relacion_asistencial",
                entidad_id=relacion.id,
                paciente_id=paciente.id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
                motivo="Acceso de emergencia declarado; vigencia limitada a 30 minutos.",
                aviso_administrativo_id=str(aviso.id),
            )
        ]
    )
    await sesion.commit()
    return AccesoEmergenciaCreado(relacion_id=relacion.id, vence_en=vence_en)


@enrutador.get(
    "/avisos-acceso-emergencia/cuenta",
    response_model=ConteoAvisosEmergencia,
    summary="Contar avisos pendientes de revisión administrativa",
)
async def contar_avisos(
    peticion: Request,
    principal: PuedeRevisar,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> ConteoAvisosEmergencia:
    if principal.clinica_id is None:
        return ConteoAvisosEmergencia(cantidad=0)
    cantidad = await sesion.scalar(
        select(func.count())
        .select_from(AvisoAccesoEmergencia)
        .where(
            AvisoAccesoEmergencia.clinica_id == principal.clinica_id,
            AvisoAccesoEmergencia.revisada_en.is_(None),
        )
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ACCESO_EMERGENCIA_AVISO_LEIDO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="aviso_acceso_emergencia",
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
                cantidad=cantidad or 0,
                solo_conteo=True,
            )
        ]
    )
    await sesion.commit()
    return ConteoAvisosEmergencia(cantidad=cantidad or 0)


@enrutador.get(
    "/avisos-acceso-emergencia",
    response_model=list[AvisoAccesoEmergenciaSalida],
    summary="Listar avisos de acceso de emergencia sin datos del paciente",
)
async def listar_avisos(
    peticion: Request,
    principal: PuedeRevisar,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> list[AvisoAccesoEmergenciaSalida]:
    if principal.clinica_id is None:
        return []
    filas = (
        await sesion.execute(
            select(
                AvisoAccesoEmergencia,
                RelacionAsistencial.vigente_hasta,
                Profesional.nombre,
                Profesional.apellido,
            )
            .join(RelacionAsistencial, RelacionAsistencial.id == AvisoAccesoEmergencia.relacion_id)
            .join(Profesional, Profesional.id == AvisoAccesoEmergencia.profesional_id)
            .where(
                AvisoAccesoEmergencia.clinica_id == principal.clinica_id,
                AvisoAccesoEmergencia.revisada_en.is_(None),
            )
            .order_by(AvisoAccesoEmergencia.creado_en.asc())
        )
    ).all()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ACCESO_EMERGENCIA_AVISO_LEIDO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="aviso_acceso_emergencia",
                entidad_id=aviso.id,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
            )
            for aviso, _, _, _ in filas
        ]
    )
    await sesion.commit()
    return [
        AvisoAccesoEmergenciaSalida(
            id=aviso.id,
            profesional=f"{nombre} {apellido}",
            creado_en=aviso.creado_en,
            vence_en=vence_en,
        )
        for aviso, vence_en, nombre, apellido in filas
    ]


@enrutador.post(
    "/avisos-acceso-emergencia/{aviso_id}/revision",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marcar aviso de acceso de emergencia como revisado",
)
async def revisar_aviso(
    peticion: Request,
    aviso_id: Annotated[uuid.UUID, Path()],
    principal: PuedeRevisar,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> None:
    aviso = await sesion.scalar(
        select(AvisoAccesoEmergencia)
        .where(
            AvisoAccesoEmergencia.id == aviso_id,
            AvisoAccesoEmergencia.clinica_id == principal.clinica_id,
        )
        .with_for_update()
    )
    if aviso is None:
        raise RecursoNoEncontrado("El aviso solicitado no existe.")
    if aviso.revisada_en is not None:
        raise ConflictoEstado("Este aviso ya se revisó.")
    ahora = reloj.ahora()
    aviso.revisada_en = ahora
    aviso.revisada_por = principal.actor_id
    aviso.actualizado_por = principal.actor_id
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ACCESO_EMERGENCIA_AVISO_REVISADO,
                principal=principal,
                ahora=ahora,
                entidad_tipo="aviso_acceso_emergencia",
                entidad_id=aviso.id,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
            )
        ]
    )
    await sesion.commit()
