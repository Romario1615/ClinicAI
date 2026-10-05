"""Esquemas de salida de pacientes.

Lo que NO sale de aqui, y por que
---------------------------------
El modelo `Paciente` tiene mas campos de los que se declaran. Quedan fuera a
proposito:

* `preferencias_horario` -- util para la lista de espera, no para una ficha.
* `verificado_por` y `verificado_en` -- trazabilidad interna del proceso de
  verificacion de identidad; el dato que la interfaz necesita es el nivel
  alcanzado, no quien lo concedio.
* Las columnas de auditoria y de anulacion.

No es una lista de exclusiones: es una lista de inclusiones. Un esquema que
serializa el modelo completo y confia en recordar excluir campos filtra datos
en cuanto alguien anade una columna meses despues.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modulos.pacientes.modelos import TipoDocumento


class DatosPaciente(BaseModel):
    """Ficha administrativa. El nivel de identidad no lo decide este formulario."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    tipo_documento: TipoDocumento = TipoDocumento.CEDULA
    numero_documento: str | None = Field(default=None, min_length=3, max_length=32)
    fecha_nacimiento: date | None = None
    sexo: Literal["F", "M", "OTRO"] | None = None
    telefono_whatsapp: str | None = Field(default=None, pattern=r"^\+?[0-9 ()-]{7,32}$")
    correo: str | None = Field(default=None, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    direccion: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def documento_coherente(self) -> DatosPaciente:
        if self.tipo_documento != TipoDocumento.SIN_DOCUMENTO and not self.numero_documento:
            raise ValueError("Indique el numero de documento.")
        if self.tipo_documento == TipoDocumento.SIN_DOCUMENTO and self.numero_documento:
            raise ValueError("Sin documento no admite un numero de documento.")
        return self


class RespuestaPaciente(BaseModel):
    """Paciente tal como aparece en un listado o en un buscador."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    tipo_documento: str
    numero_documento: str | None
    nombre: str
    apellido: str
    fecha_nacimiento: date | None
    telefono_whatsapp: str | None
    correo: str | None
    # Nivel de verificacion de identidad. Importa en la interfaz: un telefono
    # no verificado NO basta para dar informacion por WhatsApp, y quien
    # atiende tiene que verlo antes de hablar.
    nivel_verificacion: str


class RespuestaPacienteDetalle(RespuestaPaciente):
    """Ficha completa administrativa. Sigue sin contener nada clinico."""

    sexo: str | None
    direccion: str | None
    activo: bool


class PaginaPacientes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elementos: list[RespuestaPaciente]
    total: int
    limite: int
    desplazamiento: int
    # Cierto cuando el termino era demasiado corto y se ignoro. Sin este
    # campo, la interfaz mostraria "sin resultados" y el usuario creeria que
    # ese paciente no existe.
    termino_ignorado: bool = False


__all__ = [
    "PaginaPacientes",
    "RespuestaPaciente",
    "RespuestaPacienteDetalle",
]
