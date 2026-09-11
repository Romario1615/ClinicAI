"""Modelos de profesionales y de la conexion con calendarios externos.

Sobre los tokens OAuth
----------------------
Nunca se almacena la contrasena del calendario del profesional.  La conexion
es OAuth y solo se guardan los tokens, **cifrados con AES-GCM ligado al
identificador del profesional** (ver `CifradorDatos`).  Ese ligado importa: sin
el, copiar el valor cifrado de una fila a otra daria acceso al calendario de
otra persona, y un volcado de la base seria suficiente para moverlo.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAnulacion, MezclaAuditoria, MezclaIdentificador


class EstadoDisponibilidad(StrEnum):
    DISPONIBLE = "DISPONIBLE"
    AGENDA_COMPLETA = "AGENDA_COMPLETA"
    AUSENTE = "AUSENTE"
    INACTIVO = "INACTIVO"


class EstadoSincronizacion(StrEnum):
    CONECTADO = "CONECTADO"
    TOKEN_VENCIDO = "TOKEN_VENCIDO"
    DESCONECTADO = "DESCONECTADO"
    ERROR = "ERROR"


class EstadoEventoCalendario(StrEnum):
    PENDIENTE = "PENDIENTE"
    SINCRONIZADO = "SINCRONIZADO"
    ELIMINADO_EXTERNAMENTE = "ELIMINADO_EXTERNAMENTE"
    CONFLICTO = "CONFLICTO"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
#  Profesional
# ---------------------------------------------------------------------------
class Profesional(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    """Persona que presta atencion.

    Se separa de `Usuario` porque no son lo mismo: un profesional puede
    existir en la agenda antes de tener cuenta, y un usuario de recepcion no
    es profesional.  Unirlos en una sola tabla obligaria a dejar nulas la
    mitad de las columnas en cada caso.
    """

    __tablename__ = "profesional"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    # Nulo mientras el profesional no tiene cuenta de acceso.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), default=None
    )
    especialidad_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("especialidad.id", ondelete="RESTRICT")
    )

    nombre: Mapped[str] = mapped_column(String(100))
    apellido: Mapped[str] = mapped_column(String(100))
    numero_registro_profesional: Mapped[str | None] = mapped_column(String(64), default=None)
    telefono_whatsapp: Mapped[str | None] = mapped_column(String(32), default=None)
    # Correo de la cuenta de calendario.  Se usa para la conexion OAuth; la
    # contrasena NUNCA se almacena.
    correo_calendario: Mapped[str | None] = mapped_column(String(200), default=None)

    estado_disponibilidad: Mapped[str] = mapped_column(
        String(24), default=EstadoDisponibilidad.DISPONIBLE.value
    )
    acepta_pacientes_nuevos: Mapped[bool] = mapped_column(Boolean, default=True)
    # Buffer propio, que se suma al del servicio si es mayor.
    minutos_preparacion_propio: Mapped[int] = mapped_column(SmallInteger, default=0)
    config_recordatorios: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sedes: Mapped[list[ProfesionalSede]] = relationship(
        back_populates="profesional", lazy="raise", cascade="all, delete-orphan"
    )
    servicios: Mapped[list[ProfesionalServicio]] = relationship(
        back_populates="profesional", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "clinica_id",
            "numero_registro_profesional",
            name="uq_profesional_clinica_id_numero_registro_profesional",
        ),
        UniqueConstraint("usuario_id", name="uq_profesional_usuario_id"),
        CheckConstraint(
            "estado_disponibilidad IN ('DISPONIBLE', 'AGENDA_COMPLETA', 'AUSENTE', 'INACTIVO')",
            name="estado_disponibilidad_valido",
        ),
        CheckConstraint("minutos_preparacion_propio >= 0", name="preparacion_no_negativa"),
        Index("ix_profesional_especialidad", "especialidad_id", "activo"),
        Index("ix_profesional_clinica_activo", "clinica_id", "activo"),
    )

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"


class ProfesionalSede(Base):
    """Sedes en las que atiende un profesional."""

    __tablename__ = "profesional_sede"

    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE"), primary_key=True
    )
    sede_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sede.id", ondelete="CASCADE"), primary_key=True
    )
    principal: Mapped[bool] = mapped_column(Boolean, default=False)

    profesional: Mapped[Profesional] = relationship(back_populates="sedes", lazy="raise")

    __table_args__ = (
        # Una sola sede principal por profesional.
        Index(
            "ix_profesional_sede_principal",
            "profesional_id",
            unique=True,
            postgresql_where=text("principal"),
        ),
    )


class ProfesionalServicio(Base):
    """Servicios que presta un profesional, con ajustes propios.

    Los `override` existen porque el mismo servicio puede tardar distinto
    segun quien lo haga, y el precio puede variar por experiencia.  Forzar un
    valor unico por servicio produciria agendas que no cuadran con la
    realidad, y de ahi retrasos acumulados.
    """

    __tablename__ = "profesional_servicio"

    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE"), primary_key=True
    )
    servicio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("servicio.id", ondelete="CASCADE"), primary_key=True
    )
    duracion_minutos_override: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    precio_override: Mapped[object | None] = mapped_column(Numeric(12, 2), default=None)

    profesional: Mapped[Profesional] = relationship(back_populates="servicios", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "duracion_minutos_override IS NULL OR duracion_minutos_override > 0",
            name="duracion_override_positiva",
        ),
        CheckConstraint(
            "precio_override IS NULL OR precio_override >= 0",
            name="precio_override_no_negativo",
        ),
    )


class AgendaPlantilla(Base, MezclaIdentificador, MezclaAuditoria):
    """Franja de trabajo de un profesional en una sede, en hora LOCAL.

    Se separa de `HorarioAtencion` de la sede porque un profesional puede
    trabajar un subconjunto del horario de la sede, y en sedes distintas en
    dias distintos.
    """

    __tablename__ = "agenda_plantilla"

    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE")
    )
    sede_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sede.id", ondelete="CASCADE"))
    dia_semana: Mapped[int] = mapped_column(SmallInteger)
    hora_inicio: Mapped[object] = mapped_column(String(8))
    hora_fin: Mapped[object] = mapped_column(String(8))
    granularidad_minutos: Mapped[int] = mapped_column(SmallInteger, default=15)
    vigente_desde: Mapped[object | None] = mapped_column(String(10), default=None)
    vigente_hasta: Mapped[object | None] = mapped_column(String(10), default=None)

    __table_args__ = (
        CheckConstraint("dia_semana BETWEEN 1 AND 7", name="dia_semana_iso"),
        CheckConstraint("granularidad_minutos > 0", name="granularidad_positiva"),
        Index("ix_agenda_plantilla_profesional", "profesional_id", "dia_semana"),
    )


# ---------------------------------------------------------------------------
#  Conexion con calendarios externos
# ---------------------------------------------------------------------------
class CalendarioConexion(Base, MezclaIdentificador, MezclaAuditoria):
    """Conexion OAuth con el calendario de un profesional.

    Los tokens estan cifrados.  `estado_sincronizacion` permite distinguir un
    calendario desconectado a proposito de uno con el token vencido: el
    primero no necesita accion, el segundo si, y confundirlos hace que los
    profesionales pierdan la sincronizacion sin enterarse.
    """

    __tablename__ = "calendario_conexion"

    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE")
    )
    proveedor: Mapped[str] = mapped_column(String(24), default="google")
    calendar_id: Mapped[str] = mapped_column(String(255))

    # Cifrados con AES-GCM y contexto = profesional_id.
    token_acceso_cifrado: Mapped[str | None] = mapped_column(Text, default=None)
    token_refresco_cifrado: Mapped[str | None] = mapped_column(Text, default=None)
    expira_en: Mapped[datetime | None] = mapped_column(default=None)
    alcances: Mapped[str | None] = mapped_column(Text, default=None)

    estado_sincronizacion: Mapped[str] = mapped_column(
        String(24), default=EstadoSincronizacion.DESCONECTADO.value
    )
    ultima_sincronizacion_en: Mapped[datetime | None] = mapped_column(default=None)
    ultimo_error: Mapped[str | None] = mapped_column(Text, default=None)
    # Token de sincronizacion incremental del proveedor.  Evita releer el
    # calendario completo en cada reconciliacion.
    token_sincronizacion_incremental: Mapped[str | None] = mapped_column(Text, default=None)

    eventos: Mapped[list[CalendarioEvento]] = relationship(back_populates="conexion", lazy="raise")

    __table_args__ = (
        UniqueConstraint(
            "profesional_id",
            "proveedor",
            "calendar_id",
            name="uq_calendario_conexion_profesional_id_proveedor",
        ),
        CheckConstraint(
            "estado_sincronizacion IN ('CONECTADO', 'TOKEN_VENCIDO', 'DESCONECTADO', 'ERROR')",
            name="estado_sincronizacion_valido",
        ),
        # Un estado CONECTADO sin token es incoherente y produciria fallos
        # confusos en cada intento de sincronizacion.
        CheckConstraint(
            "estado_sincronizacion <> 'CONECTADO' OR token_refresco_cifrado IS NOT NULL",
            name="conectado_exige_token",
        ),
        Index(
            "ix_calendario_conexion_a_renovar",
            "expira_en",
            postgresql_where=text("estado_sincronizacion = 'CONECTADO'"),
        ),
    )


class CalendarioEvento(Base, MezclaIdentificador, MezclaAuditoria):
    """Reflejo de una cita en un calendario externo.

    Mantiene la relacion que exige el requisito RF-I05 entre `cita_id`,
    `profesional_id`, `calendar_id` y `external_event_id`.

    El `etag` del proveedor permite detectar que el evento cambio fuera del
    sistema.  Sin el, la reconciliacion tendria que comparar campo a campo y
    no distinguiria un cambio externo de un dato desactualizado propio.

    La agenda interna es la fuente de verdad: si el evento externo se borra,
    la cita **sigue existiendo** y se marca el evento como eliminado
    externamente para volver a crearlo.
    """

    __tablename__ = "calendario_evento"

    cita_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cita.id", ondelete="CASCADE"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE")
    )
    calendario_conexion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendario_conexion.id", ondelete="CASCADE")
    )
    calendar_id: Mapped[str] = mapped_column(String(255))
    external_event_id: Mapped[str | None] = mapped_column(String(255), default=None)
    etag: Mapped[str | None] = mapped_column(String(255), default=None)
    estado: Mapped[str] = mapped_column(String(32), default=EstadoEventoCalendario.PENDIENTE.value)
    sincronizado_en: Mapped[datetime | None] = mapped_column(default=None)
    ultimo_error: Mapped[str | None] = mapped_column(Text, default=None)
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)

    conexion: Mapped[CalendarioConexion] = relationship(back_populates="eventos", lazy="raise")

    __table_args__ = (
        # Un evento externo no puede corresponder a dos citas: esa es la
        # invariante que impide duplicar eventos al reintentar.  Indice
        # parcial porque external_event_id es nulo hasta la primera creacion.
        Index(
            "ix_calendario_evento_externo",
            "calendario_conexion_id",
            "external_event_id",
            unique=True,
            postgresql_where=text("external_event_id IS NOT NULL"),
        ),
        UniqueConstraint(
            "cita_id",
            "calendario_conexion_id",
            name="uq_calendario_evento_cita_id_calendario_conexion_id",
        ),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'SINCRONIZADO', 'ELIMINADO_EXTERNAMENTE', "
            "'CONFLICTO', 'ERROR')",
            name="estado_valido",
        ),
        Index(
            "ix_calendario_evento_pendientes",
            "estado",
            postgresql_where=text("estado IN ('PENDIENTE', 'ERROR')"),
        ),
    )
