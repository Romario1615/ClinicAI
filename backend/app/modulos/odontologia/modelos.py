"""Odontograma y plan de tratamiento.

Odontograma: versiones, no ediciones
------------------------------------
Cada fila de `odontograma` es el estado **completo** de la boca en un
momento. Registrar un hallazgo crea la version siguiente; la anterior queda
intacta y marcada como no vigente. Asi la pregunta «como estaba el 36 en
marzo» se responde leyendo una fila, y una reclamacion sobre un tratamiento
tiene el estado previo exacto.

Un disparador rechaza `DELETE` y cualquier `UPDATE` que no sea apagar
`vigente` (mismo patron que `nota_evolucion`, ADR-0011). Un indice unico
parcial garantiza una sola version vigente por paciente.

El estado va en JSONB y no en una tabla por pieza: se lee y se escribe
siempre entero, y una tabla de 32 filas por version multiplicaria las
escrituras sin ganar ninguna consulta util. La forma la valida Pydantic en
el servicio contra el vocabulario cerrado de `vocabulario.py`.

Plan de tratamiento
-------------------
El plan lo crea y lo propone un profesional; el paciente lo acepta; los
procedimientos se completan uno a uno. Completar un procedimiento con
`hallazgo_resultante` crea una version nueva del odontograma: el registro
clinico y el plan no pueden divergir.

Nada aqui lo escribe la IA (CLAUDE.md, regla 5). El agente puede, como mucho,
informar al paciente de que tiene una fase pendiente de agendar, sin nombrar
el procedimiento (regla 10).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAnulacion, MezclaAuditoria, MezclaIdentificador


# ---------------------------------------------------------------------------
#  Odontograma
# ---------------------------------------------------------------------------
class Odontograma(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "odontograma"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    denticion: Mapped[str] = mapped_column(String(10))
    # Ejemplo del JSON: pieza 36 con estado de cara oclusal en CARIES.
    piezas: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    motivo_modificacion: Mapped[str | None] = mapped_column(Text, default=None)
    # Clasificación por versión. N3 exige historia_clinica.leer_sensible.
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2), default="N2")
    # Si la version la genero completar un procedimiento del plan.
    procedimiento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("procedimiento_plan.id", ondelete="RESTRICT", use_alter=True),
        default=None,
    )

    __table_args__ = (
        UniqueConstraint("paciente_id", "version", name="uq_odontograma_paciente_id_version"),
        Index(
            "uq_odontograma_vigente",
            "paciente_id",
            unique=True,
            postgresql_where=text("vigente"),
        ),
        CheckConstraint("version >= 1", name="version_positiva"),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        CheckConstraint(
            "denticion IN ('PERMANENTE', 'TEMPORAL', 'MIXTA')", name="denticion_valida"
        ),
        CheckConstraint(
            "version = 1 OR motivo_modificacion IS NOT NULL", name="motivo_desde_version_dos"
        ),
    )


# ---------------------------------------------------------------------------
#  Plan de tratamiento
# ---------------------------------------------------------------------------
class EstadoPlan(StrEnum):
    BORRADOR = "BORRADOR"
    PROPUESTO = "PROPUESTO"
    ACEPTADO = "ACEPTADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


class MedioAceptacion(StrEnum):
    """Como consta que el paciente acepto el plan.

    Solo existe el documento firmado en la clinica. La autenticacion actual
    identifica al personal, no al paciente: un clic del profesional no es la
    aceptacion del paciente y no se presenta como tal. Cuando exista un canal
    con identidad de paciente verificada (fase G), se anadira aqui.
    """

    DOCUMENTO_FIRMADO = "DOCUMENTO_FIRMADO"


class EstadoProcedimiento(StrEnum):
    PENDIENTE = "PENDIENTE"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


class PlanTratamiento(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "plan_tratamiento"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    titulo: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(16), default=EstadoPlan.BORRADOR.value)
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    observaciones: Mapped[str | None] = mapped_column(Text, default=None)
    # Los procedimientos heredan la sensibilidad del plan que los contiene.
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2), default="N2")
    propuesto_en: Mapped[datetime | None] = mapped_column(default=None)
    aceptado_en: Mapped[datetime | None] = mapped_column(default=None)
    # Constancia de la aceptacion: medio, referencia del documento archivado
    # (numero de hoja, codigo de archivo) y, si se escaneo, la imagen.
    aceptacion_medio: Mapped[str | None] = mapped_column(String(24), default=None)
    aceptacion_referencia: Mapped[str | None] = mapped_column(String(200), default=None)
    aceptacion_imagen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("imagen_paciente.id", ondelete="RESTRICT"), default=None
    )
    aceptacion_registrada_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    completado_en: Mapped[datetime | None] = mapped_column(default=None)
    cancelado_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint(
            "estado IN ('BORRADOR', 'PROPUESTO', 'ACEPTADO', 'COMPLETADO', 'CANCELADO')",
            name="estado_valido",
        ),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        CheckConstraint(
            "estado <> 'CANCELADO' OR motivo_cancelacion IS NOT NULL",
            name="cancelacion_con_motivo",
        ),
        # Un plan aceptado o completado sin constancia de aceptacion es como
        # se cobra un tratamiento que el paciente nunca acepto.
        CheckConstraint(
            "estado NOT IN ('ACEPTADO', 'COMPLETADO') "
            "OR (aceptado_en IS NOT NULL AND aceptacion_medio IS NOT NULL "
            "AND aceptacion_referencia IS NOT NULL)",
            name="aceptacion_con_constancia",
        ),
        Index("ix_plan_tratamiento_paciente", "paciente_id", "estado"),
    )


class ProcedimientoPlan(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "procedimiento_plan"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_tratamiento.id", ondelete="RESTRICT")
    )
    fase: Mapped[int] = mapped_column(SmallInteger, default=1)
    orden: Mapped[int] = mapped_column(SmallInteger, default=1)
    pieza: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    caras: Mapped[str | None] = mapped_column(String(5), default=None)
    servicio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicio.id", ondelete="RESTRICT"), default=None
    )
    descripcion: Mapped[str] = mapped_column(String(300))
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    estado: Mapped[str] = mapped_column(String(16), default=EstadoProcedimiento.PENDIENTE.value)
    # Lo que queda registrado en el odontograma al completarlo.
    hallazgo_resultante: Mapped[str | None] = mapped_column(String(32), default=None)
    cita_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="SET NULL"), default=None
    )
    completado_en: Mapped[datetime | None] = mapped_column(default=None)
    completado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    control_recomendado_en: Mapped[date | None] = mapped_column(default=None)
    control_atendido_en: Mapped[datetime | None] = mapped_column(default=None)
    control_atendido_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    control_nota: Mapped[str | None] = mapped_column(Text, default=None)
    cancelado_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint("fase >= 1 AND fase <= 20", name="fase_valida"),
        CheckConstraint("precio >= 0", name="precio_no_negativo"),
        CheckConstraint("estado IN ('PENDIENTE', 'COMPLETADO', 'CANCELADO')", name="estado_valido"),
        CheckConstraint(
            "estado <> 'CANCELADO' OR motivo_cancelacion IS NOT NULL",
            name="cancelacion_con_motivo",
        ),
        CheckConstraint(
            "estado <> 'COMPLETADO' OR completado_en IS NOT NULL", name="completado_con_fecha"
        ),
        CheckConstraint(
            "(control_recomendado_en IS NULL OR estado = 'COMPLETADO') AND "
            "(control_nota IS NULL OR (control_recomendado_en IS NOT NULL "
            "AND control_atendido_en IS NOT NULL)) AND "
            "((control_atendido_en IS NULL AND control_atendido_por IS NULL) OR "
            "(control_recomendado_en IS NOT NULL AND control_atendido_en IS NOT NULL "
            "AND control_atendido_por IS NOT NULL))",
            name="control_atendido_coherente",
        ),
        Index("ix_procedimiento_plan_plan", "plan_id", "fase", "orden"),
    )


class PlantillaPlan(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Lista de procedimientos reutilizable para armar planes («Rehabilitacion
    con corona», «Ortodoncia fase inicial»).

    Es catalogo de la clinica, no dato de un paciente: no lleva paciente ni
    precio acordado con nadie. Al usarla, el profesional revisa y ajusta el
    borrador antes de proponerlo. Se retira con motivo, nunca se borra.
    """

    __tablename__ = "plantilla_plan"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[str | None] = mapped_column(Text, default=None)
    # Misma forma que `ProcedimientoNuevo`, validada por Pydantic al crear.
    procedimientos: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    __table_args__ = (
        Index(
            "uq_plantilla_plan_nombre_vigente",
            "clinica_id",
            "nombre",
            unique=True,
            postgresql_where=text("anulado_en IS NULL"),
        ),
        CheckConstraint(
            "jsonb_typeof(procedimientos) = 'array' AND jsonb_array_length(procedimientos) > 0",
            name="con_procedimientos",
        ),
    )


