"""Esquemas de salida del centro de ayuda.

Explicitos, como todos los de la API: el manual expone el codigo y la
descripcion de cada permiso que menciona, y nada de la cuenta ni del ambito.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class TipoManual(StrEnum):
    SISTEMA = "SISTEMA"
    PERSONALIZADO = "PERSONALIZADO"


class PermisoSalida(BaseModel):
    codigo: str
    descripcion: str


class SeccionSalida(BaseModel):
    clave: str
    titulo: str
    ruta: str | None
    proposito: str
    pasos: list[str]
    limites: list[str]
    permisos: list[PermisoSalida]


class ManualSalida(BaseModel):
    rol_codigo: str
    rol_nombre: str
    tipo: TipoManual
    titulo: str
    introduccion: str
    responsabilidades: list[str]
    limites: list[str]
    secciones: list[SeccionSalida]


class RespuestaManuales(BaseModel):
    """Los manuales de los roles vigentes de quien consulta."""

    manuales: list[ManualSalida]
