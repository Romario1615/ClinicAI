"""Historia clinica, recetas y adherencia.

Las garantias viven en la base de datos, no en Python
-----------------------------------------------------
Tres reglas de este modulo pueden hacer dano a un paciente si se incumplen, y
las tres estan sostenidas por el motor y no por una convencion de codigo:

1. **Una nota de evolucion no se modifica ni se borra.** Un disparador
   rechaza `UPDATE` y `DELETE` sobre `nota_evolucion`. Corregir una nota crea
   una version nueva con su motivo; la anterior queda intacta. Un `merge`
   descuidado o una rama de codigo nueva no pueden saltarselo.

2. **Solo una receta confirmada por un profesional genera calendario de
   tomas.** Un disparador rechaza insertar una `toma` cuya receta no este
   confirmada. La comprobacion tambien esta en el servicio; la del motor es la
   que sigue en pie cuando alguien anada otro camino de escritura.

3. **Un medicamento «cuando sea necesario» no tiene horarios fijos.** Una
   restriccion `CHECK` impide que un PRN lleve frecuencia, y el disparador de
   tomas rechaza generarlas para el. Convertir un PRN en pauta fija es un
   error de medicacion, no un detalle de interfaz.

Sobre las dosis: este modulo **almacena** lo que un profesional indica. No
calcula dosis, no sugiere ajustes y no valida interacciones. Esas decisiones
son clinicas y ningun automatismo de este sistema las toma (CLAUDE.md,
regla 5).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    FetchedValue,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class TipoNota(StrEnum):
    """Que clase de anotacion es.

    Importa para el control de acceso: el asistente ve las notas
    administrativas y de enfermeria, no la evolucion medica.
    """

    EVOLUCION = "EVOLUCION"
    ENFERMERIA = "ENFERMERIA"
    INTERCONSULTA = "INTERCONSULTA"
    PROCEDIMIENTO = "PROCEDIMIENTO"


class EstadoReceta(StrEnum):
    BORRADOR = "BORRADOR"
    CONFIRMADA = "CONFIRMADA"
    SUSPENDIDA = "SUSPENDIDA"
    CUMPLIDA = "CUMPLIDA"


class EstadoToma(StrEnum):
    PENDIENTE = "PENDIENTE"
    TOMADA = "TOMADA"
    OMITIDA = "OMITIDA"
    # La receta se modifico o suspendio y esta toma futura ya no aplica.
    CANCELADA = "CANCELADA"


class ViaAdministracion(StrEnum):
    ORAL = "ORAL"
    TOPICA = "TOPICA"
    INHALATORIA = "INHALATORIA"
    INTRAMUSCULAR = "INTRAMUSCULAR"
    INTRAVENOSA = "INTRAVENOSA"
    SUBCUTANEA = "SUBCUTANEA"
    OFTALMICA = "OFTALMICA"
    OTICA = "OTICA"
    RECTAL = "RECTAL"
    OTRA = "OTRA"


class SeveridadAlerta(StrEnum):
    INFORMATIVA = "INFORMATIVA"
    ATENCION = "ATENCION"
    URGENTE = "URGENTE"


class EstadoPlantillaAnamnesis(StrEnum):
    BORRADOR = "BORRADOR"
    PUBLICADA = "PUBLICADA"
    RETIRADA = "RETIRADA"


# ---------------------------------------------------------------------------
#  Notas de evolucion
# ---------------------------------------------------------------------------
class NotaEvolucion(Base, MezclaIdentificador, MezclaAuditoria):
    """Una version de una nota clinica.

    Cada fila es **una version**, no una nota. Las versiones de una misma nota
    comparten `raiz_id`; la vigente es la que tiene `vigente = true`, y un
    indice unico parcial garantiza que solo haya una.

    Por que versiones en la misma tabla y no una tabla de historico
    ---------------------------------------------------------------
    Con una tabla aparte hay dos sitios donde buscar y dos esquemas que
    mantener sincronizados, y la consulta de "dame la nota tal como estaba el
    12 de marzo" tiene que unir ambas. Con versiones en la misma tabla esa
    consulta es un `WHERE raiz_id = ... AND creado_en <= ...` ordenado por
    version.

    El precio es que toda consulta de la nota actual tiene que filtrar por
    `vigente`. Se acepta: olvidarlo devuelve versiones de mas, que es visible;
    lo contrario -- olvidar mirar el historico -- devuelve de menos y no se
    nota.
    """

    __tablename__ = "nota_evolucion"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    # La cita de la que surge la nota. Opcional: una interconsulta o una nota
    # de seguimiento telefonico no tienen cita.
    cita_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="SET NULL"), default=None
    )

    # --- Versionado ---
    #
    # `raiz_id` apunta a la PRIMERA version. La primera version se apunta a si
    # misma, lo que hace que `WHERE raiz_id = X` devuelva siempre el hilo
    # completo, incluida la original, sin una columna anulable de por medio.
    #
    # Lo rellena un disparador BEFORE INSERT cuando llega vacio: el
    # identificador lo genera la base (`gen_random_uuid()`), asi que la
    # aplicacion no lo conoce antes de insertar. Fijarlo despues con un UPDATE
    # seria imposible, porque el disparador de inmutabilidad lo rechaza -- y
    # debe rechazarlo.
    #
    # `FetchedValue` le dice a SQLAlchemy que el valor lo pone la base; con
    # `eager_defaults` se recupera por RETURNING en la misma sentencia.
    raiz_id: Mapped[uuid.UUID] = mapped_column(FetchedValue())
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    # Obligatorio a partir de la version 2. Sin el, ante una reclamacion no se
    # puede explicar por que cambio una nota clinica.
    motivo_modificacion: Mapped[str | None] = mapped_column(Text, default=None)

    # --- Contenido ---
    tipo: Mapped[str] = mapped_column(String(16), default=TipoNota.EVOLUCION.value)
    # El control reforzado pertenece a la nota/version, no solo al paciente.
    # Por omision, las notas existentes y las nuevas son N2.
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2), default="N2")
    motivo_consulta: Mapped[str | None] = mapped_column(Text, default=None)
    # Estructura SOAP, que es la convencion de la historia clinica orientada
    # a problemas. Se guardan por separado y no como un texto unico para que
    # la interfaz pueda mostrarlos etiquetados y para poder buscar por uno.
    subjetivo: Mapped[str | None] = mapped_column(Text, default=None)
    objetivo: Mapped[str | None] = mapped_column(Text, default=None)
    analisis: Mapped[str | None] = mapped_column(Text, default=None)
    plan: Mapped[str | None] = mapped_column(Text, default=None)

    # Signos vitales como JSON y no como columnas: el conjunto depende de la
    # especialidad, y anadir una columna por cada medida posible produciria
    # una tabla con cuarenta columnas casi siempre nulas.
    signos_vitales: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    diagnosticos: Mapped[list[Diagnostico]] = relationship(
        back_populates="nota", lazy="raise", cascade="all, delete-orphan"
    )

    # Recupera con RETURNING lo que pone la base -- `raiz_id`, `creado_en` --
    # en la misma sentencia del INSERT. En codigo asincrono no es una
    # optimizacion: sin ello la carga perezosa dentro de una corrutina lanza
    # MissingGreenlet.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('EVOLUCION', 'ENFERMERIA', 'INTERCONSULTA', 'PROCEDIMIENTO')",
            name="tipo_nota_valido",
        ),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        CheckConstraint("version >= 1", name="version_positiva"),
        # A partir de la segunda version el motivo es obligatorio. La primera
        # no lo lleva porque no modifica nada.
        CheckConstraint(
            "version = 1 OR motivo_modificacion IS NOT NULL",
            name="modificacion_exige_motivo",
        ),
        # Una sola version vigente por nota. Indice parcial porque las
        # versiones antiguas son la mayoria de las filas y no participan.
        Index(
            "ix_nota_vigente_unica",
            "raiz_id",
            unique=True,
            postgresql_where=text("vigente"),
        ),
        UniqueConstraint("raiz_id", "version", name="uq_nota_raiz_version"),
        # Consulta tipica: la historia de un paciente en orden cronologico.
        Index("ix_nota_paciente", "paciente_id", "creado_en"),
        Index("ix_nota_profesional", "profesional_id", "creado_en"),
        Index("ix_nota_cita", "cita_id"),
    )


class Diagnostico(Base, MezclaIdentificador, MezclaAuditoria):
    """Diagnostico asociado a una version de nota.

    Se ata a la version y no a la raiz a proposito: si una correccion de la
    nota cambia el diagnostico, la version anterior conserva el que tenia. Un
    diagnostico que cambia retroactivamente en el historico haria imposible
    reconstruir que se sabia en cada momento.
    """

    __tablename__ = "diagnostico"

    nota_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("nota_evolucion.id", ondelete="CASCADE"))
    # Codigo CIE-10 cuando lo hay. Opcional: en la primera consulta a menudo
    # hay una impresion diagnostica sin codificar, y exigir el codigo llevaria
    # a elegir uno aproximado, que es peor que no poner ninguno.
    codigo_cie10: Mapped[str | None] = mapped_column(String(16), default=None)
    descripcion: Mapped[str] = mapped_column(Text)
    principal: Mapped[bool] = mapped_column(Boolean, default=False)
    # Presuntivo mientras no esta confirmado por estudios.
    presuntivo: Mapped[bool] = mapped_column(Boolean, default=True)

    nota: Mapped[NotaEvolucion] = relationship(back_populates="diagnosticos", lazy="raise")

    __table_args__ = (
        Index("ix_diagnostico_nota", "nota_id"),
        Index("ix_diagnostico_cie10", "codigo_cie10"),
    )


# ---------------------------------------------------------------------------
#  Recetas
# ---------------------------------------------------------------------------
class Receta(Base, MezclaIdentificador, MezclaAuditoria):
    """Prescripcion. Solo genera tomas cuando esta confirmada.

    La confirmacion no es un detalle de flujo: separa un borrador que el
    profesional esta escribiendo de una indicacion vigente. Generar
    recordatorios desde un borrador significaria avisar a un paciente de que
    tome algo que nadie le ha indicado todavia.
    """

    __tablename__ = "receta"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    nota_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nota_evolucion.id", ondelete="SET NULL"), default=None
    )

    estado: Mapped[str] = mapped_column(String(16), default=EstadoReceta.BORRADOR.value)
    # Quien confirma y cuando. `confirmada_por` es el profesional, no el
    # usuario: la responsabilidad de una prescripcion es suya.
    confirmada_en: Mapped[datetime | None] = mapped_column(default=None)
    confirmada_por: Mapped[uuid.UUID | None] = mapped_column(default=None)

    suspendida_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_suspension: Mapped[str | None] = mapped_column(Text, default=None)

    # Receta anterior, cuando esta la sustituye. Permite seguir la cadena de
    # cambios de tratamiento sin borrar nada.
    receta_anterior_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("receta.id", ondelete="SET NULL"), default=None
    )

    indicaciones_generales: Mapped[str | None] = mapped_column(Text, default=None)
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2), default="N2")
    vigente_desde: Mapped[date | None] = mapped_column(default=None)
    vigente_hasta: Mapped[date | None] = mapped_column(default=None)

    medicamentos: Mapped[list[RecetaMedicamento]] = relationship(
        back_populates="receta", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('BORRADOR', 'CONFIRMADA', 'SUSPENDIDA', 'CUMPLIDA')",
            name="estado_receta_valido",
        ),
        # Confirmada exige quien y cuando. Sin esto, una receta podria quedar
        # en estado confirmado sin responsable.
        CheckConstraint(
            "estado <> 'CONFIRMADA' OR (confirmada_en IS NOT NULL AND confirmada_por IS NOT NULL)",
            name="confirmada_exige_responsable",
        ),
        CheckConstraint(
            "estado <> 'BORRADOR' OR (confirmada_en IS NULL AND confirmada_por IS NULL)",
            name="borrador_sin_firma",
        ),
        CheckConstraint(
            "estado <> 'SUSPENDIDA' OR motivo_suspension IS NOT NULL",
            name="suspension_exige_motivo",
        ),
        CheckConstraint(
            "estado <> 'SUSPENDIDA' OR suspendida_en IS NOT NULL",
            name="suspension_exige_instante",
        ),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        Index("ix_receta_paciente", "paciente_id", "creado_en"),
        Index("ix_receta_estado", "clinica_id", "estado"),
    )


class RecetaMedicamento(Base, MezclaIdentificador, MezclaAuditoria):
    """Una linea de la receta.

    El nombre del medicamento se guarda como texto y **no** se valida contra
    un vademecum: este sistema no tiene uno, y ofrecer autocompletado sobre
    una lista incompleta llevaria a elegir el parecido en lugar del correcto.
    Lo que escribe el profesional es lo que queda.
    """

    __tablename__ = "receta_medicamento"

    receta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receta.id", ondelete="CASCADE"))

    nombre: Mapped[str] = mapped_column(String(200))
    concentracion: Mapped[str | None] = mapped_column(String(64), default=None)
    forma: Mapped[str | None] = mapped_column(String(48), default=None)
    dosis: Mapped[str] = mapped_column(String(120))
    via: Mapped[str] = mapped_column(String(16), default=ViaAdministracion.ORAL.value)

    # --- Pauta ---
    #
    # `cuando_sea_necesario` (PRN) y `frecuencia_horas` son excluyentes. Un
    # PRN con frecuencia es una contradiccion: si hay que tomarlo cada ocho
    # horas, no es "cuando sea necesario".
    cuando_sea_necesario: Mapped[bool] = mapped_column(Boolean, default=False)
    frecuencia_horas: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    duracion_dias: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    # Hora local de la primera toma. La zona es la de la sede del paciente.
    hora_primera_toma: Mapped[str | None] = mapped_column(String(5), default=None)

    instrucciones: Mapped[str | None] = mapped_column(Text, default=None)

    receta: Mapped[Receta] = relationship(back_populates="medicamentos", lazy="raise")
    tomas: Mapped[list[Toma]] = relationship(
        back_populates="medicamento", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "via IN ('ORAL', 'TOPICA', 'INHALATORIA', 'INTRAMUSCULAR', 'INTRAVENOSA', "
            "'SUBCUTANEA', 'OFTALMICA', 'OTICA', 'RECTAL', 'OTRA')",
            name="via_valida",
        ),
        # La regla que impide convertir un PRN en pauta fija, a nivel de
        # motor. Ver la nota del campo.
        CheckConstraint(
            "NOT cuando_sea_necesario OR frecuencia_horas IS NULL",
            name="prn_sin_frecuencia",
        ),
        # Y al reves: una pauta fija necesita frecuencia, o no se puede
        # generar el calendario.
        CheckConstraint(
            "cuando_sea_necesario OR frecuencia_horas IS NOT NULL",
            name="pauta_fija_exige_frecuencia",
        ),
        CheckConstraint(
            "frecuencia_horas IS NULL OR (frecuencia_horas >= 1 AND frecuencia_horas <= 168)",
            name="frecuencia_razonable",
        ),
        Index("ix_medicamento_receta", "receta_id"),
    )


# ---------------------------------------------------------------------------
#  Adherencia
# ---------------------------------------------------------------------------
class Toma(Base, MezclaIdentificador):
    """Una toma programada.

    Solo existe para medicamentos de pauta fija de una receta **confirmada**:
    un disparador rechaza la insercion en cualquier otro caso.

    No lleva `MezclaAuditoria` completa a proposito: se generan cientos por
    receta y las cuatro columnas de auditoria multiplicarian el tamano de la
    tabla sin aportar nada. Quien genero el calendario consta en la receta.
    """

    __tablename__ = "toma"

    receta_medicamento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("receta_medicamento.id", ondelete="CASCADE")
    )
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))

    programada_en: Mapped[datetime] = mapped_column()
    estado: Mapped[str] = mapped_column(String(16), default=EstadoToma.PENDIENTE.value)

    registrada_en: Mapped[datetime | None] = mapped_column(default=None)
    # Quien registro la toma: el propio paciente por WhatsApp, o el personal.
    registrada_por_tipo: Mapped[str | None] = mapped_column(String(16), default=None)
    registrada_por_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    nota_paciente: Mapped[str | None] = mapped_column(Text, default=None)
    # Solo mueve el aviso de WhatsApp cuando el paciente pide que le
    # recordemos después. Nunca cambia la hora de la pauta prescrita.
    recordatorio_diferido_en: Mapped[datetime | None] = mapped_column(default=None)

    creada_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    medicamento: Mapped[RecetaMedicamento] = relationship(back_populates="tomas", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE', 'TOMADA', 'OMITIDA', 'CANCELADA')",
            name="estado_toma_valido",
        ),
        CheckConstraint(
            "estado = 'PENDIENTE' OR estado = 'CANCELADA' OR registrada_en IS NOT NULL",
            name="registro_exige_instante",
        ),
        # La misma toma no puede programarse dos veces. Evita duplicar
        # recordatorios si el calendario se regenera por error.
        UniqueConstraint(
            "receta_medicamento_id", "programada_en", name="uq_toma_medicamento_instante"
        ),
        # Consulta del worker de recordatorios: pendientes de una ventana.
        Index(
            "ix_toma_pendientes",
            "programada_en",
            postgresql_where=text("estado = 'PENDIENTE'"),
        ),
        Index("ix_toma_paciente", "paciente_id", "programada_en"),
    )


class AlertaAdherencia(Base, MezclaIdentificador, MezclaAuditoria):
    """Aviso al profesional por un patron de tomas omitidas.

    **No es una alerta clinica y no interpreta nada.** Dice cuantas tomas se
    omitieron y en que periodo; no concluye que el tratamiento haya fallado ni
    sugiere cambiarlo. Esa lectura es del profesional (CLAUDE.md, regla 5).
    """

    __tablename__ = "alerta_adherencia"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    receta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("receta.id", ondelete="CASCADE"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )

    severidad: Mapped[str] = mapped_column(String(16), default=SeveridadAlerta.ATENCION.value)
    tomas_omitidas: Mapped[int] = mapped_column(SmallInteger)
    tomas_esperadas: Mapped[int] = mapped_column(SmallInteger)
    periodo_desde: Mapped[datetime] = mapped_column()
    periodo_hasta: Mapped[datetime] = mapped_column()

    atendida_en: Mapped[datetime | None] = mapped_column(default=None)
    atendida_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    nota_profesional: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint(
            "severidad IN ('INFORMATIVA', 'ATENCION', 'URGENTE')", name="severidad_valida"
        ),
        CheckConstraint("tomas_omitidas >= 0", name="omitidas_no_negativas"),
        CheckConstraint("tomas_esperadas > 0", name="esperadas_positivas"),
        CheckConstraint("periodo_hasta > periodo_desde", name="periodo_coherente"),
        # Una alerta abierta por receta: repetirla cada dia convertiria el
        # aviso en ruido y el profesional dejaria de mirarlo.
        Index(
            "ix_alerta_abierta_unica",
            "receta_id",
            unique=True,
            postgresql_where=text("atendida_en IS NULL"),
        ),
        Index("ix_alerta_paciente", "paciente_id", "creado_en"),
    )


class PlantillaAnamnesis(Base, MezclaIdentificador, MezclaAuditoria):
    """Versión de una plantilla de preguntas configurada por una clínica.

    Las preguntas se guardan como un documento pequeño validado por el API.
    Una versión publicada queda congelada por un trigger en PostgreSQL; los
    cambios parten de una copia que incrementa `version`.
    """

    __tablename__ = "plantilla_anamnesis"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    estado: Mapped[str] = mapped_column(String(16), default=EstadoPlantillaAnamnesis.BORRADOR.value)
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2), default="N2")
    preguntas: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    publicada_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("clinica_id", "nombre", "version", name="uq_plantilla_anamnesis_version"),
        CheckConstraint("version > 0", name="version_positiva"),
        CheckConstraint("estado IN ('BORRADOR', 'PUBLICADA', 'RETIRADA')", name="estado_valido"),
        CheckConstraint("nivel_sensibilidad IN ('N2', 'N3')", name="sensibilidad_valida"),
        CheckConstraint(
            "jsonb_typeof(preguntas) = 'array' AND jsonb_array_length(preguntas) BETWEEN 1 AND 40",
            name="preguntas_acotadas",
        ),
        CheckConstraint(
            "(estado = 'BORRADOR') = (publicada_en IS NULL)",
            name="publicada_exige_fecha",
        ),
        Index(
            "ix_plantilla_anamnesis_publicada",
            "clinica_id",
            text("lower(nombre)"),
            unique=True,
            postgresql_where=text("estado = 'PUBLICADA'"),
        ),
        Index("ix_plantilla_anamnesis_clinica", "clinica_id", "creado_en"),
    )


class RespuestaAnamnesis(Base, MezclaIdentificador):
    """Captura inmutable de respuestas a una versión publicada."""

    __tablename__ = "respuesta_anamnesis"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    plantilla_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plantilla_anamnesis.id", ondelete="RESTRICT")
    )
    version_plantilla: Mapped[int] = mapped_column(SmallInteger)
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    respuestas: Mapped[dict[str, object]] = mapped_column(JSONB)
    registrada_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(default=None)

    __table_args__ = (
        CheckConstraint("version_plantilla > 0", name="version_positiva"),
        CheckConstraint("jsonb_typeof(respuestas) = 'object'", name="respuestas_objeto"),
        Index("ix_respuesta_anamnesis_paciente", "clinica_id", "paciente_id", "registrada_en"),
    )


__all__ = [
    "AlertaAdherencia",
    "Diagnostico",
    "EstadoPlantillaAnamnesis",
    "EstadoReceta",
    "EstadoToma",
    "NotaEvolucion",
    "PlantillaAnamnesis",
    "Receta",
    "RecetaMedicamento",
    "RespuestaAnamnesis",
    "SeveridadAlerta",
    "TipoNota",
    "Toma",
    "ViaAdministracion",
]
