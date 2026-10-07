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

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.modulos.usuarios import administracion
from app.modulos.usuarios.esquemas import (
    ActualizarEstadoUsuario,
    ActualizarRolesUsuario,
    CambioContrasena,
    CrearRolClinica,
    CrearUsuarioClinica,
    EditarDatosUsuario,
    PermisoDisponible,
    PeticionAccesoLocal,
    PeticionCierreSesion,
    PeticionInicioSesion,
    PeticionRefresco,
    ProfesionalDisponible,
    RespuestaAccesosLocales,
    RespuestaIdentidad,
    RespuestaTokens,
    ResumenAmbito,
    RolDisponible,
    UsuarioAdministrado,
)
from app.modulos.usuarios.modelos import MotivoRevocacion
from app.modulos.usuarios.servicios import ParTokens
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import Principal
from app.nucleo.dependencias import (
    Auditor,
    ConfiguracionActual,
    Limitador,
    PrincipalActual,
    RelojActual,
    ServicioAuth,
    Sesion,
    exige_permiso,
)
from app.nucleo.errores import (
    CredencialesInvalidas,
    CuentaBloqueada,
    PermisoDenegado,
    RecursoNoEncontrado,
    SegundoFactorInvalido,
    SegundoFactorRequerido,
    TokenInvalido,
)

enrutador = APIRouter(prefix="/autenticacion", tags=["autenticacion"])
enrutador_usuarios = APIRouter(prefix="/usuarios", tags=["usuarios y accesos"])
PuedeLeerUsuarios = Annotated[Principal, Depends(exige_permiso("usuario.leer"))]
PuedeCrearUsuarios = Annotated[
    Principal, Depends(exige_permiso("usuario.crear", "rol.asignar", exigir_todos=True))
]
PuedeAsignarRoles = Annotated[Principal, Depends(exige_permiso("rol.asignar"))]
PuedeGestionarCuentas = Annotated[
    Principal, Depends(exige_permiso("usuario.editar", "usuario.desactivar"))
]


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
        f"login:cuenta:{datos.correo.lower()}",
        limite=configuracion.limite_login_por_minuto,
        fallar_cerrado=True,
    )

    try:
        resultado = await servicio.iniciar_sesion(
            correo=datos.correo,
            contrasena=datos.contrasena,
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


@enrutador.get(
    "/accesos-locales",
    response_model=RespuestaAccesosLocales,
    summary="Roles disponibles para acceso local de desarrollo",
)
async def accesos_locales(servicio: ServicioAuth) -> RespuestaAccesosLocales:
    """Expone accesos de datos sinteticos solo en local/desarrollo."""
    nombres = {
        "superadministrador": "Superadministrador",
        "administrador_clinica": "Administración de clínica",
        "recepcion": "Recepción",
        "asistente": "Asistencia clínica",
        "auditor": "Auditoría",
        "profesional": "Profesional de salud",
    }
    roles = await servicio.roles_acceso_local()
    return RespuestaAccesosLocales(
        habilitado=bool(roles),
        roles=[{"codigo": codigo, "nombre": nombres[codigo]} for codigo in roles],
    )


@enrutador.post(
    "/sesion-local",
    response_model=RespuestaTokens,
    summary="Entrar con un rol de datos sinteticos (solo desarrollo)",
    responses={404: {"description": "El acceso local no esta disponible"}},
)
async def iniciar_sesion_local(
    peticion: Request,
    datos: PeticionAccesoLocal,
    sesion: Sesion,
    servicio: ServicioAuth,
    auditor: Auditor,
    limitador: Limitador,
    configuracion: ConfiguracionActual,
) -> RespuestaTokens:
    """Acceso rapido de desarrollo limitado a las cuentas sinteticas.

    El servicio solo permite esta ruta si la configuracion de la app habilita
    local/desarrollo; el rol se resuelve en servidor, nunca llega un user id.
    """
    origen = _ip(peticion) or "desconocido"
    await limitador.exigir(
        f"login-local:ip:{origen}",
        limite=configuracion.limite_login_por_minuto,
        fallar_cerrado=True,
    )
    resultado = await servicio.iniciar_sesion_rol_local(
        codigo_rol=datos.codigo_rol,
        ip=_ip(peticion),
        agente_usuario=_agente(peticion),
    )
    if resultado.tokens is None:  # pragma: sin cobertura - el metodo emite o lanza
        raise CredencialesInvalidas("El acceso local no esta disponible.")
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
        profesional_id=principal.profesional_id,
    )


@enrutador.post(
    "/cambio-contrasena",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la contraseña",
)
async def cambiar_contrasena(
    datos: CambioContrasena,
    principal: PrincipalActual,
    servicio: ServicioAuth,
    sesion: Sesion,
    auditor: Auditor,
) -> Response:
    if principal.actor_id is None:
        raise RecursoNoEncontrado("No se pudo resolver el usuario de la sesion.")
    entrada = await servicio.cambiar_contrasena(
        principal.actor_id, datos.contrasena_actual, datos.contrasena_nueva
    )
    await auditor.registrar([entrada])
    await sesion.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@enrutador_usuarios.get("", response_model=list[UsuarioAdministrado])
