"""Modelo del outbox transaccional (ADR-0008).

Este es el mecanismo que convierte «mandamos un recordatorio» en una
garantia.

El problema que resuelve
------------------------
El patron habitual -- encolar el envio en Redis dentro del manejador de la
peticion -- tiene dos fallos que en un contexto clinico son inaceptables:

1. **Escritura dual.**  Si la transaccion de la cita se confirma y el encolado
   en Redis falla, o al reves, el estado queda inconsistente: cita confirmada
   sin recordatorio, o recordatorio de una cita que nunca existio.

2. **Durabilidad de Redis.**  Con la configuracion habitual, Redis puede
   perder los ultimos segundos de escrituras al caer.  Un recordatorio de
   medicacion perdido no es un fallo cosmetico.

La solucion: la intencion de enviar se escribe en esta tabla **en la misma
transaccion** que el cambio de negocio.  Un worker aparte la entrega despues,
con reintentos.  Redis pasa a ser un acelerador reemplazable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador


class EstadoOutbox(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    ENTREGADO = "ENTREGADO"
    # Agoto los reintentos.  NO desaparece: genera alerta.  Un mensaje que se
    # borra al fallar deja al personal creyendo que el paciente fue avisado.
    FALLIDO = "FALLIDO"
    # Descartado por una razon de negocio: el paciente revoco el
    # consentimiento, o la cita se cancelo antes del envio.
    DESCARTADO = "DESCARTADO"


class CanalOutbox(StrEnum):
    WHATSAPP = "WHATSAPP"
    CORREO = "CORREO"
    CALENDARIO = "CALENDARIO"
    INTERNO = "INTERNO"


class TipoMensajeOutbox(StrEnum):
    """Tipos de comunicacion saliente.

    Catalogo cerrado para que el procesador pueda enrutar sin adivinar y para
    que una prueba pueda recorrer todos los tipos y comprobar que ninguna
    plantilla incluye datos clinicos (requisito RF-K07).
    """

    CITA_CONFIRMACION = "CITA_CONFIRMACION"
    CITA_RECORDATORIO_DIA_ANTES = "CITA_RECORDATORIO_DIA_ANTES"
    CITA_RECORDATORIO_HORAS_ANTES = "CITA_RECORDATORIO_HORAS_ANTES"
    CITA_CANCELACION = "CITA_CANCELACION"
    CITA_REPROGRAMACION = "CITA_REPROGRAMACION"
    OFERTA_TURNO = "OFERTA_TURNO"
    OFERTA_EXPIRADA = "OFERTA_EXPIRADA"
    OFERTA_PERDIDA = "OFERTA_PERDIDA"
    TOMA_RECORDATORIO = "TOMA_RECORDATORIO"
    TOMA_SEGUIMIENTO = "TOMA_SEGUIMIENTO"
    RESUMEN_DIARIO_PROFESIONAL = "RESUMEN_DIARIO_PROFESIONAL"
    CAMBIO_AGENDA_PROFESIONAL = "CAMBIO_AGENDA_PROFESIONAL"
    ALERTA_PERSONAL = "ALERTA_PERSONAL"
    VERIFICACION_CORREO = "VERIFICACION_CORREO"
    RECUPERACION_CONTRASENA = "RECUPERACION_CONTRASENA"
    CALENDARIO_CREAR_EVENTO = "CALENDARIO_CREAR_EVENTO"
    CALENDARIO_ACTUALIZAR_EVENTO = "CALENDARIO_ACTUALIZAR_EVENTO"
    CALENDARIO_ELIMINAR_EVENTO = "CALENDARIO_ELIMINAR_EVENTO"


class OutboxMensaje(Base, MezclaIdentificador):
    """Intencion de comunicacion saliente, durable y reintentable."""

    __tablename__ = "outbox_mensaje"

    tipo: Mapped[str] = mapped_column(String(48))
    canal: Mapped[str] = mapped_column(String(16))
    clinica_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    # A quien va dirigido.  Sin clave externa: el destinatario puede ser un
    # paciente, un profesional o un usuario, y una columna por tipo dejaria
    # tres nulas siempre.
    destino_tipo: Mapped[str] = mapped_column(String(16))
    destino_id: Mapped[uuid.UUID] = mapped_column()

    # Contenido ya resuelto: nombre de plantilla y parametros.  NO lleva
    # diagnosticos ni nombres de medicamentos (requisito RF-K07); una prueba
    # recorre las plantillas y lo verifica.
    carga_util: Mapped[dict[str, object]] = mapped_column(JSONB)

    # =====================================================================
    #  Deduplicacion
    # =====================================================================
    # Clave derivada de la intencion, no del momento: por ejemplo
    # hash("recordatorio_24h" + cita_id).  Si la misma intencion se registra
    # dos veces, la restriccion unica lo rechaza y el paciente no recibe el
    # mismo recordatorio dos veces.
    #
    # Recibir dos recordatorios de la misma cita erosiona la confianza en las
    # notificaciones y lleva al paciente a silenciarlas, que es peor que no
    # enviarlas.
    clave_deduplicacion: Mapped[str] = mapped_column(String(64))

    estado: Mapped[str] = mapped_column(String(16), default=EstadoOutbox.PENDIENTE.value)
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_intentos: Mapped[int] = mapped_column(SmallInteger, default=6)
    # Cuando volver a intentarlo.  Es la columna por la que barre el worker.
    proximo_intento_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    # Trazabilidad: por que se contacto al paciente.  Permite responder
    # «quien decidio enviar esto» en una revision.
    entidad_origen_tipo: Mapped[str | None] = mapped_column(String(48), default=None)
    entidad_origen_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    ultimo_error: Mapped[str | None] = mapped_column(Text, default=None)
    # Identificador que devuelve el proveedor.  Permite conciliar los estados
    # de entrega que llegan despues por webhook.
    referencia_externa: Mapped[str | None] = mapped_column(String(255), default=None)

    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))
    actualizado_en: Mapped[datetime | None] = mapped_column(default=None)
    entregado_en: Mapped[datetime | None] = mapped_column(default=None)
    # Identificador del worker que lo tomo.  Sirve para recuperar mensajes
    # que quedaron EN_PROCESO porque el worker murio a media entrega.
    tomado_por: Mapped[str | None] = mapped_column(String(64), default=None)
    tomado_en: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("clave_deduplicacion", name="uq_outbox_mensaje_clave_deduplicacion"),
        CheckConstraint(
            "estado IN ('PENDIENTE', 'EN_PROCESO', 'ENTREGADO', 'FALLIDO', 'DESCARTADO')",
            name="estado_valido",
        ),
        CheckConstraint(
            "canal IN ('WHATSAPP', 'CORREO', 'CALENDARIO', 'INTERNO')",
            name="canal_valido",
        ),
        CheckConstraint(
            "destino_tipo IN ('PACIENTE', 'PROFESIONAL', 'USUARIO', 'CLINICA')",
            name="destino_tipo_valido",
        ),
        CheckConstraint("intentos >= 0", name="intentos_no_negativos"),
        CheckConstraint("max_intentos > 0", name="max_intentos_positivo"),
        # Un fallo sin error registrado no se puede diagnosticar.
        CheckConstraint(
            "estado <> 'FALLIDO' OR ultimo_error IS NOT NULL",
            name="fallido_con_error",
        ),
        # =================================================================
        #  Indice del camino caliente del worker.
        #
        #  Parcial sobre los pendientes: la tabla crece sin limite con los
        #  entregados, y un indice completo sobre `proximo_intento_en` haria
        #  que el barrido se degradara con el tiempo.  Asi el indice se
        #  mantiene del tamano de la cola, no del historico.
        # =================================================================
        Index(
            "ix_outbox_pendientes",
            "proximo_intento_en",
            postgresql_where=text("estado = 'PENDIENTE'"),
        ),
        # Recuperacion de mensajes huerfanos: los que quedaron EN_PROCESO
        # porque el worker murio entre tomar y entregar.
        Index(
            "ix_outbox_en_proceso",
            "tomado_en",
            postgresql_where=text("estado = 'EN_PROCESO'"),
        ),
        # Cola de alertas: los fallidos requieren intervencion humana.
        Index(
            "ix_outbox_fallidos",
            "clinica_id",
            "creado_en",
            postgresql_where=text("estado = 'FALLIDO'"),
        ),
        Index("ix_outbox_origen", "entidad_origen_tipo", "entidad_origen_id"),
        Index("ix_outbox_referencia_externa", "referencia_externa"),
    )

    @property
    def agoto_intentos(self) -> bool:
        return self.intentos >= self.max_intentos


class Recordatorio(Base, MezclaIdentificador):
    """Recordatorio programado, antes de convertirse en mensaje del outbox.

    Existe como tabla propia y no solo como fila del outbox porque hay que
    poder **cancelar** recordatorios futuros cuando la cita se cancela o la
    receta cambia (requisitos RF-K03 y RF-L09).  Con solo el outbox habria que
    buscar por carga util, que es fragil; aqui la relacion con la entidad de
    origen es explicita y el borrado logico es directo.
    """

    __tablename__ = "recordatorio"

    tipo: Mapped[str] = mapped_column(String(48))
    clinica_id: Mapped[uuid.UUID] = mapped_column()
    entidad_tipo: Mapped[str] = mapped_column(String(48))
    entidad_id: Mapped[uuid.UUID] = mapped_column()
    destinatario_tipo: Mapped[str] = mapped_column(String(16))
    destinatario_id: Mapped[uuid.UUID] = mapped_column()

    programado_para: Mapped[datetime] = mapped_column()
    estado: Mapped[str] = mapped_column(String(16), default="PROGRAMADO")
    # Se rellena al encolar.  SET NULL y no CASCADE: purgar mensajes
    # entregados del outbox no debe borrar el registro de que el
    # recordatorio existio y se envio.
    outbox_mensaje_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outbox_mensaje.id", ondelete="SET NULL"), default=None
    )
    cancelado_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(255), default=None)
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            "estado IN ('PROGRAMADO', 'ENCOLADO', 'CANCELADO', 'OMITIDO')",
            name="estado_valido",
        ),
        CheckConstraint(
            "estado <> 'CANCELADO' OR motivo_cancelacion IS NOT NULL",
            name="cancelacion_con_motivo",
        ),
        # Barrido del planificador: solo los programados que ya vencieron.
        Index(
            "ix_recordatorio_a_encolar",
            "programado_para",
            postgresql_where=text("estado = 'PROGRAMADO'"),
        ),
        # Cancelacion en bloque al cambiar una cita o una receta: esta es la
        # consulta que hace posible el requisito RF-L09.
        Index(
            "ix_recordatorio_entidad",
            "entidad_tipo",
            "entidad_id",
            postgresql_where=text("estado = 'PROGRAMADO'"),
        ),
    )
