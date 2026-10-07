"""Alta y mantenimiento de perfiles profesionales de la clínica."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.profesionales.gestion_esquemas import (
    DatosPerfilProfesional,
    RespuestaPerfilProfesional,
)
from app.modulos.profesionales.modelos import EstadoDisponibilidad, Profesional, ProfesionalSede
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, RecursoNoEncontrado

enrutador = APIRouter(prefix="/profesionales", tags=["profesionales"])
PuedeGestionarProfesionales = Annotated[Principal, Depends(exige_permiso("profesional.gestionar"))]


async def _clinica_activa(principal: Principal, sesion: Sesion) -> Clinica:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("No hay una clínica asociada a esta sesión.")
    clinica = await sesion.get(Clinica, principal.clinica_id)
    if clinica is None or not clinica.activa or clinica.anulado_en is not None:
        raise RecursoNoEncontrado("No hay una clínica activa asociada a esta sesión.")
    return clinica


async def _validar_destino(
    datos: DatosPerfilProfesional,
    principal: Principal,
    sesion: Sesion,
) -> tuple[Especialidad, list[Sede]]:
    especialidad = await sesion.scalar(
        select(Especialidad).where(
            Especialidad.id == datos.especialidad_id,
            Especialidad.clinica_id == principal.clinica_id,
            Especialidad.activa.is_(True),
            Especialidad.anulado_en.is_(None),
        )
    )
    if especialidad is None or not principal.ambito.cubre_especialidad(especialidad.id):
        raise RecursoNoEncontrado("No se encontró una especialidad activa dentro de su ámbito.")

    sedes = list(
        (
            await sesion.execute(
                select(Sede).where(
                    Sede.id.in_(datos.sede_ids),
                    Sede.clinica_id == principal.clinica_id,
                    Sede.activa.is_(True),
                    Sede.anulado_en.is_(None),
                )
            )
        ).scalars()
    )
    if len(sedes) != len(datos.sede_ids) or any(
        not principal.ambito.cubre_sede(sede.id) for sede in sedes
    ):
        raise RecursoNoEncontrado("Una o más sedes no existen o están fuera de su ámbito.")
    return especialidad, sedes


def _respuesta(
    profesional: Profesional,
    asignaciones: list[ProfesionalSede],
    *,
    sede_principal_id: uuid.UUID | None = None,
) -> RespuestaPerfilProfesional:
    principal = next((fila.sede_id for fila in asignaciones if fila.principal), None)
    if sede_principal_id is not None:
        principal = sede_principal_id
    sedes = sorted(fila.sede_id for fila in asignaciones)
    return RespuestaPerfilProfesional(
        id=profesional.id,
        especialidad_id=profesional.especialidad_id,
        nombre=profesional.nombre,
        apellido=profesional.apellido,
        numero_registro_profesional=profesional.numero_registro_profesional,
        telefono_whatsapp=profesional.telefono_whatsapp,
        correo_calendario=profesional.correo_calendario,
        estado_disponibilidad=profesional.estado_disponibilidad,
        acepta_pacientes_nuevos=profesional.acepta_pacientes_nuevos,
        minutos_preparacion_propio=profesional.minutos_preparacion_propio,
        activo=profesional.activo,
        sede_ids=sedes,
        sede_principal_id=principal,
    )


async def _asignaciones(profesional_id: uuid.UUID, sesion: Sesion) -> list[ProfesionalSede]:
    return list(
        (
            await sesion.execute(
                select(ProfesionalSede).where(ProfesionalSede.profesional_id == profesional_id)
            )
        ).scalars()
    )


@enrutador.get("/gestion", response_model=list[RespuestaPerfilProfesional])
async def listar_perfiles_profesionales(
    principal: PuedeGestionarProfesionales,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    peticion: Request,
) -> list[RespuestaPerfilProfesional]:
    await _clinica_activa(principal, sesion)
    consulta = select(Profesional).where(
        Profesional.clinica_id == principal.clinica_id,
        Profesional.anulado_en.is_(None),
    )
    ambito = principal.ambito
    if not ambito.todos_los_profesionales:
        if not ambito.profesionales:
            return []
        consulta = consulta.where(Profesional.id.in_(ambito.profesionales))
    if not ambito.todas_las_especialidades:
        if not ambito.especialidades:
            return []
        consulta = consulta.where(Profesional.especialidad_id.in_(ambito.especialidades))
    if not ambito.todas_las_sedes:
        if not ambito.sedes:
            return []
        consulta = consulta.where(
            select(ProfesionalSede.profesional_id)
            .where(
                ProfesionalSede.profesional_id == Profesional.id,
                ProfesionalSede.sede_id.in_(ambito.sedes),
            )
            .exists()
        )
    perfiles = list(
        (
            await sesion.execute(consulta.order_by(Profesional.apellido, Profesional.nombre))
        ).scalars()
    )
    resultado: list[RespuestaPerfilProfesional] = []
    visibles_ids: list[uuid.UUID] = []
    for perfil in perfiles:
        asignaciones = await _asignaciones(perfil.id, sesion)
        visibles = [fila for fila in asignaciones if ambito.cubre_sede(fila.sede_id)]
        principal_visible = next((fila for fila in visibles if fila.principal), None)
        if principal_visible is not None:
            resultado.append(_respuesta(perfil, visibles))
            visibles_ids.append(perfil.id)
        elif visibles:
            # No se devuelve la sede principal si pertenece a otro ámbito.
            resultado.append(_respuesta(perfil, visibles, sede_principal_id=None))
            visibles_ids.append(perfil.id)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PROFESIONAL_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="profesional",
                entidad_id=perfil.id,
                nivel_sensibilidad=NivelSensibilidad.ADMINISTRATIVO,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
            )
            for profesional_id in visibles_ids
            for perfil in perfiles
            if perfil.id == profesional_id
        ]
    )
    await sesion.commit()
    return resultado


@enrutador.post(
    "/gestion", response_model=RespuestaPerfilProfesional, status_code=status.HTTP_201_CREATED
)
async def crear_perfil_profesional(
    datos: DatosPerfilProfesional,
    principal: PuedeGestionarProfesionales,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaPerfilProfesional:
    await _clinica_activa(principal, sesion)
    especialidad, sedes = await _validar_destino(datos, principal, sesion)
    profesional = Profesional(
        clinica_id=principal.clinica_id,
        especialidad_id=especialidad.id,
        nombre=datos.nombre,
        apellido=datos.apellido,
        numero_registro_profesional=datos.numero_registro_profesional,
        telefono_whatsapp=datos.telefono_whatsapp,
        correo_calendario=datos.correo_calendario,
        estado_disponibilidad=datos.estado_disponibilidad,
        acepta_pacientes_nuevos=datos.acepta_pacientes_nuevos,
        minutos_preparacion_propio=datos.minutos_preparacion_propio,
        activo=datos.activo,
    )
    if not datos.activo:
        profesional.estado_disponibilidad = EstadoDisponibilidad.INACTIVO.value
    try:
        sesion.add(profesional)
        await sesion.flush()
        asignaciones = [
            ProfesionalSede(
                profesional_id=profesional.id,
                sede_id=sede.id,
                principal=sede.id == datos.sede_principal_id,
            )
            for sede in sedes
        ]
        sesion.add_all(asignaciones)
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un profesional con ese registro en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PROFESIONAL_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="profesional",
                entidad_id=profesional.id,
                sede_ids=[str(sede.id) for sede in sedes],
            )
        ]
    )
    await sesion.commit()
    return _respuesta(profesional, asignaciones)


@enrutador.put("/gestion/{profesional_id}", response_model=RespuestaPerfilProfesional)
async def actualizar_perfil_profesional(
    datos: DatosPerfilProfesional,
    principal: PuedeGestionarProfesionales,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    profesional_id: Annotated[uuid.UUID, Path()],
) -> RespuestaPerfilProfesional:
    await _clinica_activa(principal, sesion)
    profesional = (
        await sesion.execute(
            select(Profesional)
            .where(
                Profesional.id == profesional_id,
                Profesional.clinica_id == principal.clinica_id,
                Profesional.anulado_en.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if profesional is None or not principal.ambito.cubre_profesional(profesional_id):
        raise RecursoNoEncontrado("No se encontró el profesional dentro de su ámbito.")
    especialidad, sedes = await _validar_destino(datos, principal, sesion)
    profesional.especialidad_id = especialidad.id
    profesional.nombre = datos.nombre
    profesional.apellido = datos.apellido
    profesional.numero_registro_profesional = datos.numero_registro_profesional
    profesional.telefono_whatsapp = datos.telefono_whatsapp
    profesional.correo_calendario = datos.correo_calendario
    profesional.acepta_pacientes_nuevos = datos.acepta_pacientes_nuevos
    profesional.minutos_preparacion_propio = datos.minutos_preparacion_propio
    profesional.activo = datos.activo
    profesional.estado_disponibilidad = (
        EstadoDisponibilidad.INACTIVO.value if not datos.activo else datos.estado_disponibilidad
    )
    anteriores = await _asignaciones(profesional.id, sesion)
    sedes_en_ambito = {
        fila.sede_id for fila in anteriores if principal.ambito.cubre_sede(fila.sede_id)
    }
    await sesion.execute(
        delete(ProfesionalSede).where(
            ProfesionalSede.profesional_id == profesional.id,
            ProfesionalSede.sede_id.in_(sedes_en_ambito),
        )
    )
    heredadas = [fila for fila in anteriores if not principal.ambito.cubre_sede(fila.sede_id)]
    principal_heredada = next((fila.sede_id for fila in heredadas if fila.principal), None)
    asignaciones_visibles = [
        ProfesionalSede(
            profesional_id=profesional.id,
            sede_id=sede.id,
            principal=principal_heredada is None and sede.id == datos.sede_principal_id,
        )
        for sede in sedes
    ]
    sesion.add_all(asignaciones_visibles)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe un profesional con ese registro en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.PROFESIONAL_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="profesional",
                entidad_id=profesional.id,
                activo=profesional.activo,
                sede_ids=[str(sede.id) for sede in sedes],
            )
        ]
    )
    await sesion.commit()
    return _respuesta(
        profesional,
        asignaciones_visibles,
        sede_principal_id=(datos.sede_principal_id if principal_heredada is None else None),
    )
