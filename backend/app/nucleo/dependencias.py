"""Dependencias de FastAPI.

Aqui se resuelve, por peticion: la sesion de base de datos, el reloj, el
principal que hace la peticion y el permiso que el endpoint exige.

Tres decisiones que conviene no deshacer
----------------------------------------
**Los objetos de larga vida cuelgan de `app.state`, no de variables de
modulo.** Un motor de base de datos en una variable global hace imposible
levantar dos aplicaciones en el mismo proceso, que es justo lo que hace la
suite de API. Con `app.state` cada aplicacion tiene los suyos.

**`exige_permiso` comprueba el permiso, y ademas el segundo factor.** Tener
el permiso no basta si el rol exige 2FA y la sesion todavia no lo cumplio: el
token se emite igualmente para que el cliente pueda pedir el codigo, y es
aqui donde se le impide operar con el.

**El permiso no es toda la autorizacion.** Esta capa responde «esta persona
puede ejecutar esta operacion»; el repositorio responde ademas «sobre estos
datos», aplicando el filtro de ambito. Un endpoint que solo declare el
permiso y no filtre por ambito tiene un IDOR, y ninguna de las dos
comprobaciones sustituye a la otra.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.repositorio import RepositorioAgenda
from app.modulos.agenda.servicios import ServicioAgenda
from app.modulos.auditoria.repositorio import RepositorioAuditoria
from app.modulos.historia.repositorio import RepositorioHistoria
from app.modulos.historia.servicios import ServicioHistoria
from app.modulos.organizacion.repositorio import RepositorioCatalogo
from app.modulos.pacientes.repositorio import RepositorioPacientes
from app.modulos.usuarios.servicios import ServicioAutenticacion
from app.nucleo.auditoria import AccionAuditada, ResultadoAuditoria, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.bd import GestorBaseDatos
from app.nucleo.configuracion import Configuracion
from app.nucleo.errores import (
    NoAutenticado,
    PermisoDenegado,
    SegundoFactorRequerido,
    TokenInvalido,
    TokenRevocado,
)
from app.nucleo.limite_tasa import LimitadorTasa
from app.nucleo.registro import obtener_logger
from app.nucleo.reloj import Reloj
from app.nucleo.seguridad import CifradorDatos

CABECERA_AUTORIZACION = "Authorization"
PREFIJO_BEARER = "Bearer "

_logger = obtener_logger(__name__)


# ---------------------------------------------------------------------------
#  Objetos de larga vida
# ---------------------------------------------------------------------------
def obtener_configuracion(peticion: Request) -> Configuracion:
    configuracion: Configuracion = peticion.app.state.configuracion
    return configuracion


def obtener_reloj(peticion: Request) -> Reloj:
    reloj: Reloj = peticion.app.state.reloj
    return reloj


def obtener_gestor_bd(peticion: Request) -> GestorBaseDatos:
    gestor: GestorBaseDatos = peticion.app.state.gestor_bd
    return gestor


def obtener_cifrador(peticion: Request) -> CifradorDatos:
    cifrador: CifradorDatos = peticion.app.state.cifrador
    return cifrador


def obtener_limitador(peticion: Request) -> LimitadorTasa:
    limitador: LimitadorTasa = peticion.app.state.limitador
    return limitador


async def obtener_sesion(
    gestor: Annotated[GestorBaseDatos, Depends(obtener_gestor_bd)],
) -> AsyncIterator[AsyncSession]:
    async for sesion in gestor.sesion():
        yield sesion


Sesion = Annotated[AsyncSession, Depends(obtener_sesion)]
ConfiguracionActual = Annotated[Configuracion, Depends(obtener_configuracion)]
RelojActual = Annotated[Reloj, Depends(obtener_reloj)]
Limitador = Annotated[LimitadorTasa, Depends(obtener_limitador)]


# ---------------------------------------------------------------------------
#  Servicios
# ---------------------------------------------------------------------------
def obtener_servicio_autenticacion(
    sesion: Sesion,
    reloj: RelojActual,
    configuracion: ConfiguracionActual,
    cifrador: Annotated[CifradorDatos, Depends(obtener_cifrador)],
) -> ServicioAutenticacion:
    return ServicioAutenticacion(
        sesion,
        reloj,
        clave_secreta=configuracion.clave_secreta.get_secret_value(),
        algoritmo=configuracion.algoritmo_jwt,
        minutos_token_acceso=configuracion.minutos_token_acceso,
        dias_token_refresco=configuracion.dias_token_refresco,
        max_intentos_login=configuracion.max_intentos_login,
        minutos_bloqueo_login=configuracion.minutos_bloqueo_login,
        roles_con_2fa=frozenset(configuracion.lista_roles_con_2fa),
        cifrador=cifrador,
    )


def obtener_repositorio_auditoria(sesion: Sesion) -> RepositorioAuditoria:
    return RepositorioAuditoria(sesion)


def obtener_repositorio_agenda(sesion: Sesion) -> RepositorioAgenda:
    return RepositorioAgenda(sesion)


def obtener_servicio_agenda(
    sesion: Sesion,
    reloj: RelojActual,
    repositorio: Annotated[RepositorioAgenda, Depends(obtener_repositorio_agenda)],
    configuracion: ConfiguracionActual,
) -> ServicioAgenda:
    return ServicioAgenda(
        sesion,
        repositorio,
        reloj,
        minutos_expiracion_held=configuracion.minutos_expiracion_held,
    )


def obtener_repositorio_historia(sesion: Sesion) -> RepositorioHistoria:
    return RepositorioHistoria(sesion)


def obtener_servicio_historia(
    sesion: Sesion,
    reloj: RelojActual,
    repositorio: Annotated[RepositorioHistoria, Depends(obtener_repositorio_historia)],
    configuracion: ConfiguracionActual,
) -> ServicioHistoria:
    return ServicioHistoria(
        sesion,
        repositorio,
        reloj,
        zona_por_defecto=configuracion.zona_horaria_por_defecto,
    )


def obtener_repositorio_catalogo(sesion: Sesion) -> RepositorioCatalogo:
    return RepositorioCatalogo(sesion)


def obtener_repositorio_pacientes(sesion: Sesion) -> RepositorioPacientes:
    return RepositorioPacientes(sesion)


ServicioAuth = Annotated[ServicioAutenticacion, Depends(obtener_servicio_autenticacion)]
RepoCatalogo = Annotated[RepositorioCatalogo, Depends(obtener_repositorio_catalogo)]
RepoPacientes = Annotated[RepositorioPacientes, Depends(obtener_repositorio_pacientes)]
RepoHistoria = Annotated[RepositorioHistoria, Depends(obtener_repositorio_historia)]
ServicioDeHistoria = Annotated[ServicioHistoria, Depends(obtener_servicio_historia)]
RepoAgenda = Annotated[RepositorioAgenda, Depends(obtener_repositorio_agenda)]
ServicioDeAgenda = Annotated[ServicioAgenda, Depends(obtener_servicio_agenda)]
Auditor = Annotated[RepositorioAuditoria, Depends(obtener_repositorio_auditoria)]


# ---------------------------------------------------------------------------
#  Identidad
# ---------------------------------------------------------------------------
def extraer_token(peticion: Request) -> str:
    """Saca el token del encabezado `Authorization`.

    Se exige el esquema `Bearer` exacto. Aceptar el token sin esquema, o con
    otro esquema, haria que un `Authorization: Basic ...` de otro sistema se
    interpretara como token de este.
    """
    cabecera = peticion.headers.get(CABECERA_AUTORIZACION)
    if not cabecera:
        raise NoAutenticado("Falta la cabecera de autorizacion.")
    if not cabecera.startswith(PREFIJO_BEARER):
        raise NoAutenticado("El esquema de autorizacion debe ser Bearer.")

    token = cabecera[len(PREFIJO_BEARER) :].strip()
    if not token:
        raise NoAutenticado("El token esta vacio.")
    return token


async def obtener_principal(
    peticion: Request,
    servicio: ServicioAuth,
) -> Principal:
    """Resuelve quien hace la peticion.

    Los permisos se leen de la base de datos en cada peticion, no del token
    (ver `ServicioAutenticacion`). Cuesta una consulta y es lo que hace que
    revocar un permiso surta efecto de inmediato.
    """
    token = extraer_token(peticion)
    try:
        principal = await servicio.resolver_principal_desde_token(token)
    except (TokenInvalido, TokenRevocado):
        # Se propaga tal cual: ambos son 401 y sus mensajes no distinguen
        # entre "token manipulado" y "cuenta desactivada", que es lo
        # deseable de cara a quien presenta el token.
        raise

    # El identificador de correlacion se enlaza aqui para que toda linea de
    # registro y toda entrada de auditoria de esta peticion lo lleven.
    peticion.state.principal = principal
    return principal


PrincipalActual = Annotated[Principal, Depends(obtener_principal)]


# ---------------------------------------------------------------------------
#  Autorizacion
# ---------------------------------------------------------------------------
def exige_permiso(
    *codigos: str,
    exigir_todos: bool = False,
) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Dependencia que exige uno de los permisos indicados.

    Con varios codigos, basta con tener uno (`exigir_todos=False`, el valor
    por omision): es el caso de un endpoint al que llegan roles distintos por
    caminos distintos. Con `exigir_todos=True` hacen falta todos.

    Un acceso denegado se registra en auditoria antes de rechazarse. Sin ese
    registro, un intento sistematico de acceder a datos ajenos seria
    invisible: el atacante recibe un 403 y no queda rastro de que lo intento.
    """
    if not codigos:
        raise ValueError("exige_permiso necesita al menos un codigo de permiso.")

    async def dependencia(
        peticion: Request,
        principal: PrincipalActual,
        gestor: Annotated[GestorBaseDatos, Depends(obtener_gestor_bd)],
    ) -> Principal:
        concedidos = [c for c in codigos if principal.tiene_permiso(c)]
        suficiente = len(concedidos) == len(codigos) if exigir_todos else bool(concedidos)

        if not suficiente:
            await _auditar_denegacion(
                peticion,
                principal,
                gestor,
                motivo=f"Permiso requerido: {', '.join(codigos)}",
            )
            raise PermisoDenegado(
                "No tiene permiso para realizar esta operacion.",
                detalles={"permiso_requerido": list(codigos)},
            )

        if not principal.cumple_segundo_factor:
            # El token se emitio, pero la sesion no ha completado el segundo
            # factor que su rol exige. Tenerlo todo menos eso no da acceso.
            await _auditar_denegacion(
                peticion,
                principal,
                gestor,
                motivo="Segundo factor pendiente",
            )
            raise SegundoFactorRequerido(
                "Su rol exige segundo factor. Complete la verificacion para continuar."
            )

        return principal

    return dependencia


