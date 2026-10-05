"""Contratos HTTP de las campanas de promociones."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modulos.promociones.modelos import EstadoCampana

_HUECO = re.compile(r"[{}]")


def limpiar_texto(texto: str) -> str:
    """Normaliza espacios y rechaza llaves: el nombre del paciente lo pone el sistema."""
    limpio = " ".join(texto.split())
    if _HUECO.search(limpio):
        raise ValueError("El texto no admite llaves: el nombre del paciente se agrega solo.")
    return limpio


class Segmento(BaseModel):
    """A quien va la campana. Solo datos administrativos.

    `sin_visita_hace_dias`: ultima visita completada hace al menos N dias
    (reactivacion). `visita_en_ultimos_dias`: visito en los ultimos N dias.
    No hay filtro por diagnostico ni por tratamiento, a proposito.
    """

    model_config = ConfigDict(extra="forbid")

    sede_id: uuid.UUID | None = None
    sin_visita_hace_dias: Annotated[int | None, Field(ge=1, le=3650)] = None
    visita_en_ultimos_dias: Annotated[int | None, Field(ge=1, le=3650)] = None

    @model_validator(mode="after")
    def coherente(self) -> Segmento:
        if self.sin_visita_hace_dias and self.visita_en_ultimos_dias:
            raise ValueError("Elija «sin visita desde» o «visitó en», no ambos.")
        return self


class CampanaNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=3, max_length=150)]
    texto: Annotated[str, Field(min_length=10, max_length=500)]
    plantilla_meta: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,100}$")] = "promocion_clinica"
    segmento: Segmento = Field(default_factory=Segmento)

    @field_validator("texto")
    @classmethod
    def texto_sin_huecos(cls, texto: str) -> str:
        return limpiar_texto(texto)


class CambiosCampana(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str | None, Field(min_length=3, max_length=150)] = None
    texto: Annotated[str | None, Field(min_length=10, max_length=500)] = None
    plantilla_meta: Annotated[str | None, Field(pattern=r"^[a-z0-9_]{1,100}$")] = None
    segmento: Segmento | None = None

    @field_validator("texto")
    @classmethod
    def texto_sin_huecos(cls, texto: str | None) -> str | None:
        return limpiar_texto(texto) if texto is not None else None


class GenerarImagen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descripcion: Annotated[str, Field(min_length=10, max_length=600)]


class EnviarCampana(BaseModel):
    model_config = ConfigDict(extra="forbid")

    programada_para: datetime | None = None


class Cancelacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Annotated[str, Field(min_length=5, max_length=500)]


class CampanaSalida(BaseModel):
    id: uuid.UUID
    nombre: str
    texto: str
    plantilla_meta: str
    estado: EstadoCampana
    segmento: Segmento
    tiene_imagen: bool
    imagen_origen: str | None
    imagen_proveedor: str | None
    imagen_prompt: str | None
    aprobada_en: datetime | None
    programada_para: datetime | None
    enviada_en: datetime | None
    encolados: int
    omitidos: int
    cancelada_en: datetime | None
    motivo_cancelacion: str | None
    creado_en: datetime
    vista_previa: str


class Audiencia(BaseModel):
    """Cuantos recibirian la campana. Solo el recuento: no se listan pacientes."""

    con_consentimiento: int


__all__ = [
    "Audiencia",
    "CambiosCampana",
    "CampanaNueva",
    "CampanaSalida",
    "Cancelacion",
    "EnviarCampana",
    "GenerarImagen",
    "Segmento",
]
