"""Esquemas de salida del catalogo.

Todos explicitos. `Clinica` tiene `identificacion_fiscal`, y `Sede` tiene
`minutos_antelacion_minima` y las columnas de auditoria: nada de eso sale
salvo que se declare aqui, y de la identificacion fiscal no hay ningun motivo
para que llegue a un desplegable de la interfaz.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RespuestaClinica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    zona_horaria: str
    idioma: str
    moneda: str
    identificacion_fiscal: str | None = None
    telefono: str | None = None
    correo: str | None = None


class RespuestaClinicaCatalogo(BaseModel):
    """Datos de clinica para catálogos, sin información fiscal."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    zona_horaria: str
    idioma: str
    moneda: str
    telefono: str | None = None
    correo: str | None = None


class ActualizarClinica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str
    identificacion_fiscal: str | None = None
    zona_horaria: str
    idioma: str
    moneda: str
    telefono: str | None = None
    correo: str | None = None


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


class ActualizarSede(BaseModel):
    """Campos que la clínica puede mantener en una sede ya aprovisionada."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=200)
    direccion: str | None = Field(default=None, max_length=500)
    telefono: str | None = Field(default=None, max_length=32)
    zona_horaria: str = Field(min_length=1, max_length=64)
    minutos_antelacion_minima: int = Field(ge=0, le=10080)


class RespuestaConsultorio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sede_id: uuid.UUID
    nombre: str
    tipo: str
    capacidad: int
    activo: bool = True


class DatosConsultorio(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str
    tipo: Literal["CONSULTA", "PROCEDIMIENTOS", "IMAGEN", "LABORATORIO", "OTRO"]
    capacidad: int


class CrearConsultorio(DatosConsultorio):
    sede_id: uuid.UUID


class EstadoConsultorio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activo: bool


class DatosEspecialidad(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nombre: str
    codigo: str | None = None
    descripcion: str | None = None


class CrearEspecialidad(DatosEspecialidad):
    pass


class EstadoRecurso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activo: bool


class DatosServicio(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    especialidad_id: uuid.UUID
    nombre: str
    descripcion: str | None = None
    duracion_minutos: int
    minutos_preparacion: int = 0
    precio: Decimal | None = None
    moneda: str = "USD"
    requiere_pago_previo: bool = False
    instrucciones_preparacion: str | None = None
    tipo_consultorio_requerido: (
        Literal["CONSULTA", "PROCEDIMIENTOS", "IMAGEN", "LABORATORIO", "OTRO"] | None
    ) = None


class CrearServicio(DatosServicio):
    pass


class RespuestaEspecialidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    codigo: str | None
    descripcion: str | None
    activa: bool = True


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


class RespuestaServicioGestion(RespuestaServicio):
    activo: bool
    requiere_pago_previo: bool
    instrucciones_preparacion: str | None
    tipo_consultorio_requerido: str | None


class DatosDescansoHorario(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hora_inicio: time
    hora_fin: time
    motivo: str | None = Field(default=None, max_length=150)


class RespuestaDescansoHorario(DatosDescansoHorario):
    id: uuid.UUID


class DatosHorarioSede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dia_semana: int = Field(ge=1, le=7)
    hora_inicio: time
    hora_fin: time
    granularidad_minutos: int = Field(default=15, ge=1, le=60)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    descansos: list[DatosDescansoHorario] = Field(default_factory=list, max_length=8)


class RespuestaHorarioSede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    granularidad_minutos: int
    vigente_desde: date | None
    vigente_hasta: date | None
    descansos: list[RespuestaDescansoHorario]


class DatosFeriado(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sede_id: uuid.UUID | None = None
    fecha: date
    nombre: str = Field(min_length=1, max_length=150)
    recurrente_anual: bool = False
    hora_inicio: time | None = None
    hora_fin: time | None = None


class RespuestaFeriado(DatosFeriado):
    id: uuid.UUID


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
    "CrearConsultorio",
    "CrearEspecialidad",
    "CrearServicio",
    "DatosConsultorio",
    "DatosDescansoHorario",
    "DatosEspecialidad",
    "DatosFeriado",
    "DatosHorarioSede",
    "DatosServicio",
    "EstadoConsultorio",
    "EstadoRecurso",
    "RespuestaClinica",
    "RespuestaClinicaCatalogo",
    "RespuestaConsultorio",
    "RespuestaDescansoHorario",
    "RespuestaEspecialidad",
    "RespuestaFeriado",
    "RespuestaHorarioSede",
    "RespuestaProfesional",
    "RespuestaSede",
    "RespuestaServicio",
    "RespuestaServicioGestion",
]
