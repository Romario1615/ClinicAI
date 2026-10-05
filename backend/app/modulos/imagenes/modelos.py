"""Imagenes de pacientes: foto de perfil, radiografias y fotos clinicas.

Que guarda la tabla y que no
----------------------------
La fila guarda **metadatos y la clave del objeto**; los bytes viven en el
almacen de objetos, cifrados con AES-GCM y ligados al identificador de la
fila (ver `app/nucleo/almacen.py`). Un objeto copiado a la clave de otra
imagen no descifra.

Dos niveles de sensibilidad en la misma tabla
---------------------------------------------
* `PERFIL` es identificacion: recepcion la usa para reconocer al paciente en
  el mostrador. Nivel **N1**, permisos administrativos del paciente.
* Todo lo demas (radiografias, fotos intraorales) es **N2 · Clinico**:
  permiso propio, relacion asistencial y auditoria de cada visualizacion.

Una restriccion `CHECK` ata el tipo al nivel: una radiografia no puede quedar
marcada como N1 por un descuido en un camino de escritura nuevo.

Nunca se borra
--------------
Una imagen equivocada se **anula** con motivo (`MezclaAnulacion`). El objeto
cifrado se conserva: la historia clinica no se destruye.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.nucleo.bd import Base, MezclaAnulacion, MezclaAuditoria, MezclaIdentificador


class TipoImagen(StrEnum):
    PERFIL = "PERFIL"
    RADIOGRAFIA_PERIAPICAL = "RADIOGRAFIA_PERIAPICAL"
    RADIOGRAFIA_BITEWING = "RADIOGRAFIA_BITEWING"
    RADIOGRAFIA_PANORAMICA = "RADIOGRAFIA_PANORAMICA"
    RADIOGRAFIA_CEFALOMETRICA = "RADIOGRAFIA_CEFALOMETRICA"
    FOTO_INTRAORAL = "FOTO_INTRAORAL"
    FOTO_EXTRAORAL = "FOTO_EXTRAORAL"
    OTRA = "OTRA"

    @property
    def es_clinica(self) -> bool:
        return self is not TipoImagen.PERFIL


SQL_TIPOS_IMAGEN = ", ".join(f"'{tipo.value}'" for tipo in TipoImagen)


class ImagenPaciente(Base, MezclaIdentificador, MezclaAuditoria, MezclaAnulacion):
    __tablename__ = "imagen_paciente"

    clinica_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clinica.id", ondelete="RESTRICT"))
    paciente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paciente.id", ondelete="RESTRICT"))
    tipo: Mapped[str] = mapped_column(String(32))
    nivel_sensibilidad: Mapped[str] = mapped_column(String(2))

    # Piezas dentales en notacion FDI. Vacio en una panoramica o en la foto
    # de perfil. Permite filtrar «todas las imagenes del 36».
    piezas: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), default=list)
    tomada_en: Mapped[date | None] = mapped_column(default=None)
    descripcion: Mapped[str | None] = mapped_column(Text, default=None)
    cita_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cita.id", ondelete="SET NULL"), default=None
    )
    profesional_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profesional.id", ondelete="RESTRICT"), default=None
    )
    # Procedimiento del plan al que documenta la foto (antes, durante,
    # despues). Opcional: una radiografia de control no tiene procedimiento.
    procedimiento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("procedimiento_plan.id", ondelete="RESTRICT"), default=None
    )

    # --- Objeto ---
    tipo_mime: Mapped[str] = mapped_column(String(32))
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    # Del archivo ya saneado, en claro. Detecta duplicados y permite probar
    # integridad ante una reclamacion.
    sha256: Mapped[str] = mapped_column(String(64))
    clave_objeto: Mapped[str] = mapped_column(String(300))
    antivirus: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        UniqueConstraint("clave_objeto", name="uq_imagen_paciente_clave_objeto"),
        CheckConstraint(f"tipo IN ({SQL_TIPOS_IMAGEN})", name="tipo_valido"),
        CheckConstraint(
            "(tipo = 'PERFIL' AND nivel_sensibilidad = 'N1') "
            "OR (tipo <> 'PERFIL' AND nivel_sensibilidad IN ('N2', 'N3'))",
            name="nivel_coherente_con_tipo",
        ),
        CheckConstraint("tamano_bytes > 0", name="tamano_positivo"),
        CheckConstraint(
            "descripcion IS NULL OR char_length(descripcion) <= 500", name="descripcion_corta"
        ),
        Index("ix_imagen_paciente_paciente_tipo", "paciente_id", "tipo", "creado_en"),
    )


__all__ = ["SQL_TIPOS_IMAGEN", "ImagenPaciente", "TipoImagen"]
