"""Administración de clínicas reservada al superadministrador."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.usuarios.modelos import (
    AmbitoAsignacion,
    Permiso,
    Rol,
    RolPermiso,
    Usuario,
    UsuarioRol,
)
from app.modulos.usuarios.modelos import (
    Sesion as SesionAuth,
)
from app.nucleo.autorizacion import CATALOGO_PERMISOS
from app.nucleo.seguridad import hashear_contrasena, verificar_contrasena
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.asyncio]


async def _preparar_superadmin(sesion: AsyncSession, usuario: Usuario) -> None:
    rol = await sesion.scalar(
        sa.select(Rol).where(Rol.codigo == "superadministrador", Rol.clinica_id.is_(None))
    )
    if rol is None:
        rol = Rol(
            clinica_id=None,
            codigo="superadministrador",
            nombre="Superadministrador",
            es_sistema=True,
        )
        sesion.add(rol)
        await sesion.flush()
    for codigo in ("clinica.leer", "clinica.escribir"):
        definicion = next(p for p in CATALOGO_PERMISOS if p.codigo == codigo)
        permiso = await sesion.scalar(sa.select(Permiso).where(Permiso.codigo == codigo))
        if permiso is None:
            permiso = Permiso(
                codigo=codigo,
                descripcion=definicion.descripcion,
                categoria=definicion.categoria,
                requiere_relacion_asistencial=definicion.requiere_relacion_asistencial,
                nivel_sensibilidad=definicion.nivel.value,
            )
            sesion.add(permiso)
        await sesion.flush()
        existe = await sesion.scalar(
            sa.select(RolPermiso.rol_id).where(
                RolPermiso.rol_id == rol.id, RolPermiso.permiso_id == permiso.id
            )
        )
        if existe is None:
            sesion.add(RolPermiso(rol_id=rol.id, permiso_id=permiso.id))
    await sesion.flush()
    sesion.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    await sesion.flush()


def _datos(sufijo: str) -> dict[str, str]:
    return {
        "nombre": f"Clínica Nueva {sufijo}",
        "identificacion_fiscal": f"ALTA-{sufijo}",
        "zona_horaria": "America/Guayaquil",
        "idioma": "es",
        "moneda": "USD",
        "correo": f"contacto-{sufijo}@example.invalid",
        "sede_nombre": "Sede inicial",
        "sede_direccion": "Dirección ficticia 123",
        "administrador_nombre": "María",
        "administrador_apellido": "Administradora",
        "administrador_correo": f"admin-{sufijo}@example.invalid",
        "contrasena_inicial": "Temporal!Seguro1234",
    }


class TestAdministracionPlataforma:
    async def test_crea_clinica_sede_y_administrador_en_una_operacion(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        sufijo: str,
        configuracion,
    ) -> None:
        await _preparar_superadmin(sesion, usuario)
        configuracion.roles_con_2fa_obligatorio = ""
        cabeceras = await cabecera_bearer(cliente, usuario, None)

        respuesta = await cliente.post(
            f"{api}/plataforma/clinicas", headers=cabeceras, json=_datos(sufijo)
        )

        assert respuesta.status_code == 201, respuesta.text
        salida = respuesta.json()
        assert salida["nombre"] == f"Clínica Nueva {sufijo}"
        assert salida["cantidad_sedes"] == 1
        assert salida["cantidad_usuarios"] == 1
        clinica = await sesion.get(Clinica, salida["id"])
        assert clinica is not None
        sede = await sesion.scalar(sa.select(Sede).where(Sede.clinica_id == clinica.id))
        administrador = await sesion.scalar(
            sa.select(Usuario).where(Usuario.correo == f"admin-{sufijo}@example.invalid")
        )
        assert sede is not None and sede.nombre == "Sede inicial"
        assert administrador is not None and administrador.debe_cambiar_contrasena
        assert verificar_contrasena("Temporal!Seguro1234", administrador.hash_contrasena)
        assert (
            await sesion.scalar(
                sa.select(sa.func.count(Auditoria.id)).where(
                    Auditoria.entidad_id.in_([clinica.id, administrador.id])
                )
            )
            == 2
        )

    async def test_usuario_de_clinica_no_puede_abrir_la_administracion_global(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        configuracion,
    ) -> None:
        await conceder_permisos(sesion, usuario, clinica, "clinica.leer", "clinica.escribir")
        configuracion.roles_con_2fa_obligatorio = ""
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        respuesta = await cliente.get(f"{api}/plataforma/clinicas", headers=cabeceras)

        assert respuesta.status_code == 403

    async def test_crea_cuenta_y_asigna_modulos_dentro_de_la_clinica_elegida(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sufijo: str,
        configuracion,
    ) -> None:
        configuracion.roles_con_2fa_obligatorio = ""
        await _preparar_superadmin(sesion, usuario)
        rol = await sesion.scalar(
            sa.select(Rol).where(
                Rol.codigo == "recepcion",
                Rol.es_sistema.is_(True),
                Rol.clinica_id.is_(None),
            )
        )
        assert rol is not None
        cabeceras = await cabecera_bearer(cliente, usuario, clinica)

        opciones = await cliente.get(
            f"{api}/plataforma/clinicas/roles",
            params={"clinica_id": str(clinica.id)},
            headers=cabeceras,
        )
        assert opciones.status_code == 200, opciones.text
        assert "superadministrador" not in {r["codigo"] for r in opciones.json()}

        respuesta = await cliente.post(
            f"{api}/plataforma/clinicas/usuarios",
            headers=cabeceras,
            json={
                "clinica_id": str(clinica.id),
                "correo": f"persona-{sufijo}@example.invalid",
                "nombre": "Persona",
                "apellido": "Nueva",
                "contrasena_inicial": "Temporal!Seguro1234",
                "roles": [str(rol.id)],
                "profesional_id": None,
            },
        )

        assert respuesta.status_code == 201, respuesta.text
        salida = respuesta.json()
        assert salida["clinica_id"] == str(clinica.id)
        assert salida["roles"] == ["Recepcion"]
        creada = await sesion.scalar(
            sa.select(Usuario).where(Usuario.correo == f"persona-{sufijo}@example.invalid")
        )
        assert creada is not None and creada.debe_cambiar_contrasena
        scopes = list(
            (
                await sesion.scalars(
                    sa.select(AmbitoAsignacion)
                    .join(UsuarioRol, UsuarioRol.id == AmbitoAsignacion.usuario_rol_id)
                    .where(UsuarioRol.usuario_id == creada.id)
                )
            ).all()
        )
        assert {scope.tipo for scope in scopes} == {
            "SEDE",
            "ESPECIALIDAD",
            "PROFESIONAL",
            "PACIENTE",
        }

    async def test_cambiar_clinica_reemplaza_roles_y_corta_tokens_ya_emitidos(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sufijo: str,
        configuracion,
    ) -> None:
        configuracion.roles_con_2fa_obligatorio = ""
        actor = Usuario(
            clinica_id=clinica.id,
            correo=f"plataforma-{sufijo}@example.invalid",
            hash_contrasena=hashear_contrasena("ContrasenaDePrueba123"),
            nombre="Admin",
            apellido="Plataforma",
        )
        sesion.add(actor)
        await sesion.flush()
        await _preparar_superadmin(sesion, actor)
        rol_nuevo = await sesion.scalar(
            sa.select(Rol).where(
                Rol.codigo == "recepcion",
                Rol.es_sistema.is_(True),
                Rol.clinica_id.is_(None),
            )
        )
        assert rol_nuevo is not None
        rol_anterior = await conceder_permisos(
            sesion, usuario, clinica, "agenda.leer", codigo_rol=f"rol_origen_{sufijo}"
        )
        cabeceras_actor = await cabecera_bearer(cliente, actor, clinica)
        cabeceras_viejas = await cabecera_bearer(cliente, usuario, clinica)
        tokens = await sesion.scalars(
            sa.select(SesionAuth).where(SesionAuth.usuario_id == usuario.id)
        )
        ids_token = [token.id for token in tokens]
        assert ids_token

        destino = Clinica(
            nombre=f"Clínica destino {sufijo}",
            identificacion_fiscal=f"DESTINO-{sufijo}",
            zona_horaria="America/Guayaquil",
        )
        sesion.add(destino)
        await sesion.flush()
        respuesta = await cliente.put(
            f"{api}/plataforma/clinicas/usuarios/{usuario.id}/asignacion",
            headers=cabeceras_actor,
            json={
                "clinica_id": str(destino.id),
                "roles": [str(rol_nuevo.id)],
                "profesional_id": None,
            },
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["clinica_id"] == str(destino.id)
        assert respuesta.json()["roles"] == ["Recepcion"]
        assert await sesion.scalar(
            sa.select(Usuario.id).where(Usuario.clinica_id == destino.id, Usuario.id == usuario.id)
        )
        assert (
            await sesion.scalar(
                sa.select(UsuarioRol.id).where(
                    UsuarioRol.usuario_id == usuario.id, UsuarioRol.rol_id == rol_anterior.id
                )
            )
            is None
        )
        filas_token = await sesion.scalars(
            sa.select(SesionAuth).where(SesionAuth.id.in_(ids_token))
        )
        assert all(token.revocada_en is not None for token in filas_token)
        acceso_viejo = await cliente.get(f"{api}/autenticacion/yo", headers=cabeceras_viejas)
        assert acceso_viejo.status_code == 401
