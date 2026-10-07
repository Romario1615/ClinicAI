"""Administracion global de organizaciones para el superadministrador."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import replace
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.usuarios import administracion
from app.modulos.usuarios.esquemas import EditarDatosUsuario
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    MotivoRevocacion,
    Permiso,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioRol,
)
from app.modulos.usuarios.modelos import (
    Sesion as SesionAuth,
)
from app.nucleo.auditoria import AccionAuditada, construir_entrada
from app.nucleo.autorizacion import PERMISOS_SOLO_ASISTENCIALES, Principal, TipoAmbito
from app.nucleo.dependencias import Auditor, RelojActual, Sesion, exige_permiso
from app.nucleo.errores import ConflictoEstado, DatosInvalidos, PermisoDenegado
from app.nucleo.seguridad import hashear_contrasena, validar_politica_contrasena

enrutador = APIRouter(prefix="/plataforma/clinicas", tags=["administracion-plataforma"])
PuedeListarClinicas = Annotated[Principal, Depends(exige_permiso("clinica.leer"))]
PuedeCrearClinicas = Annotated[Principal, Depends(exige_permiso("clinica.escribir"))]
LONGITUD_CORREO_MAXIMA = 200
LONGITUD_MONEDA = 3


class AltaClinica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=200)
    identificacion_fiscal: str | None = Field(default=None, max_length=50)
    zona_horaria: str = Field(default="America/Guayaquil", min_length=1, max_length=64)
    idioma: str = Field(default="es", min_length=2, max_length=8)
    moneda: str = Field(default="USD", min_length=3, max_length=3)
    telefono: str | None = Field(default=None, max_length=32)
    correo: str | None = Field(default=None, max_length=200)
    sede_nombre: str = Field(default="Sede principal", min_length=1, max_length=200)
    sede_direccion: str | None = Field(default=None, max_length=500)
    administrador_nombre: str = Field(min_length=1, max_length=100)
    administrador_apellido: str = Field(min_length=1, max_length=100)
    administrador_correo: str = Field(min_length=3, max_length=200)
    contrasena_inicial: str = Field(min_length=12, max_length=128)

    @field_validator("zona_horaria")
    @classmethod
    def validar_zona(cls, valor: str) -> str:
        try:
            ZoneInfo(valor.strip())
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Seleccione una zona horaria IANA válida.") from exc
        return valor.strip()


class ClinicaPlataforma(BaseModel):
    id: uuid.UUID
    nombre: str
    identificacion_fiscal: str | None
    correo: str | None
    activa: bool
    cantidad_sedes: int
    cantidad_usuarios: int


class SedePlataforma(BaseModel):
    id: uuid.UUID
    clinica_id: uuid.UUID
    nombre: str
    direccion: str | None
    telefono: str | None
    zona_horaria: str | None
    activa: bool


class AltaSedePlataforma(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=200)
    direccion: str | None = Field(default=None, max_length=500)
    telefono: str | None = Field(default=None, max_length=32)
    zona_horaria: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("zona_horaria")
    @classmethod
    def validar_zona(cls, valor: str | None) -> str | None:
        if valor is None or not valor.strip():
            return None
        try:
            ZoneInfo(valor.strip())
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Seleccione una zona horaria IANA válida.") from exc
        return valor.strip()


class DatosClinicaPlataforma(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nombre: str = Field(min_length=1, max_length=200)
    identificacion_fiscal: str | None = Field(default=None, max_length=50)
    correo: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=32)
    zona_horaria: str = Field(min_length=1, max_length=64)
    moneda: str = Field(pattern=r"^[A-Za-z]{3}$")
    idioma: str = Field(min_length=2, max_length=8)

    @field_validator("zona_horaria")
    @classmethod
    def validar_zona(cls, valor: str) -> str:
        return AltaClinica.validar_zona(valor)

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, valor: str | None) -> str | None:
        if valor and ("@" not in valor or " " in valor):
            raise ValueError("Ingrese un correo válido.")
        return valor.lower() if valor else None


class EstadoPlataforma(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    activo: bool
    motivo: str = Field(min_length=5, max_length=500)


class UsuarioPlataforma(BaseModel):
    id: uuid.UUID
    clinica_id: uuid.UUID
    clinica_nombre: str
    correo: str
    nombre: str
    apellido: str
    activo: bool
    roles: list[str]
    profesional_id: uuid.UUID | None
    sedes_ids: list[uuid.UUID]
    todas_las_sedes: bool


class RolPlataforma(BaseModel):
    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: str | None
    es_sistema: bool


class ProfesionalPlataforma(BaseModel):
    id: uuid.UUID
    nombre: str
    apellido: str


class AltaUsuarioPlataforma(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinica_id: uuid.UUID
    correo: str = Field(min_length=3, max_length=200)
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    contrasena_inicial: str = Field(min_length=12, max_length=128)
    roles: list[uuid.UUID] = Field(min_length=1, max_length=10)
    profesional_id: uuid.UUID | None = None
    sedes_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=50)


class ActualizarAsignacionPlataforma(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinica_id: uuid.UUID
    roles: list[uuid.UUID] = Field(min_length=1, max_length=10)
    profesional_id: uuid.UUID | None = None
    sedes_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=50)


@enrutador.get("", response_model=list[ClinicaPlataforma], summary="Clínicas de la plataforma")
async def listar_clinicas(
    sesion: Sesion,
    principal: PuedeListarClinicas,
) -> list[ClinicaPlataforma]:
    _exigir_superadministrador(principal)
    filas = await sesion.execute(
        select(
            Clinica,
            select(func.count(Sede.id))
            .where(Sede.clinica_id == Clinica.id, Sede.anulado_en.is_(None))
            .scalar_subquery(),
            select(func.count(Usuario.id))
            .where(Usuario.clinica_id == Clinica.id)
            .scalar_subquery(),
        )
        .where(Clinica.anulado_en.is_(None))
        .order_by(Clinica.nombre)
    )
    return [
        ClinicaPlataforma(
            id=clinica.id,
            nombre=clinica.nombre,
            identificacion_fiscal=clinica.identificacion_fiscal,
            correo=clinica.correo,
            activa=clinica.activa,
            cantidad_sedes=sedes,
            cantidad_usuarios=usuarios,
        )
        for clinica, sedes, usuarios in filas
    ]


@enrutador.get(
    "/{clinica_id}/sedes", response_model=list[SedePlataforma], summary="Sedes de una clínica"
)
async def listar_sedes_plataforma(
    clinica_id: uuid.UUID,
    sesion: Sesion,
    principal: PuedeListarClinicas,
) -> list[SedePlataforma]:
    _exigir_superadministrador(principal)
    clinica = await _clinica_activa(sesion, clinica_id)
    sedes = await sesion.scalars(
        select(Sede)
        .where(Sede.clinica_id == clinica.id, Sede.anulado_en.is_(None))
        .order_by(Sede.nombre)
    )
    return [
        SedePlataforma(
            id=sede.id,
            clinica_id=sede.clinica_id,
            nombre=sede.nombre,
            direccion=sede.direccion,
            telefono=sede.telefono,
            zona_horaria=sede.zona_horaria,
            activa=sede.activa,
        )
        for sede in sedes
    ]


@enrutador.post(
    "/{clinica_id}/sedes",
    response_model=SedePlataforma,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una sede de la clínica",
)
async def crear_sede_plataforma(
    clinica_id: uuid.UUID,
    datos: AltaSedePlataforma,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    principal: PuedeCrearClinicas,
) -> SedePlataforma:
    _exigir_superadministrador(principal)
    clinica = await _clinica_activa(sesion, clinica_id)
    nombre = datos.nombre.strip()
    if not nombre:
        raise DatosInvalidos("El nombre de la sede es obligatorio.")
    sede = Sede(
        clinica_id=clinica.id,
        nombre=nombre,
        direccion=datos.direccion.strip() if datos.direccion else None,
        telefono=datos.telefono.strip() if datos.telefono else None,
        zona_horaria=datos.zona_horaria,
        activa=True,
    )
    sesion.add(sede)
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("Ya existe una sede con ese nombre en la clínica.") from exc
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.SEDE_CREADA,
                principal=replace(principal, clinica_id=clinica.id),
                ahora=reloj.ahora(),
                entidad_tipo="sede",
                entidad_id=sede.id,
                plataforma_global=True,
            )
        ]
    )
    await sesion.commit()
    return SedePlataforma(
        id=sede.id,
        clinica_id=sede.clinica_id,
        nombre=sede.nombre,
        direccion=sede.direccion,
        telefono=sede.telefono,
        zona_horaria=sede.zona_horaria,
        activa=sede.activa,
    )


@enrutador.get(
    "/usuarios", response_model=list[UsuarioPlataforma], summary="Personal de todas las clínicas"
)
async def listar_usuarios_plataforma(
    sesion: Sesion,
    principal: PuedeListarClinicas,
) -> list[UsuarioPlataforma]:
    _exigir_superadministrador(principal)
    filas = await sesion.execute(
        select(Usuario, Clinica.nombre, Profesional.id)
        .join(Clinica, Clinica.id == Usuario.clinica_id)
        .outerjoin(Profesional, Profesional.usuario_id == Usuario.id)
        .where(Clinica.anulado_en.is_(None))
        .order_by(Clinica.nombre, Usuario.apellido, Usuario.nombre)
    )
    usuarios = list(filas)
    if not usuarios:
        return []
    ids = [usuario.id for usuario, _, _ in usuarios]
    roles_por_usuario: dict[uuid.UUID, list[str]] = {}
    asignaciones = await sesion.execute(
        select(UsuarioRol.usuario_id, Rol.nombre)
        .join(Rol, Rol.id == UsuarioRol.rol_id)
        .where(UsuarioRol.usuario_id.in_(ids))
        .order_by(Rol.nombre)
    )
    for usuario_id, nombre_rol in asignaciones:
        roles_por_usuario.setdefault(usuario_id, []).append(nombre_rol)
    reglas_sedes = await sesion.execute(
        select(UsuarioRol.usuario_id, AmbitoAsignacion.valor_id, AmbitoAsignacion.incluir)
        .join(AmbitoAsignacion, AmbitoAsignacion.usuario_rol_id == UsuarioRol.id)
        .where(
            UsuarioRol.usuario_id.in_(ids),
            AmbitoAsignacion.tipo == TipoAmbito.SEDE.value,
        )
    )
    sedes_por_usuario: dict[uuid.UUID, list[tuple[uuid.UUID | None, bool]]] = {}
    for usuario_id, sede_id, incluir in reglas_sedes:
        sedes_por_usuario.setdefault(usuario_id, []).append((sede_id, incluir))
    return [
        UsuarioPlataforma(
            id=usuario.id,
            clinica_id=usuario.clinica_id,
            clinica_nombre=clinica_nombre,
            correo=usuario.correo,
            nombre=usuario.nombre,
            apellido=usuario.apellido,
            activo=usuario.activo,
            roles=roles_por_usuario.get(usuario.id, []),
            profesional_id=profesional_id,
            sedes_ids=_resumen_sedes(sedes_por_usuario.get(usuario.id, []))[0],
            todas_las_sedes=_resumen_sedes(sedes_por_usuario.get(usuario.id, []))[1],
        )
        for usuario, clinica_nombre, profesional_id in usuarios
    ]


@enrutador.get(
    "/roles", response_model=list[RolPlataforma], summary="Roles disponibles en una clínica"
)
async def listar_roles_plataforma(
    sesion: Sesion,
    principal: PuedeListarClinicas,
    clinica_id: uuid.UUID,
) -> list[RolPlataforma]:
    _exigir_superadministrador(principal)
    await _clinica_activa(sesion, clinica_id)
    roles = list(
        (
            await sesion.scalars(
                select(Rol)
                .where((Rol.clinica_id.is_(None)) | (Rol.clinica_id == clinica_id))
                .order_by(Rol.es_sistema.desc(), Rol.nombre)
            )
        ).all()
    )
    return [
        RolPlataforma(
            id=rol.id,
            codigo=rol.codigo,
            nombre=rol.nombre,
            descripcion=rol.descripcion,
            es_sistema=rol.es_sistema,
        )
        for rol in roles
        if rol.codigo != "superadministrador"
    ]


@enrutador.get(
    "/profesionales",
    response_model=list[ProfesionalPlataforma],
    summary="Profesionales para vincular",
)
async def listar_profesionales_plataforma(
    sesion: Sesion,
    principal: PuedeListarClinicas,
    clinica_id: uuid.UUID,
    usuario_id: uuid.UUID | None = None,
) -> list[ProfesionalPlataforma]:
    _exigir_superadministrador(principal)
    filas = await sesion.scalars(
        select(Profesional)
        .where(
            Profesional.clinica_id == clinica_id,
            (Profesional.usuario_id.is_(None) | (Profesional.usuario_id == usuario_id))
            if usuario_id
            else Profesional.usuario_id.is_(None),
            Profesional.activo.is_(True),
            Profesional.anulado_en.is_(None),
        )
        .order_by(Profesional.apellido, Profesional.nombre)
    )
    return [ProfesionalPlataforma(id=p.id, nombre=p.nombre, apellido=p.apellido) for p in filas]


@enrutador.post("/usuarios", response_model=UsuarioPlataforma, status_code=status.HTTP_201_CREATED)
async def crear_usuario_plataforma(
    datos: AltaUsuarioPlataforma,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    principal: PuedeCrearClinicas,
) -> UsuarioPlataforma:
    _exigir_superadministrador(principal)
    clinica = await _clinica_activa(sesion, datos.clinica_id)
    correo = datos.correo.strip().lower()
    if "@" not in correo or not datos.nombre.strip() or not datos.apellido.strip():
        raise DatosInvalidos("Ingrese nombre, apellido y un correo válido.")
    if await sesion.scalar(select(Usuario.id).where(func.lower(Usuario.correo) == correo)):
        raise ConflictoEstado("Ya existe una cuenta con ese correo.")
    problemas = validar_politica_contrasena(datos.contrasena_inicial)
    if problemas:
        raise DatosInvalidos(" ".join(problemas))
    await _validar_sedes_plataforma(sesion, clinica.id, datos.sedes_ids)
    roles, permisos = await _roles_globales(sesion, clinica.id, datos.roles, datos.profesional_id)
    profesional = await _profesional_global(sesion, clinica.id, datos.profesional_id, roles)
    usuario = Usuario(
        clinica_id=clinica.id,
        correo=correo,
        hash_contrasena=hashear_contrasena(datos.contrasena_inicial),
        nombre=datos.nombre.strip(),
        apellido=datos.apellido.strip(),
        activo=True,
        debe_cambiar_contrasena=True,
    )
    sesion.add(usuario)
    await sesion.flush()
    if profesional:
        profesional.usuario_id = usuario.id
    await _asignar_ambitos(
        sesion,
        principal,
        usuario,
        roles,
        permisos,
        datos.profesional_id,
        datos.sedes_ids,
    )
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_CREADO,
                principal=replace(principal, clinica_id=clinica.id),
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario.id,
                roles=[rol.nombre for rol in roles],
                sedes_ids=[str(sede_id) for sede_id in datos.sedes_ids]
                if datos.sedes_ids is not None
                else None,
                todas_las_sedes=datos.sedes_ids is None,
                plataforma_global=True,
            )
        ]
    )
    await sesion.commit()
    return await _usuario_respuesta(sesion, usuario.id)


@enrutador.put("/usuarios/{usuario_id}/asignacion", response_model=UsuarioPlataforma)
async def actualizar_asignacion_plataforma(
    usuario_id: uuid.UUID,
    datos: ActualizarAsignacionPlataforma,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    principal: PuedeCrearClinicas,
) -> UsuarioPlataforma:
    _exigir_superadministrador(principal)
    usuario = await sesion.scalar(select(Usuario).where(Usuario.id == usuario_id))
    if usuario is None:
        raise DatosInvalidos("La cuenta seleccionada no existe.")
    if await sesion.scalar(
        select(Rol.id)
        .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
        .where(UsuarioRol.usuario_id == usuario.id, Rol.codigo == "superadministrador")
    ):
        raise PermisoDenegado(
            "La asignación de cuentas de plataforma requiere un procedimiento independiente."
        )
    clinica = await _clinica_activa(sesion, datos.clinica_id)
    await _validar_sedes_plataforma(sesion, clinica.id, datos.sedes_ids)
    roles, permisos = await _roles_globales(sesion, clinica.id, datos.roles, datos.profesional_id)
    profesional = await _profesional_global(sesion, clinica.id, datos.profesional_id, roles)
    if profesional:
        asignado = await sesion.scalar(
            select(Profesional.id).where(
                Profesional.usuario_id == usuario.id,
                Profesional.id != profesional.id,
            )
        )
        if asignado:
            await sesion.execute(
                update(Profesional)
                .where(Profesional.usuario_id == usuario.id)
                .values(usuario_id=None)
            )
        profesional.usuario_id = usuario.id
    else:
        await sesion.execute(
            update(Profesional).where(Profesional.usuario_id == usuario.id).values(usuario_id=None)
        )
    clinica_anterior_id = usuario.clinica_id
    ahora = reloj.ahora()
    sesiones = await sesion.scalars(
        select(SesionAuth).where(
            SesionAuth.usuario_id == usuario.id,
            SesionAuth.revocada_en.is_(None),
        )
    )
    for token in sesiones:
        token.revocada_en = ahora
        token.motivo_revocacion = MotivoRevocacion.REVOCACION_ADMINISTRATIVA.value
    await sesion.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id))
    usuario.clinica_id = clinica.id
    for rol in roles:
        asignacion = UsuarioRol(
            usuario_id=usuario.id,
            rol_id=rol.id,
            otorgado_por=principal.actor_id,
        )
        sesion.add(asignacion)
        await sesion.flush()
        await _anadir_ambitos(
            sesion, asignacion, rol, permisos, datos.profesional_id, datos.sedes_ids
        )
    await sesion.flush()
    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.USUARIO_MODIFICADO,
                principal=replace(principal, clinica_id=clinica.id),
                ahora=ahora,
                entidad_tipo="usuario",
                entidad_id=usuario.id,
                clinica_anterior_id=str(clinica_anterior_id),
                roles=[rol.nombre for rol in roles],
                sedes_ids=[str(sede_id) for sede_id in datos.sedes_ids]
                if datos.sedes_ids is not None
                else None,
                todas_las_sedes=datos.sedes_ids is None,
                sesiones_revocadas=True,
                plataforma_global=True,
            )
        ]
    )
    await sesion.commit()
    return await _usuario_respuesta(sesion, usuario.id)


async def _clinica_activa(sesion: Sesion, clinica_id: uuid.UUID) -> Clinica:
    clinica = await sesion.scalar(
        select(Clinica).where(
            Clinica.id == clinica_id,
            Clinica.activa.is_(True),
            Clinica.anulado_en.is_(None),
        )
    )
    if clinica is None:
        raise DatosInvalidos("Seleccione una clínica activa de la plataforma.")
    return clinica


async def _roles_globales(
    sesion: Sesion,
    clinica_id: uuid.UUID,
    roles_ids: list[uuid.UUID],
    profesional_id: uuid.UUID | None,
) -> tuple[list[Rol], dict[uuid.UUID, frozenset[str]]]:
    if len(set(roles_ids)) != len(roles_ids):
        raise DatosInvalidos("No repita roles en una misma asignación.")
    roles = list(
        (
            await sesion.scalars(
                select(Rol).where(
                    Rol.id.in_(roles_ids),
                    (Rol.clinica_id.is_(None)) | (Rol.clinica_id == clinica_id),
                )
            )
        ).all()
    )
    if len(roles) != len(roles_ids) or any(rol.codigo == "superadministrador" for rol in roles):
        raise DatosInvalidos("La selección incluye roles que no pertenecen a la clínica.")
    filas = await sesion.execute(
        select(RolPermiso.rol_id, Permiso.codigo)
        .join(Permiso, Permiso.id == RolPermiso.permiso_id)
        .where(RolPermiso.rol_id.in_(roles_ids))
    )
    permisos: dict[uuid.UUID, set[str]] = {}
    for rol_id, codigo in filas:
        permisos.setdefault(rol_id, set()).add(codigo)
    congelados = {rol_id: frozenset(codigos) for rol_id, codigos in permisos.items()}
    for rol in roles:
        protegidos = congelados.get(rol.id, frozenset()) & PERMISOS_SOLO_ASISTENCIALES
        if protegidos and rol.codigo != "profesional":
            raise DatosInvalidos(
                "Los permisos clínicos solo se asignan mediante el rol profesional."
            )
    if any(rol.codigo == "profesional" for rol in roles) and profesional_id is None:
        raise DatosInvalidos("Vincule un perfil profesional para asignar ese rol.")
    return roles, congelados


async def _profesional_global(
    sesion: Sesion,
    clinica_id: uuid.UUID,
    profesional_id: uuid.UUID | None,
    roles: list[Rol],
    *,
    usuario_id: uuid.UUID | None = None,
) -> Profesional | None:
    requiere = any(rol.codigo == "profesional" for rol in roles)
    if not requiere:
        if profesional_id is not None:
            raise DatosInvalidos("Solo vincule un perfil profesional si asigna ese rol.")
        return None
    profesional = await sesion.scalar(
        select(Profesional).where(
            Profesional.id == profesional_id,
            Profesional.clinica_id == clinica_id,
            Profesional.activo.is_(True),
            Profesional.anulado_en.is_(None),
            (Profesional.usuario_id.is_(None) | (Profesional.usuario_id == usuario_id))
            if usuario_id
            else Profesional.usuario_id.is_(None),
        )
    )
    if profesional is None:
        raise DatosInvalidos("El perfil profesional no está disponible en la clínica elegida.")
    return profesional


async def _asignar_ambitos(
    sesion: Sesion,
    principal: Principal,
    usuario: Usuario,
    roles: list[Rol],
    permisos: dict[uuid.UUID, frozenset[str]],
    profesional_id: uuid.UUID | None,
    sedes_ids: list[uuid.UUID] | None,
) -> None:
    for rol in roles:
        asignacion = UsuarioRol(
            usuario_id=usuario.id,
            rol_id=rol.id,
            otorgado_por=principal.actor_id,
        )
        sesion.add(asignacion)
        await sesion.flush()
        await _anadir_ambitos(sesion, asignacion, rol, permisos, profesional_id, sedes_ids)


async def _anadir_ambitos(
    sesion: Sesion,
    asignacion: UsuarioRol,
    rol: Rol,
    permisos: dict[uuid.UUID, frozenset[str]],
    profesional_id: uuid.UUID | None,
    sedes_ids: list[uuid.UUID] | None,
) -> None:
    for tipo in (
        TipoAmbito.SEDE.value,
        TipoAmbito.ESPECIALIDAD.value,
        TipoAmbito.PROFESIONAL.value,
        TipoAmbito.PACIENTE.value,
    ):
        valores = (
            [(sede_id, True) for sede_id in sedes_ids]
            if tipo == TipoAmbito.SEDE.value and sedes_ids is not None
            else [(None, True)]
        )
        for valor_id, incluir in valores:
            sesion.add(
                AmbitoAsignacion(
                    usuario_rol_id=asignacion.id,
                    tipo=tipo,
                    valor_id=(
                        profesional_id
                        if rol.codigo == "profesional" and tipo == TipoAmbito.PROFESIONAL.value
                        else valor_id
                    ),
                    incluir=incluir,
                )
            )
    if (
        rol.codigo == "profesional"
        and permisos.get(rol.id, frozenset()) & PERMISOS_SOLO_ASISTENCIALES
    ):
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id,
                tipo=TipoAmbito.TIPO_INFORMACION.value,
                valor_id=None,
                incluir=True,
            )
        )


async def _usuario_respuesta(sesion: Sesion, usuario_id: uuid.UUID) -> UsuarioPlataforma:
    usuario, nombre_clinica, profesional_id = (
        await sesion.execute(
            select(Usuario, Clinica.nombre, Profesional.id)
            .join(Clinica, Clinica.id == Usuario.clinica_id)
            .outerjoin(Profesional, Profesional.usuario_id == Usuario.id)
            .where(Usuario.id == usuario_id)
        )
    ).one()
    nombres_roles = list(
        (
            await sesion.scalars(
                select(Rol.nombre)
                .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
                .where(UsuarioRol.usuario_id == usuario.id)
                .order_by(Rol.nombre)
            )
        ).all()
    )
    reglas_sede = await sesion.execute(
        select(AmbitoAsignacion.valor_id, AmbitoAsignacion.incluir)
        .join(UsuarioRol, UsuarioRol.id == AmbitoAsignacion.usuario_rol_id)
        .where(
            UsuarioRol.usuario_id == usuario.id,
            AmbitoAsignacion.tipo == TipoAmbito.SEDE.value,
        )
    )
    sedes_ids, todas_las_sedes = _resumen_sedes(reglas_sede.tuples().all())
    return UsuarioPlataforma(
        id=usuario.id,
        clinica_id=usuario.clinica_id,
        clinica_nombre=nombre_clinica,
        correo=usuario.correo,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        activo=usuario.activo,
        roles=nombres_roles,
        profesional_id=profesional_id,
        sedes_ids=sedes_ids,
        todas_las_sedes=todas_las_sedes,
    )


def _resumen_sedes(
    reglas: Iterable[tuple[uuid.UUID | None, bool]],
) -> tuple[list[uuid.UUID], bool]:
    todas_las_sedes = False
    sedes_ids: set[uuid.UUID] = set()
    sedes_excluidas: set[uuid.UUID] = set()
    for sede_id, incluir in reglas:
        if sede_id is None:
            todas_las_sedes = todas_las_sedes or incluir
        elif incluir:
            sedes_ids.add(sede_id)
        else:
            sedes_excluidas.add(sede_id)
    if sedes_excluidas:
        todas_las_sedes = False
        sedes_ids.difference_update(sedes_excluidas)
    return sorted(sedes_ids), todas_las_sedes


async def _validar_sedes_plataforma(
    sesion: Sesion,
    clinica_id: uuid.UUID,
    sedes_ids: list[uuid.UUID] | None,
) -> None:
    if sedes_ids is None:
        return
    if len(sedes_ids) != len(set(sedes_ids)):
        raise DatosInvalidos("No repita sedes en una misma asignación.")
    encontradas = set(
        (
            await sesion.scalars(
                select(Sede.id).where(
                    Sede.id.in_(sedes_ids),
                    Sede.clinica_id == clinica_id,
                    Sede.activa.is_(True),
                    Sede.anulado_en.is_(None),
                )
            )
        ).all()
    )
    if encontradas != set(sedes_ids):
        raise DatosInvalidos("Seleccione sedes activas que pertenezcan a la clínica elegida.")


@enrutador.post("", response_model=ClinicaPlataforma, status_code=status.HTTP_201_CREATED)
async def crear_clinica(
    datos: AltaClinica,
    sesion: Sesion,
    reloj: RelojActual,
    auditor: Auditor,
    principal: PuedeCrearClinicas,
) -> ClinicaPlataforma:
    _exigir_superadministrador(principal)
    correo_admin = datos.administrador_correo.strip().lower()
    if not datos.nombre.strip() or not datos.sede_nombre.strip():
        raise DatosInvalidos("El nombre de la clínica y de su sede son obligatorios.")
    if not datos.administrador_nombre.strip() or not datos.administrador_apellido.strip():
        raise DatosInvalidos("El nombre y apellido del administrador son obligatorios.")
    if "@" not in correo_admin:
        raise DatosInvalidos("Ingrese un correo válido para el administrador.")
    if await sesion.scalar(select(Usuario.id).where(func.lower(Usuario.correo) == correo_admin)):
        raise ConflictoEstado("Ya existe una cuenta con ese correo.")
    if datos.correo and ("@" not in datos.correo or len(datos.correo) > LONGITUD_CORREO_MAXIMA):
        raise DatosInvalidos("Ingrese un correo válido para la clínica.")
    if datos.identificacion_fiscal and await sesion.scalar(
        select(Clinica.id).where(
            Clinica.identificacion_fiscal == datos.identificacion_fiscal.strip()
        )
    ):
        raise ConflictoEstado("La identificación fiscal ya está registrada.")
    if len(datos.moneda) != LONGITUD_MONEDA or not datos.moneda.isalpha():
        raise DatosInvalidos("La moneda debe ser un código de tres letras.")
    problemas = validar_politica_contrasena(datos.contrasena_inicial)
    if problemas:
        raise DatosInvalidos(" ".join(problemas))

    rol_admin = await sesion.scalar(
        select(Rol).where(
            Rol.codigo == "administrador_clinica",
            Rol.es_sistema.is_(True),
            Rol.clinica_id.is_(None),
        )
    )
    if rol_admin is None:
        raise DatosInvalidos("No está cargado el rol base de administrador de clínica.")

    clinica = Clinica(
        nombre=datos.nombre.strip(),
        identificacion_fiscal=datos.identificacion_fiscal.strip()
        if datos.identificacion_fiscal
        else None,
        zona_horaria=datos.zona_horaria,
        idioma=datos.idioma.strip().lower(),
        moneda=datos.moneda.upper(),
        telefono=datos.telefono.strip() if datos.telefono else None,
        correo=datos.correo.strip().lower() if datos.correo else None,
    )
    sesion.add(clinica)
    await sesion.flush()
    sede = Sede(
        clinica_id=clinica.id,
        nombre=datos.sede_nombre.strip(),
        direccion=datos.sede_direccion.strip() if datos.sede_direccion else None,
        zona_horaria=datos.zona_horaria,
        activa=True,
    )
    usuario = Usuario(
        clinica_id=clinica.id,
        correo=correo_admin,
        hash_contrasena=hashear_contrasena(datos.contrasena_inicial),
        nombre=datos.administrador_nombre.strip(),
        apellido=datos.administrador_apellido.strip(),
        activo=True,
        debe_cambiar_contrasena=True,
    )
    sesion.add_all([sede, usuario])
    await sesion.flush()
    asignacion = UsuarioRol(
        usuario_id=usuario.id, rol_id=rol_admin.id, otorgado_por=principal.actor_id
    )
    sesion.add(asignacion)
    await sesion.flush()
    for tipo in (
        TipoAmbito.SEDE.value,
        TipoAmbito.ESPECIALIDAD.value,
        TipoAmbito.PROFESIONAL.value,
        TipoAmbito.PACIENTE.value,
    ):
        sesion.add(
            AmbitoAsignacion(
                usuario_rol_id=asignacion.id,
                tipo=tipo,
                valor_id=None,
                incluir=True,
            )
        )
    try:
        await sesion.flush()
    except IntegrityError as exc:
        await sesion.rollback()
        raise ConflictoEstado("El correo o la identificación fiscal ya están registrados.") from exc

    await auditor.registrar(
        [
            construir_entrada(
                accion=AccionAuditada.CLINICA_CREADA,
                principal=replace(principal, clinica_id=clinica.id),
                ahora=reloj.ahora(),
                entidad_tipo="clinica",
                entidad_id=clinica.id,
                cantidad_sedes=1,
                administrador_id=str(usuario.id),
            ),
            construir_entrada(
                accion=AccionAuditada.USUARIO_CREADO,
                principal=replace(principal, clinica_id=clinica.id),
                ahora=reloj.ahora(),
                entidad_tipo="usuario",
                entidad_id=usuario.id,
                roles=["Administrador de clínica"],
            ),
        ]
    )
    await sesion.commit()
    return ClinicaPlataforma(
        id=clinica.id,
        nombre=clinica.nombre,
        identificacion_fiscal=clinica.identificacion_fiscal,
        correo=clinica.correo,
        activa=clinica.activa,
        cantidad_sedes=1,
        cantidad_usuarios=1,
    )


def _exigir_superadministrador(principal: Principal) -> None:
    if "superadministrador" not in principal.roles:
        raise PermisoDenegado("Esta operación requiere el rol superadministrador.")


async def _clinica_existente(sesion: Sesion, clinica_id: uuid.UUID) -> Clinica:
    fila = await sesion.scalar(select(Clinica).where(
        Clinica.id == clinica_id, Clinica.anulado_en.is_(None)
    ).with_for_update())
    if fila is None:
        raise DatosInvalidos("La clínica seleccionada no existe.")
    return fila


@enrutador.get("/{clinica_id}/datos", response_model=DatosClinicaPlataforma)
async def datos_clinica(clinica_id: uuid.UUID, sesion: Sesion, principal: PuedeListarClinicas) -> DatosClinicaPlataforma:
    _exigir_superadministrador(principal)
    fila = await _clinica_existente(sesion, clinica_id)
    return DatosClinicaPlataforma.model_validate(fila, from_attributes=True)


@enrutador.put("/{clinica_id}/datos", response_model=DatosClinicaPlataforma)
async def editar_clinica(clinica_id: uuid.UUID, datos: DatosClinicaPlataforma, sesion: Sesion,
                        principal: PuedeCrearClinicas, reloj: RelojActual, auditor: Auditor) -> DatosClinicaPlataforma:
    _exigir_superadministrador(principal)
    fila = await _clinica_existente(sesion, clinica_id)
    for clave, valor in datos.model_dump().items():
        setattr(fila, clave, valor.upper() if clave == "moneda" else valor)
    fila.actualizado_por = principal.actor_id
    try:
        await sesion.flush()
    except IntegrityError as exc:
        raise ConflictoEstado("La identificación fiscal ya está registrada.") from exc
    await auditor.registrar([construir_entrada(accion=AccionAuditada.CLINICA_MODIFICADA,
        principal=replace(principal, clinica_id=clinica_id), ahora=reloj.ahora(),
        entidad_tipo="clinica", entidad_id=clinica_id, plataforma_global=True)])
    await sesion.commit()
    return DatosClinicaPlataforma.model_validate(fila, from_attributes=True)


@enrutador.put("/{clinica_id}/estado", response_model=EstadoPlataforma)
async def estado_clinica(clinica_id: uuid.UUID, datos: EstadoPlataforma, sesion: Sesion,
                        principal: PuedeCrearClinicas, reloj: RelojActual, auditor: Auditor) -> EstadoPlataforma:
    _exigir_superadministrador(principal)
    fila = await _clinica_existente(sesion, clinica_id)
    if not datos.activo and await sesion.scalar(select(Usuario.id).join(UsuarioRol).join(Rol).where(
        Usuario.clinica_id == clinica_id, Usuario.activo.is_(True), Rol.codigo == "superadministrador"
    ).limit(1)):
        raise DatosInvalidos("No puede desactivar la organización que administra la plataforma.")
    fila.activa = datos.activo
    fila.actualizado_por = principal.actor_id
    if not datos.activo:
        await sesion.execute(update(SesionAuth).where(
            SesionAuth.usuario_id.in_(select(Usuario.id).where(Usuario.clinica_id == clinica_id)),
            SesionAuth.revocada_en.is_(None)
        ).values(revocada_en=reloj.ahora(), motivo_revocacion=MotivoRevocacion.REVOCACION_ADMINISTRATIVA.value))
    await auditor.registrar([construir_entrada(accion=AccionAuditada.CLINICA_MODIFICADA,
        principal=replace(principal, clinica_id=clinica_id), ahora=reloj.ahora(),
        entidad_tipo="clinica", entidad_id=clinica_id, activa=datos.activo, motivo=datos.motivo,
        plataforma_global=True)])
    await sesion.commit()
    return datos


@enrutador.put("/usuarios/{usuario_id}/datos", response_model=UsuarioPlataforma)
async def editar_usuario_global(usuario_id: uuid.UUID, datos: EditarDatosUsuario, sesion: Sesion,
                               principal: PuedeCrearClinicas, reloj: RelojActual, auditor: Auditor) -> UsuarioPlataforma:
    _exigir_superadministrador(principal)
    usuario = await sesion.get(Usuario, usuario_id)
    if usuario is None:
        raise DatosInvalidos("La cuenta no existe.")
    actor = replace(principal, clinica_id=usuario.clinica_id)
    await administracion.editar_datos_usuario(sesion, actor, usuario_id, datos)
    await sesion.execute(update(SesionAuth).where(SesionAuth.usuario_id == usuario_id,
        SesionAuth.revocada_en.is_(None)).values(revocada_en=reloj.ahora(),
        motivo_revocacion=MotivoRevocacion.REVOCACION_ADMINISTRATIVA.value))
    await auditor.registrar([construir_entrada(accion=AccionAuditada.USUARIO_MODIFICADO,
        principal=actor, ahora=reloj.ahora(), entidad_tipo="usuario", entidad_id=usuario_id,
        plataforma_global=True, sesiones_revocadas=True)])
    await sesion.commit()
    return await _usuario_respuesta(sesion, usuario_id)


@enrutador.put("/usuarios/{usuario_id}/estado", response_model=UsuarioPlataforma)
async def estado_usuario_global(usuario_id: uuid.UUID, datos: EstadoPlataforma, sesion: Sesion,
                               principal: PuedeCrearClinicas, reloj: RelojActual, auditor: Auditor) -> UsuarioPlataforma:
    _exigir_superadministrador(principal)
    usuario = await sesion.get(Usuario, usuario_id)
    if usuario is None:
        raise DatosInvalidos("La cuenta no existe.")
    if await sesion.scalar(select(Rol.id).join(UsuarioRol).where(
        UsuarioRol.usuario_id == usuario_id, Rol.codigo == "superadministrador")):
        raise DatosInvalidos("No puede desactivar cuentas de plataforma desde esta pantalla.")
    actor = replace(principal, clinica_id=usuario.clinica_id)
    await administracion.cambiar_estado_usuario(sesion, actor, usuario_id, datos.activo)
    if not datos.activo:
        await sesion.execute(update(SesionAuth).where(SesionAuth.usuario_id == usuario_id,
            SesionAuth.revocada_en.is_(None)).values(revocada_en=reloj.ahora(),
            motivo_revocacion=MotivoRevocacion.USUARIO_DESACTIVADO.value))
    await auditor.registrar([construir_entrada(accion=AccionAuditada.USUARIO_MODIFICADO,
        principal=actor, ahora=reloj.ahora(), entidad_tipo="usuario", entidad_id=usuario_id,
        activo=datos.activo, motivo=datos.motivo, plataforma_global=True)])
    await sesion.commit()
    return await _usuario_respuesta(sesion, usuario_id)


__all__ = ["enrutador"]
