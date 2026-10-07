import uuid
from datetime import date, datetime
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
    total_acordado: Decimal | None = Field(
        default=None, gt=0, le=9999999999, max_digits=12, decimal_places=2
    )
    fecha_vencimiento: date | None = None


class DatosCargoPago(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cita_id: uuid.UUID
    total_acordado: Decimal = Field(gt=0, le=9999999999, max_digits=12, decimal_places=2)
    fecha_vencimiento: date | None = None


class TotalCargoPago(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    total_acordado: Decimal = Field(gt=0, le=9999999999, max_digits=12, decimal_places=2)
    fecha_vencimiento: date | None = None


class FechaVencimientoCargo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha_vencimiento: date


class CambioPago(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    estado: EstadoPago
    comentario: str = Field(min_length=3, max_length=500)


class RespuestaPago(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    cita_id: uuid.UUID
    cargo_id: uuid.UUID | None = None
    importe: Decimal
    moneda: str
    metodo: str
    estado: EstadoPago
    referencia: str | None
    comentario: str | None
    validado_por: uuid.UUID | None
    validado_en: datetime | None
    creado_en: datetime
    # Para reconocer el pago de un vistazo; solo en el listado.
    paciente: str | None = None
    cita_inicio: datetime | None = None
    total_acordado: Decimal | None = None
    total_confirmado: Decimal | None = None
    saldo_pendiente: Decimal | None = None
    saldo_no_asignado: Decimal | None = None


class PaginaPagos(BaseModel):
    elementos: list[RespuestaPago]
    total: int


class EventoHistorialPago(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estado_anterior: EstadoPago | None
    estado_nuevo: EstadoPago
    comentario: str | None
    actor_id: uuid.UUID | None
    secuencia: int
    ocurrido_en: datetime


class HistorialPago(BaseModel):
    elementos: list[EventoHistorialPago]


class ComprobantePago(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pago_id: uuid.UUID
    tipo_mime: Literal["application/pdf", "image/jpeg", "image/png", "image/webp"]
    tamano_bytes: int
    antivirus: Literal["LIMPIO", "NO_DISPONIBLE"]
    cargado_por: uuid.UUID
    cargado_en: datetime
    url_contenido: str


class ListaComprobantesPago(BaseModel):
    elementos: list[ComprobantePago]


class RespuestaCargoPago(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cita_id: uuid.UUID
    total_acordado: Decimal | None
    fecha_vencimiento: date | None
    moneda: Literal["USD"]
    origen: Literal["PACTADO", "HISTORICO_SIN_TOTAL"]
    creado_en: datetime
    paciente: str | None = None
    cita_inicio: datetime | None = None
    total_confirmado: Decimal
    total_comprometido: Decimal
    saldo_pendiente: Decimal | None
    saldo_no_asignado: Decimal | None
    vencido: bool


class PaginaCargosPago(BaseModel):
    elementos: list[RespuestaCargoPago]
    total: int
