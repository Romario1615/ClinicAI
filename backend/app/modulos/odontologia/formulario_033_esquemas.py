"""Esquemas estrictos para la captura del Formulario MSP 033/2021.

Los datos demográficos y registros clínicos enlazados no se aceptan del
navegador: la ruta los resuelve desde sus entidades autorizadas. El formulario
solo recibe sus campos de captura y las referencias que luego se verifican.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PIEZAS_PERMANENTES = 32
MAX_PIEZAS_TEMPORALES = 20

AntecedentePersonal = Literal[
    "ALERGIA_ANTIBIOTICO",
    "ALERGIA_ANESTESIA",
    "HEMORRAGIA",
    "VIH_SIDA",
    "TUBERCULOSIS",
    "ASMA",
    "DIABETES",
    "HIPERTENSION_ARTERIAL",
    "ENFERMEDAD_CARDIACA",
    "OTRO",
]
AntecedenteFamiliar = Literal[
    "CARDIOPATIA",
    "HIPERTENSION_ARTERIAL",
    "ENFERMEDAD_CEREBROVASCULAR",
    "ENDOCRINO_METABOLICO",
    "CANCER",
    "TUBERCULOSIS",
    "ENFERMEDAD_MENTAL",
    "ENFERMEDAD_INFECCIOSA",
    "MALFORMACION",
    "OTRO",
]
RegionEstomatognatica = Literal[
    "LABIOS",
    "MEJILLAS",
    "MAXILAR_SUPERIOR",
    "MAXILAR_INFERIOR",
    "LENGUA",
    "PALADAR",
    "PISO_DE_LA_BOCA",
    "CARRILLOS",
    "GLANDULAS_SALIVALES",
    "OROFARINGE",
    "ATM",
    "GANGLIOS",
    "OTROS",
]
PiezaIndiceSimplificado = Literal[
    16,
    17,
    55,
    11,
    21,
    51,
    26,
    27,
    65,
    36,
    37,
    75,
    31,
    41,
    71,
    46,
    47,
    85,
]
CODIGOS_ANTECEDENTE_PERSONAL = frozenset(
    {
        "ALERGIA_ANTIBIOTICO",
        "ALERGIA_ANESTESIA",
        "HEMORRAGIA",
        "VIH_SIDA",
        "TUBERCULOSIS",
        "ASMA",
        "DIABETES",
        "HIPERTENSION_ARTERIAL",
        "ENFERMEDAD_CARDIACA",
        "OTRO",
    }
)
CODIGOS_ANTECEDENTE_FAMILIAR = frozenset(
    {
        "CARDIOPATIA",
        "HIPERTENSION_ARTERIAL",
        "ENFERMEDAD_CEREBROVASCULAR",
        "ENDOCRINO_METABOLICO",
        "CANCER",
        "TUBERCULOSIS",
        "ENFERMEDAD_MENTAL",
        "ENFERMEDAD_INFECCIOSA",
        "MALFORMACION",
        "OTRO",
    }
)


class ModeloEstricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Antecedente033(ModeloEstricto):
    codigo: AntecedentePersonal | AntecedenteFamiliar
    presente: bool | None = None
    detalle: Annotated[str | None, Field(default=None, max_length=1000)] = None


class ConstantesVitales033(ModeloEstricto):
    temperatura_c: Annotated[float | None, Field(default=None, ge=25, le=45)] = None
    pulso_minuto: Annotated[int | None, Field(default=None, ge=20, le=300)] = None
    frecuencia_respiratoria_minuto: Annotated[int | None, Field(default=None, ge=4, le=100)] = None
    presion_sistolica_mmhg: Annotated[int | None, Field(default=None, ge=30, le=300)] = None
    presion_diastolica_mmhg: Annotated[int | None, Field(default=None, ge=20, le=200)] = None


class HallazgoEstomatognatico033(ModeloEstricto):
    region: RegionEstomatognatica
    hallazgo: Literal["SIN_HALLAZGO", "PATOLOGIA", "NO_EVALUADO"]
    detalle: Annotated[str | None, Field(default=None, max_length=1000)] = None
    grado: Annotated[int | None, Field(default=None, ge=1, le=5)] = None

    @model_validator(mode="after")
    def detalle_coherente(self) -> HallazgoEstomatognatico033:
        if self.hallazgo == "PATOLOGIA" and not self.detalle:
            raise ValueError("Describa la patología registrada.")
        if self.hallazgo != "PATOLOGIA" and self.grado is not None:
            raise ValueError("El grado solo aplica a una patología registrada.")
        return self


class SitioHigieneOral033(ModeloEstricto):
    pieza: PiezaIndiceSimplificado
    placa: Annotated[int | None, Field(default=None, ge=0, le=3)] = None
    calculo: Annotated[int | None, Field(default=None, ge=0, le=3)] = None
    gingivitis: bool | None = None


class IndicadoresSaludBucal033(ModeloEstricto):
    sitios: Annotated[list[SitioHigieneOral033], Field(min_length=18, max_length=18)]
    enfermedad_periodontal: Literal["LEVE", "MODERADA", "SEVERA", "SIN_REGISTRO"] | None = None
    oclusion: Literal["ANGLE_I", "ANGLE_II", "ANGLE_III", "SIN_REGISTRO"] | None = None
    fluorosis: Literal["LEVE", "MODERADA", "SEVERA", "SIN_REGISTRO"] | None = None

    @model_validator(mode="after")
    def seis_sitios_unicos(self) -> IndicadoresSaludBucal033:
        piezas = [sitio.pieza for sitio in self.sitios]
        if len(set(piezas)) != len(piezas):
            raise ValueError("Cada pieza del índice simplificado se registra una sola vez.")
        return self


class IndicesCpoCeo033(ModeloEstricto):
    permanentes_d: Annotated[int | None, Field(default=None, ge=0, le=32)] = None
    permanentes_c: Annotated[int | None, Field(default=None, ge=0, le=32)] = None
    permanentes_p: Annotated[int | None, Field(default=None, ge=0, le=32)] = None
    permanentes_o: Annotated[int | None, Field(default=None, ge=0, le=32)] = None
    temporales_d: Annotated[int | None, Field(default=None, ge=0, le=20)] = None
    temporales_c: Annotated[int | None, Field(default=None, ge=0, le=20)] = None
    temporales_e: Annotated[int | None, Field(default=None, ge=0, le=20)] = None
    temporales_o: Annotated[int | None, Field(default=None, ge=0, le=20)] = None

    @model_validator(mode="after")
    def denticion_dentro_de_limites(self) -> IndicesCpoCeo033:
        permanentes = sum(
            valor or 0
            for valor in (
                self.permanentes_d,
                self.permanentes_c,
                self.permanentes_p,
                self.permanentes_o,
            )
        )
        temporales = sum(
            valor or 0
            for valor in (
                self.temporales_d,
                self.temporales_c,
                self.temporales_e,
                self.temporales_o,
            )
        )
        if permanentes > MAX_PIEZAS_PERMANENTES or temporales > MAX_PIEZAS_TEMPORALES:
            raise ValueError("El total CPO/ceo no puede superar las piezas de cada dentición.")
        return self


class ExamenComplementario033(ModeloEstricto):
    tipo: Literal["BIOMETRIA", "QUIMICA_SANGUINEA", "RAYOS_X", "OTROS"]
    descripcion: Annotated[str, Field(min_length=2, max_length=500)]
    resultado: Annotated[str | None, Field(default=None, max_length=2000)] = None


class Diagnostico033(ModeloEstricto):
    codigo_cie: Annotated[str | None, Field(default=None, max_length=16)] = None
    descripcion: Annotated[str, Field(min_length=2, max_length=500)]
    tipo: Literal["PRESUNTIVO", "DEFINITIVO"]


class SesionTratamiento033(ModeloEstricto):
    numero: Annotated[int, Field(ge=1, le=99)]
    fecha: date
    diagnostico_complicaciones: Annotated[str | None, Field(default=None, max_length=2000)] = None
    procedimiento: Annotated[str | None, Field(default=None, max_length=3000)] = None
    prescripciones: Annotated[str | None, Field(default=None, max_length=3000)] = None
    proxima_cita: date | None = None
    alta: bool = False


class Formulario033Datos(ModeloEstricto):
    embarazada: bool | None = None
    motivo_consulta: Annotated[str, Field(min_length=2, max_length=1000)]
    enfermedad_actual: Annotated[str | None, Field(default=None, max_length=4000)] = None
    antecedentes_personales: Annotated[list[Antecedente033], Field(max_length=10)] = Field(
        default_factory=list
    )
    antecedentes_familiares: Annotated[list[Antecedente033], Field(max_length=10)] = Field(
        default_factory=list
    )
    constantes_vitales: ConstantesVitales033
    examen_estomatognatico: Annotated[
        list[HallazgoEstomatognatico033], Field(min_length=13, max_length=13)
    ]
    indicadores_salud_bucal: IndicadoresSaludBucal033
    indices_cpo_ceo: IndicesCpoCeo033
    examenes_complementarios: Annotated[list[ExamenComplementario033], Field(max_length=30)] = (
        Field(default_factory=list)
    )
    diagnosticos: Annotated[list[Diagnostico033], Field(max_length=6)] = Field(default_factory=list)
    sesiones_tratamiento: Annotated[list[SesionTratamiento033], Field(max_length=6)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def secciones_sin_duplicados(self) -> Formulario033Datos:
        personales = [item.codigo for item in self.antecedentes_personales]
        familiares = [item.codigo for item in self.antecedentes_familiares]
        regiones = [item.region for item in self.examen_estomatognatico]
        if len(set(personales)) != len(personales):
            raise ValueError("No repita un antecedente personal.")
        if len(set(familiares)) != len(familiares):
            raise ValueError("No repita un antecedente familiar.")
        if len(set(regiones)) != len(regiones):
            raise ValueError("Cada región estomatognática se registra una sola vez.")
        codigos_personales = {item.codigo for item in self.antecedentes_personales}
        codigos_familiares = {item.codigo for item in self.antecedentes_familiares}
        if not codigos_personales.issubset(CODIGOS_ANTECEDENTE_PERSONAL):
            raise ValueError(
                "Hay un tipo de antecedente personal fuera del catálogo del formulario."
            )
        if not codigos_familiares.issubset(CODIGOS_ANTECEDENTE_FAMILIAR):
            raise ValueError(
                "Hay un tipo de antecedente familiar fuera del catálogo del formulario."
            )
        return self


class Formulario033Entrada(ModeloEstricto):
    sede_id: uuid.UUID | None = None
    cita_id: uuid.UUID | None = None
    nota_id: uuid.UUID | None = None
    odontograma_id: uuid.UUID | None = None
    registro_placa_id: uuid.UUID | None = None
    datos: Formulario033Datos


class Formulario033VersionEntrada(Formulario033Entrada):
    version_base: Annotated[int, Field(ge=1)]
    motivo: Annotated[str, Field(min_length=8, max_length=500)]


class Formulario033Salida(ModeloEstricto):
    id: uuid.UUID
    raiz_id: uuid.UUID
    version: int
    vigente: bool
    motivo_modificacion: str | None
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    sede_id: uuid.UUID
    cita_id: uuid.UUID | None
    nota_id: uuid.UUID | None
    odontograma_id: uuid.UUID | None
    registro_placa_id: uuid.UUID | None
    contexto_identidad: dict[str, object]
    datos: Formulario033Datos
    creado_en: datetime
