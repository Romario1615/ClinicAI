"""Delegaciones de firma de recetas.

La administracion (`profesional.gestionar`) registra que un profesional puede
firmar por otro durante un periodo, con motivo. El delegado consulta las suyas
para saber por quien puede firmar. Revocar no borra: deja fecha y autor.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select

from app.modulos.profesionales.modelos import DelegacionFirma, Profesional
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado

enrutador = APIRouter(prefix="/profesionales/delegaciones", tags=["delegaciones de firma"])
PuedeGestionar = Annotated[Principal, Depends(exige_permiso("profesional.gestionar"))]
PuedeFirmar = Annotated[Principal, Depends(exige_permiso("receta.crear", "receta.confirmar"))]


class DelegacionNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delegante_id: uuid.UUID
    delegado_id: uuid.UUID
    vigente_desde: datetime
    vigente_hasta: datetime
    motivo: Annotated[str, Field(min_length=5, max_length=500)]

    @model_validator(mode="after")
    def coherente(self) -> DelegacionNueva:
        if self.delegante_id == self.delegado_id:
            raise ValueError("Un profesional no se delega la firma a si mismo.")
        if self.vigente_hasta <= self.vigente_desde:
            raise ValueError("La vigencia debe terminar despues de empezar.")
        if self.vigente_desde.tzinfo is None or self.vigente_hasta.tzinfo is None:
            raise ValueError("Las fechas deben incluir zona horaria.")
        return self


class DelegacionSalida(BaseModel):
    id: uuid.UUID
    delegante_id: uuid.UUID
    delegado_id: uuid.UUID
    vigente_desde: datetime
    vigente_hasta: datetime
    motivo: str
    revocada_en: datetime | None
    vigente: bool


def _salida(fila: DelegacionFirma, ahora: datetime) -> DelegacionSalida:
    return DelegacionSalida(
        id=fila.id,
        delegante_id=fila.delegante_id,
        delegado_id=fila.delegado_id,
        vigente_desde=fila.vigente_desde,
        vigente_hasta=fila.vigente_hasta,
        motivo=fila.motivo,
        revocada_en=fila.revocada_en,
        vigente=fila.revocada_en is None and fila.vigente_desde <= ahora < fila.vigente_hasta,
    )


@enrutador.get("", response_model=list[DelegacionSalida], summary="Delegaciones de la clinica")
async def listar(
    principal: PuedeGestionar, sesion: Sesion, reloj: RelojActual
) -> list[DelegacionSalida]:
    filas = (
        await sesion.execute(
            select(DelegacionFirma)
            .where(DelegacionFirma.clinica_id == principal.clinica_id)
            .order_by(DelegacionFirma.creado_en.desc())
            .limit(200)
        )
    ).scalars()
    return [_salida(fila, reloj.ahora()) for fila in filas]


@enrutador.get("/mias", response_model=list[DelegacionSalida], summary="Por quien puedo firmar")
async def mias(
    principal: PuedeFirmar, sesion: Sesion, reloj: RelojActual
) -> list[DelegacionSalida]:
    if principal.profesional_id is None:
        return []
    ahora = reloj.ahora()
    filas = (
        await sesion.execute(
            select(DelegacionFirma).where(
                DelegacionFirma.clinica_id == principal.clinica_id,
                or_(
                    DelegacionFirma.delegado_id == principal.profesional_id,
                    DelegacionFirma.delegante_id == principal.profesional_id,
                ),
                DelegacionFirma.revocada_en.is_(None),
                DelegacionFirma.vigente_hasta > ahora,
            )
        )
    ).scalars()
    return [_salida(fila, ahora) for fila in filas]


@enrutador.post("", response_model=DelegacionSalida, status_code=status.HTTP_201_CREATED)
async def crear(
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    datos: DelegacionNueva,
) -> DelegacionSalida:
    ids = {datos.delegante_id, datos.delegado_id}
    encontrados = set(
        (
            await sesion.execute(
                select(Profesional.id).where(
                    Profesional.id.in_(ids),
                    Profesional.clinica_id == principal.clinica_id,
                    Profesional.anulado_en.is_(None),
                )
            )
        ).scalars()
    )
    if encontrados != ids:
        raise RecursoNoEncontrado("Uno de los profesionales no existe en esta clinica.")
    fila = DelegacionFirma(
        clinica_id=principal.clinica_id,
        delegante_id=datos.delegante_id,
        delegado_id=datos.delegado_id,
        vigente_desde=datos.vigente_desde,
        vigente_hasta=datos.vigente_hasta,
        motivo=datos.motivo.strip(),
        creado_por=principal.actor_id,
    )
    sesion.add(fila)
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.DELEGACION_FIRMA_CREADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="delegacion_firma",
                entidad_id=fila.id,
                delegante=str(fila.delegante_id),
                delegado=str(fila.delegado_id),
                motivo=fila.motivo,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila, reloj.ahora())


@enrutador.post("/{delegacion_id}/revocacion", response_model=DelegacionSalida)
async def revocar(
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    delegacion_id: Annotated[uuid.UUID, Path()],
) -> DelegacionSalida:
    fila = (
        await sesion.execute(
            select(DelegacionFirma).where(
                DelegacionFirma.id == delegacion_id,
                DelegacionFirma.clinica_id == principal.clinica_id,
            )
        )
    ).scalar_one_or_none()
    if fila is None:
        raise RecursoNoEncontrado("La delegacion no existe.")
    if fila.revocada_en is not None:
        raise ConflictoEstado("La delegacion ya estaba revocada.")
    ahora = reloj.ahora()
    if fila.vigente_hasta <= ahora:
        raise DatosInvalidos("La delegacion ya vencio.")
    fila.revocada_en = ahora
    fila.revocada_por = principal.actor_id
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.DELEGACION_FIRMA_REVOCADA,
                principal=principal,
                ahora=ahora,
                entidad_tipo="delegacion_firma",
                entidad_id=fila.id,
            )
        ]
    )
    await sesion.commit()
    return _salida(fila, ahora)


__all__ = ["enrutador"]