# ---------------------------------------------------------------------------
#  Indice de placa de O'Leary (periodoncia)
# ---------------------------------------------------------------------------
# Superficies que revisa el indice: sin oclusal.
CARAS_OLEARY = ("V", "L", "M", "D")


class RegistroPlaca(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "registro_placa"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    piezas_evaluadas: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    # {"16": ["V", "M"]}: solo las superficies CON placa.
    superficies_con_placa: Mapped[dict[str, list[str]]] = mapped_column(JSONB, default=dict)
    total_superficies: Mapped[int] = mapped_column(Integer)
    total_con_placa: Mapped[int] = mapped_column(Integer)
    porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    observacion: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint("total_superficies > 0", name="con_superficies"),
        CheckConstraint(
            "total_con_placa >= 0 AND total_con_placa <= total_superficies", name="conteo_coherente"
        ),
        CheckConstraint("porcentaje >= 0 AND porcentaje <= 100", name="porcentaje_valido"),
        Index("ix_registro_placa_paciente", "paciente_id", "creado_en"),
    )


class Formulario033(Base, MezclaIdentificador, MezclaAuditoria):
    """Una captura del 033/2021, conservada como documento clínico versionado.

    `contenido` contiene la captura del formulario; `nota_id`, `odontograma_id`
    y `registro_placa_id` enlazan fuentes clínicas ya versionadas, no copias
    editables de esas mismas fuentes. `contexto_identidad` congela los datos
    maestros que se imprimieron para que una corrección posterior de nombre o
    documento no cambie la representación histórica del formulario.
    """

    __tablename__ = "formulario_033"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    sede_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sede.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    cita_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="RESTRICT"), default=None
    )
    nota_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nota_evolucion.id", ondelete="RESTRICT"), default=None
    )
    odontograma_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("odontograma.id", ondelete="RESTRICT"), default=None
    )
    registro_placa_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("registro_placa.id", ondelete="RESTRICT"), default=None
    )
    raiz_id: Mapped[uuid.UUID] = mapped_column(FetchedValue())
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo_modificacion: Mapped[str | None] = mapped_column(Text, default=None)
    contexto_identidad: Mapped[dict[str, object]] = mapped_column(JSONB)
    contenido: Mapped[dict[str, object]] = mapped_column(JSONB)

    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    __table_args__ = (
        UniqueConstraint("raiz_id", "version", name="uq_formulario_033_raiz_version"),
        Index(
            "uq_formulario_033_vigente",
            "raiz_id",
            unique=True,
            postgresql_where=text("vigente"),
        ),
        Index(
            "uq_formulario_033_cita_vigente",
            "cita_id",
            unique=True,
            postgresql_where=text("vigente AND cita_id IS NOT NULL"),
        ),
        Index("ix_formulario_033_paciente", "clinica_id", "paciente_id", "creado_en"),
        CheckConstraint("version >= 1", name="version_positiva"),
        CheckConstraint(
            "version = 1 OR motivo_modificacion IS NOT NULL", name="modificacion_con_motivo"
        ),
        CheckConstraint("jsonb_typeof(contexto_identidad) = 'object'", name="identidad_objeto"),
        CheckConstraint("jsonb_typeof(contenido) = 'object'", name="contenido_objeto"),
    )


__all__ = [
    "CARAS_OLEARY",
    "EstadoPlan",
    "EstadoProcedimiento",
    "Formulario033",
    "MedioAceptacion",
    "Odontograma",
    "PlanTratamiento",
    "PlantillaPlan",
    "ProcedimientoPlan",
    "RegistroPlaca",
]
