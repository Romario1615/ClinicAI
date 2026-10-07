"""Edición y baja lógica de organizaciones y cuentas con aislamiento real."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.modulos.organizacion.modelos import Clinica
from app.modulos.usuarios.modelos import Sesion as SesionAuth
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import CONTRASENA, cabecera_bearer, conceder_permisos
from pruebas.api.test_plataforma_api import _preparar_superadmin

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def actor_plataforma(cliente, sesion, usuario, configuracion):
    configuracion.roles_con_2fa_obligatorio = ""
    await _preparar_superadmin(sesion, usuario)
    return await cabecera_bearer(cliente, usuario, None)


async def test_clinica_edita_desactiva_reactiva_y_conserva_filas(
    cliente, api, sesion, usuario, configuracion, sufijo
):
    cabeceras = await actor_plataforma(cliente, sesion, usuario, configuracion)
    clinica = Clinica(nombre=f"Clínica sintética {sufijo}", zona_horaria="America/Guayaquil")
    sesion.add(clinica)
    await sesion.flush()
    ruta = f"{api}/plataforma/clinicas/{clinica.id}"
    datos = (await cliente.get(ruta + "/datos", headers=cabeceras)).json()
    datos["nombre"] = "Clínica actualizada sintética"
    actualizado = await cliente.put(ruta + "/datos", json=datos, headers=cabeceras)
    assert actualizado.status_code == 200, actualizado.text
    assert actualizado.json()["nombre"] == datos["nombre"]
    for activo in (False, True):
        r = await cliente.put(
            ruta + "/estado",
            json={"activo": activo, "motivo": "Cambio administrativo sintético"},
            headers=cabeceras,
        )
        assert r.status_code == 200, r.text
        assert clinica.activa is activo
    assert await sesion.get(Clinica, clinica.id) is not None


async def test_no_desactiva_clinica_de_superadmin(
    cliente, api, sesion, usuario, clinica, configuracion
):
    cabeceras = await actor_plataforma(cliente, sesion, usuario, configuracion)
    r = await cliente.put(
        f"{api}/plataforma/clinicas/{clinica.id}/estado",
        json={"activo": False, "motivo": "Prueba de protección"},
        headers=cabeceras,
    )
    assert r.status_code == 422, r.text
    assert clinica.activa


async def test_usuario_local_edita_y_revoca_tokens(cliente, api, sesion, usuario, clinica, sufijo):
    await conceder_permisos(sesion, usuario, clinica, "usuario.editar", "usuario.desactivar")
    actor = await cabecera_bearer(cliente, usuario, clinica)
    cuenta = Usuario(
        clinica_id=clinica.id,
        nombre="Nombre",
        apellido="Sintético",
        correo=f"cuenta-{sufijo}@example.invalid",
        hash_contrasena=usuario.hash_contrasena,
    )
    sesion.add(cuenta)
    await sesion.flush()
    await conceder_permisos(
        sesion, cuenta, clinica, "paciente.leer_administrativo", codigo_rol=f"cuenta-{sufijo}"
    )
    anterior = await cabecera_bearer(cliente, cuenta, clinica)
    r = await cliente.put(
        f"{api}/usuarios/{cuenta.id}/datos",
        json={"nombre": "Actualizado", "apellido": "Sintético", "correo": cuenta.correo},
        headers=actor,
    )
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Actualizado"
    assert (await cliente.get(f"{api}/autenticacion/yo", headers=anterior)).status_code == 401
    tokens = list(
        await sesion.scalars(select(SesionAuth).where(SesionAuth.usuario_id == cuenta.id))
    )
    assert tokens and all(t.revocada_en for t in tokens)


async def test_usuario_global_crud_logico(
    cliente, api, sesion, usuario, clinica, configuracion, sufijo
):
    actor = await actor_plataforma(cliente, sesion, usuario, configuracion)
    cuenta = Usuario(
        clinica_id=clinica.id,
        nombre="Otra",
        apellido="Cuenta",
        correo=f"global-{sufijo}@example.invalid",
        hash_contrasena=usuario.hash_contrasena,
    )
    sesion.add(cuenta)
    await sesion.flush()
    ruta = f"{api}/plataforma/clinicas/usuarios/{cuenta.id}"
    r = await cliente.put(
        ruta + "/datos",
        json={"nombre": "Editada", "apellido": "Cuenta", "correo": cuenta.correo},
        headers=actor,
    )
    assert r.status_code == 200, r.text
    for activo in (False, True):
        r = await cliente.put(
            ruta + "/estado",
            json={"activo": activo, "motivo": "Estado sintético de cuenta"},
            headers=actor,
        )
        assert r.status_code == 200, r.text
        assert r.json()["activo"] is activo
    assert await sesion.get(Usuario, cuenta.id) is not None


async def test_clinica_inactiva_impide_nuevo_login(cliente, api, sesion, usuario, clinica):
    clinica.activa = False
    await sesion.flush()
    r = await cliente.post(
        f"{api}/autenticacion/sesion",
        json={"correo": usuario.correo, "contrasena": CONTRASENA},
    )
    assert r.status_code in (401, 403), r.text


@pytest.mark.parametrize(
    "ruta",
    [
        "plataforma/clinicas/{id}/datos",
        "plataforma/clinicas/{id}/estado",
        "plataforma/clinicas/usuarios/{id}/datos",
        "plataforma/clinicas/usuarios/{id}/estado",
        "usuarios/{id}/datos",
    ],
)
async def test_crud_sin_autenticacion(cliente, api, ruta):
    r = await cliente.put(
        f"{api}/{ruta.format(id=uuid.uuid4())}",
        json={
            "nombre": "Sintético",
            "apellido": "Usuario",
            "correo": "sintetico@example.invalid",
            "activo": True,
            "motivo": "Prueba sintética",
        },
    )
    assert r.status_code == 401


@pytest.mark.parametrize("tipo", ["datos", "estado"])
async def test_cuenta_local_no_edita_otra_clinica(
    cliente, api, sesion, usuario, clinica, sufijo, tipo
):
    await conceder_permisos(sesion, usuario, clinica, "usuario.editar", "usuario.desactivar")
    actor = await cabecera_bearer(cliente, usuario, clinica)
    ajena = Clinica(nombre=f"Otra {sufijo}")
    sesion.add(ajena)
    await sesion.flush()
    cuenta = Usuario(
        clinica_id=ajena.id,
        nombre="Ajena",
        apellido="Sintética",
        correo=f"ajena-{sufijo}@example.invalid",
        hash_contrasena=usuario.hash_contrasena,
    )
    sesion.add(cuenta)
    await sesion.flush()
    datos = (
        {"nombre": "Intento", "apellido": "Sintético", "correo": cuenta.correo}
        if tipo == "datos"
        else {"activo": False}
    )
    r = await cliente.put(f"{api}/usuarios/{cuenta.id}/{tipo}", json=datos, headers=actor)
    assert r.status_code == 404, r.text
    assert cuenta.nombre == "Ajena" and cuenta.activo


async def test_clinica_datos_invalidos_rechazados(
    cliente, api, sesion, usuario, clinica, configuracion
):
    actor = await actor_plataforma(cliente, sesion, usuario, configuracion)
    r = await cliente.put(
        f"{api}/plataforma/clinicas/{clinica.id}/datos",
        json={"nombre": "Clínica", "zona_horaria": "No/Zona", "moneda": "USD", "idioma": "es"},
        headers=actor,
    )
    assert r.status_code == 422
