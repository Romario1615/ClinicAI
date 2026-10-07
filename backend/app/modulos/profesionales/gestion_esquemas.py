"""Contratos para la administración de perfiles profesionales."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EstadoPerfil = Literal["DISPONIBLE", "AGENDA_COMPLETA", "AUSENTE", "INACTIVO"]


class DatosPerfilProfesional(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    especialidad_id: uuid.UUID
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    numero_registro_profesional: str | None = Field(default=None, max_length=64)
    telefono_whatsapp: str | None = Field(default=None, max_length=32)
    correo_calendario: str | None = Field(default=None, max_length=200)
    estado_disponibilidad: EstadoPerfil = "DISPONIBLE"
    acepta_pacientes_nuevos: bool = True
    minutos_preparacion_propio: int = Field(default=0, ge=0, le=240)
    activo: bool = True
    sede_ids: list[uuid.UUID] = Field(min_length=1, max_length=30)
    sede_principal_id: uuid.UUID

    @field_validator("numero_registro_profesional", "telefono_whatsapp", "correo_calendario")
    @classmethod
    def texto_opcional_no_vacio(cls, valor: str | None) -> str | None:
        if valor is not None and not valor.strip():
            return None
        return valor

    @field_validator("sede_ids")
    @classmethod
    def sedes_sin_duplicados(cls, sedes: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(sedes) != len(set(sedes)):
            raise ValueError("La lista de sedes no puede tener duplicados.")
        return sedes

    @model_validator(mode="after")
    def sede_principal_asignada(self) -> DatosPerfilProfesional:
        if self.sede_principal_id not in self.sede_ids:
            raise ValueError("La sede principal debe estar asignada al profesional.")
        if self.activo and self.estado_disponibilidad == "INACTIVO":
            raise ValueError("Un profesional activo no puede tener disponibilidad inactiva.")
        return self


class RespuestaPerfilProfesional(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    especialidad_id: uuid.UUID
    nombre: str
    apellido: str
    numero_registro_profesional: str | None
    telefono_whatsapp: str | None
    correo_calendario: str | None
    estado_disponibilidad: EstadoPerfil
    acepta_pacientes_nuevos: bool
    minutos_preparacion_propio: int
    activo: bool
    sede_ids: list[uuid.UUID]
    sede_principal_id: uuid.UUID | None
