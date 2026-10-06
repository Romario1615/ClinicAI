"""Rutas del asistente interno del personal."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.ia.embeddings import ProveedorEmbeddings
from app.modulos.asistente.servicios import ServicioAsistente
from app.modulos.promociones.rutas import _servicio as servicio_promociones
from app.modulos.promociones.servicios import ServicioPromociones
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    PrincipalActual,
    RelojActual,
    Sesion,
)
from app.nucleo.errores import PermisoDenegado

enrutador = APIRouter(prefix="/asistente", tags=["asistente"])


def _personal(principal: PrincipalActual) -> Principal:
    if principal.es_agente or principal.clinica_id is None or principal.actor_id is None:
        raise PermisoDenegado("El asistente es solo para el personal de la clínica.")
    return principal


Personal = Annotated[Principal, Depends(_personal)]


def _asistente(
    peticion: Request,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    promociones: Annotated[ServicioPromociones, Depends(servicio_promociones)],
) -> ServicioAsistente:
    embeddings: ProveedorEmbeddings = peticion.app.state.embeddings
    return ServicioAsistente(sesion, reloj, configuracion, embeddings, promociones)


Asistente = Annotated[ServicioAsistente, Depends(_asistente)]


class Mensaje(BaseModel):
    texto: str = Field(min_length=1, max_length=1000)
    paciente_id: uuid.UUID | None = None


class ElementoSalida(BaseModel):
    titulo: str
    detalle: str | None
    enlace: str | None


class RespuestaSalida(BaseModel):
    intencion: str
    texto: str
    elementos: list[ElementoSalida]
    enlace: str | None
    sugerencias: list[str]


@enrutador.get("/sugerencias", response_model=list[str])
async def sugerencias(principal: Personal, asistente: Asistente) -> list[str]:
    """Qué puede pedir esta persona, según sus permisos."""
    return list(asistente.sugerencias(principal))


@enrutador.post("/mensajes", response_model=RespuestaSalida)
async def enviar(
    principal: Personal,
    asistente: Asistente,
    sesion: Sesion,
    auditor: Auditor,
    mensaje: Mensaje,
) -> RespuestaSalida:
    """Responde y, si hizo falta, crea borradores; todo con los permisos de quien escribe."""
    respuesta = await asistente.responder(
        mensaje.texto, principal=principal, paciente_id=mensaje.paciente_id
    )
    await auditor.registrar(respuesta.auditoria)
    await sesion.commit()
    return RespuestaSalida(
        intencion=respuesta.intencion.value,
        texto=respuesta.texto,
        elementos=[
            ElementoSalida(titulo=e.titulo, detalle=e.detalle, enlace=e.enlace)
            for e in respuesta.elementos
        ],
        enlace=respuesta.enlace,
        sugerencias=list(respuesta.sugerencias),
    )


__all__ = ["enrutador"]
