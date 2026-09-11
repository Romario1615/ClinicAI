"""Modelos de la organizacion: clinica, sedes, especialidades y horarios.

Nota sobre las horas locales
----------------------------
Los horarios de atencion, los descansos y los feriados se almacenan como
**hora y fecha locales**, no como instantes UTC.  Es deliberado y contrario a
la regla general del ADR-0010, por un motivo concreto: «atiende de 08:00 a
13:00» es una afirmacion local que sigue siendo verdadera aunque cambie el
desplazamiento de la zona.  Guardarla como instante UTC obligaria a
reescribir todos los horarios cada vez que una zona cambia de regla.

Los instantes concretos (una cita, un bloqueo) si van en UTC.  La conversion
entre ambos mundos ocurre en el motor de disponibilidad, con la zona horaria
de la sede.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAnulacion, MezclaAuditoria, MezclaIdentificador


class TipoPropietarioHorario(StrEnum):
    """Un horario puede pertenecer a una sede o a un profesional concreto."""

    SEDE = "SEDE"
    PROFESIONAL = "PROFESIONAL"


class TipoConsultorio(StrEnum):
    CONSULTA = "CONSULTA"
    PROCEDIMIENTOS = "PROCEDIMIENTOS"
    IMAGEN = "IMAGEN"
    LABORATORIO = "LABORATORIO"
    OTRO = "OTRO"


# ---------------------------------------------------------------------------
#  Clinica y sedes
# ---------------------------------------------------------------------------
class Clinica(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Entidad raiz.

    El sistema arranca con una sola clinica, pero el modelo admite varias
    desde el principio: anadir `clinica_id` mas tarde a treinta tablas con
    datos ya cargados es una migracion de riesgo que no merece la pena
    aplazar.
    """

    __tablename__ = "clinica"

    nombre: Mapped[str] = mapped_column(String(200))
    identificacion_fiscal: Mapped[str | None] = mapped_column(String(50), default=None)
    # Zona horaria IANA.  Validada en la capa de aplicacion al escribir.
    zona_horaria: Mapped[str] = mapped_column(String(64), default="America/Guayaquil")
    idioma: Mapped[str] = mapped_column(String(8), default="es")
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    telefono: Mapped[str | None] = mapped_column(String(32), default=None)
    correo: Mapped[str | None] = mapped_column(String(200), default=None)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    sedes: Mapped[list[Sede]] = relationship(back_populates="clinica", lazy="raise")
    especialidades: Mapped[list[Especialidad]] = relationship(
        back_populates="clinica", lazy="raise"
    )

    __table_args__ = (
        UniqueConstraint("identificacion_fiscal", name="uq_clinica_identificacion_fiscal"),
    )


class Sede(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Ubicacion fisica donde se atiende."""

    __tablename__ = "sede"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(200))
    direccion: Mapped[str | None] = mapped_column(Text, default=None)
    telefono: Mapped[str | None] = mapped_column(String(32), default=None)
    # Si es nula, se hereda la de la clinica.  Permite sedes en husos
    # distintos sin obligar a repetir el valor en la sede habitual.
    zona_horaria: Mapped[str | None] = mapped_column(String(64), default=None)
    # Minutos de antelacion minima para reservar por un canal automatizado.
    minutos_antelacion_minima: Mapped[int] = mapped_column(SmallInteger, default=60)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    clinica: Mapped[Clinica] = relationship(back_populates="sedes", lazy="raise")
    consultorios: Mapped[list[Consultorio]] = relationship(back_populates="sede", lazy="raise")

    __table_args__ = (
        UniqueConstraint("clinica_id", "nombre", name="uq_sede_clinica_id_nombre"),
        Index("ix_sede_clinica_activa", "clinica_id", "activa"),
    )


class Consultorio(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Recurso fisico.

    Importa porque la restriccion de exclusion que impide el solapamiento de
    citas se aplica tambien por consultorio: dos profesionales distintos no
    pueden ocupar la misma sala a la vez.
    """

    __tablename__ = "consultorio"

    sede_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sede.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(32), default=TipoConsultorio.CONSULTA.value)
    capacidad: Mapped[int] = mapped_column(SmallInteger, default=1)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sede: Mapped[Sede] = relationship(back_populates="consultorios", lazy="raise")

    __table_args__ = (
        UniqueConstraint("sede_id", "nombre", name="uq_consultorio_sede_id_nombre"),
        CheckConstraint("capacidad > 0", name="capacidad_positiva"),
    )


