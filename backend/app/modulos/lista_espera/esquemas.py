from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DIA_SEMANA_MINIMO = 0
DIA_SEMANA_MAXIMO = 6


class PreferenciasHorario(BaseModel):
    """Ventana local de días y horas que el paciente puede aceptar.

    Los días usan ISO-8601: lunes es 0 y domingo es 6. Las horas se interpretan
    en la zona horaria de la sede que se eligió para la lista.
    """

    model_config = ConfigDict(extra="forbid")

    dias_semana: list[int] = Field(default_factory=list, max_length=7)
    hora_desde: time | None = None
    hora_hasta: time | None = None

    @field_validator("hora_desde", "hora_hasta")
    @classmethod
    def hora_local_sin_desplazamiento(cls, valor: time | None) -> time | None:
        if valor is not None and valor.tzinfo is not None:
            raise ValueError("Las horas son locales a la sede y no aceptan un desplazamiento UTC.")
        return valor

    @model_validator(mode="after")
    def preferencias_coherentes(self) -> PreferenciasHorario:
        if any(not DIA_SEMANA_MINIMO <= dia <= DIA_SEMANA_MAXIMO for dia in self.dias_semana):
            raise ValueError("Los días deben ir de 0 (lunes) a 6 (domingo).")
        if len(set(self.dias_semana)) != len(self.dias_semana):
            raise ValueError("No repita días de la semana.")
        if (self.hora_desde is None) != (self.hora_hasta is None):
            raise ValueError("Indique tanto la hora inicial como la final.")
        if (
            self.hora_desde is not None
            and self.hora_hasta is not None
            and self.hora_desde >= self.hora_hasta
        ):
            raise ValueError("La hora final debe ser posterior a la inicial.")
        if not self.dias_semana and self.hora_desde is None:
            raise ValueError("Seleccione al menos un día o una franja horaria.")
        return self


class DatosEspera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paciente_id: uuid.UUID
    sede_id: uuid.UUID
    especialidad_id: uuid.UUID
    servicio_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    disponible_desde: date | None = None
    disponible_hasta: date | None = None
    prioridad: Literal["NORMAL", "ALTA"] = "NORMAL"
    horas_antelacion_minima: int = Field(default=4, ge=0, le=168)
    preferencias: PreferenciasHorario | None = None
    cita_previa_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def disponibilidad_coherente(self) -> DatosEspera:
        if (
            self.disponible_desde is not None
            and self.disponible_hasta is not None
            and self.disponible_hasta < self.disponible_desde
        ):
            raise ValueError("La fecha final no puede ser anterior a la inicial.")
        return self


class RespuestaEspera(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    paciente_id: uuid.UUID
    sede_id: uuid.UUID
    especialidad_id: uuid.UUID
    servicio_id: uuid.UUID | None
    profesional_id: uuid.UUID | None
    prioridad: str
    estado: str
    horas_antelacion_minima: int
    disponible_desde: date | None
    disponible_hasta: date | None
    preferencias: PreferenciasHorario | None
    cita_previa_id: uuid.UUID | None
    cita_resultante_id: uuid.UUID | None
    oferta_id: uuid.UUID | None = None
    oferta_inicio: datetime | None = None
    oferta_expira_en: datetime | None = None
    # Falso cuando al paciente no se le pudo avisar por un canal automatico:
    # no tiene consentimiento vigente para mensajes.
    #
    # Es el dato que convierte una oferta invisible en trabajo accionable. Sin
    # el, el turno se retiene hasta que vence y nadie sabe que hay que llamar.
    oferta_avisada: bool | None = None


class PaginaEspera(BaseModel):
    elementos: list[RespuestaEspera]
    total: int


class AccionEspera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accion: Literal["cancelar", "aceptar", "rechazar"]
