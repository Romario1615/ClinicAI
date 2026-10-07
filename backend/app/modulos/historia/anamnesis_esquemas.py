"""Contratos para el diseñador y registro de anamnesis configurable."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TipoPregunta = Literal["texto", "texto_largo", "booleano", "seleccion", "seleccion_multiple"]
SensibilidadAnamnesis = Literal["N2", "N3"]


class PreguntaAnamnesis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: Annotated[str, Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_-]*$")]
    etiqueta: Annotated[str, Field(min_length=2, max_length=160)]
    tipo: TipoPregunta
    obligatoria: bool = False
    ayuda: Annotated[str | None, Field(default=None, max_length=240)]
    opciones: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=100)]], Field(max_length=20)
    ] = Field(default_factory=list)

    @field_validator("opciones")
    @classmethod
    def opciones_sin_duplicados(cls, opciones: list[str]) -> list[str]:
        normalizadas = [opcion.casefold() for opcion in opciones]
        if len(normalizadas) != len(set(normalizadas)):
            raise ValueError("Las opciones de una pregunta no pueden repetirse.")
        return opciones

    @model_validator(mode="after")
    def opciones_coherentes(self) -> PreguntaAnamnesis:
        requiere_opciones = self.tipo in {"seleccion", "seleccion_multiple"}
        if requiere_opciones and not self.opciones:
            raise ValueError("Las preguntas de selección necesitan al menos una opción.")
        if not requiere_opciones and self.opciones:
            raise ValueError("Solo las preguntas de selección pueden definir opciones.")
        return self


class PlantillaAnamnesisEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: Annotated[str, Field(min_length=3, max_length=100)]
    nivel_sensibilidad: SensibilidadAnamnesis = "N2"
    preguntas: Annotated[list[PreguntaAnamnesis], Field(min_length=1, max_length=40)]

    @field_validator("preguntas")
    @classmethod
    def ids_unicos(cls, preguntas: list[PreguntaAnamnesis]) -> list[PreguntaAnamnesis]:
        ids = [pregunta.id for pregunta in preguntas]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada pregunta debe tener un identificador único.")
        return preguntas


class PlantillaAnamnesisSalida(BaseModel):
    id: uuid.UUID
    nombre: str
    version: int
    estado: str
    nivel_sensibilidad: str
    preguntas: list[PreguntaAnamnesis]
    creada_en: datetime
    publicada_en: datetime | None


class CapturaAnamnesisEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plantilla_id: uuid.UUID
    respuestas: Annotated[dict[str, object], Field(max_length=40)]


class RespuestaAnamnesisSalida(BaseModel):
    id: uuid.UUID
    plantilla_id: uuid.UUID
    plantilla: str
    version_plantilla: int
    nivel_sensibilidad: str
    preguntas: list[PreguntaAnamnesis]
    respuestas: dict[str, object]
    registrada_en: datetime


__all__ = [
    "CapturaAnamnesisEntrada",
    "PlantillaAnamnesisEntrada",
    "PlantillaAnamnesisSalida",
    "PreguntaAnamnesis",
    "RespuestaAnamnesisSalida",
]
