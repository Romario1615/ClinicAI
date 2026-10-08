"""Modelos de la agenda.

Aqui esta la pieza central del sistema: la restriccion que impide la doble
reserva.  No es una comprobacion en Python, es una restriccion de exclusion de
PostgreSQL (ADR-0009).

Por que importa
---------------
El enfoque habitual -- consultar si el turno esta libre y despues insertar --
es una condicion de carrera.  Con el nivel de aislamiento por defecto
(`READ COMMITTED`) la consulta no bloquea nada, asi que dos peticiones
simultaneas pueden ver el mismo hueco libre y ambas insertar.  El resultado es
dos pacientes a la misma hora con el mismo medico.

La restriccion de exclusion traslada la garantia al motor: si el codigo tiene
un error, el `INSERT` es rechazado igualmente.  El servicio trata esa violacion
como un resultado esperado y la traduce a «turno ya no disponible».

Como se calcula el rango
------------------------
Un disparador BEFORE INSERT OR UPDATE calcula `fin` a partir de `inicio`,
`duracion_minutos` y `minutos_preparacion`; la columna generada `rango` deriva
de `inicio` y `fin`.  De ese modo el buffer de preparacion tambien queda
protegido por la restriccion, y no depende de que el codigo lo recuerde.

No se usa una columna generada para `fin` porque PostgreSQL exige que la
expresion sea IMMUTABLE y `timestamptz + interval` es solo STABLE: la
aritmetica de meses y dias depende de la zona horaria de la sesion.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    FetchedValue,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class EstadoCita(StrEnum):
    """Estados fijados por la especificacion; se conservan en ingles.

    Ver ADR-0015: la especificacion los define de forma normativa y
    traducirlos romperia el contrato acordado.
    """

    PENDING = "PENDING"
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"

    @property
    def ocupa_turno(self) -> bool:
        """Estados que bloquean el horario frente a otras reservas.

        Es exactamente el conjunto que aparece en la clausula WHERE de la
        restriccion de exclusion.  Se define aqui para que el codigo y la
        migracion no puedan divergir sin que una prueba lo detecte.
        """
        return self in _ESTADOS_QUE_OCUPAN

    @property
    def es_terminal(self) -> bool:
        return self in {
            EstadoCita.CANCELLED,
            EstadoCita.COMPLETED,
            EstadoCita.NO_SHOW,
        }

    def etiqueta(self) -> str:
        """Texto en espanol para la interfaz."""
        return _ETIQUETAS_ESTADO[self]


_ESTADOS_QUE_OCUPAN: frozenset[EstadoCita] = frozenset(
    {EstadoCita.HELD, EstadoCita.CONFIRMED, EstadoCita.RESCHEDULED}
)

_ETIQUETAS_ESTADO: dict[EstadoCita, str] = {
    EstadoCita.PENDING: "Pendiente",
    EstadoCita.HELD: "Bloqueada temporalmente",
    EstadoCita.CONFIRMED: "Confirmada",
    EstadoCita.RESCHEDULED: "Reprogramada",
    EstadoCita.CANCELLED: "Cancelada",
    EstadoCita.COMPLETED: "Completada",
    EstadoCita.NO_SHOW: "Inasistencia",
}

# Literal SQL con los estados que ocupan turno.  Se deriva del conjunto de
# Python para que la migracion y el codigo no puedan desalinearse.
SQL_ESTADOS_QUE_OCUPAN = ", ".join(
    f"'{estado.value}'" for estado in sorted(_ESTADOS_QUE_OCUPAN, key=str)
)


# Transiciones permitidas.  Se define como dato, no como cadena de `if`:
# asi se puede probar exhaustivamente y la interfaz puede consultarla para
# mostrar solo las acciones posibles.
TRANSICIONES_PERMITIDAS: dict[EstadoCita, frozenset[EstadoCita]] = {
    EstadoCita.PENDING: frozenset({EstadoCita.HELD, EstadoCita.CONFIRMED, EstadoCita.CANCELLED}),
    EstadoCita.HELD: frozenset({EstadoCita.CONFIRMED, EstadoCita.CANCELLED}),
    EstadoCita.CONFIRMED: frozenset(
        {
            EstadoCita.RESCHEDULED,
            EstadoCita.CANCELLED,
            EstadoCita.COMPLETED,
            EstadoCita.NO_SHOW,
        }
    ),
    EstadoCita.RESCHEDULED: frozenset(
        {
            EstadoCita.CONFIRMED,
            EstadoCita.CANCELLED,
            EstadoCita.COMPLETED,
            EstadoCita.NO_SHOW,
        }
    ),
    # Los estados terminales no admiten salida.  Reabrir una cita cancelada
    # perderia la trazabilidad de por que se cancelo; se crea una nueva.
    EstadoCita.CANCELLED: frozenset(),
    EstadoCita.COMPLETED: frozenset(),
    EstadoCita.NO_SHOW: frozenset(),
}


class OrigenCita(StrEnum):
    PANEL = "PANEL"
    WHATSAPP = "WHATSAPP"
    LISTA_ESPERA = "LISTA_ESPERA"
    RECURRENTE = "RECURRENTE"


class TipoBloqueo(StrEnum):
    VACACIONES = "VACACIONES"
    AUSENCIA = "AUSENCIA"
    CAPACITACION = "CAPACITACION"
    MANTENIMIENTO = "MANTENIMIENTO"
    OTRO = "OTRO"


# ---------------------------------------------------------------------------
#  Cita
# ---------------------------------------------------------------------------
class Cita(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "cita"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    sede_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sede.id", ondelete="RESTRICT"))
    consultorio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consultorio.id", ondelete="RESTRICT"), default=None
    )
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    profesional_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT")
    )
    servicio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servicio.id", ondelete="RESTRICT"))

    # --- Tiempo ---
    inicio: Mapped[datetime] = mapped_column()
    duracion_minutos: Mapped[int] = mapped_column(SmallInteger)
    minutos_preparacion: Mapped[int] = mapped_column(SmallInteger, default=0)

    # =====================================================================
    #  `fin` y `rango`: calculados por la base de datos, no por Python
    # =====================================================================
    #  `fin` lo rellena un disparador BEFORE INSERT OR UPDATE a partir de
    #  `inicio`, `duracion_minutos` y `minutos_preparacion`.  Los
    #  disparadores BEFORE se ejecutan antes de comprobar NOT NULL, asi que
    #  la aplicacion puede insertar sin darle valor.
    #
    #  Por que un disparador y no una columna generada:
    #  PostgreSQL exige que la expresion de una columna generada sea
    #  IMMUTABLE, y `timestamptz + interval` es solo STABLE, porque la
    #  aritmetica de meses y dias depende de la zona horaria de la sesion.
    #  El intento con `Computed` fallaba con "generation expression is not
    #  immutable".
    #
    #  Lo que importa es que el calculo sigue estando en el motor: un camino
    #  de codigo que olvidara el buffer de preparacion no puede producir un
    #  `rango` incorrecto, porque el disparador lo sobrescribe.
    #
    #  `FetchedValue` le dice a SQLAlchemy que el valor lo pone la base de
    #  datos. Sin el, tras insertar la fila el objeto en memoria conserva
    #  `fin = None`: la fila en PostgreSQL esta bien, pero cualquier codigo
    #  que lea `cita.fin` justo despues de crearla -- serializar la respuesta
    #  HTTP, componer un recordatorio, exportar al calendario -- ve None.
    #  Combinado con `eager_defaults`, SQLAlchemy lo recupera con RETURNING
    #  en la misma sentencia, sin una consulta extra.
    fin: Mapped[datetime] = mapped_column(FetchedValue())

    #  `rango` SI puede ser columna generada: `tstzrange(timestamptz,
    #  timestamptz, text)` es inmutable.  Deriva de `inicio` y `fin`, que a su
    #  vez los garantiza el disparador.  Es la columna sobre la que actua la
    #  restriccion de exclusion.
    rango: Mapped[object] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(inicio, fin, '[)')", persisted=True),
    )

    # --- Estado ---
    estado: Mapped[str] = mapped_column(String(16), default=EstadoCita.PENDING.value)
    # Solo con estado HELD.  Un bloqueo sin caducidad retendria el turno para
    # siempre si el paciente abandona el flujo a medias.
    expira_en: Mapped[datetime | None] = mapped_column(default=None)
    origen: Mapped[str] = mapped_column(String(16), default=OrigenCita.PANEL.value)

    # --- Trazabilidad de cambios ---
    # Reprogramacion: apunta a la cita de la que proviene.  Permite reconstruir
    # la cadena completa de cambios de un paciente.
    cita_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="SET NULL"), default=None
    )
    # Trazabilidad y tope de turnos liberados por reagendamientos sucesivos
    # aceptados desde la lista de espera.
    cadena_lista_espera_id: Mapped[uuid.UUID | None] = mapped_column(
        default=None,
        comment="Identificador de la cadena de reagendamientos desde lista de espera",
    )
    profundidad_lista_espera: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        server_default=text("0"),
        comment="Máximo: 5 eslabones de horarios liberados",
    )
    serie_recurrente_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    clave_idempotencia: Mapped[str | None] = mapped_column(String(200), default=None)

    confirmada_en: Mapped[datetime | None] = mapped_column(default=None)
    llegada_en: Mapped[datetime | None] = mapped_column(default=None)
    atencion_iniciada_en: Mapped[datetime | None] = mapped_column(default=None)
    completada_en: Mapped[datetime | None] = mapped_column(default=None)
    cancelada_en: Mapped[datetime | None] = mapped_column(default=None)
    cancelada_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, default=None)

    # Texto administrativo. NO clinico: el motivo de consulta y el diagnostico
    # viven en la historia clinica, con su control de acceso.  Recepcion
    # escribe aqui y no tiene acceso a aquello.
    notas_recepcion: Mapped[str | None] = mapped_column(Text, default=None)

    historial: Mapped[list[CitaHistorial]] = relationship(back_populates="cita", lazy="raise")

    # Recupera con RETURNING los valores que pone la base de datos -- `fin`,
    # `rango`, `creado_en` -- en la misma sentencia del INSERT.
    #
    # En codigo asincrono esto no es una optimizacion, es un requisito: sin
    # ello SQLAlchemy los cargaria de forma perezosa al acceder al atributo, y
    # una carga perezosa dentro de una corrutina lanza MissingGreenlet en
    # lugar de devolver el valor.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    __table_args__ = (
        # =====================================================================
        #  La restriccion central del sistema (ADR-0009).
        #
        #  Un profesional no puede tener dos citas activas cuyos rangos se
        #  solapen.  `&&` es el operador de solapamiento de rangos y `=` la
        #  igualdad; combinarlos en un indice GiST requiere btree_gist.
        #
        #  La clausula WHERE deja fuera las citas canceladas, completadas y
        #  las inasistencias: el historico se conserva completo sin bloquear
        #  el turno.
        # =====================================================================
        ExcludeConstraint(
            ("profesional_id", "="),
            ("rango", "&&"),
            name="cita_sin_solape_profesional",
            using="gist",
            where=text(f"estado IN ({SQL_ESTADOS_QUE_OCUPAN})"),
        ),
        # Misma proteccion para el recurso fisico: dos profesionales distintos
        # no pueden ocupar la misma sala a la vez.
        ExcludeConstraint(
            ("consultorio_id", "="),
            ("rango", "&&"),
            name="cita_sin_solape_consultorio",
            using="gist",
            where=text(f"estado IN ({SQL_ESTADOS_QUE_OCUPAN}) AND consultorio_id IS NOT NULL"),
        ),
        # Idempotencia: la misma clave no puede crear dos citas.  Indice
        # parcial porque la mayoria de citas del panel no llevan clave.
        Index(
            "ix_cita_idempotencia",
            "clinica_id",
            "clave_idempotencia",
            unique=True,
            postgresql_where=text("clave_idempotencia IS NOT NULL"),
        ),
        Index(
            "ix_cita_cadena_lista_espera",
            "cadena_lista_espera_id",
            "profundidad_lista_espera",
            postgresql_where=text("cadena_lista_espera_id IS NOT NULL"),
        ),
        Index(
            "ix_cita_serie_recurrente",
            "serie_recurrente_id",
            postgresql_where=text("serie_recurrente_id IS NOT NULL"),
        ),
        CheckConstraint("duracion_minutos > 0", name="duracion_positiva"),
        CheckConstraint(
            "profundidad_lista_espera >= 0 AND profundidad_lista_espera <= 6",
            name="profundidad_lista_espera_valida",
        ),
        CheckConstraint("minutos_preparacion >= 0", name="preparacion_no_negativa"),
        # Red de seguridad sobre el disparador: si alguien lo deshabilitara
        # o insertara con `session_replication_role = replica`, esta
        # comprobacion sigue impidiendo un `fin` anterior al inicio.
        CheckConstraint("fin > inicio", name="fin_posterior_al_inicio"),
        CheckConstraint(
            "atencion_iniciada_en IS NULL OR llegada_en IS NOT NULL",
            name="atencion_exige_llegada",
        ),
        CheckConstraint(
            "estado IN ('PENDING', 'HELD', 'CONFIRMED', 'RESCHEDULED', "
            "'CANCELLED', 'COMPLETED', 'NO_SHOW')",
            name="estado_valido",
        ),
        # Un HELD sin caducidad retendria el turno indefinidamente.
        CheckConstraint("estado <> 'HELD' OR expira_en IS NOT NULL", name="held_exige_expiracion"),
        # Cancelar sin motivo impide saber despues por que un paciente no fue
        # atendido, que es exactamente lo que se pregunta ante una queja.
        CheckConstraint(
            "estado <> 'CANCELLED' OR motivo_cancelacion IS NOT NULL",
            name="cancelacion_exige_motivo",
        ),
        CheckConstraint(
            "origen IN ('PANEL', 'WHATSAPP', 'LISTA_ESPERA', 'RECURRENTE')",
            name="origen_valido",
        ),
        # Indices de las consultas del camino caliente.
        Index("ix_cita_profesional_inicio", "profesional_id", "inicio"),
        Index("ix_cita_paciente_inicio", "paciente_id", "inicio"),
        Index("ix_cita_sede_inicio", "sede_id", "inicio"),
        Index("ix_cita_estado_inicio", "clinica_id", "estado", "inicio"),
        # Barrido de bloqueos vencidos: indice parcial porque solo interesan
        # las filas en HELD, que son una fraccion minima del total.
        Index(
            "ix_cita_held_expirando",
            "expira_en",
            postgresql_where=text("estado = 'HELD'"),
        ),
        # Sala de espera y cancelaciones del día: el panel las consulta por
        # rango de llegada o de cancelación, y sin índice recorría toda la
        # historia de citas. Parciales: solo cuentan las filas con valor.
        Index(
            "ix_cita_llegada",
            "clinica_id",
            "llegada_en",
            postgresql_where=text("llegada_en IS NOT NULL"),
        ),
        Index(
            "ix_cita_cancelada",
            "clinica_id",
            "cancelada_en",
            postgresql_where=text("cancelada_en IS NOT NULL"),
        ),
        # Solapamiento con una ventana (`inicio < hasta AND fin > desde`): el
        # índice por inicio solo acota por arriba y recorría toda la historia;
        # `fin > desde` deja fuera casi todo lo ya terminado.
        Index("ix_cita_clinica_fin", "clinica_id", "fin"),
    )

    @property
    def estado_enum(self) -> EstadoCita:
        return EstadoCita(self.estado)

    def puede_transicionar_a(self, nuevo: EstadoCita) -> bool:
        return nuevo in TRANSICIONES_PERMITIDAS[self.estado_enum]


class CitaHistorial(Base, MezclaIdentificador):
    """Registro append-only de los cambios de una cita.

    Se conserva el estado y el inicio anteriores, no solo el nuevo: ante una
    reclamacion la pregunta es «a que hora estaba la cita antes de que la
    movieran», y sin el valor anterior no se puede responder.
    """

    __tablename__ = "cita_historial"

    cita_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cita.id", ondelete="CASCADE"))
    estado_anterior: Mapped[str | None] = mapped_column(String(16), default=None)
    estado_nuevo: Mapped[str] = mapped_column(String(16))
    inicio_anterior: Mapped[datetime | None] = mapped_column(default=None)
    inicio_nuevo: Mapped[datetime | None] = mapped_column(default=None)
    profesional_anterior_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    profesional_nuevo_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    actor_tipo: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    motivo: Mapped[str | None] = mapped_column(Text, default=None)
    ocurrido_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    metadatos: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    cita: Mapped[Cita] = relationship(back_populates="historial", lazy="raise")

    __table_args__ = (Index("ix_cita_historial_cita", "cita_id", "ocurrido_en"),)


# ---------------------------------------------------------------------------
#  Bloqueos de agenda
# ---------------------------------------------------------------------------
class BloqueoAgenda(Base, MezclaIdentificador, MezclaAuditoria):
    """Periodo sin disponibilidad: vacaciones, ausencia, mantenimiento.

    `profesional_id` nulo significa que afecta a toda la sede.  Los bloqueos
    restan disponibilidad igual que las citas, pero **no** se modelan como
    citas: una cita tiene paciente y servicio obligatorios, y forzar valores
    ficticios para representar unas vacaciones contaminaria las metricas de
    ocupacion y de ingresos.
    """

    __tablename__ = "bloqueo_agenda"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="CASCADE"))
    sede_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sede.id", ondelete="CASCADE"), default=None
    )
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profesional.id", ondelete="CASCADE"), default=None
    )
    consultorio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consultorio.id", ondelete="CASCADE"), default=None
    )
    tipo: Mapped[str] = mapped_column(String(24), default=TipoBloqueo.OTRO.value)
    inicio: Mapped[datetime] = mapped_column()
    fin: Mapped[datetime] = mapped_column()
    rango: Mapped[object] = mapped_column(
        TSTZRANGE,
        Computed("tstzrange(inicio, fin, '[)')", persisted=True),
    )
    motivo: Mapped[str | None] = mapped_column(Text, default=None)
    # Un bloqueo puede crearse aunque haya citas dentro; se avisa al operador
    # y las citas afectadas se listan para reprogramarlas. Se registra si se
    # forzo, para poder auditar la decision.
    creado_con_citas_afectadas: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("fin > inicio", name="bloqueo_con_duracion"),
        CheckConstraint(
            "tipo IN ('VACACIONES', 'AUSENCIA', 'CAPACITACION', 'MANTENIMIENTO', 'OTRO')",
            name="tipo_valido",
        ),
        # Un bloqueo sin destino no bloquea nada identificable.
        CheckConstraint(
            "sede_id IS NOT NULL OR profesional_id IS NOT NULL OR consultorio_id IS NOT NULL",
            name="bloqueo_con_destino",
        ),
        Index("ix_bloqueo_profesional_rango", "profesional_id", "inicio", "fin"),
        Index("ix_bloqueo_sede_rango", "sede_id", "inicio", "fin"),
    )


# ---------------------------------------------------------------------------
#  Idempotencia
# ---------------------------------------------------------------------------
class ClaveIdempotencia(Base, MezclaIdentificador):
    """Registro de operaciones ya procesadas.

    Vive en PostgreSQL y no en Redis a proposito: si Redis se vacia, un
    reintento de webhook de WhatsApp volveria a procesarse y podria duplicar
    una cita.  La durabilidad de la deduplicacion tiene que ser la misma que
    la del dato de negocio.
    """

    __tablename__ = "clave_idempotencia"

    clave: Mapped[str] = mapped_column(String(200))
    alcance: Mapped[str] = mapped_column(String(50))
    clinica_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # Hash canonico del cuerpo.  Misma clave con cuerpo distinto es un
    # conflicto, no una repeticion.
    hash_peticion: Mapped[str] = mapped_column(String(64))
    estado: Mapped[str] = mapped_column(String(16), default="EN_CURSO")
    respuesta: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    codigo_http: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    completado_en: Mapped[datetime | None] = mapped_column(default=None)
    expira_en: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("alcance", "clave", name="uq_clave_idempotencia_alcance_clave"),
        CheckConstraint("estado IN ('EN_CURSO', 'COMPLETADA', 'FALLIDA')", name="estado_valido"),
        Index("ix_clave_idempotencia_expiracion", "expira_en"),
    )
