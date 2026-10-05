"""Bandeja protegida para conversaciones derivadas a una persona."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import false, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.modulos.conversaciones.modelos import Conversacion, EstadoConversacion, MensajeEntrante
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import RecursoNoEncontrado

enrutador = APIRouter(prefix="/conversaciones", tags=["conversaciones"])
PuedeLeer = Annotated[Principal, Depends(exige_permiso("conversacion.leer"))]


@enrutador.get("/pendientes/cuenta", summary="Contar derivaciones pendientes")
async def contar_pendientes(
    peticion: Request,
    principal: PuedeLeer,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> dict[str, int]:
    if principal.clinica_id is None:
        return {"cantidad": 0}
    cantidad = (
        await sesion.scalar(
            select(func.count())
            .select_from(Conversacion)
            .where(
                *_filtro_ambito(principal),
                Conversacion.estado == EstadoConversacion.EN_HANDOFF.value,
                Conversacion.canal == "WHATSAPP",
            )
        )
        or 0
    )
    entrada = construir_entrada(
        accion=AccionAuditada.CONVERSACION_LEIDA,
        principal=principal,
        ahora=reloj.ahora(),
        entidad_tipo="conversacion",
        nivel_sensibilidad=NivelSensibilidad.CLINICO,
        ip=peticion.client.host if peticion.client else None,
        correlacion_id=getattr(peticion.state, "correlacion_id", None),
        cantidad=cantidad,
        solo_conteo=True,
    )
    await auditor.registrar([entrada])
    await sesion.commit()
    return {"cantidad": cantidad}


class MensajeSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    texto: str | None
    intencion: str
    recibido_en: datetime


class ConversacionSalida(BaseModel):
    id: uuid.UUID
    telefono: str
    paciente_id: uuid.UUID | None
    estado: str
    motivo_handoff: str | None
    ultima_actividad_en: datetime
    ultimo_mensaje: str | None


class ConversacionDetalle(ConversacionSalida):
    ventana_expira_en: datetime | None
    mensajes: list[MensajeSalida]


class PaginaConversaciones(BaseModel):
    elementos: list[ConversacionSalida]
    total: int
    limite: int
    desplazamiento: int


def _filtro_ambito(principal: Principal) -> list[ColumnElement[bool]]:
    condiciones = [Conversacion.clinica_id == principal.clinica_id]
    ambito = principal.ambito
    if not ambito.cubre_nivel(NivelSensibilidad.CLINICO):
        condiciones.append(false())
    if not ambito.todos_los_pacientes:
        if not ambito.pacientes:
            # Conversaciones sin identidad resuelta también pueden contener
            # datos sensibles. Un ámbito vacío no da acceso a la bandeja.
            condiciones.append(false())
        else:
            condiciones.append(Conversacion.paciente_id.in_(ambito.pacientes))
    return condiciones


@enrutador.get(
    "", response_model=PaginaConversaciones, summary="Bandeja de conversaciones derivadas"
)
async def listar(
    peticion: Request,
    principal: PuedeLeer,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaConversaciones:
    if principal.clinica_id is None:
        return PaginaConversaciones(
            elementos=[], total=0, limite=limite, desplazamiento=desplazamiento
        )
    filtros = [
        *_filtro_ambito(principal),
        Conversacion.estado == EstadoConversacion.EN_HANDOFF.value,
        Conversacion.canal == "WHATSAPP",
    ]
    total = await sesion.scalar(select(func.count()).select_from(Conversacion).where(*filtros)) or 0
    ultima = (
        select(MensajeEntrante.texto)
        .where(MensajeEntrante.conversacion_id == Conversacion.id)
        .order_by(MensajeEntrante.recibido_en.desc())
        .limit(1)
        .scalar_subquery()
    )
    filas = (
        await sesion.execute(
            select(Conversacion, ultima.label("ultimo_mensaje"))
            .where(
                *filtros,
            )
            .order_by(Conversacion.ultima_actividad_en.asc())
            .limit(limite)
            .offset(desplazamiento)
        )
    ).all()
    entrada = construir_entrada(
        accion=AccionAuditada.CONVERSACION_LEIDA,
        principal=principal,
        ahora=reloj.ahora(),
        entidad_tipo="conversacion",
        nivel_sensibilidad=NivelSensibilidad.CLINICO,
        ip=peticion.client.host if peticion.client else None,
        correlacion_id=getattr(peticion.state, "correlacion_id", None),
        cantidad=len(filas),
    )
    await auditor.registrar([entrada])
    await sesion.commit()
    elementos = [
        ConversacionSalida(
            id=c.id,
            telefono=c.telefono,
            paciente_id=c.paciente_id,
            estado=c.estado,
            motivo_handoff=c.motivo_handoff,
            ultima_actividad_en=c.ultima_actividad_en,
            ultimo_mensaje=mensaje,
        )
        for c, mensaje in filas
    ]
    return PaginaConversaciones(
        elementos=elementos, total=total, limite=limite, desplazamiento=desplazamiento
    )


@enrutador.get(
    "/{conversacion_id}", response_model=ConversacionDetalle, summary="Leer una conversación"
)
async def obtener(
    peticion: Request,
    conversacion_id: uuid.UUID,
    principal: PuedeLeer,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> ConversacionDetalle:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("La conversación solicitada no existe.")
    conversacion = await sesion.scalar(
        select(Conversacion).where(
            Conversacion.id == conversacion_id,
            *_filtro_ambito(principal),
            Conversacion.canal == "WHATSAPP",
        )
    )
    if conversacion is None:
        raise RecursoNoEncontrado("La conversación solicitada no existe.")
    mensajes = list(
        (
            await sesion.scalars(
                select(MensajeEntrante)
                .where(MensajeEntrante.conversacion_id == conversacion.id)
                .order_by(MensajeEntrante.recibido_en.asc())
            )
        ).all()
    )
    entrada = construir_entrada(
        accion=AccionAuditada.CONVERSACION_CONSULTADA,
        principal=principal,
        ahora=reloj.ahora(),
        entidad_tipo="conversacion",
        entidad_id=conversacion.id,
        paciente_id=conversacion.paciente_id,
        nivel_sensibilidad=NivelSensibilidad.CLINICO,
        ip=peticion.client.host if peticion.client else None,
        correlacion_id=getattr(peticion.state, "correlacion_id", None),
    )
    await auditor.registrar([entrada])
    await sesion.commit()
    return ConversacionDetalle(
        id=conversacion.id,
        telefono=conversacion.telefono,
        paciente_id=conversacion.paciente_id,
        estado=conversacion.estado,
        motivo_handoff=conversacion.motivo_handoff,
        ultima_actividad_en=conversacion.ultima_actividad_en,
        ultimo_mensaje=mensajes[-1].texto if mensajes else None,
        ventana_expira_en=conversacion.ventana_expira_en,
        mensajes=[MensajeSalida.model_validate(m) for m in mensajes],
    )
