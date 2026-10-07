"""Esquemas de entrada y salida de la agenda.

Dos reglas que se aplican en todo el modulo:

**Todo instante lleva zona horaria.** Un `datetime` sin zona se rechaza con
error de validacion (ADR-0010). Aceptarlo obligaria a adivinar de que huso
es, y en una agenda medica adivinar mal desplaza la cita una hora sin que
nadie se entere hasta que el paciente llega y no le esperan.

**Los esquemas de salida son explicitos.** `Cita` tiene `notas_recepcion`,
`clave_idempotencia` y `rango`; ninguno sale salvo que se declare aqui. En
particular, `rango` es un `tstzrange` de PostgreSQL que ni siquiera es
serializable a JSON, y `notas_recepcion` es texto libre que solo debe ver
quien gestiona la agenda.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modulos.agenda.modelos import EstadoCita, OrigenCita

# Techo de la ventana de consulta. El servicio lo vuelve a comprobar; aqui se
# rechaza antes de tocar la base de datos.
DIAS_MAXIMOS_CONSULTA = 62
LONGITUD_MAXIMA_MOTIVO = 500
LONGITUD_MAXIMA_NOTAS = 2000
FrecuenciaSerieCitas = Literal["SEMANAL", "QUINCENAL", "MENSUAL"]


def _exigir_zona(valor: datetime) -> datetime:
    """Rechaza los instantes sin zona horaria (ADR-0010)."""
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError(
            "El instante debe incluir zona horaria (por ejemplo "
            "2026-04-16T09:00:00-05:00). Un instante sin zona es ambiguo."
        )
    return valor


InstanteConZona = Annotated[datetime, Field(description="ISO-8601 con desplazamiento.")]


class _ConInstantes(BaseModel):
    """Base que valida la zona horaria de todo campo de instante de entrada."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _instantes_con_zona(cls, valor: object) -> object:
        if isinstance(valor, datetime):
            return _exigir_zona(valor)
        return valor


# ---------------------------------------------------------------------------
#  Disponibilidad
# ---------------------------------------------------------------------------
class TurnoDisponible(BaseModel):
    """Un turno ofrecible.

    Se devuelven dos finales distintos a proposito. `fin_consulta` es cuando
    termina la atencion y es lo que se le muestra al paciente; `fin_bloque`
    incluye la preparacion y es lo que realmente se reserva. Mostrar el
    segundo diria que una consulta de 30 minutos dura 40.
    """

    model_config = ConfigDict(extra="forbid")

    inicio: datetime
    fin_consulta: datetime
    fin_bloque: datetime
    duracion_minutos: int
    minutos_preparacion: int


class RespuestaDisponibilidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    sede_id: uuid.UUID
    zona_horaria: str
    desde: datetime
    hasta: datetime
    turnos: list[TurnoDisponible]
    # Recuento por motivo de descarte. Permite explicar «no hay turnos»
    # diciendo si fue por feriado, por vacaciones o porque ya estan ocupados,
    # en lugar de dejar al paciente sin saber si insistir otro dia.
    motivos_sin_turno: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
