"""Lectura de un documento marcado por el análisis de inyección.

`POST /documentos/{id}/revision-de-riesgo` desbloquea la aprobación, pero
exige que alguien haya **leído** el contenido. Sin esta lectura, quien aprueba
solo vería «revisión pendiente» y tendría que aceptar a ciegas: justo el caso
que el bloqueo quiere evitar (ADR-0014).

Devuelve los hallazgos del análisis y el texto de la versión vigente, tal como
quedó fragmentado. Exige `conocimiento.aprobar` y el mismo ámbito que el
listado (clínica, nivel, sede, especialidad y ACL), en el `WHERE`. La lectura
se audita: el texto puede ser contenido clínico de nivel N2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlalchemy import literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ia.recuperador import contexto_desde_principal
from app.modulos.conocimiento.modelos import KnowledgeDocument, KnowledgeVersion
from app.modulos.conocimiento.repositorio import (
    condicion_acl_documento,
    contenido_de_version_revisable,
)
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import NivelSensibilidad, Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import RecursoNoEncontrado

MAX_FRAGMENTOS = 80

enrutador = APIRouter(prefix="/conocimiento", tags=["conocimiento"])

PuedeAprobar = Annotated[Principal, Depends(exige_permiso("conocimiento.aprobar"))]


class HallazgoRiesgo(BaseModel):
    patron: str
    riesgo: str
    motivo: str
    extracto: str


class RevisionRiesgo(BaseModel):
    """Lo necesario para decidir si el texto marcado es aceptable."""

    document_id: uuid.UUID
    titulo: str
    version: int
    riesgo: str
    hallazgos: list[HallazgoRiesgo]
    fragmentos: list[str]
    fragmentos_totales: int
    revisado: bool
    revisado_en: datetime | None
    nota_revision: str | None


async def _documento_visible(
    sesion: AsyncSession, principal: Principal, ahora: datetime, document_id: uuid.UUID
) -> KnowledgeDocument | None:
    """El documento, si entra en el ámbito del principal. Mismo filtro que el listado."""
    contexto = contexto_desde_principal(principal, ahora=ahora)
    condiciones = [
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.clinic_id == principal.clinica_id,
        KnowledgeDocument.sensitivity_level.in_(
            sorted(n.value for n in NivelSensibilidad if contexto.nivel_maximo.cubre(n))
        ),
        condicion_acl_documento(KnowledgeDocument.id, contexto),
    ]
    if contexto.sedes is not None:
        condiciones.append(
            or_(
                KnowledgeDocument.branch_id.is_(None),
                KnowledgeDocument.branch_id.in_(sorted(contexto.sedes)),
            )
            if contexto.sedes
            else literal(False)
        )
    if contexto.especialidades is not None:
        condiciones.append(
            or_(
                KnowledgeDocument.specialty_id.is_(None),
                KnowledgeDocument.specialty_id.in_(sorted(contexto.especialidades)),
            )
            if contexto.especialidades
            else literal(False)
        )
    resultado = await sesion.execute(select(KnowledgeDocument).where(*condiciones))
    return resultado.scalar_one_or_none()


def _hallazgos(analisis: dict[str, object]) -> list[HallazgoRiesgo]:
    crudos = analisis.get("hallazgos")
    if not isinstance(crudos, list):
        return []
    return [
        HallazgoRiesgo(
            patron=str(h.get("patron", "")),
            riesgo=str(h.get("riesgo", "")),
            motivo=str(h.get("motivo", "")),
            extracto=str(h.get("extracto", "")),
        )
        for h in crudos
        if isinstance(h, dict)
    ]


@enrutador.get(
    "/documentos/{document_id}/revision-de-riesgo",
    response_model=RevisionRiesgo,
    summary="Leer los hallazgos y el texto de la versión vigente antes de revisarla",
    responses={
        403: {"description": "Sin permiso de aprobación"},
        404: {"description": "No existe, está fuera de ámbito o no tiene versión"},
    },
)
async def leer_revision_de_riesgo(
    principal: PuedeAprobar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    document_id: Annotated[uuid.UUID, Path(description="Identificador del documento.")],
) -> RevisionRiesgo:
    documento = await _documento_visible(sesion, principal, reloj.ahora(), document_id)
    if documento is None or documento.version_vigente <= 0:
        raise RecursoNoEncontrado("El documento no existe o no tiene una versión cargada.")

    version = (
        await sesion.execute(
            select(KnowledgeVersion).where(
                KnowledgeVersion.document_id == documento.id,
                KnowledgeVersion.version == documento.version_vigente,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        raise RecursoNoEncontrado("No se encuentra la versión vigente del documento.")

    contenidos = await contenido_de_version_revisable(
        sesion, documento=documento, version=version.version
    )
    analisis = dict(version.resultado_analisis_inyeccion or {})
    revisado_en = analisis.get("revisado_en")
    nota = analisis.get("nota_revision")

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CONOCIMIENTO_RIESGO_LEIDO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="knowledge_version",
                entidad_id=documento.id,
                version=version.version,
            )
        ]
    )
    await sesion.commit()
    return RevisionRiesgo(
        document_id=documento.id,
        titulo=documento.titulo,
        version=version.version,
        riesgo=str(analisis.get("riesgo", "DESCONOCIDO")),
        hallazgos=_hallazgos(analisis),
        fragmentos=list(contenidos[:MAX_FRAGMENTOS]),
        fragmentos_totales=len(contenidos),
        revisado=bool(analisis.get("revisado_por")),
        revisado_en=datetime.fromisoformat(revisado_en) if isinstance(revisado_en, str) else None,
        nota_revision=nota if isinstance(nota, str) else None,
    )


__all__ = ["enrutador"]
