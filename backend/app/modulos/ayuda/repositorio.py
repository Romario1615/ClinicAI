"""Acceso a datos del centro de ayuda.

Solo se leen los roles **vigentes del propio principal** (`role_ids`, que
resuelve el servicio de autenticacion en cada peticion) y sus permisos. Como
defensa adicional se exige que el rol sea del sistema o de la clinica del
principal: un identificador de rol de otra clinica nunca aporta un manual.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.usuarios.modelos import Permiso, Rol, RolPermiso
from app.nucleo.autorizacion import Principal


@dataclass(frozen=True, slots=True)
class RolConPermisos:
    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: str | None
    es_sistema: bool
    permisos: frozenset[str]


class RepositorioAyuda:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def roles_del_principal(self, principal: Principal) -> list[RolConPermisos]:
        if not principal.role_ids:
            return []
        filtro_clinica = (
            Rol.clinica_id.is_(None)
            if principal.clinica_id is None
            else or_(Rol.clinica_id.is_(None), Rol.clinica_id == principal.clinica_id)
        )
        roles = (
            (
                await self._sesion.execute(
                    select(Rol)
                    .where(Rol.id.in_(principal.role_ids), filtro_clinica)
                    .order_by(Rol.es_sistema.desc(), Rol.nombre)
                )
            )
            .scalars()
            .all()
        )
        if not roles:
            return []
        permisos: dict[uuid.UUID, set[str]] = defaultdict(set)
        filas = await self._sesion.execute(
            select(RolPermiso.rol_id, Permiso.codigo)
            .join(Permiso, Permiso.id == RolPermiso.permiso_id)
            .where(RolPermiso.rol_id.in_([rol.id for rol in roles]))
        )
        for rol_id, codigo in filas:
            permisos[rol_id].add(codigo)
        return [
            RolConPermisos(
                id=rol.id,
                codigo=rol.codigo,
                nombre=rol.nombre,
                descripcion=rol.descripcion,
                es_sistema=rol.es_sistema,
                permisos=frozenset(permisos[rol.id]),
            )
            for rol in roles
        ]
