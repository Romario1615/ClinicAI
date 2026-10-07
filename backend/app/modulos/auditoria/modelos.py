"""Modelo de la tabla de auditoría.

La migración instala disparadores PostgreSQL que rechazan `UPDATE`, `DELETE`
y `TRUNCATE`, incluso cuando el rol local es propietario del esquema. En
producción también se debe usar una cuenta de aplicación distinta del dueño
del esquema para impedir que el proceso desactive o elimine los disparadores.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaIdentificador


class Auditoria(Base, MezclaIdentificador):
    """Registro de una accion o de un acceso.

    Sin claves externas a `usuario`, `paciente` ni `clinica`, a proposito:

    * el actor puede ser el sistema o el agente de IA, que no son filas de
      `usuario`, y una clave externa obligaria a inventar usuarios ficticios
      para representarlos;
    * la auditoria debe sobrevivir al borrado de la entidad referenciada.  Si
      un paciente se elimina por una orden judicial, el registro de quien
      accedio a sus datos tiene que seguir existiendo, y una clave externa con
      `CASCADE` lo borraria justo cuando mas hace falta.

    El precio es perder integridad referencial en los identificadores.  Se
    acepta: la auditoria es un registro historico, no un modelo relacional
    vivo.
    """

    __tablename__ = "auditoria"

    accion: Mapped[str] = mapped_column(String(64))
    actor_tipo: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    resultado: Mapped[str] = mapped_column(String(16), default="EXITO")

    entidad_tipo: Mapped[str | None] = mapped_column(String(48), default=None)
    entidad_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    clinica_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    sede_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    nivel_sensibilidad: Mapped[str | None] = mapped_column(String(4), default=None)

    ip: Mapped[str | None] = mapped_column(INET, default=None)
    origen: Mapped[str] = mapped_column(String(16), default="API")
    correlacion_id: Mapped[str | None] = mapped_column(String(64), default=None)
    motivo: Mapped[str | None] = mapped_column(Text, default=None)
    # Referencias y contadores. NUNCA contenido clinico ni secretos: se valida
    # en `app.nucleo.auditoria.validar_metadatos`, que falla de forma explicita
    # si alguien intenta guardar una nota o una dosis aqui.
    metadatos: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)

    ocurrido_en: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            "actor_tipo IN ('USUARIO', 'SISTEMA', 'AGENTE_IA', 'PACIENTE')",
            name="actor_tipo_valido",
        ),
        CheckConstraint("resultado IN ('EXITO', 'DENEGADO', 'ERROR')", name="resultado_valido"),
        # `DEMO_LOCAL` marca lo que hizo el agente en una simulacion. Sin un
        # origen propio, una revision de auditoria no podria distinguir una
        # reserva simulada de una real, que es justo para lo que existe este
        # campo. Solo aparece en el entorno local.
        CheckConstraint(
            "origen IN ('WEB', 'API', 'WHATSAPP', 'WORKER', 'DEMO_LOCAL')",
            name="origen_valido",
        ),
        CheckConstraint(
            "nivel_sensibilidad IS NULL OR nivel_sensibilidad IN ('N0', 'N1', 'N2', 'N3')",
            name="nivel_valido",
        ),
        # Consultas tipicas del auditor.  El orden de las columnas sigue el
        # patron de uso: primero se filtra por paciente o actor, despues por
        # fecha.
        Index("ix_auditoria_paciente", "paciente_id", "ocurrido_en"),
        Index("ix_auditoria_actor", "actor_id", "ocurrido_en"),
        Index("ix_auditoria_accion", "clinica_id", "accion", "ocurrido_en"),
        Index("ix_auditoria_entidad", "entidad_tipo", "entidad_id"),
        Index("ix_auditoria_correlacion", "correlacion_id"),
        # Indice parcial para la revision de accesos denegados y de accesos a
        # informacion de sensibilidad alta, que son las consultas de
        # seguridad.  El indice completo seria enorme y poco util.
        Index(
            "ix_auditoria_revision_seguridad",
            "clinica_id",
            "ocurrido_en",
            postgresql_where=text("resultado = 'DENEGADO' OR nivel_sensibilidad = 'N3'"),
        ),
    )
