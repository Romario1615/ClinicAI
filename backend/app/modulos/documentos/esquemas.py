from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ZONAS = {
    "frente_central": ("Frente central", 160, 82),
    "frente_derecha": ("Frente derecha", 120, 90),
    "frente_izquierda": ("Frente izquierda", 200, 90),
    "glabela": ("Glabela", 160, 121),
    "sien_derecha": ("Sien derecha", 92, 130),
    "sien_izquierda": ("Sien izquierda", 228, 130),
    "periocular_derecha": ("Zona periocular derecha", 103, 154),
    "periocular_izquierda": ("Zona periocular izquierda", 217, 154),
    "ojera_derecha": ("Zona infraorbitaria derecha", 125, 175),
    "ojera_izquierda": ("Zona infraorbitaria izquierda", 195, 175),
    "nariz": ("Nariz", 160, 180),
    "pomulo_derecho": ("Pómulo derecho", 106, 194),
    "pomulo_izquierdo": ("Pómulo izquierdo", 214, 194),
    "mejilla_derecha": ("Mejilla derecha", 114, 220),
    "mejilla_izquierda": ("Mejilla izquierda", 206, 220),
    "surco_derecho": ("Surco nasolabial derecho", 137, 216),
    "surco_izquierdo": ("Surco nasolabial izquierdo", 183, 216),
    "labio_superior": ("Labio superior", 160, 229),
    "labio_inferior": ("Labio inferior", 160, 247),
    "menton": ("Mentón", 160, 279),
    "mandibula_derecha": ("Contorno mandibular derecho", 115, 259),
    "mandibula_izquierda": ("Contorno mandibular izquierdo", 205, 259),
    "cuello": ("Cuello", 160, 338),
}


class ZonaFacial(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    zona: str
    estado: Literal["OBSERVACION", "PLANIFICADO", "REALIZADO"] = "OBSERVACION"
    observacion: str = Field(min_length=1, max_length=1500)
    procedimiento: str | None = Field(default=None, max_length=500)


class Partida(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    descripcion: str = Field(min_length=1, max_length=300)
    cantidad: Decimal = Field(gt=0, le=9999, decimal_places=2)
    precio_unitario: Decimal = Field(ge=0, le=999999, decimal_places=2)


class RegistroNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    clave_idempotencia: uuid.UUID
    tipo: Literal["FACIOGRAMA", "PRESUPUESTO", "COTIZACION", "RECETA"]
    titulo: str = Field(min_length=3, max_length=200)
    especialidad_id: uuid.UUID
    cita_id: uuid.UUID | None = None
    sede_id: uuid.UUID | None = None
    raiz_id: uuid.UUID | None = None
    version_base: int = Field(default=0, ge=0)
    motivo: str = Field(min_length=5, max_length=500)
    nivel_sensibilidad: Literal["N2", "N3"] = "N2"
    zonas: list[ZonaFacial] = Field(default_factory=list, max_length=len(ZONAS))
    partidas: list[Partida] = Field(default_factory=list, max_length=100)
    observaciones: str = Field(default="", max_length=4000)
    moneda: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    valido_hasta: date | None = None
    receta_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validar_contenido(self) -> RegistroNuevo:
        if (self.raiz_id is None) != (self.version_base == 0):
            raise ValueError("Indique la raíz y versión base juntas para editar.")
        if self.tipo == "FACIOGRAMA":
            if self.partidas or self.receta_id:
                raise ValueError("El mapa facial solo admite observaciones por zona.")
            claves = [z.zona for z in self.zonas]
            if len(set(claves)) != len(claves) or any(z not in ZONAS for z in claves):
                raise ValueError("Seleccione zonas faciales válidas sin repetir.")
        elif self.tipo == "RECETA":
            if self.receta_id is None or self.partidas or self.zonas or self.raiz_id:
                raise ValueError("Emita una receta confirmada desde su registro original.")
        elif not self.partidas or self.zonas or self.receta_id:
            raise ValueError("El presupuesto o cotización necesita partidas.")
        return self


class RegistroSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    raiz_id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    especialidad_id: uuid.UUID
    sede_id: uuid.UUID | None
    cita_id: uuid.UUID | None
    version: int
    tipo: str
    titulo: str
    vigente: bool
    anulado: bool
    motivo: str
    nivel_sensibilidad: str
    contenido: dict[str, object]
    creado_en: datetime


class Motivo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    motivo: str = Field(min_length=5, max_length=500)


class Compartir(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clave_idempotencia: uuid.UUID
    dias_validez: int = Field(default=7, ge=1, le=30)
    identidad_destinatario_confirmada: Literal[True]


class EntregaSalida(BaseModel):
    id: uuid.UUID
    enlace: str
    expira_en: datetime
    estado: str
    modo: str


class ContextoAtencion(BaseModel):
    id: uuid.UUID
    inicio: datetime
    estado: str
    sede_id: uuid.UUID
    sede: str
    zona_horaria: str
    especialidad_id: uuid.UUID
    especialidad: str
    profesional: str
    servicio: str


class PresupuestoDesdePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clave_idempotencia: uuid.UUID
    sede_id: uuid.UUID | None = None
    cita_id: uuid.UUID | None = None
