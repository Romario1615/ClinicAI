"""Rutas de automatizaciones: ver el catálogo y encender o apagar flujos."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from app.modulos.automatizaciones import servicios
from app.modulos.automatizaciones.catalogo import FLUJOS, Flujo
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import DatosInvalidos

enrutador = APIRouter(prefix="/automatizaciones", tags=["automatizaciones"])
PuedeVer = Annotated[Principal, Depends(exige_permiso("configuracion.escribir", "auditoria.leer"))]
PuedeCambiar = Annotated[Principal, Depends(exige_permiso("configuracion.escribir"))]


class AutomatizacionSalida(BaseModel):
    codigo: str
    nombre: str
    fase: str
    disparador: str
    accion: str
    canal: str
    quien_ve: list[str]
    quien_interviene: list[str]
    obligatorio: bool
    nota: str | None
    activo: bool
    ejecuciones_30_dias: int


class CambioAutomatizacion(BaseModel):
    activo: bool
    motivo: str = Field(min_length=5, max_length=300)


def _salida(flujo: Flujo, activo: bool, ejecuciones: int) -> AutomatizacionSalida:
    return AutomatizacionSalida(
        codigo=flujo.codigo,
        nombre=flujo.nombre,
        fase=flujo.fase.value,
        disparador=flujo.disparador,
        accion=flujo.accion,
        canal=flujo.canal,
        quien_ve=list(flujo.quien_ve),
        quien_interviene=list(flujo.quien_interviene),
        obligatorio=flujo.obligatorio,
        nota=flujo.nota,
        activo=activo,
        ejecuciones_30_dias=ejecuciones,
    )


@enrutador.get("", response_model=list[AutomatizacionSalida])
async def listar(principal: PuedeVer, sesion: Sesion) -> list[AutomatizacionSalida]:
    if principal.clinica_id is None:
        raise DatosInvalidos("La sesión no pertenece a una clínica.")
    estados = await servicios.estados(sesion, principal.clinica_id)
    ejecuciones = await servicios.ejecuciones_30_dias(sesion, principal.clinica_id)
    return [_salida(f, estados[f.codigo], ejecuciones.get(f.codigo, 0)) for f in FLUJOS]


@enrutador.put("/{codigo}", response_model=AutomatizacionSalida)
async def cambiar(
    principal: PuedeCambiar,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    datos: CambioAutomatizacion,
    codigo: Annotated[str, Path(max_length=64, pattern=r"^[a-z_]+$")],
) -> AutomatizacionSalida:
    flujo, entrada = await servicios.cambiar(
        sesion, principal, reloj, codigo, datos.activo, datos.motivo.strip()
    )
    await auditor.registrar([entrada])
    await sesion.commit()
    ejecuciones = (
        await servicios.ejecuciones_30_dias(sesion, principal.clinica_id)
        if principal.clinica_id
        else {}
    )
    return _salida(flujo, datos.activo, ejecuciones.get(codigo, 0))


__all__ = ["enrutador"]
