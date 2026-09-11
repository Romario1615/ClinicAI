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

from pydantic import BaseModel, ConfigDict


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
