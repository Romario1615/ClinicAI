import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modulos.dashboard.esquemas import FiltroDashboard


class AbrirDemo(FiltroDashboard):
    model_config = ConfigDict(extra="forbid")
    paciente_id: uuid.UUID
    sede_id: uuid.UUID
    servicio_id: uuid.UUID
    profesional_id: uuid.UUID
    modo: Literal["simulado", "configurado"] = "simulado"


class MensajeDemo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    texto: str = Field(min_length=1, max_length=1000)


class RespuestaDemo(BaseModel):
    sesion_id: uuid.UUID
    modo: Literal["simulado", "configurado"] = "simulado"
    mensaje: str
    requiere_humano: bool = False
    herramientas: list[str] = Field(default_factory=list)
    datos: dict[str, Any] = Field(default_factory=dict)
