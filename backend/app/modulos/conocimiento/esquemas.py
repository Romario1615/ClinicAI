"""Esquemas de entrada y salida de la base de conocimiento.

Los de salida son explicitos. En particular, el resultado de una busqueda
**no** devuelve el contenido completo del fragmento a cualquiera: devuelve un
extracto y la referencia. Quien necesite el texto entero abre el documento,
que es una lectura distinta y se audita.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modulos.conocimiento.modelos import (
    EstadoDocumento,
    TipoDocumentoConocimiento,
)

# Longitud del extracto que acompana a cada resultado de busqueda. Suficiente
# para que una persona reconozca si el fragmento responde su pregunta, sin
# volcar el documento entero en una respuesta de listado.
LONGITUD_EXTRACTO = 300


class SolicitudDocumento(BaseModel):
    """Alta de un documento. Nace en `DRAFT`, sin excepcion."""

    titulo: str = Field(min_length=3, max_length=300)
    tipo: TipoDocumentoConocimiento
    sensibilidad: str = Field(default="N1", pattern=r"^N[0-3]$")
    branch_id: uuid.UUID | None = None
    specialty_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    responsable_id: uuid.UUID | None = None
    etiquetas: list[str] | None = Field(default=None, max_length=20)
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class SolicitudIngesta(BaseModel):
    """Contenido de una version nueva.

    Solo texto en esta fase. La carga de PDF (RF-M01) exige extraccion y
    analisis de archivo, que van con el resto de la gestion documental.
    """

    contenido: str = Field(min_length=1, max_length=500_000)
    nombre_archivo: str | None = Field(default=None, max_length=255)
    notas_cambio: str | None = Field(default=None, max_length=1000)


class SolicitudCambioEstado(BaseModel):
    nuevo_estado: EstadoDocumento
    motivo: str | None = Field(default=None, max_length=500)


class SolicitudRevision(BaseModel):
    """Desbloqueo explicito de un documento marcado como riesgoso.

    El motivo es obligatorio y con longitud minima: es la constancia de que
    alguien miro el contenido de verdad.
    """

    version: int = Field(ge=1)
    nota: str = Field(min_length=10, max_length=1000)


class RespuestaDocumento(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    titulo: str
    tipo: str
    status: str
    version_vigente: int
    sensitivity_level: str
    branch_id: uuid.UUID | None
    specialty_id: uuid.UUID | None
    service_id: uuid.UUID | None
    etiquetas: list[str] | None
    effective_from: datetime | None
    effective_until: datetime | None
    aprobado_por: uuid.UUID | None
    aprobado_en: datetime | None
    archivado_en: datetime | None
    # Cierto si su version vigente tiene un analisis de riesgo alto sin
    # revisar. Es lo que el panel necesita para mostrar el aviso, sin exponer
    # los hallazgos a quien solo lista documentos.
    requiere_revision: bool = False


class PaginaDocumentos(BaseModel):
    elementos: list[RespuestaDocumento]
    total: int


class RespuestaIngesta(BaseModel):
    document_id: uuid.UUID
    version: int
    fragmentos: int
    embeddings: int
    riesgo_inyeccion: str
    requiere_revision: bool


class SolicitudBusqueda(BaseModel):
    consulta: str = Field(min_length=3, max_length=1000)
    limite: int = Field(default=8, ge=1, le=20)


class ResultadoBusqueda(BaseModel):
    """Un fragmento recuperado, con extracto y no con el texto completo."""

    document_id: uuid.UUID
    version: int
    indice_fragmento: int
    referencia: str
    extracto: str
    puntuacion: float
    # Posiciones en cada ranking. Se exponen para poder diagnosticar por que
    # un resultado salio primero: sin ellas, la busqueda hibrida es una caja
    # negra y no se puede afinar.
    posicion_vectorial: int | None
    posicion_textual: int | None


class RespuestaBusqueda(BaseModel):
    """Resultado de una busqueda.

    `hay_fuente` en falso **no es un error**: significa que no hay
    documentacion aprobada que cubra la consulta, y el cliente debe mostrar
    `mensaje` en lugar de improvisar (RF-O06).
    """

    hay_fuente: bool
    mensaje: str | None
    resultados: list[ResultadoBusqueda]
    documentos_citados: list[uuid.UUID]


__all__ = [
    "LONGITUD_EXTRACTO",
    "PaginaDocumentos",
    "RespuestaBusqueda",
    "RespuestaDocumento",
    "RespuestaIngesta",
    "ResultadoBusqueda",
    "SolicitudBusqueda",
    "SolicitudCambioEstado",
    "SolicitudDocumento",
    "SolicitudIngesta",
    "SolicitudRevision",
]
