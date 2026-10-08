"""Salidas del chat por expediente: campos del catálogo de herramientas."""

import uuid
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field


class CitaAgente(BaseModel):
    cita_id: uuid.UUID
    inicio: AwareDatetime
    estado: str


class TurnoAgente(BaseModel):
    inicio: AwareDatetime
    fin: AwareDatetime


class PagoAgente(BaseModel):
    importe: str
    moneda: str
    estado: str
    cita: AwareDatetime


class ElementoAgente(BaseModel):
    titulo: str
    detalle: str | None = None
    enlace: str | None = None


class DatosAgente(BaseModel):
    citas: list[CitaAgente] = Field(default_factory=list)
    turnos: list[TurnoAgente] = Field(default_factory=list)
    pagos: list[PagoAgente] = Field(default_factory=list)
    elementos: list[ElementoAgente] = Field(default_factory=list)
    cita_id: uuid.UUID | None = None
    inicio: AwareDatetime | None = None
    expira_en: AwareDatetime | None = None
    zona_horaria: str | None = None
    cita_activa_inicio: AwareDatetime | None = None
    hay_mas: bool = False
    motivo: str | None = None


class PropuestaAgente(BaseModel):
    id: uuid.UUID
    nombre: str
    titulo: str
    argumentos: dict[str, Any]
    expira_en: AwareDatetime


class RespuestaAgente(BaseModel):
    sesion_id: uuid.UUID
    paciente_id: uuid.UUID
    expira_en: AwareDatetime
    texto: str
    datos: DatosAgente
    requiere_humano: bool
    modo: Literal["local", "configurado"]
    propuesta: PropuestaAgente | None = None