async def _auditar_denegacion(
    peticion: Request,
    principal: Principal,
    gestor: GestorBaseDatos,
    *,
    motivo: str,
) -> None:
    """Deja constancia del intento denegado, en su propia transaccion.

    Usa una sesion aparte de la de la peticion a proposito. La peticion va a
    terminar con una excepcion, y su transaccion se deshace: si la entrada se
    escribiera ahi, desapareceria justo con el error que la provoco. Un
    registro de seguridad que solo sobrevive cuando no hace falta no sirve
    para detectar nada.

    Un fallo al auditar no debe convertir un 403 en un 500: se registra y se
    sigue, porque la denegacion en si ya se esta aplicando.
    """
    entrada = construir_entrada(
        accion=AccionAuditada.PERMISO_DENEGADO,
        principal=principal,
        ahora=peticion.app.state.reloj.ahora(),
        resultado=ResultadoAuditoria.DENEGADO,
        ip=peticion.client.host if peticion.client else None,
        correlacion_id=getattr(peticion.state, "correlacion_id", None),
        motivo=motivo,
        ruta=peticion.url.path,
        metodo=peticion.method,
    )
    try:
        async for sesion in gestor.sesion():
            await RepositorioAuditoria(sesion).registrar([entrada])
            await sesion.commit()
    except Exception:
        _logger.exception(
            "auditoria.denegacion.no_registrada",
            ruta=peticion.url.path,
            actor_id=str(principal.actor_id) if principal.actor_id else None,
        )


__all__ = [
    "Auditor",
    "ConfiguracionActual",
    "Limitador",
    "PrincipalActual",
    "RelojActual",
    "RepoAgenda",
    "RepoCatalogo",
    "RepoHistoria",
    "RepoPacientes",
    "ServicioAuth",
    "ServicioDeAgenda",
    "ServicioDeHistoria",
    "Sesion",
    "exige_permiso",
    "extraer_token",
    "obtener_cifrador",
    "obtener_configuracion",
    "obtener_gestor_bd",
    "obtener_limitador",
    "obtener_principal",
    "obtener_reloj",
    "obtener_repositorio_agenda",
    "obtener_repositorio_auditoria",
    "obtener_repositorio_catalogo",
    "obtener_repositorio_historia",
    "obtener_repositorio_pacientes",
    "obtener_servicio_agenda",
    "obtener_servicio_autenticacion",
    "obtener_servicio_historia",
    "obtener_sesion",
]
