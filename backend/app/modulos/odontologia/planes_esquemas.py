"""Contratos HTTP del plan de tratamiento."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modulos.odontologia.modelos import EstadoPlan, EstadoProcedimiento, MedioAceptacion
from app.modulos.odontologia.vocabulario import (
    HallazgoCara,
    HallazgoPieza,
    es_pieza_valida,
    validar_caras,
)

LONGITUD_MINIMA_CAMPO = 3
LONGITUD_MINIMA_MOTIVO = 5


class ProcedimientoNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fase: Annotated[int, Field(ge=1, le=20)] = 1
    orden: Annotated[int, Field(ge=1, le=100)] = 1
    pieza: Annotated[int | None, Field(ge=11, le=85)] = None
    caras: Annotated[str | None, Field(max_length=5)] = None
    servicio_id: uuid.UUID | None = None
    descripcion: Annotated[str, Field(min_length=3, max_length=300)]
    precio: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] = Decimal("0")

    @field_validator("pieza")
    @classmethod
    def validar_fdi(cls, pieza: int | None) -> int | None:
        if pieza is not None and not es_pieza_valida(pieza):
            raise ValueError("La pieza debe usar notación FDI válida.")
        return pieza

    @field_validator("caras")
    @classmethod
    def validar_caras_fdi(cls, caras: str | None) -> str | None:
        if caras is None:
            return None
        return validar_caras(caras)

    @field_validator("descripcion")
    @classmethod
    def limpiar_descripcion(cls, descripcion: str) -> str:
        limpia = descripcion.strip()
        if len(limpia) < LONGITUD_MINIMA_CAMPO:
            raise ValueError("La descripción debe tener al menos 3 caracteres útiles.")
        return limpia


class PlanNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Annotated[str, Field(min_length=3, max_length=200)]
    moneda: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    observaciones: Annotated[str | None, Field(max_length=2000)] = None
    nivel_sensibilidad: Literal["N2", "N3"] = "N2"
    procedimientos: Annotated[list[ProcedimientoNuevo], Field(min_length=1, max_length=100)]

    @field_validator("titulo")
    @classmethod
    def limpiar_titulo(cls, titulo: str) -> str:
        limpio = titulo.strip()
        if len(limpio) < LONGITUD_MINIMA_CAMPO:
            raise ValueError("El título debe tener al menos 3 caracteres útiles.")
        return limpio

    @field_validator("observaciones")
    @classmethod
    def limpiar_observaciones(cls, observaciones: str | None) -> str | None:
        return observaciones.strip() or None if observaciones is not None else None

    @model_validator(mode="after")
    def ordenes_unicas(self) -> PlanNuevo:
        posiciones = [(item.fase, item.orden) for item in self.procedimientos]
        if len(posiciones) != len(set(posiciones)):
            raise ValueError("No repita el orden de un procedimiento dentro de una fase.")
        return self


class PlantillaNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=3, max_length=150)]
    descripcion: Annotated[str | None, Field(max_length=1000)] = None
    procedimientos: Annotated[list[ProcedimientoNuevo], Field(min_length=1, max_length=100)]

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, nombre: str) -> str:
        limpio = " ".join(nombre.split())
        if len(limpio) < LONGITUD_MINIMA_CAMPO:
            raise ValueError("El nombre debe tener al menos 3 caracteres utiles.")
        return limpio


class PlantillaSalida(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    procedimientos: list[ProcedimientoNuevo]
    creado_en: datetime


class AceptacionPlan(BaseModel):
    """Constancia de que el paciente acepto el plan.

    El profesional **registra** una aceptacion que ya ocurrio fuera del
    sistema (documento firmado en la clinica). No es una firma digital del
    paciente y la interfaz no la presenta como tal.
    """

    model_config = ConfigDict(extra="forbid")

    medio: MedioAceptacion
    referencia: Annotated[str, Field(min_length=3, max_length=200)]
    imagen_id: uuid.UUID | None = None

    @field_validator("referencia")
    @classmethod
    def limpiar_referencia(cls, referencia: str) -> str:
        limpia = referencia.strip()
        if len(limpia) < LONGITUD_MINIMA_CAMPO:
            raise ValueError("Indique la referencia del documento firmado.")
        return limpia


class CompletarProcedimiento(BaseModel):
    """Cierre, resultado odontográfico y fecha de control elegida por el profesional."""

    model_config = ConfigDict(extra="forbid")

    hallazgo_resultante: HallazgoPieza | HallazgoCara | None = None
    cita_id: uuid.UUID | None = None
    control_recomendado_en: date | None = None


class AtencionControl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nota: Annotated[str | None, Field(max_length=1000)] = None

    @field_validator("nota")
    @classmethod
    def limpiar_nota(cls, nota: str | None) -> str | None:
        limpia = nota.strip() if nota is not None else None
        return limpia or None


class Cancelacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Annotated[str, Field(min_length=5, max_length=500)]

    @field_validator("motivo")
    @classmethod
    def limpiar_motivo(cls, motivo: str) -> str:
        limpio = motivo.strip()
        if len(limpio) < LONGITUD_MINIMA_MOTIVO:
            raise ValueError("Indique el motivo de la cancelacion.")
        return limpio


class ProcedimientoPlanSalida(BaseModel):
    id: uuid.UUID
    fase: int
    orden: int
    pieza: int | None
    caras: str | None
    servicio_id: uuid.UUID | None
    descripcion: str
    precio: Decimal
    estado: EstadoProcedimiento
    hallazgo_resultante: str | None = None
    cita_id: uuid.UUID | None
    completado_en: datetime | None
    control_recomendado_en: date | None = None
    control_atendido_en: datetime | None = None
    control_nota: str | None = None
    cancelado_en: datetime | None = None
    motivo_cancelacion: str | None = None


class PlanSalida(BaseModel):
    id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    titulo: str
    estado: EstadoPlan
    moneda: str
    observaciones: str | None
    nivel_sensibilidad: Literal["N2", "N3"]
    propuesto_en: datetime | None
    aceptado_en: datetime | None
    aceptacion_medio: MedioAceptacion | None = None
    aceptacion_referencia: str | None = None
    completado_en: datetime | None
    cancelado_en: datetime | None = None
    motivo_cancelacion: str | None = None
    creado_en: datetime
    procedimientos: list[ProcedimientoPlanSalida]


__all__ = [
    "AceptacionPlan",
    "AtencionControl",
    "Cancelacion",
    "CompletarProcedimiento",
    "PlanNuevo",
    "PlanSalida",
    "PlantillaNueva",
    "PlantillaSalida",
    "ProcedimientoNuevo",
    "ProcedimientoPlanSalida",
]
