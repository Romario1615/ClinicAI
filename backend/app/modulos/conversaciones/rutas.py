"""Bandeja protegida de conversaciones de WhatsApp.

Lee las conversaciones derivadas y, desde ADR-0025, permite actuar sobre ellas:
responder con texto libre dentro de la ventana de 24 horas, tomar un hilo que
atendia el agente, devolverlo al agente y cerrarlo.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import false, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.modulos.conversaciones.modelos import (
    AvisoRevisionTratamiento,
    Conversacion,
    EstadoConversacion,
    MensajeEntrante,
)
from app.modulos.outbox.modelos import OutboxMensaje, TipoMensajeOutbox
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, RecursoNoEncontrado

enrutador = APIRouter(prefix="/conversaciones", tags=["conversaciones"])
PuedeLeer = Annotated[Principal, Depends(exige_permiso("conversacion.leer"))]
PuedeResponder = Annotated[
    Principal,
    Depends(exige_permiso("conversacion.leer", "conversacion.responder", exigir_todos=True)),
]
PuedeTomar = Annotated[
    Principal,
    Depends(exige_permiso("conversacion.leer", "conversacion.tomar", exigir_todos=True)),
]
Idempotencia = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]
PuedeRevisarAvisos = Annotated[
    Principal,
    Depends(exige_permiso("alerta_adherencia.atender", "conversacion.leer", exigir_todos=True)),
]


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


class RespuestaSalida(BaseModel):
    """Lo que salio hacia el paciente en este hilo, con su estado de entrega."""

    id: uuid.UUID
    texto: str
    autor: Literal["AGENTE", "PERSONAL"]
    estado: str
    creado_en: datetime
    entregado_en: datetime | None
    error: str | None


class ConversacionDetalle(ConversacionSalida):
    ventana_expira_en: datetime | None
    asignado_a_usuario_id: uuid.UUID | None = None
    mensajes: list[MensajeSalida]
    respuestas: list[RespuestaSalida] = Field(default_factory=list)


class RespuestaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    texto: str = Field(min_length=1, max_length=1000)


class PaginaConversaciones(BaseModel):
    elementos: list[ConversacionSalida]
    total: int
    limite: int
    desplazamiento: int


class AvisoRevisionTratamientoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversacion_id: uuid.UUID
    creado_en: datetime


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
    "/avisos-tratamiento/cuenta",
    summary="Contar reportes de tratamiento sin confirmar revisión",
)
async def contar_avisos_tratamiento(
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
            .select_from(AvisoRevisionTratamiento)
            .join(Conversacion, Conversacion.id == AvisoRevisionTratamiento.conversacion_id)
            .where(
                AvisoRevisionTratamiento.revisada_en.is_(None),
                *_filtro_ambito(principal),
                Conversacion.canal == "WHATSAPP",
            )
        )
        or 0
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.AVISO_TRATAMIENTO_LEIDO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="aviso_revision_tratamiento",
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
                cantidad=cantidad,
                solo_conteo=True,
            )
        ]
    )
    await sesion.commit()
    return {"cantidad": cantidad}


@enrutador.get(
    "/avisos-tratamiento",
    response_model=list[AvisoRevisionTratamientoSalida],
    summary="Listar reportes de tratamiento pendientes de revisión humana",
)
async def listar_avisos_tratamiento(
    peticion: Request,
    principal: PuedeLeer,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    limite: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AvisoRevisionTratamientoSalida]:
    if principal.clinica_id is None:
        return []
    avisos = list(
        (
            await sesion.scalars(
                select(AvisoRevisionTratamiento)
                .join(Conversacion, Conversacion.id == AvisoRevisionTratamiento.conversacion_id)
                .where(
                    AvisoRevisionTratamiento.revisada_en.is_(None),
                    *_filtro_ambito(principal),
                    Conversacion.canal == "WHATSAPP",
                )
                .order_by(AvisoRevisionTratamiento.creado_en.asc())
                .limit(limite)
            )
        ).all()
    )
    if avisos:
        await auditor.registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.AVISO_TRATAMIENTO_LEIDO,
                    principal=principal,
                    ahora=reloj.ahora(),
                    entidad_tipo="aviso_revision_tratamiento",
                    entidad_id=aviso.id,
                    nivel_sensibilidad=NivelSensibilidad.CLINICO,
                    ip=peticion.client.host if peticion.client else None,
                    correlacion_id=getattr(peticion.state, "correlacion_id", None),
                )
                for aviso in avisos
            ]
        )
        await sesion.commit()
    return [AvisoRevisionTratamientoSalida.model_validate(aviso) for aviso in avisos]


@enrutador.post(
    "/avisos-tratamiento/{aviso_id}/revision",
    status_code=204,
    summary="Confirmar que un reporte de tratamiento fue revisado por personal clínico",
    responses={
        404: {"description": "No existe o está fuera del ámbito"},
        409: {"description": "Ya revisado"},
    },
)
async def revisar_aviso_tratamiento(
    peticion: Request,
    aviso_id: uuid.UUID,
    principal: PuedeRevisarAvisos,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> None:
    aviso = await sesion.scalar(
        select(AvisoRevisionTratamiento)
        .join(Conversacion, Conversacion.id == AvisoRevisionTratamiento.conversacion_id)
        .where(
            AvisoRevisionTratamiento.id == aviso_id,
            AvisoRevisionTratamiento.clinica_id == principal.clinica_id,
            *_filtro_ambito(principal),
            Conversacion.canal == "WHATSAPP",
        )
        .with_for_update(of=AvisoRevisionTratamiento)
    )
    if aviso is None:
        raise RecursoNoEncontrado("El reporte solicitado no existe.")
    if aviso.revisada_en is not None:
        raise ConflictoEstado("Este reporte ya tiene revisión registrada.")

    ahora = reloj.ahora()
    aviso.revisada_en = ahora
    aviso.revisada_por = principal.actor_id
    aviso.actualizado_por = principal.actor_id
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.AVISO_TRATAMIENTO_REVISADO,
                principal=principal,
                ahora=ahora,
                entidad_tipo="aviso_revision_tratamiento",
                entidad_id=aviso.id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
            )
        ]
    )
    await sesion.commit()


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
    estado: Annotated[
        Literal["EN_HANDOFF", "ABIERTA", "CERRADA"],
        Query(description="EN_HANDOFF: esperan a una persona; ABIERTA: las atiende el agente."),
    ] = "EN_HANDOFF",
) -> PaginaConversaciones:
    if principal.clinica_id is None:
        return PaginaConversaciones(
            elementos=[], total=0, limite=limite, desplazamiento=desplazamiento
        )
    filtros = [
        *_filtro_ambito(principal),
        Conversacion.estado == estado,
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
    respuestas = await _respuestas(sesion, conversacion.id)
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
        asignado_a_usuario_id=conversacion.asignado_a_usuario_id,
        mensajes=[MensajeSalida.model_validate(m) for m in mensajes],
        respuestas=respuestas,
    )


async def _respuestas(sesion: Sesion, conversacion_id: uuid.UUID) -> list[RespuestaSalida]:
    filas = (
        await sesion.scalars(
            select(OutboxMensaje)
            .where(
                OutboxMensaje.destino_tipo == "CONVERSACION",
                OutboxMensaje.destino_id == conversacion_id,
                OutboxMensaje.tipo == TipoMensajeOutbox.RESPUESTA_CONVERSACION.value,
            )
            .order_by(OutboxMensaje.creado_en.asc())
        )
    ).all()
    return [
        RespuestaSalida(
            id=fila.id,
            texto=str((fila.carga_util or {}).get("texto", "")),
            autor="PERSONAL" if fila.entidad_origen_tipo == "usuario" else "AGENTE",
            estado=fila.estado,
            creado_en=fila.creado_en,
            entregado_en=fila.entregado_en,
            error=fila.ultimo_error,
        )
        for fila in filas
    ]


# ---------------------------------------------------------------------------
#  Acciones sobre un hilo (ADR-0025)
# ---------------------------------------------------------------------------
async def _para_actuar(
    sesion: Sesion, principal: Principal, conversacion_id: uuid.UUID
) -> Conversacion:
    """El hilo bloqueado para escribir, o 404 si no existe en el ambito."""
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("La conversación solicitada no existe.")
    conversacion = await sesion.scalar(
        select(Conversacion)
        .where(
            Conversacion.id == conversacion_id,
            *_filtro_ambito(principal),
            Conversacion.canal == "WHATSAPP",
        )
        .with_for_update()
    )
    if conversacion is None:
        raise RecursoNoEncontrado("La conversación solicitada no existe.")
    return conversacion


async def _auditar(
    auditor: Auditor,
    peticion: Request,
    principal: Principal,
    reloj: RelojActual,
    accion: AccionAuditada,
    conversacion: Conversacion,
) -> None:
    await auditor.registrar(
        [
            construir_entrada(
                accion=accion,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="conversacion",
                entidad_id=conversacion.id,
                paciente_id=conversacion.paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                ip=peticion.client.host if peticion.client else None,
                correlacion_id=getattr(peticion.state, "correlacion_id", None),
            )
        ]
    )


def _exigir_abierta(conversacion: Conversacion) -> None:
    if conversacion.estado == EstadoConversacion.CERRADA.value:
        raise ConflictoEstado("La conversación está cerrada.")


@enrutador.post(
    "/{conversacion_id}/respuestas",
    status_code=202,
    summary="Responder al paciente con texto libre dentro de la ventana de 24 h",
    responses={
        404: {"description": "No existe o está fuera del ámbito"},
        409: {"description": "Conversación cerrada o ventana de 24 h vencida"},
    },
)
async def responder(
    peticion: Request,
    conversacion_id: uuid.UUID,
    datos: RespuestaEntrada,
    principal: PuedeResponder,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
    clave: Idempotencia,
) -> dict[str, bool]:
    from app.modulos.conversaciones import agente_whatsapp  # noqa: PLC0415

    conversacion = await _para_actuar(sesion, principal, conversacion_id)
    _exigir_abierta(conversacion)
    if conversacion.ventana_expira_en is None or conversacion.ventana_expira_en <= reloj.ahora():
        raise ConflictoEstado(
            "Pasaron más de 24 h desde el último mensaje del paciente: WhatsApp solo "
            "admite plantillas aprobadas. Espere a que el paciente escriba de nuevo."
        )
    # La clave del cliente puede medir 200 caracteres y el outbox admite 64: se
    # resume, ligada al hilo para que la misma clave en otro hilo no choque.
    huella = hashlib.sha256(f"{conversacion.id}:{clave}".encode()).hexdigest()[:48]
    encolado = await agente_whatsapp.responder(
        sesion,
        reloj,
        conversacion,
        datos.texto,
        f"personal:{huella}",
        autor_usuario_id=principal.actor_id,
    )
    if encolado is not None:
        # Quien responde se queda con el hilo; el agente deja de contestar.
        conversacion.estado = EstadoConversacion.EN_HANDOFF.value
        conversacion.asignado_a_usuario_id = (
            conversacion.asignado_a_usuario_id or principal.actor_id
        )
        conversacion.ultima_actividad_en = reloj.ahora()
        await _auditar(
            auditor,
            peticion,
            principal,
            reloj,
            AccionAuditada.CONVERSACION_RESPONDIDA,
            conversacion,
        )
    await sesion.commit()
    return {"encolado": True}


@enrutador.post(
    "/{conversacion_id}/toma",
    status_code=204,
    summary="Tomar la conversación: la atiende una persona y el agente deja de contestar",
    responses={404: {"description": "No existe o está fuera del ámbito"}},
)
async def tomar(
    peticion: Request,
    conversacion_id: uuid.UUID,
    principal: PuedeTomar,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> None:
    conversacion = await _para_actuar(sesion, principal, conversacion_id)
    _exigir_abierta(conversacion)
    conversacion.estado = EstadoConversacion.EN_HANDOFF.value
    conversacion.asignado_a_usuario_id = principal.actor_id
    conversacion.motivo_handoff = conversacion.motivo_handoff or "Tomada por el equipo."
    await _auditar(
        auditor, peticion, principal, reloj, AccionAuditada.CONVERSACION_TOMADA, conversacion
    )
    await sesion.commit()


@enrutador.post(
    "/{conversacion_id}/devolucion",
    status_code=204,
    summary="Devolver la conversación al agente",
    responses={
        404: {"description": "No existe o está fuera del ámbito"},
        409: {"description": "Agente apagado, sin paciente identificado o conversación cerrada"},
    },
)
async def devolver_al_agente(
    peticion: Request,
    conversacion_id: uuid.UUID,
    principal: PuedeTomar,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> None:
    from app.modulos.conversaciones import agente_whatsapp  # noqa: PLC0415

    conversacion = await _para_actuar(sesion, principal, conversacion_id)
    _exigir_abierta(conversacion)
    if conversacion.paciente_id is None:
        raise ConflictoEstado("El agente solo atiende conversaciones con paciente identificado.")
    if not await agente_whatsapp.habilitado(sesion, conversacion.clinica_id):
        raise ConflictoEstado("El agente de WhatsApp está apagado en esta clínica.")
    conversacion.estado = EstadoConversacion.ABIERTA.value
    conversacion.asignado_a_usuario_id = None
    conversacion.motivo_handoff = None
    await _auditar(
        auditor,
        peticion,
        principal,
        reloj,
        AccionAuditada.CONVERSACION_DEVUELTA_AL_AGENTE,
        conversacion,
    )
    await sesion.commit()


@enrutador.post(
    "/{conversacion_id}/cierre",
    status_code=204,
    summary="Cerrar la conversación",
    responses={404: {"description": "No existe o está fuera del ámbito"}},
)
async def cerrar(
    peticion: Request,
    conversacion_id: uuid.UUID,
    principal: PuedeResponder,
    sesion: Sesion,
    auditor: Auditor,
    reloj: RelojActual,
) -> None:
    conversacion = await _para_actuar(sesion, principal, conversacion_id)
    if conversacion.estado != EstadoConversacion.CERRADA.value:
        conversacion.estado = EstadoConversacion.CERRADA.value
        conversacion.cerrada_en = reloj.ahora()
        await _auditar(
            auditor, peticion, principal, reloj, AccionAuditada.CONVERSACION_CERRADA, conversacion
        )
    await sesion.commit()
