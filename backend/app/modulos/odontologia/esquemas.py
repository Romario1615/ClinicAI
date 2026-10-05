"""Contratos HTTP del odontograma versionado."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modulos.odontologia.vocabulario import (
    PIEZAS_PERMANENTES,
    PIEZAS_TEMPORALES,
    Cara,
    Denticion,
    HallazgoCara,
    HallazgoPieza,
    es_pieza_valida,
)


class PiezaOdontograma(BaseModel):
    """Estado observado en una pieza; no representa diagnóstico generado por IA."""

    model_config = ConfigDict(extra="forbid")

    pieza: HallazgoPieza | None = None
    caras: dict[Cara, HallazgoCara] = Field(default_factory=dict)
    nota: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def ausencia_sin_caras(self) -> PiezaOdontograma:
        if self.pieza is HallazgoPieza.AUSENTE and self.caras:
            raise ValueError("Una pieza ausente no puede tener hallazgos por cara.")
        return self


class ContenidoOdontograma(BaseModel):
    """Contenido completo de una versión, nunca un parche parcial."""

    model_config = ConfigDict(extra="forbid")

    denticion: Denticion
    piezas: dict[str, PiezaOdontograma] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def validar_piezas_fdi(self) -> ContenidoOdontograma:
        for codigo in self.piezas:
            if not codigo.isdecimal() or not es_pieza_valida(int(codigo)):
                raise ValueError(f"La pieza FDI {codigo!r} no existe.")
            numero = int(codigo)
            if self.denticion is Denticion.PERMANENTE and numero not in PIEZAS_PERMANENTES:
                raise ValueError("La dentición permanente no admite piezas temporales.")
            if self.denticion is Denticion.TEMPORAL and numero not in PIEZAS_TEMPORALES:
                raise ValueError("La dentición temporal no admite piezas permanentes.")
        return self


class OdontogramaInicial(ContenidoOdontograma):
    """Primera versión del odontograma de un paciente."""


class NuevaVersionOdontograma(ContenidoOdontograma):
    """Reemplazo completo con control optimista y motivo obligatorio."""

    version_base: Annotated[int, Field(ge=1)]
    motivo: Annotated[str, Field(min_length=8, max_length=500)]


class OdontogramaSalida(ContenidoOdontograma):
    id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    version: int
    vigente: bool
    motivo_modificacion: str | None
    procedimiento_id: uuid.UUID | None
    creado_en: datetime


__all__ = [
    "ContenidoOdontograma",
    "NuevaVersionOdontograma",
    "OdontogramaInicial",
    "OdontogramaSalida",
    "PiezaOdontograma",
]