# ---------------------------------------------------------------------------
#  Especialidades y servicios
# ---------------------------------------------------------------------------
class Especialidad(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    __tablename__ = "especialidad"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(150))
    codigo: Mapped[str | None] = mapped_column(String(32), default=None)
    descripcion: Mapped[str | None] = mapped_column(Text, default=None)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    clinica: Mapped[Clinica] = relationship(back_populates="especialidades", lazy="raise")
    servicios: Mapped[list[Servicio]] = relationship(back_populates="especialidad", lazy="raise")

    __table_args__ = (
        UniqueConstraint("clinica_id", "nombre", name="uq_especialidad_clinica_id_nombre"),
    )


class Servicio(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Prestacion concreta que se agenda.

    `minutos_preparacion` es el tiempo entre citas que necesita el servicio
    (limpieza de sala, preparacion de instrumental).  Se suma a la duracion
    para calcular el rango que ocupa la cita, de modo que la restriccion de
    exclusion de la base de datos tambien protege el buffer.  Si el buffer
    viviera solo en el codigo, un camino que lo olvidara produciria citas
    pegadas sin margen.
    """

    __tablename__ = "servicio"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    especialidad_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("especialidad.id", ondelete="RESTRICT")
    )
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text, default=None)
    duracion_minutos: Mapped[int] = mapped_column(SmallInteger)
    minutos_preparacion: Mapped[int] = mapped_column(SmallInteger, default=0)
    precio: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    requiere_pago_previo: Mapped[bool] = mapped_column(Boolean, default=False)
    instrucciones_preparacion: Mapped[str | None] = mapped_column(Text, default=None)
    # Un servicio puede requerir un tipo de consultorio concreto.
    tipo_consultorio_requerido: Mapped[str | None] = mapped_column(String(32), default=None)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    especialidad: Mapped[Especialidad] = relationship(back_populates="servicios", lazy="raise")

    __table_args__ = (
        UniqueConstraint("clinica_id", "nombre", name="uq_servicio_clinica_id_nombre"),
        CheckConstraint("duracion_minutos > 0", name="duracion_positiva"),
        CheckConstraint("minutos_preparacion >= 0", name="preparacion_no_negativa"),
        CheckConstraint("precio IS NULL OR precio >= 0", name="precio_no_negativo"),
        Index("ix_servicio_especialidad_activo", "especialidad_id", "activo"),
    )


# ---------------------------------------------------------------------------
#  Horarios, descansos y feriados
# ---------------------------------------------------------------------------
class HorarioAtencion(Base, MezclaIdentificador, MezclaAuditoria):
    """Franja semanal de atencion, en hora LOCAL.

    `dia_semana` sigue la convencion ISO: 1 es lunes y 7 es domingo.  Se
    elige ISO y no la de Python (0 = lunes) ni la de PostgreSQL
    (0 = domingo) para tener una unica convencion explicita en todo el
    sistema; mezclarlas desplaza la agenda un dia entero.
    """

    __tablename__ = "horario_atencion"

    propietario_tipo: Mapped[str] = mapped_column(String(16))
    propietario_id: Mapped[uuid.UUID] = mapped_column()
    dia_semana: Mapped[int] = mapped_column(SmallInteger)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)
    # Granularidad de los turnos ofrecidos dentro de la franja.
    granularidad_minutos: Mapped[int] = mapped_column(SmallInteger, default=15)
    vigente_desde: Mapped[date | None] = mapped_column(Date, default=None)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, default=None)

    descansos: Mapped[list[Descanso]] = relationship(
        back_populates="horario", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("dia_semana BETWEEN 1 AND 7", name="dia_semana_iso"),
        CheckConstraint("hora_fin > hora_inicio", name="franja_con_duracion"),
        CheckConstraint("granularidad_minutos > 0", name="granularidad_positiva"),
        CheckConstraint(
            "vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
            name="vigencia_coherente",
        ),
        CheckConstraint("propietario_tipo IN ('SEDE', 'PROFESIONAL')", name="propietario_valido"),
        Index(
            "ix_horario_propietario",
            "propietario_tipo",
            "propietario_id",
            "dia_semana",
        ),
    )


class Descanso(Base, MezclaIdentificador, MezclaAuditoria):
    """Pausa dentro de una franja de atencion, en hora local."""

    __tablename__ = "descanso"

    horario_atencion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("horario_atencion.id", ondelete="CASCADE")
    )
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)
    motivo: Mapped[str | None] = mapped_column(String(150), default=None)

    horario: Mapped[HorarioAtencion] = relationship(back_populates="descansos", lazy="raise")

    __table_args__ = (CheckConstraint("hora_fin > hora_inicio", name="descanso_con_duracion"),)


class Feriado(Base, MezclaIdentificador, MezclaAuditoria):
    """Dia sin atencion, en fecha LOCAL de la sede.

    `sede_id` nulo significa que afecta a toda la clinica.  Es mas comodo que
    obligar a crear una fila por sede, que es lo habitual con los feriados
    nacionales.
    """

    __tablename__ = "feriado"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="CASCADE"))
    sede_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sede.id", ondelete="CASCADE"), default=None
    )
    fecha: Mapped[date] = mapped_column(Date)
    nombre: Mapped[str] = mapped_column(String(150))
    # Si es cierto, se repite el mismo dia y mes cada ano.  Evita tener que
    # cargar a mano los feriados fijos cada diciembre.
    recurrente_anual: Mapped[bool] = mapped_column(Boolean, default=False)
    # Un feriado puede ser de media jornada.
    hora_inicio: Mapped[time | None] = mapped_column(Time, default=None)
    hora_fin: Mapped[time | None] = mapped_column(Time, default=None)

    __table_args__ = (
        Index("ix_feriado_clinica_fecha", "clinica_id", "fecha"),
        CheckConstraint(
            "(hora_inicio IS NULL) = (hora_fin IS NULL)",
            name="feriado_parcial_completo",
        ),
        CheckConstraint(
            "hora_fin IS NULL OR hora_fin > hora_inicio",
            name="feriado_parcial_con_duracion",
        ),
    )


# ---------------------------------------------------------------------------
#  Configuracion
# ---------------------------------------------------------------------------
class ConfiguracionClinica(Base, MezclaIdentificador, MezclaAuditoria):
    """Configuracion por clave, versionada.

    Se usa una tabla clave-valor en lugar de columnas fijas porque la
    configuracion crece con cada fase (politica de cancelacion, horas de
    recordatorio, plantillas aprobadas, umbrales de alerta) y una tabla
    ancha exigiria una migracion por cada ajuste.

    El precio es perder la validacion del esquema; se compensa validando
    cada clave con un modelo Pydantic en la capa de servicios.
    """

    __tablename__ = "configuracion_clinica"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="CASCADE"))
    clave: Mapped[str] = mapped_column(String(100))
    valor: Mapped[dict[str, object]] = mapped_column(JSONB)
    # Version del valor.  Se conserva el historico: saber que politica de
    # cancelacion estaba vigente cuando se cancelo una cita importa ante una
    # reclamacion.
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint(
            "clinica_id", "clave", "version", name="uq_configuracion_clinica_id_clave"
        ),
        # Indice unico PARCIAL: una sola version vigente por clave, pero
        # tantas versiones historicas como haga falta.  Sin la clausula
        # `postgresql_where` el indice impediria conservar el historico, que
        # es justo lo que esta tabla existe para guardar.
        Index(
            "ix_configuracion_una_vigente_por_clave",
            "clinica_id",
            "clave",
            unique=True,
            postgresql_where=text("vigente"),
        ),
    )
