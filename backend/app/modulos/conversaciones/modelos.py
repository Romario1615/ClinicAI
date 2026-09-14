"""Conversaciones y mensajes entrantes.

Que hace falta guardar y por que
--------------------------------
El webhook de WhatsApp entrega mensajes **al menos una vez**: ante cualquier
duda de entrega, Meta reintenta.  Si el sistema no recuerda que ya vio un
mensaje, un reintento vuelve a ejecutar su efecto -- y el efecto puede ser
revocar el consentimiento de un paciente o abrir una derivacion duplicada.
De ahi la restriccion unica sobre `external_id`: es la deduplicacion real, y
esta en la base de datos, no en Redis, porque debe durar lo mismo que el dato
de negocio.

La ventana de 24 horas
----------------------
WhatsApp solo permite texto libre durante las 24 horas siguientes al ultimo
mensaje del paciente.  Fuera de esa ventana hay que usar una plantilla
aprobada.  `ventana_expira_en` guarda ese limite para que el personal sepa,
al abrir la conversacion, si puede responder con texto libre o no; sin ese
dato la respuesta se rechaza en el proveedor y parece un fallo del sistema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador


class EstadoConversacion(StrEnum):
    ABIERTA = "ABIERTA"
    # Esperando a una persona. Es el estado al que va todo lo que el sistema
    # no entiende con certeza, y todo lo clinico (CLAUDE.md, regla 5).
    EN_HANDOFF = "EN_HANDOFF"
    CERRADA = "CERRADA"


class IntencionEntrante(StrEnum):
    """Intencion reconocida de un mensaje entrante.

    Catalogo deliberadamente corto.  Solo se reconocen intenciones que se
    pueden resolver con una coincidencia exacta de palabra clave y cuyo efecto
    es reversible o inocuo.  Todo lo demas es `DESCONOCIDA` y va a una
    persona: interpretar mal «no puedo tomar la pastilla» tiene consecuencias
    clinicas, y este modulo no interpreta.
    """

    CONFIRMAR = "CONFIRMAR"
    CANCELAR = "CANCELAR"
    ACEPTAR_OFERTA = "ACEPTAR_OFERTA"
    REGISTRAR_TOMA = "REGISTRAR_TOMA"
    BAJA = "BAJA"
    ALTA = "ALTA"
    AYUDA = "AYUDA"
    DESCONOCIDA = "DESCONOCIDA"


class Conversacion(Base, MezclaIdentificador):
    """Hilo con un numero de telefono."""

    __tablename__ = "conversacion"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="CASCADE"))
    canal: Mapped[str] = mapped_column(String(16), default="WHATSAPP")
    # El telefono, no el paciente, es la clave del hilo: quien escribe puede
    # no estar identificado todavia, y un mismo numero puede corresponder a
    # varios pacientes (una madre que gestiona las citas de tres hijos).
    telefono: Mapped[str] = mapped_column(String(32))
    # Se rellena cuando la identidad queda resuelta. Nulo mientras no lo este:
    # atribuir la conversacion al paciente equivocado por compartir telefono
    # mezclaria hilos de personas distintas.
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paciente.id", ondelete="SET NULL"), default=None
    )

    estado: Mapped[str] = mapped_column(String(16), default=EstadoConversacion.ABIERTA.value)
    ventana_expira_en: Mapped[datetime | None] = mapped_column(default=None)
    asignado_a_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), default=None
    )
    motivo_handoff: Mapped[str | None] = mapped_column(String(255), default=None)

    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    ultima_actividad_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    cerrada_en: Mapped[datetime | None] = mapped_column(default=None)
    # Lista de pacientes ofrecida cuando el telefono corresponde a varios.
    #
    # Se guarda **con su orden**: reconstruirla al recibir la respuesta podria
    # devolver otro -- por una ficha nueva con ese mismo numero -- y entonces
    # el «2» de quien escribe seleccionaria a otra persona.
    #
    # Lleva su propia caducidad: una lista ofrecida ayer y respondida hoy con
    # «2» es una respuesta a una pregunta que ya nadie recuerda.
    seleccion_pendiente: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    __table_args__ = (
        # Un hilo abierto por numero y canal. Sin esto, dos mensajes casi
        # simultaneos abririan dos conversaciones y el personal veria el hilo
        # partido en dos.
        Index(
            "ix_conversacion_activa_unica",
            "clinica_id",
            "canal",
            "telefono",
            unique=True,
            postgresql_where=text("estado <> 'CERRADA'"),
        ),
        CheckConstraint(
            "estado IN ('ABIERTA', 'EN_HANDOFF', 'CERRADA')",
            name="estado_valido",
        ),
        # `DEMO` existe para que un hilo de simulacion **no sea
        # indistinguible** de uno real. Sin un canal propio habria que
        # marcarlo por el formato del telefono, y cualquier consulta que
        # olvidara ese detalle trataria la simulacion como un paciente al que
        # se le puede escribir.
        CheckConstraint("canal IN ('WHATSAPP', 'DEMO')", name="canal_valido"),
        CheckConstraint(
            "estado <> 'EN_HANDOFF' OR motivo_handoff IS NOT NULL",
            name="handoff_con_motivo",
        ),
        # Cola de trabajo del personal: las que esperan a una persona,
        # primero las que llevan mas esperando.
        Index(
            "ix_conversacion_en_handoff",
            "clinica_id",
            "ultima_actividad_en",
            postgresql_where=text("estado = 'EN_HANDOFF'"),
        ),
    )


class MensajeEntrante(Base, MezclaIdentificador):
    """Mensaje recibido del paciente.

    Se guarda el texto tal como llego.  No es contenido clinico por
    construccion -- pero el paciente puede escribir lo que quiera, incluido
    un sintoma.  Por eso esta tabla se trata como historia clinica a efectos
    de acceso: se lee con permiso explicito y toda lectura se audita.
    """

    __tablename__ = "mensaje_entrante"

    conversacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversacion.id", ondelete="CASCADE")
    )
    # Identificador del proveedor (`wamid....`). Es la clave de deduplicacion.
    external_id: Mapped[str] = mapped_column(String(128))
    telefono_origen: Mapped[str] = mapped_column(String(32))
    tipo: Mapped[str] = mapped_column(String(24))
    texto: Mapped[str | None] = mapped_column(Text, default=None)
    # Payload crudo del proveedor, para poder diagnosticar un mensaje que el
    # sistema interpreto mal sin pedirle al paciente que lo repita.
    carga_util: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    intencion: Mapped[str] = mapped_column(String(24), default=IntencionEntrante.DESCONOCIDA.value)
    recibido_en: Mapped[datetime] = mapped_column()
    procesado_en: Mapped[datetime | None] = mapped_column(default=None)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        # LA deduplicacion. Un reintento de Meta choca aqui y no vuelve a
        # producir efecto.
        UniqueConstraint("external_id", name="uq_mensaje_entrante_external_id"),
        CheckConstraint(
            "intencion IN ('CONFIRMAR', 'CANCELAR', 'ACEPTAR_OFERTA', 'REGISTRAR_TOMA', "
            "'BAJA', 'ALTA', 'AYUDA', 'DESCONOCIDA')",
            name="intencion_valida",
        ),
        Index("ix_mensaje_entrante_conversacion", "conversacion_id", "recibido_en"),
    )


__all__ = [
    "Conversacion",
    "EstadoConversacion",
    "IntencionEntrante",
    "MensajeEntrante",
]
