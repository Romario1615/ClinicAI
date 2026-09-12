"""Lista de espera y oferta de turnos liberados.

El problema que resuelve
------------------------
Cuando alguien cancela, queda un turno libre que nadie ve. La lista de espera
lo ofrece a quien lo estaba esperando.

Por que se ofrece a UNA persona a la vez
----------------------------------------
La alternativa -- avisar a todos y que gane el primero en responder -- produce
un ganador y varios avisos de «ya no esta disponible». Eso erosiona la
confianza en el aviso: a la tercera vez, el paciente deja de mirarlos, y
entonces el mecanismo completo deja de funcionar.

Se ofrece a una sola persona, con plazo. Si no responde, el plazo vence y el
turno pasa al siguiente. Es mas lento y es lo que mantiene el aviso creible.

Las dos garantias del motor
---------------------------
1. **Una oferta activa por turno.** Un indice unico parcial sobre
   `(cita_liberada_id)` donde el estado es `OFRECIDA`. Sin el, dos barridos
   simultaneos del worker ofrecerian el mismo turno a dos personas.

2. **Una sola aceptacion gana.** El indice anterior mas un bloqueo consultivo
   sobre el turno en el servicio. Dos pacientes aceptando a la vez: uno se
   queda con la cita, el otro recibe que el turno acaba de tomarse.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class EstadoEspera(StrEnum):
    ACTIVA = "ACTIVA"
    # Tiene una oferta en curso; no se le ofrece otro turno mientras tanto.
    OFERTADA = "OFERTADA"
    CUMPLIDA = "CUMPLIDA"
    CANCELADA = "CANCELADA"
    EXPIRADA = "EXPIRADA"


class EstadoOferta(StrEnum):
    OFRECIDA = "OFRECIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    EXPIRADA = "EXPIRADA"
    # El turno se ocupo por otra via antes de que respondiera.
    PERDIDA = "PERDIDA"


class PrioridadEspera(StrEnum):
    NORMAL = "NORMAL"
    ALTA = "ALTA"


class EntradaListaEspera(Base, MezclaIdentificador, MezclaAuditoria):
    """Un paciente esperando turno para una especialidad en una sede."""

    __tablename__ = "lista_espera"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    sede_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sede.id", ondelete="RESTRICT"))
    especialidad_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("especialidad.id", ondelete="RESTRICT")
    )
    servicio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicio.id", ondelete="SET NULL"), default=None
    )
    # Opcional: quien espera a un profesional concreto no acepta cualquier
    # hueco de la especialidad.
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profesional.id", ondelete="SET NULL"), default=None
    )

    estado: Mapped[str] = mapped_column(String(16), default=EstadoEspera.ACTIVA.value)
    prioridad: Mapped[str] = mapped_column(String(8), default=PrioridadEspera.NORMAL.value)

    # --- Preferencias ---
    #
    # Franjas horarias aceptables como JSON: el conjunto varia por paciente
    # («solo mananas», «martes y jueves», «cualquier dia menos viernes») y
    # modelarlo con columnas produciria una tabla que no cubre el caso
    # siguiente.
    preferencias: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    # Antelacion minima con la que el paciente puede presentarse. Sin esto se
    # le ofreceria un hueco de dentro de veinte minutos que no puede alcanzar.
    horas_antelacion_minima: Mapped[int] = mapped_column(SmallInteger, default=4)

    disponible_desde: Mapped[date | None] = mapped_column(default=None)
    disponible_hasta: Mapped[date | None] = mapped_column(default=None)

    # Cuantas ofertas se le han hecho y cuantas ha dejado vencer. Importa: a
    # quien nunca responde se le deja de ofrecer, o bloquea la cola.
    ofertas_realizadas: Mapped[int] = mapped_column(SmallInteger, default=0)
    ofertas_vencidas: Mapped[int] = mapped_column(SmallInteger, default=0)

    nota: Mapped[str | None] = mapped_column(Text, default=None)
    cita_resultante_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="SET NULL"), default=None
    )

    ofertas: Mapped[list[OfertaTurno]] = relationship(
        back_populates="entrada", lazy="raise", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('ACTIVA', 'OFERTADA', 'CUMPLIDA', 'CANCELADA', 'EXPIRADA')",
            name="estado_espera_valido",
        ),
        CheckConstraint("prioridad IN ('NORMAL', 'ALTA')", name="prioridad_valida"),
        CheckConstraint(
            "horas_antelacion_minima >= 0 AND horas_antelacion_minima <= 168",
            name="antelacion_razonable",
        ),
        CheckConstraint(
            "disponible_hasta IS NULL OR disponible_desde IS NULL "
            "OR disponible_hasta >= disponible_desde",
            name="ventana_coherente",
        ),
        # Un paciente no se apunta dos veces a la misma especialidad y sede.
        # Indice parcial: las entradas cerradas no participan, y quien ya fue
        # atendido puede volver a apuntarse.
        Index(
            "ix_espera_sin_duplicados",
            "paciente_id",
            "sede_id",
            "especialidad_id",
            unique=True,
            postgresql_where=text("estado IN ('ACTIVA', 'OFERTADA')"),
        ),
        # Consulta del worker: a quien ofrecer un turno liberado. El orden de
        # las columnas sigue el del filtro y despues el del ordenamiento.
        Index(
            "ix_espera_candidatos",
            "sede_id",
            "especialidad_id",
            "prioridad",
            "creado_en",
            postgresql_where=text("estado = 'ACTIVA'"),
        ),
    )


class OfertaTurno(Base, MezclaIdentificador, MezclaAuditoria):
    """Ofrecimiento de un turno liberado a una persona concreta."""

    __tablename__ = "oferta_turno"

    lista_espera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lista_espera.id", ondelete="CASCADE")
    )
    # La cita que quedo libre. Se conserva aunque despues se reasigne: es lo
    # que permite reconstruir la cadena de huecos liberados.
    cita_liberada_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cita.id", ondelete="CASCADE"))

    estado: Mapped[str] = mapped_column(String(16), default=EstadoOferta.OFRECIDA.value)
    # El plazo es obligatorio. Una oferta sin plazo retiene el turno
    # indefinidamente si el paciente no contesta, y el turno vuelve a estar
    # tan perdido como antes de ofrecerlo.
    expira_en: Mapped[datetime] = mapped_column()

    respondida_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, default=None)
    cita_creada_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="SET NULL"), default=None
    )

    # Canal por el que se envio. Se registra para poder medir cual funciona.
    canal: Mapped[str] = mapped_column(String(16), default="WHATSAPP")
    notificada: Mapped[bool] = mapped_column(Boolean, default=False)

    entrada: Mapped[EntradaListaEspera] = relationship(back_populates="ofertas", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "estado IN ('OFRECIDA', 'ACEPTADA', 'RECHAZADA', 'EXPIRADA', 'PERDIDA')",
            name="estado_oferta_valido",
        ),
        CheckConstraint(
            "estado = 'OFRECIDA' OR respondida_en IS NOT NULL OR estado = 'EXPIRADA'",
            name="respuesta_exige_instante",
        ),
        CheckConstraint(
            "estado <> 'ACEPTADA' OR cita_creada_id IS NOT NULL",
            name="aceptada_exige_cita",
        ),
        # ===================================================================
        #  La garantia central de esta fase.
        #
        #  Una sola oferta activa por turno liberado. Sin ella, dos barridos
        #  simultaneos del worker ofrecerian el mismo hueco a dos personas, y
        #  las dos lo aceptarian: una se quedaria sin cita despues de que el
        #  sistema le dijera que era suya.
        # ===================================================================
        Index(
            "ix_oferta_activa_unica",
            "cita_liberada_id",
            unique=True,
            postgresql_where=text("estado = 'OFRECIDA'"),
        ),
        # Y una sola oferta activa por persona: ofrecerle dos turnos a la vez
        # le obliga a elegir contra reloj y deja el segundo bloqueado.
        Index(
            "ix_oferta_activa_por_entrada",
            "lista_espera_id",
            unique=True,
            postgresql_where=text("estado = 'OFRECIDA'"),
        ),
        # Barrido de ofertas vencidas.
        Index(
            "ix_oferta_vencidas",
            "expira_en",
            postgresql_where=text("estado = 'OFRECIDA'"),
        ),
    )


__all__ = [
    "EntradaListaEspera",
    "EstadoEspera",
    "EstadoOferta",
    "OfertaTurno",
    "PrioridadEspera",
]
