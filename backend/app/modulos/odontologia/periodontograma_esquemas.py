"""Mediciones periodontales, sin inferencia de diagnóstico o tratamiento.

Convención: margen apical/recesión positivo; coronal negativo. NIC = PS + MG.
Los valores ausentes son NULL, nunca una medición de cero.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_MOTIVO = 8
PROFUNDIDAD_INTERMEDIA = 4
PROFUNDIDAD_ALTA = 6

Sitio = Literal["VM", "VC", "VD", "LM", "LC", "LD"]
SITIOS: tuple[Sitio, ...] = ("VM", "VC", "VD", "LM", "LC", "LD")
PIEZAS = tuple(q * 10 + p for q in range(1, 5) for p in range(1, 9))


class MedicionPeriodontal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profundidad: Annotated[float | None, Field(ge=0, le=20, allow_inf_nan=False, strict=True)] = (
        None
    )
    margen: Annotated[float | None, Field(ge=-20, le=20, allow_inf_nan=False, strict=True)] = None
    sangrado: bool | None = None
    placa: bool | None = None
    supuracion: bool | None = None


class PiezaPeriodontal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ausente: bool = False
    implante: bool = False
    movilidad: Annotated[int | None, Field(ge=0, le=3, strict=True)] = None
    furcacion: Annotated[int | None, Field(ge=0, le=3, strict=True)] = None
    sitios: dict[Sitio, MedicionPeriodontal] = Field(default_factory=dict)
    nota: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def coherente(self) -> PiezaPeriodontal:
        if self.ausente and (
            self.sitios or self.implante or self.movilidad is not None or self.furcacion is not None
        ):
            raise ValueError(
                "Una pieza ausente no admite mediciones, movilidad, furcación o implante."
            )
        if self.implante and (self.movilidad is not None or self.furcacion is not None):
            raise ValueError("Los implantes no admiten movilidad dental ni furcación.")
        return self


class PeriodontogramaNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clave_idempotencia: uuid.UUID
    version_anterior_id: uuid.UUID | None = None
    fecha_examen: date
    cita_id: uuid.UUID | None = None
    sede_id: uuid.UUID | None = None
    piezas: dict[str, PiezaPeriodontal] = Field(default_factory=dict, max_length=32)
    observaciones: Annotated[str | None, Field(max_length=2000)] = None
    motivo: Annotated[str, Field(min_length=8, max_length=500)]
    nivel_sensibilidad: Literal["N2", "N3"] = "N2"
    anulado: bool = False

    @model_validator(mode="after")
    def coherente(self) -> PeriodontogramaNuevo:
        if any(p not in {str(n) for n in PIEZAS} for p in self.piezas):
            raise ValueError("El periodontograma utiliza las 32 piezas permanentes FDI.")
        if len(self.motivo.strip()) < MIN_MOTIVO:
            raise ValueError("Explique el motivo con al menos ocho caracteres.")
        if self.anulado and self.version_anterior_id is None:
            raise ValueError("Solo se puede anular un registro existente.")
        if not self.anulado and not any(
            p.ausente
            or p.implante
            or p.movilidad is not None
            or p.furcacion is not None
            or any(any(v is not None for v in s.model_dump().values()) for s in p.sitios.values())
            for p in self.piezas.values()
        ):
            raise ValueError("Registre al menos una observación periodontal.")
        return self


class ResumenPeriodontal(BaseModel):
    sitios_posibles: int
    sitios_sondados: int
    profundidad_media: float | None
    insercion_media: float | None
    sitios_insercion: int
    sangrado_positivos: int
    sangrado_evaluados: int
    sangrado_porcentaje: float | None
    placa_positivos: int
    placa_evaluados: int
    placa_porcentaje: float | None
    sitios_4_5: int
    sitios_6_mas: int


def resumir_piezas(piezas: dict[str, PiezaPeriodontal]) -> ResumenPeriodontal:
    presentes = [p for p in piezas.values() if not p.ausente]
    sitios = [s for p in presentes for s in p.sitios.values()]
    profundidades = [s.profundidad for s in sitios if s.profundidad is not None]
    inserciones = [
        s.profundidad + s.margen
        for s in sitios
        if s.profundidad is not None and s.margen is not None
    ]
    sangrado = [s.sangrado for s in sitios if s.sangrado is not None]
    placa = [s.placa for s in sitios if s.placa is not None]
    ausentes = sum(p.ausente for p in piezas.values())
    return ResumenPeriodontal(
        sitios_posibles=(32 - ausentes) * 6,
        sitios_sondados=len(profundidades),
        profundidad_media=round(sum(profundidades) / len(profundidades), 2)
        if profundidades
        else None,
        insercion_media=round(sum(inserciones) / len(inserciones), 2) if inserciones else None,
        sitios_insercion=len(inserciones),
        sangrado_positivos=sum(sangrado),
        sangrado_evaluados=len(sangrado),
        sangrado_porcentaje=round(sum(sangrado) * 100 / len(sangrado), 2) if sangrado else None,
        placa_positivos=sum(placa),
        placa_evaluados=len(placa),
        placa_porcentaje=round(sum(placa) * 100 / len(placa), 2) if placa else None,
        sitios_4_5=sum(PROFUNDIDAD_INTERMEDIA <= p < PROFUNDIDAD_ALTA for p in profundidades),
        sitios_6_mas=sum(p >= PROFUNDIDAD_ALTA for p in profundidades),
    )


class PeriodontogramaSalida(BaseModel):
    id: uuid.UUID
    raiz_id: uuid.UUID
    version: int
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    especialidad_id: uuid.UUID
    sede_id: uuid.UUID | None
    cita_id: uuid.UUID | None
    fecha_examen: date
    piezas: dict[str, PiezaPeriodontal]
    observaciones: str | None
    motivo: str
    nivel_sensibilidad: Literal["N2", "N3"]
    anulado: bool
    vigente: bool
    puede_editar: bool
    creado_en: datetime
    resumen: ResumenPeriodontal
