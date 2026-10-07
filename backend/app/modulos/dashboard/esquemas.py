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


class ResumenOcupacionAgenda(BaseModel):
    """Tiempo de agenda disponible frente a tiempo reservado dentro del ámbito."""

    minutos_disponibles: int | None
    minutos_ocupados: int | None
    porcentaje: float | None
    detalle: str


class CohorteRegistroPacientes(BaseModel):
    """Altas agrupadas por mes, con citas registradas dentro del filtro actual."""

    mes: date
    registrados: int
    con_cita_en_filtros: int
    sin_cita_en_filtros: int


class CeldaDemografica(BaseModel):
    """Una categoría agregada; el valor es nulo cuando se protege."""

    categoria: str
    pacientes: int | None
    suprimida: bool


class ResumenDemografico(BaseModel):
    """Distribuciones separadas, sin cruces que faciliten identificar personas."""

    edades: list[CeldaDemografica]
    sexos: list[CeldaDemografica]


class Retorno30Dias(BaseModel):
    """Retorno a otra atención completada en los 30 días siguientes a la cita índice."""

    pacientes_seguimiento_completo: int
    pacientes_que_regresaron: int
    porcentaje: float


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
    pacientes_registrados: int | None = None
    pacientes_registrados_sin_cita: int | None = None
    cohortes_registro: list[CohorteRegistroPacientes] | None = None
    demografia: ResumenDemografico | None = None
    retorno_30_dias: Retorno30Dias | None = None
    espera: ResumenEspera
    recuperacion_turnos: ResumenRecuperacionTurnos
    ocupacion_agenda: ResumenOcupacionAgenda
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
