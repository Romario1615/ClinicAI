"""Esquemas de salida del catalogo.

Todos explicitos. `Clinica` tiene `identificacion_fiscal`, y `Sede` tiene
`minutos_antelacion_minima` y las columnas de auditoria: nada de eso sale
salvo que se declare aqui, y de la identificacion fiscal no hay ningun motivo
para que llegue a un desplegable de la interfaz.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RespuestaClinica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    zona_horaria: str
    idioma: str
    moneda: str


class RespuestaSede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    direccion: str | None
    telefono: str | None
    # La zona horaria efectiva: la de la sede si la tiene, la de la clinica si
    # no. Se resuelve en la ruta para que el cliente no tenga que combinar dos
    # respuestas y arriesgarse a mostrar una hora en el huso equivocado.
    zona_horaria: str
    minutos_antelacion_minima: int


class RespuestaConsultorio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sede_id: uuid.UUID
    nombre: str
    tipo: str
    capacidad: int


class RespuestaEspecialidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    codigo: str | None
    descripcion: str | None


class RespuestaServicio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    especialidad_id: uuid.UUID
    nombre: str
    descripcion: str | None
    duracion_minutos: int
    minutos_preparacion: int
    precio: Decimal | None
    moneda: str


class RespuestaProfesional(BaseModel):
    """Ficha publica de un profesional.

    No incluye `telefono_whatsapp` ni `correo_calendario`: son datos de
    contacto personal del profesional y de configuracion de integraciones, y
    un desplegable de la agenda no los necesita.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    especialidad_id: uuid.UUID
    nombre: str
    apellido: str
    numero_registro_profesional: str | None
    estado_disponibilidad: str
    minutos_preparacion_propio: int


__all__ = [
    "RespuestaClinica",
    "RespuestaConsultorio",
    "RespuestaEspecialidad",
    "RespuestaProfesional",
    "RespuestaSede",
    "RespuestaServicio",
]
