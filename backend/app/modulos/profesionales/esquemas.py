"""Esquemas para la disponibilidad semanal de cada profesional."""

from __future__ import annotations

import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatosAgendaPlantilla(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dia_semana: int = Field(ge=1, le=7)
    hora_inicio: time
    hora_fin: time
    granularidad_minutos: int = Field(default=15, ge=1, le=240)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None

    @model_validator(mode="after")
    def validar_intervalo(self) -> DatosAgendaPlantilla:
        if self.hora_inicio >= self.hora_fin:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio.")
        if (
            self.hora_inicio.second
            or self.hora_inicio.microsecond
            or self.hora_fin.second
            or self.hora_fin.microsecond
        ):
            raise ValueError("Las horas deben expresarse con precisión de minutos.")
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            raise ValueError("La fecha final no puede ser anterior a la fecha inicial.")
        return self


class RespuestaAgendaPlantilla(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    profesional_id: uuid.UUID
    sede_id: uuid.UUID
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    granularidad_minutos: int
    vigente_desde: date | None
    vigente_hasta: date | None


__all__ = ["DatosAgendaPlantilla", "RespuestaAgendaPlantilla"]
