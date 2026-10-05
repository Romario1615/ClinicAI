"""Esquemas explícitos para el ciclo HTTP de imágenes de pacientes."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modulos.imagenes.modelos import TipoImagen


class ImagenSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paciente_id: uuid.UUID
    tipo: TipoImagen
    piezas: list[int]
    tomada_en: date | None
    descripcion: str | None
    procedimiento_id: uuid.UUID | None = None
    tipo_mime: str
    tamano_bytes: int
    antivirus: str
    creado_en: datetime
    url_contenido: str


class AnulacionImagen(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


__all__ = ["AnulacionImagen", "ImagenSalida"]