#  Reserva
# ---------------------------------------------------------------------------
class PeticionReserva(_ConInstantes):
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    sede_id: uuid.UUID
    inicio: InstanteConZona
    consultorio_id: uuid.UUID | None = None
    # Vínculo opcional cuando la reserva agenda un procedimiento de un plan
    # aceptado. El servicio lo valida y lo guarda en la misma transacción.
    procedimiento_plan_id: uuid.UUID | None = None
    notas_recepcion: Annotated[str | None, Field(default=None, max_length=LONGITUD_MAXIMA_NOTAS)]

    @field_validator("notas_recepcion")
    @classmethod
    def _sin_espacios_sobrantes(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = valor.strip()
        return limpio or None


class PeticionSerieReserva(PeticionReserva):
    """Reserva una serie corta, siempre en el mismo horario local.

    Las citas se confirman juntas o no se crea ninguna. El máximo protege la
    agenda de una operación masiva y limita las fechas propuestas a un año.
    """

    frecuencia: FrecuenciaSerieCitas
    cantidad: Annotated[int, Field(ge=2, le=53)]

    @model_validator(mode="after")
    def _limitar_horizonte_de_serie(self) -> PeticionSerieReserva:
        maximo = 13 if self.frecuencia == "MENSUAL" else 53
        if self.cantidad > maximo:
            raise ValueError("La serie no puede superar un año de citas.")
        if self.procedimiento_plan_id is not None:
            raise ValueError("Los procedimientos de un plan dental se reservan individualmente.")
        return self


class PeticionCancelacion(_ConInstantes):
    motivo: Annotated[str, Field(min_length=3, max_length=LONGITUD_MAXIMA_MOTIVO)]
    # Politica de cancelacion de la clinica, en horas. Cero significa que el
    # personal puede cancelar en cualquier momento; el valor mayor que cero se
    # usa en el camino del paciente.
    horas_antelacion_minima: Annotated[int, Field(default=0, ge=0, le=720)]


class PeticionReprogramacion(_ConInstantes):
    nuevo_inicio: InstanteConZona
    motivo: Annotated[str, Field(min_length=3, max_length=LONGITUD_MAXIMA_MOTIVO)]
    nuevo_profesional_id: uuid.UUID | None = None
    nuevo_consultorio_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
#  Salida
# ---------------------------------------------------------------------------
class RespuestaCita(BaseModel):
    """Cita tal como la ve quien gestiona la agenda.

    No incluye `notas_recepcion`: ese texto lo devuelve el detalle, no el
    listado, para que una exportacion de la agenda no arrastre comentarios
    administrativos sobre cada paciente.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    sede_id: uuid.UUID
    consultorio_id: uuid.UUID | None
    inicio: datetime
    fin: datetime
    duracion_minutos: int
    minutos_preparacion: int
    estado: EstadoCita
    origen: OrigenCita
    expira_en: datetime | None
    confirmada_en: datetime | None
    llegada_en: datetime | None
    atencion_iniciada_en: datetime | None
    completada_en: datetime | None
    cancelada_en: datetime | None
    motivo_cancelacion: str | None
    serie_recurrente_id: uuid.UUID | None


class RespuestaSerieCitas(BaseModel):
    """Resultado confirmado de una reserva recurrente."""

    model_config = ConfigDict(extra="forbid")

    serie_id: uuid.UUID
    frecuencia: FrecuenciaSerieCitas
    cantidad: int
    citas: list[RespuestaCita]


class RespuestaCitaDetalle(RespuestaCita):
    """Detalle de una cita. Anade el texto administrativo."""

    notas_recepcion: str | None


class PaginaCitas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elementos: list[RespuestaCita]
    total: int
    limite: int
    desplazamiento: int


class DatosBloqueoAgenda(_ConInstantes):
    """Bloqueo administrativo ligado a una sede y un único recurso opcional."""

    sede_id: uuid.UUID
    profesional_id: uuid.UUID | None = None
    consultorio_id: uuid.UUID | None = None
    tipo: Literal["VACACIONES", "AUSENCIA", "CAPACITACION", "MANTENIMIENTO", "OTRO"] = "OTRO"
    inicio: InstanteConZona
    fin: InstanteConZona
    motivo: Annotated[str | None, Field(max_length=LONGITUD_MAXIMA_MOTIVO)] = None
    aceptar_citas_afectadas: bool = False

    @field_validator("motivo", mode="before")
    @classmethod
    def _limpiar_motivo_bloqueo(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor


class CitaAfectadaBloqueo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    inicio: datetime
    fin: datetime


class RespuestaBloqueoAgenda(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sede_id: uuid.UUID
    profesional_id: uuid.UUID | None
    consultorio_id: uuid.UUID | None
    tipo: str
    inicio: datetime
    fin: datetime
    motivo: str | None
    creado_con_citas_afectadas: bool


# Estados que se pueden pedir como filtro. Se declara como literal y no como
# cadena libre para que un estado mal escrito sea un 422 y no un listado
# vacio que parece «no hay citas».
EstadoFiltro = Literal[
    "PENDING",
    "HELD",
    "CONFIRMED",
    "RESCHEDULED",
    "CANCELLED",
    "COMPLETED",
    "NO_SHOW",
]


__all__ = [
    "DIAS_MAXIMOS_CONSULTA",
    "CitaAfectadaBloqueo",
    "DatosBloqueoAgenda",
    "EstadoFiltro",
    "PaginaCitas",
    "PeticionCancelacion",
    "PeticionReprogramacion",
    "PeticionReserva",
    "RespuestaBloqueoAgenda",
    "RespuestaCita",
    "RespuestaCitaDetalle",
    "RespuestaDisponibilidad",
    "TurnoDisponible",
]
