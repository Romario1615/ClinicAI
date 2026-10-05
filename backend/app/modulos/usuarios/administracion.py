"""Administracion de usuarios y permisos limitada a la clinica del principal."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.esquemas import (
    CrearRolClinica,
    CrearUsuarioClinica,
    PermisoDisponible,
    ProfesionalDisponible,
    RolDisponible,
    UsuarioAdministrado,
)
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    Permiso,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioRol,
)
from app.nucleo.autorizacion import PERMISOS_SOLO_ASISTENCIALES, Principal, TipoAmbito
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, RecursoNoEncontrado
from app.nucleo.seguridad import hashear_contrasena

DIMENSIONES_CLINICA = (
    TipoAmbito.SEDE.value,
    TipoAmbito.ESPECIALIDAD.value,
    TipoAmbito.PROFESIONAL.value,
    TipoAmbito.PACIENTE.value,
)


async def listar_permisos(sesion: AsyncSession, principal: Principal) -> list[PermisoDisponible]:
    filas = (
        await sesion.execute(
            select(Permiso)
            .where(Permiso.codigo.in_(principal.permisos - PERMISOS_SOLO_ASISTENCIALES))
            .order_by(Permiso.categoria, Permiso.descripcion)
        )
    ).scalars()
    return [
        PermisoDisponible(codigo=f.codigo, descripcion=f.descripcion, categoria=f.categoria)
        for f in filas
    ]


async def listar_roles(sesion: AsyncSession, principal: Principal) -> list[RolDisponible]:
    if principal.clinica_id is None:
        return []
    roles = (
        (
            await sesion.execute(
                select(Rol)
                .where(or_(Rol.clinica_id.is_(None), Rol.clinica_id == principal.clinica_id))
                .order_by(Rol.es_sistema.desc(), Rol.nombre)
            )
        )
        .scalars()
        .all()
    )
    if not roles:
        return []
    permisos_por_rol: dict[uuid.UUID, list[str]] = defaultdict(list)
    filas = await sesion.execute(
        select(RolPermiso.rol_id, Permiso.codigo)
        .join(Permiso, Permiso.id == RolPermiso.permiso_id)
        .where(RolPermiso.rol_id.in_([r.id for r in roles]))
        .order_by(Permiso.codigo)
    )
    for rol_id, codigo in filas:
        permisos_por_rol[rol_id].append(codigo)
    return [
        RolDisponible(
            id=rol.id,
            codigo=rol.codigo,
            nombre=rol.nombre,
            descripcion=rol.descripcion,
            es_sistema=rol.es_sistema,
            permisos=permisos_por_rol[rol.id],
        )
        for rol in roles
        if rol.codigo != "superadministrador"
    ]


async def listar_usuarios(sesion: AsyncSession, principal: Principal) -> list[UsuarioAdministrado]:
    if principal.clinica_id is None:
        return []
    usuarios = (
        (
            await sesion.execute(
                select(Usuario)
                .where(Usuario.clinica_id == principal.clinica_id)
                .order_by(Usuario.apellido, Usuario.nombre)
            )
        )
        .scalars()
        .all()
    )
    if not usuarios:
        return []
    roles_por_usuario: dict[uuid.UUID, list[str]] = defaultdict(list)
    filas = await sesion.execute(
        select(UsuarioRol.usuario_id, Rol.nombre)
        .join(Rol, Rol.id == UsuarioRol.rol_id)
        .where(UsuarioRol.usuario_id.in_([u.id for u in usuarios]))
        .order_by(Rol.nombre)
    )
    for usuario_id, nombre_rol in filas:
        roles_por_usuario[usuario_id].append(nombre_rol)
    filas_profesionales = await sesion.execute(
        select(Profesional.usuario_id, Profesional.id).where(
            Profesional.usuario_id.in_([u.id for u in usuarios])
        )
    )
    profesionales_por_usuario: dict[uuid.UUID | None, uuid.UUID] = dict(
        filas_profesionales.tuples().all()
    )
    return [
        UsuarioAdministrado(
            id=u.id,
            correo=u.correo,
            nombre=u.nombre,
            apellido=u.apellido,
            activo=u.activo,
            roles=roles_por_usuario[u.id],
            profesional_id=profesionales_por_usuario.get(u.id),
            ultimo_acceso_en=u.ultimo_acceso_en,
        )
        for u in usuarios
    ]


async def listar_profesionales_asignables(
    sesion: AsyncSession, principal: Principal, usuario_id: uuid.UUID | None = None
) -> list[ProfesionalDisponible]:
    if principal.clinica_id is None:
        return []
    if usuario_id is not None:
        existente = await sesion.scalar(
            select(Usuario.id).where(
                Usuario.id == usuario_id,
                Usuario.clinica_id == principal.clinica_id,
            )
        )
        if existente is None:
            raise RecursoNoEncontrado("El usuario no existe.")
    profesionales = (
        await sesion.execute(
            select(Profesional)
            .where(
                Profesional.clinica_id == principal.clinica_id,
                Profesional.activo.is_(True),
                Profesional.anulado_en.is_(None),
                or_(
                    Profesional.usuario_id.is_(None),
                    Profesional.usuario_id == usuario_id if usuario_id else false(),
                ),
            )
            .order_by(Profesional.apellido, Profesional.nombre)
        )
    ).scalars()
    return [
        ProfesionalDisponible(id=p.id, nombre=p.nombre, apellido=p.apellido) for p in profesionales
    ]


async def crear_rol(
    sesion: AsyncSession, principal: Principal, datos: CrearRolClinica
) -> RolDisponible:
    if principal.clinica_id is None:
        raise RecursoNoEncontrado("No se encontro la clinica del usuario.")
    codigos = set(datos.permisos)
    if not codigos <= principal.permisos:
        raise DatosInvalidos("Un rol solo puede incluir permisos que quien lo administra ya posee.")
    if codigos & PERMISOS_SOLO_ASISTENCIALES:
        raise DatosInvalidos(
            "Los permisos de historia clinica y prescripcion se asignan mediante el rol profesional."
        )
    existente = await sesion.scalar(
        select(Rol.id).where(
            Rol.clinica_id == principal.clinica_id,
            func.lower(Rol.codigo) == datos.codigo.lower(),
        )
    )
    if existente is not None:
        raise ConflictoEstado("Ya existe un rol con ese codigo en esta clinica.")
    permisos = (
        (await sesion.execute(select(Permiso).where(Permiso.codigo.in_(codigos)))).scalars().all()
    )
    if {p.codigo for p in permisos} != codigos:
        raise DatosInvalidos("La seleccion contiene un permiso que no existe.")
    rol = Rol(
        clinica_id=principal.clinica_id,
        codigo=datos.codigo.lower(),
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        es_sistema=False,
    )
    sesion.add(rol)
    await sesion.flush()
    sesion.add_all([RolPermiso(rol_id=rol.id, permiso_id=p.id) for p in permisos])
    return RolDisponible(
        id=rol.id,
        codigo=rol.codigo,
        nombre=rol.nombre,
        descripcion=rol.descripcion,
        es_sistema=False,
        permisos=sorted(codigos),
    )


async def crear_usuario(
    sesion: AsyncSession, principal: Principal, datos: CrearUsuarioClinica
) -> UsuarioAdministrado:
    if principal.clinica_id is None or principal.actor_id is None:
        raise RecursoNoEncontrado("No se encontro la clinica del usuario.")
    correo = datos.correo.strip().lower()
    existente = await sesion.scalar(select(Usuario.id).where(func.lower(Usuario.correo) == correo))
    if existente is not None:
        raise ConflictoEstado("Ya existe una cuenta con ese correo.")
    roles, permisos_por_rol = await _roles_asignables(
        sesion, principal, datos.roles, datos.profesional_id
    )
    usuario = Usuario(
        clinica_id=principal.clinica_id,
        correo=correo,
        hash_contrasena=hashear_contrasena(datos.contrasena_inicial),
        nombre=datos.nombre,
        apellido=datos.apellido,
        activo=True,
        debe_cambiar_contrasena=True,
    )
    sesion.add(usuario)
    await sesion.flush()
    if datos.profesional_id is not None:
        profesional = await _profesional(sesion, principal, datos.profesional_id)
        if profesional.usuario_id is not None:
            raise ConflictoEstado("Ese profesional ya tiene una cuenta vinculada.")
        profesional.usuario_id = usuario.id
    await _asignar_roles(sesion, principal, usuario, roles, permisos_por_rol, datos.profesional_id)
    return UsuarioAdministrado(
        id=usuario.id,
        correo=usuario.correo,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        activo=usuario.activo,
        roles=[r.nombre for r in roles],
        profesional_id=datos.profesional_id,
        ultimo_acceso_en=None,
    )


async def reemplazar_roles_usuario(
    sesion: AsyncSession,
    principal: Principal,
    usuario_id: uuid.UUID,
    roles_ids: list[uuid.UUID],
    profesional_id: uuid.UUID | None,
) -> UsuarioAdministrado:
    usuario = await sesion.scalar(
        select(Usuario).where(
            Usuario.id == usuario_id,
            Usuario.clinica_id == principal.clinica_id,
        )
    )
    if usuario is None:
        raise RecursoNoEncontrado("El usuario no existe.")
    roles, permisos_por_rol = await _roles_asignables(sesion, principal, roles_ids, profesional_id)
    profesional_actual = await sesion.scalar(
        select(Profesional).where(Profesional.usuario_id == usuario.id)
    )
    if profesional_actual is not None:
        profesional_actual.usuario_id = None
    if profesional_id is not None:
        profesional = await _profesional(sesion, principal, profesional_id)
        if profesional.usuario_id not in (None, usuario.id):
            raise ConflictoEstado("Ese profesional ya tiene una cuenta vinculada.")
        profesional.usuario_id = usuario.id
    asignaciones = (
        (await sesion.execute(select(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id)))
        .scalars()
        .all()
    )
    for asignacion in asignaciones:
        await sesion.delete(asignacion)
    await sesion.flush()
    await _asignar_roles(sesion, principal, usuario, roles, permisos_por_rol, profesional_id)
    return UsuarioAdministrado(
        id=usuario.id,
        correo=usuario.correo,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        activo=usuario.activo,
        roles=[r.nombre for r in roles],
        profesional_id=profesional_id,
        ultimo_acceso_en=usuario.ultimo_acceso_en,
    )


async def cambiar_estado_usuario(
    sesion: AsyncSession,
    principal: Principal,
    usuario_id: uuid.UUID,
    activo: bool,
) -> UsuarioAdministrado:
    if principal.actor_id == usuario_id and not activo:
        raise DatosInvalidos("No puede desactivar la cuenta que esta usando.")
    usuario = await sesion.scalar(
        select(Usuario).where(
            Usuario.id == usuario_id,
            Usuario.clinica_id == principal.clinica_id,
        )
    )
    if usuario is None:
        raise RecursoNoEncontrado("El usuario no existe.")
    usuario.activo = activo
    return UsuarioAdministrado(
        id=usuario.id,
        correo=usuario.correo,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        activo=usuario.activo,
        roles=[],
        ultimo_acceso_en=usuario.ultimo_acceso_en,
    )


async def _roles_asignables(
    sesion: AsyncSession,
    principal: Principal,
    ids: list[uuid.UUID],
    profesional_id: uuid.UUID | None,
) -> tuple[list[Rol], dict[uuid.UUID, frozenset[str]]]:
    if not ids or principal.clinica_id is None:
        raise DatosInvalidos("Seleccione al menos un rol valido.")
    roles = (
        (
            await sesion.execute(
                select(Rol).where(
                    Rol.id.in_(ids),
                    or_(Rol.clinica_id.is_(None), Rol.clinica_id == principal.clinica_id),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(roles) != len(ids) or any(r.codigo == "superadministrador" for r in roles):
        raise DatosInvalidos("La seleccion contiene un rol no asignable en esta clinica.")
    filas = await sesion.execute(
        select(RolPermiso.rol_id, Permiso.codigo)
        .join(Permiso, Permiso.id == RolPermiso.permiso_id)
        .where(RolPermiso.rol_id.in_(ids))
    )
    acumulados: dict[uuid.UUID, set[str]] = defaultdict(set)
    for rol_id, codigo in filas:
        acumulados[rol_id].add(codigo)
    permisos_por_rol = {rol_id: frozenset(codigos) for rol_id, codigos in acumulados.items()}
    rol_profesional = any(r.codigo == "profesional" for r in roles)
    if rol_profesional:
        if profesional_id is None:
            raise DatosInvalidos("Vincule un profesional para asignar ese rol.")
        await _profesional(sesion, principal, profesional_id)
    for rol in roles:
        permisos = permisos_por_rol.get(rol.id, frozenset())
        protegidos = permisos & PERMISOS_SOLO_ASISTENCIALES
        if protegidos and rol.codigo != "profesional":
            raise DatosInvalidos("Los permisos clinicos solo se conceden al rol profesional.")
        delegables = permisos - (
            PERMISOS_SOLO_ASISTENCIALES if rol.codigo == "profesional" else frozenset()
        )
        if not delegables <= principal.permisos:
            raise DatosInvalidos("No puede asignar permisos que su propia cuenta no tiene.")
    return list(roles), permisos_por_rol


async def _profesional(
    sesion: AsyncSession, principal: Principal, profesional_id: uuid.UUID
) -> Profesional:
    profesional = await sesion.scalar(
        select(Profesional).where(
            Profesional.id == profesional_id,
            Profesional.clinica_id == principal.clinica_id,
            Profesional.activo.is_(True),
            Profesional.anulado_en.is_(None),
        )
    )
    if profesional is None:
        raise RecursoNoEncontrado("El profesional no existe en esta clinica.")
    return profesional


async def _asignar_roles(
    sesion: AsyncSession,
    principal: Principal,
    usuario: Usuario,
    roles: list[Rol],
    permisos_por_rol: dict[uuid.UUID, frozenset[str]],
    profesional_id: uuid.UUID | None,
) -> None:
    es_profesional = any(r.codigo == "profesional" for r in roles)
    for rol in roles:
        asignacion = UsuarioRol(
            usuario_id=usuario.id,
            rol_id=rol.id,
            otorgado_por=principal.actor_id,
        )
        sesion.add(asignacion)
        await sesion.flush()
        for dimension in DIMENSIONES_CLINICA:
            valor = (
                profesional_id
                if es_profesional and dimension == TipoAmbito.PROFESIONAL.value
                else None
            )
            sesion.add(
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=dimension,
                    valor_id=valor,
                    incluir=True,
                )
            )
        if (
            rol.codigo == "profesional"
            and permisos_por_rol.get(rol.id, frozenset()) & PERMISOS_SOLO_ASISTENCIALES
        ):
            sesion.add(
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=TipoAmbito.TIPO_INFORMACION.value,
                    valor_id=None,
                    incluir=True,
                )
            )
