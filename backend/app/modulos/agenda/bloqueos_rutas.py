"""Administración de cierres y bloqueos operativos de agenda."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import select

from app.modulos.agenda.esquemas import DatosBloqueoAgenda, RespuestaBloqueoAgenda
from app.modulos.agenda.modelos import BloqueoAgenda, Cita, EstadoCita
from app.modulos.organizacion.modelos import Consultorio, Sede
from app.modulos.profesionales.modelos import Profesional, ProfesionalSede
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/agenda/bloqueos", tags=["bloqueos de agenda"])
PuedeGestionarBloqueos = Annotated[Principal, Depends(exige_permiso("bloqueo.gestionar"))]
MAX_DIAS_CONSULTA_BLOQUEOS = 370
ESTADOS_CITAS_AFECTADAS = tuple(
    estado.value for estado in (EstadoCita.HELD, EstadoCita.CONFIRMED, EstadoCita.RESCHEDULED)
)


def _exigir_instante_con_zona(instante: datetime, campo: str) -> datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise DatosInvalidos(f"{campo} debe incluir zona horaria (ISO-8601).")
    return instante.astimezone(UTC)


async def _sede_en_ambito(
    sede_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
    *,
    bloquear: bool = False,
) -> Sede:
    consulta = select(Sede).where(
        Sede.id == sede_id,
        Sede.clinica_id == principal.clinica_id,
        Sede.activa.is_(True),
        Sede.anulado_en.is_(None),
    )
    if not principal.ambito.todas_las_sedes and sede_id not in principal.ambito.sedes:
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    if bloquear:
        consulta = consulta.with_for_update()
    sede = (await sesion.execute(consulta)).scalar_one_or_none()
    if sede is None:
        raise RecursoNoEncontrado("No se encontró la sede dentro de su ámbito.")
    return sede


async def _validar_destino(
    datos: DatosBloqueoAgenda,
    principal: Principal,
    sesion: Sesion,
) -> Sede:
    sede = await _sede_en_ambito(datos.sede_id, principal, sesion, bloquear=True)
    # A professional may only manage their own blocks. A restricted provider
    # scope must also name one of its providers explicitly; site/room blocks
    # could otherwise affect schedules outside that scope.
    if not principal.ambito.todos_los_profesionales and (
        datos.profesional_id is None or datos.profesional_id not in principal.ambito.profesionales
    ):
        raise RecursoNoEncontrado("No se encontró el destino dentro de su ámbito.")
    if datos.profesional_id is not None:
        profesional = (
            await sesion.execute(
                select(Profesional.id)
                .join(
                    ProfesionalSede,
                    ProfesionalSede.profesional_id == Profesional.id,
                )
                .where(
                    Profesional.id == datos.profesional_id,
                    Profesional.clinica_id == principal.clinica_id,
                    Profesional.activo.is_(True),
                    Profesional.anulado_en.is_(None),
                    ProfesionalSede.sede_id == sede.id,
                )
            )
        ).scalar_one_or_none()
        if profesional is None:
            raise RecursoNoEncontrado("No se encontró el profesional dentro de la sede.")
    if datos.consultorio_id is not None:
        consultorio = (
            await sesion.execute(
                select(Consultorio.id).where(
                    Consultorio.id == datos.consultorio_id,
                    Consultorio.sede_id == sede.id,
                    Consultorio.activo.is_(True),
                    Consultorio.anulado_en.is_(None),
                )
            )
        ).scalar_one_or_none()
        if consultorio is None:
            raise RecursoNoEncontrado("No se encontró el consultorio dentro de la sede.")
    return sede


def _validar_datos(datos: DatosBloqueoAgenda) -> tuple[datetime, datetime]:
    inicio = _exigir_instante_con_zona(datos.inicio, "inicio")
    fin = _exigir_instante_con_zona(datos.fin, "fin")
    if fin <= inicio:
        raise DatosInvalidos("El fin del bloqueo debe ser posterior al inicio.")
    if datos.profesional_id is not None and datos.consultorio_id is not None:
        raise DatosInvalidos("Elija un profesional o un consultorio para el bloqueo, no ambos.")
    return inicio, fin


async def _citas_afectadas(
    datos: DatosBloqueoAgenda,
    principal: Principal,
    sesion: Sesion,
    inicio: datetime,
    fin: datetime,
) -> list[Cita]:
    consulta = select(Cita).where(
        Cita.clinica_id == principal.clinica_id,
        Cita.sede_id == datos.sede_id,
        Cita.estado.in_(ESTADOS_CITAS_AFECTADAS),
        Cita.inicio < fin,
        Cita.fin > inicio,
    )
    if datos.profesional_id is not None:
        consulta = consulta.where(Cita.profesional_id == datos.profesional_id)
    elif datos.consultorio_id is not None:
        consulta = consulta.where(Cita.consultorio_id == datos.consultorio_id)
    consulta = consulta.order_by(Cita.inicio, Cita.id).with_for_update()
    return list((await sesion.execute(consulta)).scalars())


def _respuesta(bloqueo: BloqueoAgenda) -> RespuestaBloqueoAgenda:
    return RespuestaBloqueoAgenda(
        id=bloqueo.id,
        sede_id=bloqueo.sede_id,
        profesional_id=bloqueo.profesional_id,
        consultorio_id=bloqueo.consultorio_id,
        tipo=bloqueo.tipo,
        inicio=bloqueo.inicio,
        fin=bloqueo.fin,
        motivo=bloqueo.motivo,
        creado_con_citas_afectadas=bloqueo.creado_con_citas_afectadas,
    )


@enrutador.get("", response_model=list[RespuestaBloqueoAgenda])
async def listar_bloqueos(
    principal: PuedeGestionarBloqueos,
    sesion: Sesion,
    sede_id: Annotated[uuid.UUID, Query()],
    desde: Annotated[datetime, Query()],
    hasta: Annotated[datetime, Query()],
) -> list[RespuestaBloqueoAgenda]:
    sede = await _sede_en_ambito(sede_id, principal, sesion)
    inicio = _exigir_instante_con_zona(desde, "desde")
    fin = _exigir_instante_con_zona(hasta, "hasta")
    if fin <= inicio or fin - inicio > timedelta(days=MAX_DIAS_CONSULTA_BLOQUEOS):
        raise DatosInvalidos("El rango debe ser válido y no superar 370 días.")
    consulta = select(BloqueoAgenda).where(
        BloqueoAgenda.clinica_id == principal.clinica_id,
        BloqueoAgenda.sede_id == sede.id,
        BloqueoAgenda.inicio < fin,
        BloqueoAgenda.fin > inicio,
    )
    if not principal.ambito.todos_los_profesionales:
        if not principal.ambito.profesionales:
            return []
        consulta = consulta.where(BloqueoAgenda.profesional_id.in_(principal.ambito.profesionales))
    bloqueos = (
        await sesion.execute(consulta.order_by(BloqueoAgenda.inicio, BloqueoAgenda.id))
    ).scalars()
    return [_respuesta(bloqueo) for bloqueo in bloqueos]


@enrutador.post("", response_model=RespuestaBloqueoAgenda, status_code=status.HTTP_201_CREATED)
async def crear_bloqueo(
    datos: DatosBloqueoAgenda,
    principal: PuedeGestionarBloqueos,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaBloqueoAgenda:
    inicio, fin = _validar_datos(datos)
    sede = await _validar_destino(datos, principal, sesion)
    afectadas = await _citas_afectadas(datos, principal, sesion, inicio, fin)
    if afectadas and not datos.aceptar_citas_afectadas:
        raise ConflictoEstado(
            f"El bloqueo coincide con {len(afectadas)} cita(s) activa(s). Confirme para continuar.",
            detalles={
                "citas_afectadas": [
                    {
                        "id": str(cita.id),
                        "inicio": cita.inicio.isoformat(),
                        "fin": cita.fin.isoformat(),
                    }
                    for cita in afectadas
                ]
            },
        )
    bloqueo = BloqueoAgenda(
        clinica_id=principal.clinica_id,
        sede_id=sede.id,
        profesional_id=datos.profesional_id,
        consultorio_id=datos.consultorio_id,
        tipo=datos.tipo,
        inicio=inicio,
        fin=fin,
        motivo=datos.motivo or None,
        creado_con_citas_afectadas=bool(afectadas),
    )
    sesion.add(bloqueo)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.BLOQUEO_AGENDA_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="bloqueo_agenda",
                entidad_id=bloqueo.id,
                sede_id=sede.id,
                tipo=datos.tipo,
                citas_afectadas=len(afectadas),
            )
        ]
    )
    await sesion.commit()
    return _respuesta(bloqueo)


async def _bloqueo_en_ambito(
    bloqueo_id: uuid.UUID,
    principal: Principal,
    sesion: Sesion,
) -> BloqueoAgenda:
    consulta = select(BloqueoAgenda).where(
        BloqueoAgenda.id == bloqueo_id,
        BloqueoAgenda.clinica_id == principal.clinica_id,
    )
    if not principal.ambito.todas_las_sedes:
        if not principal.ambito.sedes:
            raise RecursoNoEncontrado("No se encontró el bloqueo dentro de su ámbito.")
        consulta = consulta.where(BloqueoAgenda.sede_id.in_(principal.ambito.sedes))
    if not principal.ambito.todos_los_profesionales:
        if not principal.ambito.profesionales:
            raise RecursoNoEncontrado("No se encontró el bloqueo dentro de su ámbito.")
        consulta = consulta.where(BloqueoAgenda.profesional_id.in_(principal.ambito.profesionales))
    bloqueo = (await sesion.execute(consulta.with_for_update())).scalar_one_or_none()
    if bloqueo is None:
        raise RecursoNoEncontrado("No se encontró el bloqueo dentro de su ámbito.")
    return bloqueo


@enrutador.put("/{bloqueo_id}", response_model=RespuestaBloqueoAgenda)
async def actualizar_bloqueo(
    bloqueo_id: Annotated[uuid.UUID, Path()],
    datos: DatosBloqueoAgenda,
    principal: PuedeGestionarBloqueos,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> RespuestaBloqueoAgenda:
    bloqueo = await _bloqueo_en_ambito(bloqueo_id, principal, sesion)
    inicio, fin = _validar_datos(datos)
    sede = await _validar_destino(datos, principal, sesion)
    afectadas = await _citas_afectadas(datos, principal, sesion, inicio, fin)
    if afectadas and not datos.aceptar_citas_afectadas:
        raise ConflictoEstado(
            f"El bloqueo coincide con {len(afectadas)} cita(s) activa(s). Confirme para continuar.",
            detalles={
                "citas_afectadas": [
                    {
                        "id": str(cita.id),
                        "inicio": cita.inicio.isoformat(),
                        "fin": cita.fin.isoformat(),
                    }
                    for cita in afectadas
                ]
            },
        )
    bloqueo.sede_id = sede.id
    bloqueo.profesional_id = datos.profesional_id
    bloqueo.consultorio_id = datos.consultorio_id
    bloqueo.tipo = datos.tipo
    bloqueo.inicio = inicio
    bloqueo.fin = fin
    bloqueo.motivo = datos.motivo or None
    bloqueo.creado_con_citas_afectadas = bool(afectadas)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.BLOQUEO_AGENDA_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="bloqueo_agenda",
                entidad_id=bloqueo.id,
                sede_id=sede.id,
                tipo=datos.tipo,
                citas_afectadas=len(afectadas),
            )
        ]
    )
    await sesion.commit()
    return _respuesta(bloqueo)


@enrutador.delete("/{bloqueo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_bloqueo(
    bloqueo_id: Annotated[uuid.UUID, Path()],
    principal: PuedeGestionarBloqueos,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> Response:
    bloqueo = await _bloqueo_en_ambito(bloqueo_id, principal, sesion)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.BLOQUEO_AGENDA_ELIMINADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="bloqueo_agenda",
                entidad_id=bloqueo.id,
                sede_id=bloqueo.sede_id,
                tipo=bloqueo.tipo,
            )
        ]
    )
    await sesion.delete(bloqueo)
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["enrutador"]
