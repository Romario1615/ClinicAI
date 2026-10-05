"""Indicaciones después de la consulta: publicar (profesional) y leer (paciente).

Profesional
-----------
``POST /historia/pacientes/{id}/indicaciones`` guarda el texto, genera un
enlace que caduca y encola el aviso genérico por WhatsApp. Exige
``historia_clinica.escribir`` y relación asistencial, como una nota. Si el
paciente no aceptó mensajes, la indicación se guarda igual y la respuesta lo
dice: el profesional puede darle el enlace en mano.

Paciente
--------
``POST /publico/indicaciones/{token}/acceso`` sin sesión. Pide fecha de
nacimiento (o los cuatro últimos dígitos del documento si no la tiene
registrada). Cinco intentos fallidos bloquean el enlace. Con un enlace que
no existe, caducó o se anuló la respuesta es la misma: no se revela cuál de
los casos es.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.mensajeria.adaptadores import RegistroCanales
from app.mensajeria.servicios import ServicioOutbox, SolicitudEnvio
from app.modulos.agenda.modelos import Cita
from app.modulos.historia.modelos import Receta, RecetaMedicamento
from app.modulos.organizacion.modelos import Clinica
from app.modulos.outbox.modelos import CanalOutbox, TipoMensajeOutbox
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.modulos.pacientes.modelos import Paciente
from app.modulos.postconsulta.modelos import MAXIMO_INTENTOS, IndicacionPostconsulta
from app.modulos.profesionales.modelos import Profesional
from app.nucleo.auditoria import AccionAuditada, ResultadoAuditoria, construir_entrada
from app.nucleo.autorizacion import Ambito, NivelSensibilidad, Principal, TipoActor
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    Limitador,
    RelojActual,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import (
    ConflictoEstado,
    ConsentimientoRequerido,
    CredencialesInvalidas,
    DatosInvalidos,
    PermisoDenegado,
    RecursoNoEncontrado,
)

enrutador = APIRouter(tags=["indicaciones postconsulta"])
PuedeEscribir = Annotated[Principal, Depends(exige_permiso("historia_clinica.escribir"))]
PuedeLeer = Annotated[Principal, Depends(exige_permiso("historia_clinica.leer"))]


class IndicacionNueva(BaseModel):
    texto: str = Field(min_length=10, max_length=4000)
    cita_id: uuid.UUID | None = None
    receta_id: uuid.UUID | None = None
    dias_validez: int = Field(default=7, ge=1, le=30)


class IndicacionPublicada(BaseModel):
    id: uuid.UUID
    enlace: str
    expira_en: datetime
    aviso_enviado: bool
    motivo_sin_aviso: str | None


class IndicacionSalida(BaseModel):
    id: uuid.UUID
    texto: str
    receta_id: uuid.UUID | None
    creado_en: datetime
    expira_en: datetime
    lecturas: int
    primera_lectura_en: datetime | None
    bloqueada: bool
    anulada_en: datetime | None


class Anulacion(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


class Verificacion(BaseModel):
    fecha_nacimiento: date | None = None
    ultimos_digitos_documento: str | None = Field(default=None, pattern=r"^[0-9A-Za-z]{4}$")


class MedicamentoIndicado(BaseModel):
    nombre: str
    concentracion: str | None
    dosis: str
    via: str
    cuando_sea_necesario: bool
    frecuencia_horas: int | None
    duracion_dias: int | None
    instrucciones: str | None


class IndicacionParaPaciente(BaseModel):
    nombre_paciente: str
    clinica: str
    profesional: str
    fecha: datetime
    texto: str
    medicamentos: list[MedicamentoIndicado]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _salida(fila: IndicacionPostconsulta) -> IndicacionSalida:
    return IndicacionSalida(
        id=fila.id,
        texto=fila.texto,
        receta_id=fila.receta_id,
        creado_en=fila.creado_en,
        expira_en=fila.expira_en,
        lecturas=fila.lecturas,
        primera_lectura_en=fila.primera_lectura_en,
        bloqueada=fila.bloqueada,
        anulada_en=fila.anulada_en,
    )


@enrutador.post(
    "/historia/pacientes/{paciente_id}/indicaciones",
    response_model=IndicacionPublicada,
    status_code=201,
)
async def publicar(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    configuracion: ConfiguracionActual,
    datos: IndicacionNueva,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> IndicacionPublicada:
    ahora = reloj.ahora()
    paciente = await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.escribir", ahora
    )
    if principal.profesional_id is None or principal.clinica_id is None:
        raise PermisoDenegado("Solo un profesional publica indicaciones para su paciente.")
    if datos.receta_id is not None:
        receta = await sesion.get(Receta, datos.receta_id)
        if receta is None or receta.paciente_id != paciente_id or receta.estado != "CONFIRMADA":
            raise RecursoNoEncontrado("La receta indicada no existe o no está confirmada.")
    if datos.cita_id is not None:
        cita = await sesion.get(Cita, datos.cita_id)
        if cita is None or cita.paciente_id != paciente_id:
            raise RecursoNoEncontrado("La cita indicada no existe para este paciente.")

    token = secrets.token_urlsafe(32)
    expira = ahora + timedelta(days=datos.dias_validez)
    fila = IndicacionPostconsulta(
        clinica_id=principal.clinica_id,
        paciente_id=paciente_id,
        profesional_id=principal.profesional_id,
        cita_id=datos.cita_id,
        receta_id=datos.receta_id,
        texto=datos.texto.strip(),
        token_hash=_hash(token),
        expira_en=expira,
        creado_por=principal.actor_id,
    )
    sesion.add(fila)
    await sesion.flush()

    enlace = f"{configuracion.frontend_url.rstrip('/')}/indicaciones/{token}"
    clinica = await sesion.get(Clinica, principal.clinica_id)
    aviso_enviado = True
    motivo_sin_aviso: str | None = None
    try:
        async with sesion.begin_nested():
            encolado = await ServicioOutbox(sesion, reloj, RegistroCanales()).encolar(
                SolicitudEnvio(
                    tipo=TipoMensajeOutbox.INDICACIONES_DISPONIBLES,
                    canal=CanalOutbox.WHATSAPP,
                    destino_tipo="PACIENTE",
                    destino_id=paciente_id,
                    clave_deduplicacion=f"indic:{fila.id.hex}",
                    variables={
                        "nombre": paciente.nombre,
                        "clinica": clinica.nombre if clinica else "la clínica",
                        "enlace": enlace,
                        "dias": str(datos.dias_validez),
                    },
                    clinica_id=principal.clinica_id,
                    entidad_origen_tipo="indicacion_postconsulta",
                    entidad_origen_id=fila.id,
                )
            )
            if encolado is None:
                aviso_enviado = False
                motivo_sin_aviso = "La automatización de indicaciones está apagada en esta clínica."
    except ConsentimientoRequerido:
        aviso_enviado = False
        motivo_sin_aviso = (
            "El paciente no aceptó mensajes por WhatsApp: entréguele el enlace en mano."
        )

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.INDICACION_PUBLICADA,
                principal=principal,
                ahora=ahora,
                entidad_tipo="indicacion_postconsulta",
                entidad_id=fila.id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                aviso_enviado=aviso_enviado,
            )
        ]
    )
    await sesion.commit()
    return IndicacionPublicada(
        id=fila.id,
        enlace=enlace,
        expira_en=expira,
        aviso_enviado=aviso_enviado,
        motivo_sin_aviso=motivo_sin_aviso,
    )


@enrutador.get(
    "/historia/pacientes/{paciente_id}/indicaciones", response_model=list[IndicacionSalida]
)
async def listar(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> list[IndicacionSalida]:
    await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.leer", reloj.ahora()
    )
    filas = (
        await sesion.execute(
            select(IndicacionPostconsulta)
            .where(
                IndicacionPostconsulta.paciente_id == paciente_id,
                IndicacionPostconsulta.clinica_id == principal.clinica_id,
            )
            .order_by(IndicacionPostconsulta.creado_en.desc())
        )
    ).scalars()
    return [_salida(f) for f in filas]


@enrutador.patch(
    "/historia/indicaciones/{indicacion_id}/anulacion", response_model=IndicacionSalida
)
async def anular(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    datos: Anulacion,
    indicacion_id: Annotated[uuid.UUID, Path()],
) -> IndicacionSalida:
    fila = await sesion.get(IndicacionPostconsulta, indicacion_id)
    if fila is None or fila.clinica_id != principal.clinica_id:
        raise RecursoNoEncontrado("La indicación no existe.")
    await GuardiaClinica(sesion).acceso_clinico(
        principal, fila.paciente_id, "historia_clinica.escribir", reloj.ahora()
    )
    if fila.anulada_en is not None:
        raise ConflictoEstado("La indicación ya está anulada.")
    fila.anulada_en = reloj.ahora()
    fila.motivo_anulacion = datos.motivo.strip()
    fila.actualizado_por = principal.actor_id
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.INDICACION_ANULADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="indicacion_postconsulta",
                entidad_id=fila.id,
                paciente_id=fila.paciente_id,
                motivo=fila.motivo_anulacion,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


def _principal_paciente(paciente: Paciente) -> Principal:
    """Actor de la auditoría: el propio paciente, sin ningún permiso."""
    return Principal(
        actor_tipo=TipoActor.PACIENTE,
        actor_id=paciente.id,
        clinica_id=paciente.clinica_id,
        permisos=frozenset(),
        ambito=Ambito(),
    )


@enrutador.post("/publico/indicaciones/{token}/acceso", response_model=IndicacionParaPaciente)
async def leer(
    peticion: Request,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    limitador: Limitador,
    datos: Verificacion,
    token: Annotated[str, Path(min_length=20, max_length=100)],
) -> IndicacionParaPaciente:
    origen = peticion.client.host if peticion.client else "desconocido"
    await limitador.exigir(f"indicaciones:ip:{origen}", limite=10, fallar_cerrado=True)
    if datos.fecha_nacimiento is None and not datos.ultimos_digitos_documento:
        raise DatosInvalidos("Indique su fecha de nacimiento.")

    ahora = reloj.ahora()
    fila = (
        await sesion.execute(
            select(IndicacionPostconsulta).where(IndicacionPostconsulta.token_hash == _hash(token))
        )
    ).scalar_one_or_none()
    no_disponible = RecursoNoEncontrado(
        "Este enlace ya no está disponible. Pida a la clínica que le envíe uno nuevo."
    )
    if fila is None or fila.anulada_en is not None or fila.expira_en <= ahora:
        raise no_disponible
    if fila.bloqueada:
        raise ConflictoEstado(
            "El enlace se bloqueó por demasiados intentos. Pida uno nuevo a la clínica.",
            codigo="ENLACE_BLOQUEADO",
        )
    paciente = await sesion.get(Paciente, fila.paciente_id)
    if paciente is None:
        raise no_disponible

    if paciente.fecha_nacimiento is not None:
        coincide = datos.fecha_nacimiento == paciente.fecha_nacimiento
    else:
        documento = (paciente.numero_documento or "").strip()
        coincide = bool(documento) and (
            (datos.ultimos_digitos_documento or "").upper() == documento[-4:].upper()
        )
    actor = _principal_paciente(paciente)
    if not coincide:
        fila.intentos_fallidos += 1
        fila.bloqueada = fila.intentos_fallidos >= MAXIMO_INTENTOS
        await auditor.registrar(
            [
                construir_entrada(
                    accion=AccionAuditada.INDICACION_ACCESO_FALLIDO,
                    principal=actor,
                    ahora=ahora,
                    resultado=ResultadoAuditoria.DENEGADO,
                    entidad_tipo="indicacion_postconsulta",
                    entidad_id=fila.id,
                    paciente_id=fila.paciente_id,
                    ip=origen,
                    intentos=fila.intentos_fallidos,
                )
            ]
        )
        await sesion.commit()
        raise CredencialesInvalidas(
            "Los datos no coinciden con los de la ficha.",
            detalles={"intentos_restantes": max(0, MAXIMO_INTENTOS - fila.intentos_fallidos)},
        )

    fila.lecturas += 1
    fila.primera_lectura_en = fila.primera_lectura_en or ahora
    fila.ultima_lectura_en = ahora
    medicamentos: list[MedicamentoIndicado] = []
    if fila.receta_id is not None:
        filas_med = (
            await sesion.execute(
                select(RecetaMedicamento).where(RecetaMedicamento.receta_id == fila.receta_id)
            )
        ).scalars()
        medicamentos = [
            MedicamentoIndicado(
                nombre=m.nombre,
                concentracion=m.concentracion,
                dosis=m.dosis,
                via=m.via,
                cuando_sea_necesario=m.cuando_sea_necesario,
                frecuencia_horas=m.frecuencia_horas,
                duracion_dias=m.duracion_dias,
                instrucciones=m.instrucciones,
            )
            for m in filas_med
        ]
    profesional = await sesion.get(Profesional, fila.profesional_id)
    clinica = await sesion.get(Clinica, fila.clinica_id)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.INDICACION_LEIDA,
                principal=actor,
                ahora=ahora,
                entidad_tipo="indicacion_postconsulta",
                entidad_id=fila.id,
                paciente_id=fila.paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                ip=origen,
            )
        ]
    )
    await sesion.commit()
    return IndicacionParaPaciente(
        nombre_paciente=paciente.nombre,
        clinica=clinica.nombre if clinica else "",
        profesional=f"{profesional.nombre} {profesional.apellido}" if profesional else "",
        fecha=fila.creado_en,
        texto=fila.texto,
        medicamentos=medicamentos,
    )


__all__ = ["enrutador"]
