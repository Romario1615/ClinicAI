"""Indice de placa bacteriana de O'Leary.

Que mide
--------
En cada pieza presente se revisan cuatro superficies (vestibular, lingual o
palatina, mesial y distal) tras teñir la placa. El indice es:

    superficies con placa / superficies evaluadas x 100

Se usa para seguir la higiene del paciente entre controles; valores por
debajo del 20 % suelen tomarse como objetivo de control, pero **este modulo no
interpreta**: registra lo que el profesional observo y calcula el porcentaje.

Garantias
---------
* El porcentaje lo calcula el servidor, no el navegador.
* Cada registro es inmutable: un disparador rechaza `UPDATE` y `DELETE`. Un
  registro equivocado se compensa con uno nuevo; la serie temporal es la
  historia del paciente.
* Lectura y escritura con los permisos del odontograma, relacion asistencial
  y auditoria.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.modulos.historia.especialidades import exige_modulo
from app.modulos.odontologia.modelos import CARAS_OLEARY, RegistroPlaca
from app.modulos.odontologia.vocabulario import es_pieza_valida
from app.modulos.pacientes.acceso_clinico import GuardiaClinica
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion
from app.nucleo.errores import PermisoDenegado


# ---------------------------------------------------------------------------
#  Esquemas
# ---------------------------------------------------------------------------
class RegistroPlacaNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    piezas_evaluadas: Annotated[list[int], Field(min_length=1, max_length=52)]
    superficies_con_placa: dict[str, list[str]] = Field(default_factory=dict)
    observacion: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def coherente(self) -> RegistroPlacaNuevo:
        piezas = set(self.piezas_evaluadas)
        if len(piezas) != len(self.piezas_evaluadas):
            raise ValueError("Una pieza aparece dos veces.")
        invalidas = [p for p in piezas if not es_pieza_valida(p)]
        if invalidas:
            raise ValueError(f"Piezas FDI no validas: {sorted(invalidas)}.")
        for codigo, caras in self.superficies_con_placa.items():
            if not codigo.isdecimal() or int(codigo) not in piezas:
                raise ValueError(f"La pieza {codigo} tiene placa pero no figura como evaluada.")
            if len(set(caras)) != len(caras) or any(c not in CARAS_OLEARY for c in caras):
                raise ValueError("Las superficies del indice de O'Leary son V, L, M y D.")
        return self


class RegistroPlacaSalida(BaseModel):
    id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    piezas_evaluadas: list[int]
    superficies_con_placa: dict[str, list[str]]
    total_superficies: int
    total_con_placa: int
    porcentaje: Decimal
    observacion: str | None
    creado_en: datetime


def calcular(datos: RegistroPlacaNuevo) -> tuple[int, int, Decimal]:
    total = len(datos.piezas_evaluadas) * len(CARAS_OLEARY)
    con_placa = sum(len(caras) for caras in datos.superficies_con_placa.values())
    porcentaje = (Decimal(con_placa) * 100 / Decimal(total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return total, con_placa, porcentaje


def _salida(fila: RegistroPlaca) -> RegistroPlacaSalida:
    return RegistroPlacaSalida(
        id=fila.id,
        paciente_id=fila.paciente_id,
        profesional_id=fila.profesional_id,
        piezas_evaluadas=fila.piezas_evaluadas,
        superficies_con_placa=fila.superficies_con_placa,
        total_superficies=fila.total_superficies,
        total_con_placa=fila.total_con_placa,
        porcentaje=fila.porcentaje,
        observacion=fila.observacion,
        creado_en=fila.creado_en,
    )


# ---------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------
enrutador_placa = APIRouter(prefix="/odontologia", tags=["periodoncia"])
PuedeLeer = Annotated[Principal, Depends(exige_modulo("periodoncia", "odontograma.leer"))]
PuedeEscribir = Annotated[Principal, Depends(exige_modulo("periodoncia", "odontograma.escribir"))]


@enrutador_placa.get(
    "/pacientes/{paciente_id}/indice-placa",
    response_model=list[RegistroPlacaSalida],
    summary="Serie del indice de placa de O'Leary",
)
async def listar(
    principal: PuedeLeer,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
) -> list[RegistroPlacaSalida]:
    await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "odontograma.leer", reloj.ahora()
    )
    filas = list(
        (
            await sesion.execute(
                select(RegistroPlaca)
                .where(
                    RegistroPlaca.paciente_id == paciente_id,
                    RegistroPlaca.clinica_id == principal.clinica_id,
                )
                .order_by(RegistroPlaca.creado_en.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_CONSULTADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="registro_placa",
                entidad_id=paciente_id,
                paciente_id=paciente_id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                registros_devueltos=len(filas),
            )
        ]
    )
    await sesion.commit()
    return [_salida(fila) for fila in filas]


@enrutador_placa.post(
    "/pacientes/{paciente_id}/indice-placa",
    response_model=RegistroPlacaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un control de placa",
)
async def registrar(
    principal: PuedeEscribir,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    paciente_id: Annotated[uuid.UUID, Path()],
    datos: RegistroPlacaNuevo,
) -> RegistroPlacaSalida:
    paciente = await GuardiaClinica(sesion).acceso_clinico(
        principal, paciente_id, "odontograma.escribir", reloj.ahora()
    )
    if principal.profesional_id is None:
        raise PermisoDenegado("Solo un profesional registra controles de placa.")
    total, con_placa, porcentaje = calcular(datos)
    fila = RegistroPlaca(
        clinica_id=paciente.clinica_id,
        paciente_id=paciente.id,
        profesional_id=principal.profesional_id,
        piezas_evaluadas=sorted(datos.piezas_evaluadas),
        superficies_con_placa={
            codigo: sorted(caras, key=CARAS_OLEARY.index)
            for codigo, caras in datos.superficies_con_placa.items()
            if caras
        },
        total_superficies=total,
        total_con_placa=con_placa,
        porcentaje=porcentaje,
        observacion=(datos.observacion or "").strip() or None,
        creado_por=principal.actor_id,
    )
    sesion.add(fila)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ODONTOGRAMA_VERSIONADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="registro_placa",
                entidad_id=fila.id,
                paciente_id=paciente.id,
                nivel_sensibilidad=NivelSensibilidad.CLINICO,
                porcentaje=str(porcentaje),
            )
        ]
    )
    await sesion.commit()
    return _salida(fila)


__all__ = [
    "RegistroPlacaNuevo",
    "RegistroPlacaSalida",
    "calcular",
    "enrutador_placa",
]
