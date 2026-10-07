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
    async def test_crea_y_lista_sede_solo_dentro_de_la_clinica_objetivo(
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
        cabeceras = await cabecera_bearer(cliente, usuario, None)
        ruta = f"{api}/plataforma/clinicas/{clinica.id}/sedes"

        creada = await cliente.post(
            ruta,
            headers=cabeceras,
            json={
                "nombre": f"Sucursal {sufijo}",
                "direccion": "Av. Principal 123",
                "telefono": "+593 2 555 0101",
                "zona_horaria": "America/Guayaquil",
            },
        )

        assert creada.status_code == 201, creada.text
        salida = creada.json()
        assert salida["clinica_id"] == str(clinica.id)
        assert salida["nombre"] == f"Sucursal {sufijo}"
        assert salida["zona_horaria"] == "America/Guayaquil"
        duplicada = await cliente.post(
            ruta,
            headers=cabeceras,
            json={
                "nombre": f"Sucursal {sufijo}",
                "direccion": "Av. Principal 123",
                "telefono": "+593 2 555 0101",
                "zona_horaria": "America/Guayaquil",
            },
        )
        assert duplicada.status_code == 409
        listado = await cliente.get(ruta, headers=cabeceras)
        assert listado.status_code == 200, listado.text
        assert [sede["nombre"] for sede in listado.json()] == [f"Sucursal {sufijo}"]
        assert await sesion.scalar(
            sa.select(Auditoria.id).where(
                Auditoria.accion == "sede.creada", Auditoria.entidad_id == salida["id"]
            )
        )

    async def test_sede_rechaza_zona_horaria_invalida(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        configuracion,
    ) -> None:
        configuracion.roles_con_2fa_obligatorio = ""
        await _preparar_superadmin(sesion, usuario)
        cabeceras = await cabecera_bearer(cliente, usuario, None)

        respuesta = await cliente.post(
            f"{api}/plataforma/clinicas/{clinica.id}/sedes",
            headers=cabeceras,
            json={"nombre": "Sucursal inválida", "zona_horaria": "No/EsUnaZona"},
        )

        assert respuesta.status_code == 422

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
        alta_sede = await cliente.post(
            f"{api}/plataforma/clinicas/{clinica.id}/sedes",
            headers=cabeceras,
            json={"nombre": "Sucursal no autorizada"},
        )
        assert alta_sede.status_code == 403

    async def test_crea_cuenta_y_asigna_modulos_dentro_de_la_clinica_elegida(
        self,
        cliente: AsyncClient,
        api: str,
        sesion: AsyncSession,
        usuario: Usuario,
        clinica: Clinica,
        sede: Sede,
        otra_sede: Sede,
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
                "sedes_ids": [str(sede.id)],
            },
        )

        assert respuesta.status_code == 201, respuesta.text
        salida = respuesta.json()
        assert salida["clinica_id"] == str(clinica.id)
        assert salida["roles"] == ["Recepcion"]
        assert salida["todas_las_sedes"] is False
        assert salida["sedes_ids"] == [str(sede.id)]
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
        assert {scope.valor_id for scope in scopes if scope.tipo == "SEDE" and scope.incluir} == {
            sede.id
        }
        assert not any(scope.tipo == "SEDE" and scope.valor_id is None for scope in scopes)
        assert otra_sede.id != sede.id
        creada.debe_cambiar_contrasena = False
        await sesion.flush()
        inicio_sesion_restringido = await cliente.post(
            f"{api}/autenticacion/sesion",
            json={"correo": creada.correo, "contrasena": "Temporal!Seguro1234"},
        )
        assert inicio_sesion_restringido.status_code == 200, inicio_sesion_restringido.text
        cabeceras_restringidas = {
            "Authorization": f"Bearer {inicio_sesion_restringido.json()['token_acceso']}"
        }
        sedes_alcanzables = await cliente.get(
            f"{api}/catalogo/sedes", headers=cabeceras_restringidas
        )
        assert sedes_alcanzables.status_code == 200, sedes_alcanzables.text
        assert [item["id"] for item in sedes_alcanzables.json()] == [str(sede.id)]
        listado = await cliente.get(f"{api}/plataforma/clinicas/usuarios", headers=cabeceras)
        assert listado.status_code == 200, listado.text
        en_listado = next(item for item in listado.json() if item["id"] == str(creada.id))
        assert en_listado["todas_las_sedes"] is False
        assert en_listado["sedes_ids"] == [str(sede.id)]

        clinica_ajena = Clinica(
            nombre=f"Clínica ajena {sufijo}", identificacion_fiscal=f"AJENA-{sufijo}"
        )
        sesion.add(clinica_ajena)
        await sesion.flush()
        sede_ajena = Sede(clinica_id=clinica_ajena.id, nombre="Sede no compartida")
        sesion.add(sede_ajena)
        await sesion.flush()
        fuera_de_clinica = await cliente.post(
            f"{api}/plataforma/clinicas/usuarios",
            headers=cabeceras,
            json={
                "clinica_id": str(clinica.id),
                "correo": f"fuera-{sufijo}@example.invalid",
                "nombre": "Fuera",
                "apellido": "Clínica",
                "contrasena_inicial": "Temporal!Seguro1234",
                "roles": [str(rol.id)],
                "profesional_id": None,
                "sedes_ids": [str(sede_ajena.id)],
            },
        )
        assert fuera_de_clinica.status_code == 422
        acceso_total = await cliente.post(
            f"{api}/plataforma/clinicas/usuarios",
            headers=cabeceras,
            json={
                "clinica_id": str(clinica.id),
                "correo": f"todas-sedes-{sufijo}@example.invalid",
                "nombre": "Acceso",
                "apellido": "Completo",
                "contrasena_inicial": "Temporal!Seguro1234",
                "roles": [str(rol.id)],
                "profesional_id": None,
            },
        )
        assert acceso_total.status_code == 201, acceso_total.text
        assert acceso_total.json()["todas_las_sedes"] is True
        assert acceso_total.json()["sedes_ids"] == []

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
        destino_sede = Sede(clinica_id=destino.id, nombre=f"Sede destino {sufijo}")
        sesion.add(destino_sede)
        await sesion.flush()
        respuesta = await cliente.put(
            f"{api}/plataforma/clinicas/usuarios/{usuario.id}/asignacion",
            headers=cabeceras_actor,
            json={
                "clinica_id": str(destino.id),
                "roles": [str(rol_nuevo.id)],
                "profesional_id": None,
                "sedes_ids": [str(destino_sede.id)],
            },
        )

        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["clinica_id"] == str(destino.id)
        assert respuesta.json()["roles"] == ["Recepcion"]
        assert respuesta.json()["todas_las_sedes"] is False
        assert respuesta.json()["sedes_ids"] == [str(destino_sede.id)]
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
