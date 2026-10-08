"""Chat interno por expediente; el paciente de la ruta es inmutable."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ia.proveedores_clinica import decisiones_de_clinica, fabrica_de_clinica
from app.modulos.asistente.paciente_esquemas import RespuestaAgente
from app.modulos.asistente.paciente_modelos import SesionAgentePaciente
from app.modulos.asistente.paciente_servicios import NOMBRES, ServicioAgentePaciente
from app.modulos.asistente.rutas import Asistente, Personal
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    CifradorActual,
    ConfiguracionActual,
    RelojActual,
    Sesion,
)
from app.nucleo.errores import PermisoDenegado
from app.nucleo.operaciones import completar_operacion, iniciar_operacion

enrutador = APIRouter(prefix="/asistente/pacientes/{paciente_id}", tags=["agente del paciente"])
Idempotencia = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


def _operador(principal: Personal) -> Principal:
    if not principal.tiene_permiso("paciente.leer_administrativo"):
        raise PermisoDenegado("Su rol no puede abrir la ficha del paciente.")
    return principal


Operador = Annotated[Principal, Depends(_operador)]


class Abrir(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cita_id: uuid.UUID | None = None


class Mensaje(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=1, max_length=1000)


class Confirmacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    propuesta_id: uuid.UUID
    aceptar: bool


class ContextoAgenda(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sede_id: uuid.UUID
    servicio_id: uuid.UUID
    profesional_id: uuid.UUID
    desde: AwareDatetime
    hasta: AwareDatetime

    @model_validator(mode="after")
    def rango(self) -> ContextoAgenda:
        if not 0 < (self.hasta - self.desde).total_seconds() <= 14 * 86400:
            raise ValueError("Seleccione un rango positivo de hasta catorce días.")
        return self


async def _servicio(
    peticion: Request,
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    asistente: Asistente,
    cifrador: CifradorActual,
    principal: Operador,
) -> ServicioAgentePaciente:
    assert principal.clinica_id is not None
    fabrica = await fabrica_de_clinica(
        sesion,
        cifrador,
        configuracion,
        principal.clinica_id,
        peticion.app.state.fabrica_conversacional,
    )
    decisiones = await decisiones_de_clinica(
        sesion, cifrador, configuracion, principal.clinica_id, peticion.app.state.clasificador
    )
    return ServicioAgentePaciente(
        sesion,
        reloj,
        configuracion,
        peticion.app.state.embeddings,
        fabrica,
        asistente,
        decisiones.clasificador,
    )


Agente = Annotated[ServicioAgentePaciente, Depends(_servicio)]


def salida(
    fila: SesionAgentePaciente,
    texto: str = "",
    datos: dict[str, Any] | None = None,
    humano: bool = False,
) -> dict[str, Any]:
    propuesta = fila.propuesta
    return {
        "sesion_id": str(fila.id),
        "paciente_id": str(fila.paciente_id),
        "expira_en": fila.expira_en.isoformat(),
        "texto": texto,
        "datos": {
            **(datos or {}),
            "zona_horaria": (datos or {}).get("zona_horaria", fila.memoria.get("zona_horaria")),
            "cita_activa_inicio": fila.memoria.get("inicio")
            if fila.memoria.get("cita_id")
            else None,
        },
        "requiere_humano": humano,
        "modo": fila.negocio.get("_modo", "local"),
        "propuesta": {**propuesta, "titulo": NOMBRES.get(propuesta["nombre"], "Revisar acción")}
        if propuesta
        else None,
    }


@enrutador.post("/sesiones", status_code=201, response_model=RespuestaAgente)
async def abrir(
    principal: Operador,
    sesion: Sesion,
    agente: Agente,
    paciente_id: uuid.UUID,
    datos: Abrir,
    clave: Idempotencia,
    reloj: RelojActual,
    auditor: Auditor,
) -> dict[str, Any]:
    await agente.acceso(principal, paciente_id)
    operacion = await iniciar_operacion(
        sesion,
        principal,
        reloj,
        "agente_paciente.abrir",
        clave,
        {"paciente_id": paciente_id, **datos.model_dump(mode="json")},
    )
    if operacion.respuesta:
        await agente.obtener(
            principal, paciente_id, uuid.UUID(str(operacion.respuesta["sesion_id"]))
        )
        return dict(operacion.respuesta)
    fila = await agente.abrir(principal, paciente_id, datos.cita_id)
    resultado = salida(
        fila,
        "Agente vinculado a esta ficha. Puede consultar citas, pagos, documentos aprobados y el resumen permitido de su historial.",
    )
    completar_operacion(operacion, resultado, reloj)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ASISTENTE_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="agente_paciente",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                intencion="ABRIR_EXPEDIENTE",
            )
        ]
    )
    await sesion.commit()
    return resultado


@enrutador.post("/sesiones/{id_hilo}/contexto", response_model=RespuestaAgente)
async def contexto(
    principal: Operador,
    sesion: Sesion,
    agente: Agente,
    paciente_id: uuid.UUID,
    id_hilo: uuid.UUID,
    datos: ContextoAgenda,
    reloj: RelojActual,
    auditor: Auditor,
) -> dict[str, Any]:
    actor, fila = await agente.obtener(principal, paciente_id, id_hilo)
    await agente.configurar(actor, fila, datos.model_dump())
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ASISTENTE_CONSULTADO,
                principal=actor,
                ahora=reloj.ahora(),
                entidad_tipo="agente_paciente",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                intencion="CONTEXTO_AGENDA",
            )
        ]
    )
    await sesion.commit()
    return salida(fila, "Contexto de agenda actualizado para este paciente.")


@enrutador.post("/sesiones/{id_hilo}/cita", response_model=RespuestaAgente)
async def elegir_cita(
    principal: Operador,
    sesion: Sesion,
    agente: Agente,
    paciente_id: uuid.UUID,
    id_hilo: uuid.UUID,
    datos: Abrir,
    reloj: RelojActual,
    auditor: Auditor,
) -> dict[str, Any]:
    actor, fila = await agente.obtener(principal, paciente_id, id_hilo)
    if datos.cita_id:
        await agente.elegir_cita(actor, fila, datos.cita_id)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ASISTENTE_CONSULTADO,
                principal=actor,
                ahora=reloj.ahora(),
                entidad_tipo="agente_paciente",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                intencion="SELECCION_CITA",
            )
        ]
    )
    await sesion.commit()
    return salida(fila, "Cita seleccionada como contexto de la conversación.")


@enrutador.post("/sesiones/{id_hilo}/mensajes", response_model=RespuestaAgente)
async def mensaje(
    principal: Operador,
    sesion: Sesion,
    agente: Agente,
    paciente_id: uuid.UUID,
    id_hilo: uuid.UUID,
    datos: Mensaje,
    clave: Idempotencia,
    reloj: RelojActual,
    auditor: Auditor,
) -> dict[str, Any]:
    actor, fila = await agente.obtener(principal, paciente_id, id_hilo)
    operacion = await iniciar_operacion(
        sesion,
        principal,
        reloj,
        "agente_paciente.mensaje",
        clave,
        {"sesion": id_hilo, "texto": datos.texto},
    )
    if operacion.respuesta and not operacion.respuesta.get("resumen_local"):
        return dict(operacion.respuesta)
    r = await agente.responder(actor, fila, datos.texto, clave)
    respuesta = salida(fila, r.mensaje, r.datos, r.requiere_humano)
    if "elementos" in r.datos:
        completar_operacion(operacion, {"resumen_local": True}, reloj)
    else:
        completar_operacion(operacion, respuesta, reloj)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ASISTENTE_CONSULTADO,
                principal=actor,
                ahora=reloj.ahora(),
                entidad_tipo="agente_paciente",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                intencion="MENSAJE_EXPEDIENTE",
            )
        ]
    )
    await sesion.commit()
    return respuesta


@enrutador.post("/sesiones/{id_hilo}/confirmar", response_model=RespuestaAgente)
async def confirmar(
    principal: Operador,
    sesion: Sesion,
    agente: Agente,
    paciente_id: uuid.UUID,
    id_hilo: uuid.UUID,
    datos: Confirmacion,
    clave: Idempotencia,
    reloj: RelojActual,
    auditor: Auditor,
) -> dict[str, Any]:
    actor, fila = await agente.obtener(principal, paciente_id, id_hilo)
    operacion = await iniciar_operacion(
        sesion,
        principal,
        reloj,
        "agente_paciente.confirmar",
        clave,
        {"sesion": id_hilo, **datos.model_dump(mode="json")},
    )
    if operacion.respuesta:
        return dict(operacion.respuesta)
    r = await agente.confirmar(actor, fila, datos.propuesta_id, datos.aceptar, clave)
    # Las herramientas de agenda pueden revertir una colisión; la clave y el
    # bloqueo transaccional del chat se recuperan antes de guardar la salida.
    operacion = await iniciar_operacion(
        sesion,
        principal,
        reloj,
        "agente_paciente.confirmar",
        clave,
        {"sesion": id_hilo, **datos.model_dump(mode="json")},
    )
    respuesta = salida(fila, r.mensaje, r.datos, r.requiere_humano)
    completar_operacion(operacion, respuesta, reloj)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ASISTENTE_CONSULTADO,
                principal=actor,
                ahora=reloj.ahora(),
                entidad_tipo="agente_paciente",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                intencion="CONFIRMAR_ACCION" if datos.aceptar else "DESCARTAR_PROPUESTA",
            )
        ]
    )
    await sesion.commit()
    return respuesta
