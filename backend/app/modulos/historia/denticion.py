"""Edades con las que se propone la dentición inicial del odontograma.

Igual que el software odontológico del mercado (SoftDent, Sensei,
MacPractice, Dentally), el odontograma de un paciente sin registro previo se
abre con una dentición propuesta por edad, y después el profesional la cambia a
mano. Cada clínica decide los cortes: una odontopediatría puede pasar a
permanente a los 12 y otra a los 14.

Es un valor por omisión de la plantilla, **no** un dato clínico: no se escribe
en la historia hasta que el profesional crea el odontograma, y la versión
guardada siempre prevalece (ADR-0026).

Se guarda en `configuracion_clinica` con la clave ``denticion_por_edad`` y el
mismo versionado que el resto: cambiarla deja la versión anterior.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Self

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import ConfiguracionClinica
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import DatosInvalidos

CLAVE = "denticion_por_edad"

# Cortes por omisión: < 6 temporal, 6 a 12 mixta, desde 13 permanente.
EDAD_MIXTA = 6
EDAD_PERMANENTE = 13
EDAD_MINIMA = 1
EDAD_MAXIMA = 21


class DenticionPorEdad(BaseModel):
    """Desde qué edad (años cumplidos) se propone mixta y desde cuál permanente."""

    edad_mixta: int = Field(ge=EDAD_MINIMA, le=EDAD_MAXIMA)
    edad_permanente: int = Field(ge=EDAD_MINIMA, le=EDAD_MAXIMA)

    @model_validator(mode="after")
    def _ordenadas(self) -> Self:
        if self.edad_mixta >= self.edad_permanente:
            raise ValueError("La edad de dentición mixta debe ser menor que la permanente.")
        return self


class CambioDenticion(DenticionPorEdad):
    motivo: str = Field(min_length=5, max_length=300)


POR_OMISION = DenticionPorEdad(edad_mixta=EDAD_MIXTA, edad_permanente=EDAD_PERMANENTE)


async def _vigente(sesion: AsyncSession, clinica_id: uuid.UUID) -> ConfiguracionClinica | None:
    return (
        await sesion.execute(
            select(ConfiguracionClinica).where(
                ConfiguracionClinica.clinica_id == clinica_id,
                ConfiguracionClinica.clave == CLAVE,
                ConfiguracionClinica.vigente.is_(True),
            )
        )
    ).scalar_one_or_none()


async def denticion_de_clinica(sesion: AsyncSession, clinica_id: uuid.UUID) -> DenticionPorEdad:
    """Cortes vigentes; un valor guardado que ya no valida vuelve a los de omisión."""
    fila = await _vigente(sesion, clinica_id)
    if fila is None:
        return POR_OMISION
    try:
        return DenticionPorEdad.model_validate(fila.valor)
    except ValueError:
        return POR_OMISION


def _clinica(principal: Principal) -> uuid.UUID:
    if principal.clinica_id is None:
        raise DatosInvalidos("La sesión no pertenece a una clínica.")
    return principal.clinica_id


# ---------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------
enrutador = APIRouter(tags=["historia clinica"])

# Lee quien usa el odontograma y quien configura los cortes en Catálogo.
PuedeVerCortes = Annotated[
    Principal, Depends(exige_permiso("odontograma.leer", "especialidad.gestionar"))
]
PuedeGestionar = Annotated[Principal, Depends(exige_permiso("especialidad.gestionar"))]


@enrutador.get("/historia/denticion-por-edad", response_model=DenticionPorEdad)
async def ver_denticion(principal: PuedeVerCortes, sesion: Sesion) -> DenticionPorEdad:
    """Cortes de edad de la clínica de quien pregunta. No contiene datos clínicos."""
    return await denticion_de_clinica(sesion, _clinica(principal))


@enrutador.put("/catalogo/denticion-por-edad", response_model=DenticionPorEdad)
async def cambiar_denticion(
    principal: PuedeGestionar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    cambio: CambioDenticion,
) -> DenticionPorEdad:
    clinica_id = _clinica(principal)
    nuevo = DenticionPorEdad(edad_mixta=cambio.edad_mixta, edad_permanente=cambio.edad_permanente)
    actual = await _vigente(sesion, clinica_id)
    version = 1
    if actual is not None:
        version = actual.version + 1
        await sesion.execute(
            update(ConfiguracionClinica)
            .where(ConfiguracionClinica.id == actual.id)
            .values(vigente=False)
        )
        await sesion.flush()
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica_id,
            clave=CLAVE,
            valor=nuevo.model_dump(),
            version=version,
            vigente=True,
            creado_por=principal.actor_id,
        )
    )
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.DENTICION_POR_EDAD_CAMBIADA,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="clinica",
                entidad_id=clinica_id,
                motivo=cambio.motivo,
                **nuevo.model_dump(),
            )
        ]
    )
    await sesion.commit()
    return nuevo


__all__ = [
    "CLAVE",
    "POR_OMISION",
    "DenticionPorEdad",
    "denticion_de_clinica",
    "enrutador",
]
