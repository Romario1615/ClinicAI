"""Esquemas de la historia clinica.

Lo que estos esquemas protegen
------------------------------
Una respuesta de historia clinica es el dato mas sensible que este sistema
maneja. Los esquemas de salida son listas de inclusiones y **no** serializan
el modelo: una columna anadida meses despues no aparece sola en la respuesta.

Los esquemas de entrada acotan longitudes. No es cosmetica: un campo de texto
sin limite en una nota clinica permite que alguien pegue un documento entero,
y esa nota despues hay que mostrarla, exportarla e indexarla.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LONGITUD_TEXTO_CLINICO = 8000
LONGITUD_MOTIVO = 500

TipoNotaEntrada = Literal["EVOLUCION", "ENFERMERIA", "INTERCONSULTA", "PROCEDIMIENTO"]
ViaEntrada = Literal[
    "ORAL",
    "TOPICA",
    "INHALATORIA",
    "INTRAMUSCULAR",
    "INTRAVENOSA",
    "SUBCUTANEA",
    "OFTALMICA",
    "OTICA",
    "RECTAL",
    "OTRA",
]


class DiagnosticoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo_cie10: Annotated[str | None, Field(default=None, max_length=16)]
    descripcion: Annotated[str, Field(min_length=3, max_length=500)]
    principal: bool = False
    # Presuntivo por omision: en la primera consulta lo habitual es una
    # impresion diagnostica sin confirmar, y marcarla como definitiva por
    # descuido daria mas certeza de la que hay.
    presuntivo: bool = True


class NotaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    tipo: TipoNotaEntrada = "EVOLUCION"
    cita_id: uuid.UUID | None = None

    motivo_consulta: Annotated[str | None, Field(default=None, max_length=LONGITUD_MOTIVO)]
    subjetivo: Annotated[str | None, Field(default=None, max_length=LONGITUD_TEXTO_CLINICO)]
    objetivo: Annotated[str | None, Field(default=None, max_length=LONGITUD_TEXTO_CLINICO)]
    analisis: Annotated[str | None, Field(default=None, max_length=LONGITUD_TEXTO_CLINICO)]
    plan: Annotated[str | None, Field(default=None, max_length=LONGITUD_TEXTO_CLINICO)]

    # Diccionario libre de medidas. Se acota el numero de claves para que no
    # se use como almacen general de datos del paciente.
    signos_vitales: Annotated[dict[str, float] | None, Field(default=None, max_length=20)]
    diagnosticos: Annotated[list[DiagnosticoEntrada], Field(default_factory=list, max_length=20)]

    @field_validator("motivo_consulta", "subjetivo", "objetivo", "analisis", "plan")
    @classmethod
    def _sin_espacios_sobrantes(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None


class CorreccionNota(NotaEntrada):
    """Nota corregida.

    El motivo es obligatorio y con longitud minima: «correccion» no explica
    nada, y ante una reclamacion la pregunta es por que cambio, no si cambio.
    """

    motivo: Annotated[str, Field(min_length=5, max_length=LONGITUD_MOTIVO)]


class MedicamentoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, Field(min_length=2, max_length=200)]
    dosis: Annotated[str, Field(min_length=1, max_length=120)]
    via: ViaEntrada = "ORAL"
    concentracion: Annotated[str | None, Field(default=None, max_length=64)]
    forma: Annotated[str | None, Field(default=None, max_length=48)]

    # `cuando_sea_necesario` y `frecuencia_horas` son excluyentes. Lo valida
    # tambien una restriccion CHECK de la base; aqui se rechaza antes, con un
    # mensaje que dice que hacer.
    cuando_sea_necesario: bool = False
    frecuencia_horas: Annotated[int | None, Field(default=None, ge=1, le=168)]
    duracion_dias: Annotated[int | None, Field(default=None, ge=1, le=365)]
    hora_primera_toma: Annotated[
        str | None, Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    ]
    instrucciones: Annotated[str | None, Field(default=None, max_length=1000)]

    def model_post_init(self, _contexto: object) -> None:
        if self.cuando_sea_necesario and self.frecuencia_horas is not None:
            raise ValueError(
                "Un medicamento «cuando sea necesario» no lleva frecuencia: si hay que "
                "tomarlo cada cierto tiempo, no es «cuando sea necesario»."
            )
        if not self.cuando_sea_necesario and self.frecuencia_horas is None:
            raise ValueError(
                "Una pauta fija necesita frecuencia en horas, o no se puede generar el "
                "calendario de tomas."
            )


class RecetaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    nota_id: uuid.UUID | None = None
    indicaciones_generales: Annotated[str | None, Field(default=None, max_length=2000)]
    medicamentos: Annotated[list[MedicamentoEntrada], Field(min_length=1, max_length=30)]


class ConfirmacionReceta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Quien confirma. Es el profesional responsable de la prescripcion, y no
    # se deduce del usuario: un residente puede escribir bajo la firma de su
    # adjunto, y quien responde es el segundo.
    profesional_id: uuid.UUID


class SuspensionReceta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: Annotated[str, Field(min_length=5, max_length=LONGITUD_MOTIVO)]


class RegistroToma(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tomada: bool
    nota_paciente: Annotated[str | None, Field(default=None, max_length=500)]


# ---------------------------------------------------------------------------
#  Salida
# ---------------------------------------------------------------------------
class DiagnosticoSalida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    codigo_cie10: str | None
    descripcion: str
    principal: bool
    presuntivo: bool


class NotaSalida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    raiz_id: uuid.UUID
    version: int
    vigente: bool
    motivo_modificacion: str | None

    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    cita_id: uuid.UUID | None
    tipo: str

    motivo_consulta: str | None
    subjetivo: str | None
    objetivo: str | None
    analisis: str | None
    plan: str | None
    signos_vitales: dict[str, float] | None

    creado_en: datetime


class MedicamentoSalida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    concentracion: str | None
    forma: str | None
    dosis: str
    via: str
    cuando_sea_necesario: bool
    frecuencia_horas: int | None
    duracion_dias: int | None
    instrucciones: str | None


class RecetaSalida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    paciente_id: uuid.UUID
    profesional_id: uuid.UUID
    estado: str
    confirmada_en: datetime | None
    suspendida_en: datetime | None
    motivo_suspension: str | None
    indicaciones_generales: str | None
    creado_en: datetime
    medicamentos: list[MedicamentoSalida]


class ResultadoConfirmacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receta: RecetaSalida
    # Cuantas tomas se programaron. La interfaz lo muestra: confirmar una
    # receta y no ver ningun recordatorio generado seria desconcertante, y
    # con un PRN la respuesta correcta es cero.
    tomas_generadas: int


class ResultadoSuspension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receta: RecetaSalida
    tomas_canceladas: int


class TomaSalida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    receta_medicamento_id: uuid.UUID
    medicamento: str
    programada_en: datetime
    estado: str
    registrada_en: datetime | None


__all__ = [
    "ConfirmacionReceta",
    "CorreccionNota",
    "DiagnosticoEntrada",
    "DiagnosticoSalida",
    "MedicamentoEntrada",
    "MedicamentoSalida",
    "NotaEntrada",
    "NotaSalida",
    "RecetaEntrada",
    "RecetaSalida",
    "RegistroToma",
    "ResultadoConfirmacion",
    "ResultadoSuspension",
    "SuspensionReceta",
    "TomaSalida",
]
