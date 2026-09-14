import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DatosEspera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paciente_id: uuid.UUID
    sede_id: uuid.UUID
    especialidad_id: uuid.UUID
    servicio_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    prioridad: Literal["NORMAL", "ALTA"] = "NORMAL"
    horas_antelacion_minima: int = Field(default=4, ge=0, le=168)


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
