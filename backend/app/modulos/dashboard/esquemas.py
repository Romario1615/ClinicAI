from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, model_validator


class FiltroDashboard(BaseModel):
    desde: AwareDatetime
    hasta: AwareDatetime

    @model_validator(mode="after")
    def rango_valido(self) -> FiltroDashboard:
        if not timedelta(0) < self.hasta - self.desde <= timedelta(days=366):
            raise ValueError("Seleccione un periodo de hasta 366 dias con fin posterior al inicio.")
        return self


class ResumenEspera(BaseModel):
    """Medidas operativas de espera dentro del periodo y ámbito consultados."""

    promedio_minutos: int | None
    personas_en_espera: int
    espera_mayor_15_minutos: int


class ResumenRecuperacionTurnos(BaseModel):
    """Cancelaciones y ofertas de lista de espera aceptadas en el periodo."""

    turnos_liberados: int | None
    turnos_recuperados: int | None
    promedio_minutos_para_recuperar: int | None


class ResumenAdherencia(BaseModel):
    """Conteos agregados del periodo y alertas abiertas actuales, autorizados clínicamente."""

    tomas_confirmadas: int
    tomas_omitidas: int
    porcentaje_registro_positivo: float | None
    seguimientos_pendientes: int


class ConteoCitasPorDia(BaseModel):
    fecha: date
    total: int


class ConteoCitasPorHora(BaseModel):
    hora: int
    total: int


class ConteoCitasPorDiaSemana(BaseModel):
    dia: int
    total: int


class ResumenDashboard(BaseModel):
    desde: datetime
    hasta: datetime
    citas: dict[str, int]
    total_citas: int
    pacientes: int
    pacientes_nuevos: int | None
    pacientes_recurrentes: int | None
    espera: ResumenEspera
    recuperacion_turnos: ResumenRecuperacionTurnos
    adherencia: ResumenAdherencia | None
    pagos: dict[str, Decimal] | None
    tendencia_diaria: list[ConteoCitasPorDia]
    por_hora: list[ConteoCitasPorHora]
    por_dia_semana: list[ConteoCitasPorDiaSemana]


class AnalisisInteligente(BaseModel):
    analisis: str


class ResumenOperativoLocal(BaseModel):
    """Hallazgos administrativos derivados de métricas autorizadas, sin proveedor externo."""

    hallazgos: list[str]
