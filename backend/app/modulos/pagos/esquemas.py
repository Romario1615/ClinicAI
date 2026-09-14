import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EstadoPago = Literal[
    "PENDING", "PROOF_RECEIVED", "UNDER_REVIEW", "CONFIRMED", "REJECTED", "REFUND_PENDING"
]


class DatosPago(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cita_id: uuid.UUID
    importe: Decimal = Field(gt=0, le=9999999999, max_digits=12, decimal_places=2)
    metodo: Literal["EFECTIVO", "TRANSFERENCIA"]
    referencia: str | None = Field(default=None, min_length=1, max_length=100)


class CambioPago(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    estado: EstadoPago
    comentario: str = Field(min_length=3, max_length=500)


class RespuestaPago(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    cita_id: uuid.UUID
    importe: Decimal
    moneda: str
    metodo: str
    estado: EstadoPago
    referencia: str | None
    comentario: str | None
    validado_por: uuid.UUID | None
    validado_en: datetime | None
    creado_en: datetime


class PaginaPagos(BaseModel):
    elementos: list[RespuestaPago]
    total: int
