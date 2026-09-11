"""Rutas de autenticacion.

Sin logica de negocio y sin SQL: validan la entrada, invocan el servicio,
persisten la auditoria que este devuelve y confirman la transaccion.

Por que la transaccion se confirma aqui y no en el servicio
-----------------------------------------------------------
El servicio devuelve las entradas de auditoria en lugar de escribirlas. Esta
capa las escribe y confirma todo junto. Asi, el cambio de estado (una sesion
nueva, un contador de intentos incrementado) y el registro de que ocurrio se
confirman en la misma unidad: no puede quedar uno sin el otro.

El caso incomodo es el del intento fallido: el contador de intentos se
incrementa y acto seguido el servicio lanza `CredencialesInvalidas`. Si esa
excepcion deshiciera la transaccion, el contador volveria a cero y el bloqueo
por fuerza bruta no se activaria nunca. Por eso los fallos de credenciales se
confirman explicitamente antes de propagarse.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.modulos.usuarios.esquemas import (
    PeticionCierreSesion,
    PeticionInicioSesion,
    PeticionRefresco,
    RespuestaIdentidad,
    RespuestaTokens,
    ResumenAmbito,
)
from app.modulos.usuarios.servicios import ParTokens
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    Limitador,
    PrincipalActual,
    ServicioAuth,
    Sesion,
)
from app.nucleo.errores import (
    CredencialesInvalidas,
    CuentaBloqueada,
    RecursoNoEncontrado,
    SegundoFactorInvalido,
    SegundoFactorRequerido,
    TokenInvalido,
)

enrutador = APIRouter(prefix="/autenticacion", tags=["autenticacion"])


def _ip(peticion: Request) -> str | None:
    return peticion.client.host if peticion.client else None


def _agente(peticion: Request) -> str | None:
    # Se acota: el encabezado llega sin validar y termina en una columna de
    # 512 caracteres y en los registros.
    agente = peticion.headers.get("User-Agent")
    return agente[:512] if agente else None


def _a_respuesta(tokens: ParTokens) -> RespuestaTokens:
    return RespuestaTokens(
        token_acceso=tokens.token_acceso,
        token_refresco=tokens.token_refresco,
        expira_en=tokens.expira_en,
        requiere_segundo_factor=tokens.requiere_segundo_factor,
    )


@enrutador.post(
    "/sesion",
    response_model=RespuestaTokens,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesion",
    responses={
        401: {"description": "Credenciales invalidas"},
        423: {"description": "Cuenta bloqueada temporalmente"},
        429: {"description": "Demasiados intentos"},
    },
)
async def iniciar_sesion(
    peticion: Request,
    datos: PeticionInicioSesion,
    sesion: Sesion,
    servicio: ServicioAuth,
    auditor: Auditor,
    limitador: Limitador,
    configuracion: ConfiguracionActual,
) -> RespuestaTokens:
    """Autentica y emite un par de tokens.

    El limite de intentos se aplica por origen **y** por cuenta. Solo por
    cuenta, un atacante prueba una contrasena en mil cuentas distintas sin
    activar ningun bloqueo; solo por origen, se evade con direcciones
    rotatorias.

    Falla cerrado: si el contador no esta disponible, se deniega en lugar de
    dejar el login sin limite (ver `app/nucleo/limite_tasa.py`).
    """
    origen = _ip(peticion) or "desconocido"
    await limitador.exigir(
        f"login:ip:{origen}",
        limite=configuracion.limite_login_por_minuto,
        fallar_cerrado=True,
    )
    await limitador.exigir(
        f"login:cuenta:{datos.clinica_id}:{datos.correo.lower()}",
        limite=configuracion.limite_login_por_minuto,
        fallar_cerrado=True,
    )

    try:
        resultado = await servicio.iniciar_sesion(
            correo=datos.correo,
            contrasena=datos.contrasena,
            clinica_id=datos.clinica_id,
            ip=_ip(peticion),
            agente_usuario=_agente(peticion),
            codigo_2fa=datos.codigo_2fa,
        )
    except (
        CredencialesInvalidas,
        CuentaBloqueada,
        SegundoFactorRequerido,
        SegundoFactorInvalido,
    ):
        # Ver la nota del encabezado: el contador de intentos y el historial
        # de accesos ya estan escritos en la sesion, y deshacerlos vaciaria
        # el bloqueo por fuerza bruta.
        await sesion.commit()
        raise

    if resultado.tokens is None:  # pragma: sin cobertura - iniciar_sesion siempre emite o lanza
        raise CredencialesInvalidas("Correo o contrasena incorrectos.")

    await auditor.registrar(resultado.auditoria)
    await sesion.commit()
    return _a_respuesta(resultado.tokens)


@enrutador.post(
    "/refresco",
    response_model=RespuestaTokens,
    summary="Rotar el token de refresco",
    responses={401: {"description": "Token invalido, caducado o revocado"}},
)
async def refrescar(
    peticion: Request,
    datos: PeticionRefresco,
    sesion: Sesion,
    servicio: ServicioAuth,
    auditor: Auditor,
    limitador: Limitador,
    configuracion: ConfiguracionActual,
) -> RespuestaTokens:
    """Emite un par nuevo y anula el presentado.

    Si el refresco ya se habia usado, hay dos copias circulando. No se puede
    saber cual es la legitima, asi que se revoca la familia completa y ambas
    partes tienen que volver a iniciar sesion. Ese caso devuelve 401, no un
    par nuevo.
    """
    origen = _ip(peticion) or "desconocido"
    await limitador.exigir(
        f"refresco:ip:{origen}",
        limite=configuracion.limite_peticiones_por_minuto,
        fallar_cerrado=True,
    )

    resultado = await servicio.refrescar_sesion(
        token_refresco=datos.token_refresco,
        ip=_ip(peticion),
        agente_usuario=_agente(peticion),
    )

    # La auditoria se escribe en ambos casos: tanto la rotacion correcta como
    # la deteccion de reutilizacion, que es justo la que hay que conservar.
    await auditor.registrar(resultado.auditoria)
    await sesion.commit()

    if resultado.tokens is None:
        raise TokenInvalido(
            "La sesion fue revocada por seguridad: el token de refresco ya "
            "habia sido utilizado. Inicie sesion de nuevo."
        )
    return _a_respuesta(resultado.tokens)


@enrutador.post(
    "/cierre",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesion",
)
async def cerrar_sesion(
    datos: PeticionCierreSesion,
    sesion: Sesion,
    servicio: ServicioAuth,
    auditor: Auditor,
) -> Response:
    """Revoca la sesion presentada, u opcionalmente toda su familia.

    No exige token de acceso valido: cerrar sesion tiene que funcionar
    tambien cuando el de acceso ya caduco, que es el caso mas comun. La
    autorizacion la da el propio refresco, que es un secreto.

    Cerrar una sesion que no consta devuelve 204 igualmente: el resultado
    deseado -- que ese token no sirva -- ya se cumple, y distinguirlo
    permitiria comprobar si un token robado sigue vivo.
    """
    entradas = await servicio.cerrar_sesion(
        token_refresco=datos.token_refresco,
        revocar_familia=datos.todos_los_dispositivos,
    )
    await auditor.registrar(entradas)
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@enrutador.get(
    "/yo",
    response_model=RespuestaIdentidad,
    summary="Identidad y permisos del usuario autenticado",
    responses={401: {"description": "No autenticado"}},
)
async def identidad(
    principal: PrincipalActual,
    servicio: ServicioAuth,
) -> RespuestaIdentidad:
    """Devuelve quien es el usuario y que puede hacer.

    Los permisos salen de la base de datos en el momento de la llamada, no
    del token: la interfaz refleja el estado real aunque el token se emitiera
    antes de un cambio de rol.
    """
    if principal.actor_id is None:  # pragma: sin cobertura - el principal de API siempre lo tiene
        raise RecursoNoEncontrado("No se pudo resolver el usuario de la sesion.")

    usuario = await servicio.cargar_usuario(principal.actor_id)
    if usuario is None:  # pragma: sin cobertura - resolver_principal ya lo habria rechazado
        raise RecursoNoEncontrado("No se pudo resolver el usuario de la sesion.")

    return RespuestaIdentidad(
        usuario_id=usuario.id,
        correo=usuario.correo,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        clinica_id=principal.clinica_id,
        roles=sorted(principal.roles),
        permisos=sorted(principal.permisos),
        ambito=_resumir_ambito(principal),
        requiere_segundo_factor=principal.requiere_segundo_factor,
        segundo_factor_cumplido=principal.segundo_factor_cumplido,
        dosfa_habilitado=usuario.dosfa_habilitado,
        debe_cambiar_contrasena=usuario.debe_cambiar_contrasena,
        ultimo_acceso_en=usuario.ultimo_acceso_en,
    )


def _resumir_ambito(principal: Principal) -> ResumenAmbito:
    ambito = principal.ambito
    return ResumenAmbito(
        clinica_id=ambito.clinica_id,
        sedes=sorted(ambito.sedes),
        todas_las_sedes=ambito.todas_las_sedes,
        especialidades=sorted(ambito.especialidades),
        todas_las_especialidades=ambito.todas_las_especialidades,
        profesionales=sorted(ambito.profesionales),
        todos_los_profesionales=ambito.todos_los_profesionales,
        # La lista de pacientes concretos puede tener miles de elementos y no
        # sirve de nada en la interfaz; solo se expone el comodin.
        todos_los_pacientes=ambito.todos_los_pacientes,
        nivel_maximo=ambito.nivel_maximo.value,
    )


__all__ = ["enrutador"]