async def listar_usuarios(
    principal: PuedeLeerUsuarios, sesion: Sesion
) -> list[UsuarioAdministrado]:
    return await administracion.listar_usuarios(sesion, principal)


@enrutador_usuarios.get("/permisos", response_model=list[PermisoDisponible])
async def listar_permisos(principal: PuedeAsignarRoles, sesion: Sesion) -> list[PermisoDisponible]:
    return await administracion.listar_permisos(sesion, principal)


@enrutador_usuarios.get("/roles", response_model=list[RolDisponible])
async def listar_roles(principal: PuedeLeerUsuarios, sesion: Sesion) -> list[RolDisponible]:
    return await administracion.listar_roles(sesion, principal)


@enrutador_usuarios.get("/profesionales", response_model=list[ProfesionalDisponible])
async def listar_profesionales_asignables(
    principal: PuedeAsignarRoles,
    sesion: Sesion,
    usuario_id: uuid.UUID | None = None,
) -> list[ProfesionalDisponible]:
    return await administracion.listar_profesionales_asignables(sesion, principal, usuario_id)


@enrutador_usuarios.post(
    "/roles", response_model=RolDisponible, status_code=status.HTTP_201_CREATED
)
async def crear_rol(
    datos: CrearRolClinica,
    principal: PuedeAsignarRoles,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> RolDisponible:
    rol = await administracion.crear_rol(sesion, principal, datos)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.ROL_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="rol",
                entidad_id=rol.id,
                codigo_rol=rol.codigo,
                cantidad_permisos=len(rol.permisos),
            )
        ]
    )
    await sesion.commit()
    return rol


@enrutador_usuarios.post(
    "", response_model=UsuarioAdministrado, status_code=status.HTTP_201_CREATED
)
async def crear_usuario(
    datos: CrearUsuarioClinica,
    principal: PuedeCrearUsuarios,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> UsuarioAdministrado:
    usuario = await administracion.crear_usuario(sesion, principal, datos)
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_CREADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario.id,
                roles=usuario.roles,
            )
        ]
    )
    await sesion.commit()
    return usuario


@enrutador_usuarios.put("/{usuario_id}/roles", response_model=UsuarioAdministrado)
async def reemplazar_roles(
    usuario_id: uuid.UUID,
    datos: ActualizarRolesUsuario,
    principal: PuedeAsignarRoles,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
) -> UsuarioAdministrado:
    usuario = await administracion.reemplazar_roles_usuario(
        sesion, principal, usuario_id, datos.roles, datos.profesional_id
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario.id,
                roles=usuario.roles,
            )
        ]
    )
    await sesion.commit()
    return usuario


@enrutador_usuarios.put("/{usuario_id}/estado", response_model=UsuarioAdministrado)
async def cambiar_estado_usuario(
    usuario_id: uuid.UUID,
    datos: ActualizarEstadoUsuario,
    principal: PuedeGestionarCuentas,
    sesion: Sesion,
    servicio: ServicioAuth,
    reloj: RelojActual,
    auditor: Auditor,
) -> UsuarioAdministrado:
    permiso_necesario = "usuario.editar" if datos.activo else "usuario.desactivar"
    if not principal.tiene_permiso(permiso_necesario):
        raise PermisoDenegado("No tiene permiso para cambiar el estado de esta cuenta.")
    usuario = await administracion.cambiar_estado_usuario(
        sesion, principal, usuario_id, datos.activo
    )
    if not datos.activo:
        await servicio.revocar_todas_las_sesiones(
            usuario_id, motivo=MotivoRevocacion.USUARIO_DESACTIVADO
        )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_MODIFICADO
                if datos.activo
                else AccionAuditada.USUARIO_DESACTIVADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario.id,
                activo=datos.activo,
            )
        ]
    )
    await sesion.commit()
    return usuario


@enrutador_usuarios.put("/{usuario_id}/datos", response_model=UsuarioAdministrado)
async def editar_datos_usuario(
    usuario_id: uuid.UUID,
    datos: EditarDatosUsuario,
    principal: Annotated[Principal, Depends(exige_permiso("usuario.editar"))],
    sesion: Sesion,
    servicio: ServicioAuth,
    reloj: RelojActual,
    auditor: Auditor,
) -> UsuarioAdministrado:
    usuario = await administracion.editar_datos_usuario(sesion, principal, usuario_id, datos)
    await servicio.revocar_todas_las_sesiones(
        usuario_id, motivo=MotivoRevocacion.REVOCACION_ADMINISTRATIVA
    )
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_MODIFICADO,
                principal=principal,
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario_id,
                sesiones_revocadas=True,
            )
        ]
    )
    await sesion.commit()
    return usuario


__all__ = ["enrutador", "enrutador_usuarios"]
