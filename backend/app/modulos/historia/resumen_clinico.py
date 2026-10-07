"""Resumen clínico para el profesional, antes de entrar a consulta.

Responde a «¿qué tengo que saber de este paciente?» en una pantalla:
alergias activas, antecedentes, medicación confirmada y cómo la está
tomando, últimas notas, planes en curso y citas.

* El **resumen estructurado** se arma con consultas a la base: no hay IA, no
  hay interpretación, y no sale nada del servidor.
* La **redacción** convierte ese mismo resumen en un párrafo con un modelo
  local (`app/ia/resumen_clinico.py`). No se guarda en la historia.

Acceso: el mismo que leer la historia (`historia_clinica.leer`, paciente en
el ámbito y relación asistencial). Los antecedentes N3 solo se incluyen con
`historia_clinica.leer_sensible`. Cada lectura y cada redacción se auditan.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Path
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.resumen_clinico import RedactorResumenClinico
from app.modulos.agenda.modelos import Cita
from app.modulos.historia.autorizacion import PuedeLeerHistoriaDiscreta
from app.modulos.historia.modelos import NotaEvolucion, Receta, RecetaMedicamento, Toma
from app.modulos.odontologia.modelos import PlanTratamiento, ProcedimientoPlan
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.modulos.pacientes.modelos import Alergia, Antecedente
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    RelojActual,
    Sesion,
)

enrutador = APIRouter(prefix="/historia", tags=["historia clinica"])


class AlergiaResumen(BaseModel):
    id: uuid.UUID
    sustancia: str
    reaccion: str | None
    severidad: str


class AntecedenteResumen(BaseModel):
    categoria: str
    descripcion: str
    nivel_sensibilidad: str


class MedicamentoResumen(BaseModel):
    nombre: str
    concentracion: str | None
    dosis: str
    via: str
    cuando_sea_necesario: bool
    frecuencia_horas: int | None
    duracion_dias: int | None
    instrucciones: str | None
    desde: datetime | None


class AdherenciaResumen(BaseModel):
    dias: int
    tomadas: int
    omitidas: int
    sin_registrar: int


class NotaResumen(BaseModel):
    fecha: datetime
    tipo: str
    nivel_sensibilidad: str
    motivo_consulta: str | None
    analisis: str | None
    plan: str | None


class PlanResumen(BaseModel):
    titulo: str
    estado: str
    procedimientos_pendientes: int
    nivel_sensibilidad: str


class ResumenClinico(BaseModel):
    paciente_id: uuid.UUID
    edad: int | None
    sexo: str | None
    alergias: list[AlergiaResumen]
    antecedentes: list[AntecedenteResumen]
    medicacion_activa: list[MedicamentoResumen]
    adherencia: AdherenciaResumen
    ultimas_notas: list[NotaResumen]
    planes: list[PlanResumen]
    ultima_atencion: datetime | None
    proxima_cita: datetime | None
    redaccion_disponible: bool


class RedaccionSalida(BaseModel):
    texto: str
    modelo: str
    aviso: str
    generado_en: datetime


def _recortar(texto: str | None, largo: int = 400) -> str | None:
    if not texto:
        return None
    limpio = " ".join(texto.split())
    return limpio if len(limpio) <= largo else limpio[: largo - 1] + "…"


def _edad(nacimiento: date | None, hoy: date) -> int | None:
    if nacimiento is None:
        return None
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


async def construir(
    sesion: AsyncSession,
    principal: Principal,
    paciente_id: uuid.UUID,
    ahora: datetime,
    *,
    redaccion: bool,
) -> ResumenClinico:
    paciente = await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "historia_clinica.leer", ahora
    )
    alergias = (
        await sesion.execute(
            select(Alergia).where(Alergia.paciente_id == paciente_id, Alergia.activa.is_(True))
        )
    ).scalars()
    consulta_antecedentes = select(Antecedente).where(Antecedente.paciente_id == paciente_id)
    if not principal.tiene_permiso("historia_clinica.leer_sensible"):
        consulta_antecedentes = consulta_antecedentes.where(Antecedente.nivel_sensibilidad != "N3")
    antecedentes = (await sesion.execute(consulta_antecedentes)).scalars()

    medicamentos = (
        await sesion.execute(
            select(RecetaMedicamento, Receta.confirmada_en)
            .join(Receta, Receta.id == RecetaMedicamento.receta_id)
            .where(Receta.paciente_id == paciente_id, Receta.estado == "CONFIRMADA")
            .order_by(Receta.confirmada_en.desc())
        )
    ).all()

    dias = 14
    desde = ahora - timedelta(days=dias)
    filas_tomas = (
        await sesion.execute(
            select(Toma.estado, func.count())
            .where(
                Toma.paciente_id == paciente_id,
                Toma.programada_en >= desde,
                Toma.programada_en <= ahora,
            )
            .group_by(Toma.estado)
        )
    ).all()
    conteos = {str(estado): int(cantidad) for estado, cantidad in filas_tomas}

    consulta_notas = select(NotaEvolucion).where(
        NotaEvolucion.paciente_id == paciente_id,
        NotaEvolucion.vigente.is_(True),
    )
    if not principal.tiene_permiso("historia_clinica.leer_sensible"):
        consulta_notas = consulta_notas.where(
            NotaEvolucion.nivel_sensibilidad != NivelSensibilidad.CLINICO_SENSIBLE.value
        )
    notas = (
        await sesion.execute(consulta_notas.order_by(NotaEvolucion.creado_en.desc()).limit(5))
    ).scalars()

    consulta_planes = (
        select(
            PlanTratamiento.titulo,
            PlanTratamiento.estado,
            func.count(ProcedimientoPlan.id).filter(ProcedimientoPlan.estado == "PENDIENTE"),
            PlanTratamiento.nivel_sensibilidad,
        )
        .outerjoin(ProcedimientoPlan, ProcedimientoPlan.plan_id == PlanTratamiento.id)
        .where(
            PlanTratamiento.paciente_id == paciente_id,
            PlanTratamiento.estado.in_(["BORRADOR", "PROPUESTO", "ACEPTADO"]),
        )
        .group_by(PlanTratamiento.id)
    )
    if not principal.tiene_permiso("historia_clinica.leer_sensible"):
        consulta_planes = consulta_planes.where(PlanTratamiento.nivel_sensibilidad != "N3")
    planes = (await sesion.execute(consulta_planes)).all()

    ultima = (
        await sesion.execute(
            select(func.max(Cita.inicio)).where(
                Cita.paciente_id == paciente_id, Cita.estado == "COMPLETED"
            )
        )
    ).scalar_one()
    proxima = (
        await sesion.execute(
            select(func.min(Cita.inicio)).where(
                Cita.paciente_id == paciente_id,
                Cita.inicio >= ahora,
                Cita.estado.in_(["PENDING", "HELD", "CONFIRMED", "RESCHEDULED"]),
            )
        )
    ).scalar_one()

    return ResumenClinico(
        paciente_id=paciente_id,
        edad=_edad(paciente.fecha_nacimiento, ahora.date()),
        sexo=paciente.sexo,
        alergias=[
            AlergiaResumen(
                id=a.id,
                sustancia=a.sustancia,
                reaccion=a.tipo_reaccion,
                severidad=a.severidad,
            )
            for a in alergias
        ],
        antecedentes=[
            AntecedenteResumen(
                categoria=a.categoria,
                descripcion=_recortar(a.descripcion, 200) or "",
                nivel_sensibilidad=a.nivel_sensibilidad,
            )
            for a in antecedentes
        ],
        medicacion_activa=[
            MedicamentoResumen(
                nombre=m.nombre,
                concentracion=m.concentracion,
                dosis=m.dosis,
                via=m.via,
                cuando_sea_necesario=m.cuando_sea_necesario,
                frecuencia_horas=m.frecuencia_horas,
                duracion_dias=m.duracion_dias,
                instrucciones=_recortar(m.instrucciones, 200),
                desde=confirmada,
            )
            for m, confirmada in medicamentos
        ],
        adherencia=AdherenciaResumen(
            dias=dias,
            tomadas=int(conteos.get("TOMADA", 0)),
            omitidas=int(conteos.get("OMITIDA", 0)),
            sin_registrar=int(conteos.get("PENDIENTE", 0)),
        ),
        ultimas_notas=[
            NotaResumen(
                fecha=n.creado_en,
                tipo=n.tipo,
                nivel_sensibilidad=n.nivel_sensibilidad,
                motivo_consulta=_recortar(n.motivo_consulta, 200),
                analisis=_recortar(n.analisis),
                plan=_recortar(n.plan),
            )
            for n in notas
        ],
        planes=[
            PlanResumen(
                titulo=titulo,
                estado=estado,
                procedimientos_pendientes=int(pendientes),
                nivel_sensibilidad=nivel_sensibilidad,
            )
            for titulo, estado, pendientes, nivel_sensibilidad in planes
        ],
        ultima_atencion=ultima,
        proxima_cita=proxima,
        redaccion_disponible=redaccion,
    )


@enrutador.get(
    "/pacientes/{paciente_id}/resumen-clinico",
    response_model=ResumenClinico,
    responses={404: {"description": "Paciente inexistente, fuera de alcance o sin acceso clínico"}},
)
async def resumen(
    principal: PuedeLeerHistoriaDiscreta,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    configuracion: ConfiguracionActual,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> ResumenClinico:
    datos = await construir(
        sesion,
        principal,
        paciente_id,
        reloj.ahora(),
        redaccion=RedactorResumenClinico(configuracion).disponible(),
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.HISTORIA_CONSULTADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="paciente",
                entidad_id=paciente_id,
                paciente_id=paciente_id,
                nivel_sensibilidad=(
                    NivelSensibilidad.CLINICO_SENSIBLE
                    if any(
                        a.nivel_sensibilidad == NivelSensibilidad.CLINICO_SENSIBLE.value
                        for a in datos.antecedentes
                    )
                    or any(
                        nota.nivel_sensibilidad == NivelSensibilidad.CLINICO_SENSIBLE.value
                        for nota in datos.ultimas_notas
                    )
                    or any(
                        plan.nivel_sensibilidad == NivelSensibilidad.CLINICO_SENSIBLE.value
                        for plan in datos.planes
                    )
                    else NivelSensibilidad.CLINICO
                ),
                vista="resumen_clinico",
            )
        ]
    )
    await sesion.commit()
    return datos


@enrutador.post(
    "/pacientes/{paciente_id}/resumen-clinico/redaccion",
    response_model=RedaccionSalida,
    responses={404: {"description": "Paciente inexistente, fuera de alcance o sin acceso clínico"}},
)
async def redactar(
    principal: PuedeLeerHistoriaDiscreta,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    configuracion: ConfiguracionActual,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> RedaccionSalida:
    redactor = RedactorResumenClinico(configuracion)
    datos = await construir(
        sesion, principal, paciente_id, reloj.ahora(), redaccion=redactor.disponible()
    )
    # Al modelo no le hace falta saber quién es: sin identificadores.
    carga: dict[str, Any] = datos.model_dump(
        mode="json", exclude={"paciente_id", "redaccion_disponible"}
    )
    # Un antecedente N3 puede verse en la interfaz con permiso reforzado, pero
    # queda fuera de la llamada al modelo incluso si Ollama está configurado.
    carga["antecedentes"] = [
        antecedente.model_dump(mode="json")
        for antecedente in datos.antecedentes
        if antecedente.nivel_sensibilidad != NivelSensibilidad.CLINICO_SENSIBLE.value
    ]
    # La IA local recibe métricas y contexto N2; nunca recibe notas N3, aunque
    # quien solicita la redacción tenga permiso para leerlas.
    carga["ultimas_notas"] = [
        nota.model_dump(mode="json")
        for nota in datos.ultimas_notas
        if nota.nivel_sensibilidad != NivelSensibilidad.CLINICO_SENSIBLE.value
    ]
    # Los planes N3 siguen excluidos aunque quien solicita la redacción tenga
    # permiso para consultarlos en la interfaz.
    carga["planes"] = [
        plan.model_dump(mode="json")
        for plan in datos.planes
        if plan.nivel_sensibilidad != NivelSensibilidad.CLINICO_SENSIBLE.value
    ]
    redaccion = await redactor.redactar(carga)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.RESUMEN_CLINICO_REDACTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="paciente",
                entidad_id=paciente_id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                modelo=redaccion.modelo,
            )
        ]
    )
    await sesion.commit()
    return RedaccionSalida(
        texto=redaccion.texto,
        modelo=redaccion.modelo,
        aviso=redaccion.aviso,
        generado_en=reloj.ahora(),
    )


__all__ = ["ResumenClinico", "construir", "enrutador"]
