"""Rutas del centro de ayuda.

`GET /ayuda/manuales` devuelve los manuales de los roles vigentes de quien
consulta. No acepta parametros: no hay forma de pedir el manual de otro rol
ni de otra clinica, porque el manual sale de la sesion y no de la peticion.

Autorizacion: personal con sesion (nunca el agente) y con el segundo factor
cumplido si su rol lo exige. No hace falta un permiso propio: el manual es
contenido de ayuda (N0) filtrado por los permisos que la persona ya tiene, y
exigir un permiso nuevo dejaria sin manual a los roles personalizados que no
lo incluyeran. Leerlo no es una lectura de datos clinicos ni una escritura,
asi que no se audita (CLAUDE.md, seccion 5).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.modulos.ayuda.esquemas import RespuestaManuales
from app.modulos.ayuda.repositorio import RepositorioAyuda
from app.modulos.ayuda.servicios import construir_manuales
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import PrincipalActual, Sesion
from app.nucleo.errores import PermisoDenegado, SegundoFactorRequerido

enrutador = APIRouter(prefix="/ayuda", tags=["ayuda"])


def _personal_verificado(principal: PrincipalActual) -> Principal:
    if principal.es_agente or principal.actor_id is None:
        raise PermisoDenegado("La ayuda es para el personal de la clínica.")
    if not principal.cumple_segundo_factor:
        raise SegundoFactorRequerido(
            "Su rol exige segundo factor. Complete la verificación para continuar."
        )
    return principal


PersonalVerificado = Annotated[Principal, Depends(_personal_verificado)]


@enrutador.get(
    "/manuales",
    response_model=RespuestaManuales,
    summary="Manuales de ayuda de los roles de la sesión",
    responses={
        401: {"description": "No autenticado"},
        403: {"description": "Segundo factor pendiente o principal que no es personal"},
    },
)
async def manuales(principal: PersonalVerificado, sesion: Sesion) -> RespuestaManuales:
    """Un manual por cada rol vigente, con solo las tareas que ese rol puede hacer."""
    roles = await RepositorioAyuda(sesion).roles_del_principal(principal)
    return RespuestaManuales(manuales=construir_manuales(roles, principal))
