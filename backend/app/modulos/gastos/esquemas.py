"""Esquemas de entrada y salida del libro de gastos y del flujo de caja."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CategoriaGasto = Literal[
    "INSUMOS",
    "LABORATORIO",
    "NOMINA",
    "HONORARIOS",
    "ARRIENDO",
    "SERVICIOS_BASICOS",
    "MANTENIMIENTO",
    "EQUIPAMIENTO",
    "MARKETING",
    "IMPUESTOS",
    "OTROS",
]
MetodoGasto = Literal["EFECTIVO", "TRANSFERENCIA", "TARJETA"]
MINIMO_DESCRIPCION = 3
MINIMO_MOTIVO = 5
EstadoGasto = Literal["REGISTRADO", "ANULADO"]


def _texto_limpio(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = " ".join(valor.split())
    return limpio or None


class DatosGasto(BaseModel):
    """Un gasto nuevo. `clinica_id` no se acepta: sale de la sesion."""

    model_config = ConfigDict(extra="forbid")

    sede_id: uuid.UUID | None = None
    fecha: date
    categoria: CategoriaGasto
    descripcion: str = Field(min_length=3, max_length=300)
    proveedor: str | None = Field(default=None, max_length=200)
    importe: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    metodo: MetodoGasto
    referencia: str | None = Field(default=None, max_length=100)

    @field_validator("proveedor", "referencia", mode="after")
    @classmethod
    def _limpiar(cls, valor: str | None) -> str | None:
        return _texto_limpio(valor)

    @field_validator("descripcion", mode="after")
    @classmethod
    def _descripcion_presente(cls, valor: str) -> str:
        limpio = _texto_limpio(valor)
        if not limpio or len(limpio) < MINIMO_DESCRIPCION:
            raise ValueError("Describa el gasto con al menos 3 caracteres.")
        return limpio


class AnulacionGasto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=5, max_length=500)

    @field_validator("motivo", mode="after")
    @classmethod
    def _motivo_presente(cls, valor: str) -> str:
        limpio = " ".join(valor.split())
        if len(limpio) < MINIMO_MOTIVO:
            raise ValueError("El motivo de la anulación debe tener al menos 5 caracteres.")
        return limpio


class GastoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sede_id: uuid.UUID | None
    fecha: date
    categoria: CategoriaGasto
    descripcion: str
    proveedor: str | None
    importe: Decimal
    moneda: str
    metodo: MetodoGasto
    referencia: str | None
    estado: EstadoGasto
    creado_en: datetime
    anulado_en: datetime | None
    motivo_anulacion: str | None


class PaginaGastos(BaseModel):
    elementos: list[GastoSalida]
    total: int
    importe_total: Decimal


class DiaFlujo(BaseModel):
    fecha: date
    ingresos: Decimal
    gastos: Decimal
    resultado: Decimal


class CategoriaFlujo(BaseModel):
    categoria: CategoriaGasto
    total: Decimal
    cantidad: int


class FlujoCaja(BaseModel):
    """Entradas y salidas de dinero del periodo, en base de caja.

    No es un estado de resultados: no hay devengos, depreciaciones ni
    impuestos calculados. Por eso se llama «resultado de caja» y no
    «utilidad».
    """

    desde: date
    hasta: date
    moneda: str
    ingresos: Decimal
    gastos: Decimal
    resultado: Decimal
    margen_porcentaje: Decimal | None
    por_dia: list[DiaFlujo]
    por_categoria: list[CategoriaFlujo]
    base: str
