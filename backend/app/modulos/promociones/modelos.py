"""Campanas de promociones por WhatsApp.

Ciclo de vida
-------------
`BORRADOR` -> `APROBADA` -> `ENVIADA`, o `CANCELADA`. Solo una campana
aprobada se envia, y solo la aprueba quien tiene `promocion.aprobar`. La
imagen puede subirla el personal o proponerla un modelo de generacion; en
ambos casos la aprueba una persona antes de que salga.

A quien llega
-------------
A los pacientes de la clinica con consentimiento **PROMOCIONES** vigente.
El segmento solo usa datos administrativos (sede, antiguedad de la ultima
visita). Nunca diagnostico, tratamiento ni historia: usar datos clinicos con
fines comerciales exige un consentimiento especifico que este sistema no
recoge.

Los envios no tienen tabla propia: son mensajes del outbox con
`entidad_origen = campana` y clave de deduplicacion `promo:<hash(campana, paciente)>`.
Reenviar una campana no duplica nada.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAuditoria, MezclaIdentificador


class EstadoCampana(StrEnum):
    BORRADOR = "BORRADOR"
    APROBADA = "APROBADA"
    ENVIADA = "ENVIADA"
    CANCELADA = "CANCELADA"


class OrigenImagen(StrEnum):
    SUBIDA = "SUBIDA"
    GENERADA = "GENERADA"


class CampanaPromocion(Base, MezclaIdentificador, MezclaAuditoria):
    __tablename__ = "campana_promocion"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    nombre: Mapped[str] = mapped_column(String(150))
    # Texto de la oferta. Va al cuerpo de la plantilla de marketing.
    texto: Mapped[str] = mapped_column(Text)
    # Nombre de la plantilla de marketing aprobada en Meta.
    plantilla_meta: Mapped[str] = mapped_column(String(100), default="promocion_clinica")
    estado: Mapped[str] = mapped_column(String(16), default=EstadoCampana.BORRADOR.value)
    segmento: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # --- Imagen ---
    imagen_clave: Mapped[str | None] = mapped_column(String(300), default=None)
    imagen_mime: Mapped[str | None] = mapped_column(String(32), default=None)
    imagen_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    imagen_origen: Mapped[str | None] = mapped_column(String(10), default=None)
    imagen_proveedor: Mapped[str | None] = mapped_column(String(32), default=None)
    imagen_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    # Id del medio en WhatsApp, subido una vez al enviar.
    imagen_media_id: Mapped[str | None] = mapped_column(String(120), default=None)

    # --- Aprobacion y envio ---
    aprobada_por: Mapped[uuid.UUID | None] = mapped_column(default=None)
    aprobada_en: Mapped[datetime | None] = mapped_column(default=None)
    programada_para: Mapped[datetime | None] = mapped_column(default=None)
    enviada_en: Mapped[datetime | None] = mapped_column(default=None)
    encolados: Mapped[int] = mapped_column(Integer, default=0)
    omitidos: Mapped[int] = mapped_column(Integer, default=0)
    cancelada_en: Mapped[datetime | None] = mapped_column(default=None)
    motivo_cancelacion: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint(
            "estado IN ('BORRADOR', 'APROBADA', 'ENVIADA', 'CANCELADA')", name="estado_valido"
        ),
        CheckConstraint(
            "imagen_origen IS NULL OR imagen_origen IN ('SUBIDA', 'GENERADA')",
            name="origen_imagen_valido",
        ),
        # Nada sale sin imagen ni sin aprobacion registrada.
        CheckConstraint(
            "estado NOT IN ('APROBADA', 'ENVIADA') "
            "OR (imagen_clave IS NOT NULL AND aprobada_en IS NOT NULL AND aprobada_por IS NOT NULL)",
            name="aprobada_con_imagen",
        ),
        CheckConstraint(
            "estado <> 'CANCELADA' OR motivo_cancelacion IS NOT NULL",
            name="cancelacion_con_motivo",
        ),
        CheckConstraint("char_length(texto) BETWEEN 10 AND 500", name="texto_acotado"),
        Index("ix_campana_promocion_clinica", "clinica_id", "estado", "creado_en"),
    )


__all__ = ["CampanaPromocion", "EstadoCampana", "OrigenImagen"]
