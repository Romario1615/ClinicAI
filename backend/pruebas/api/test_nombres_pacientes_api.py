"""Nombres de varios pacientes en una sola petición, para rotular la agenda.

* Exige `paciente.leer_administrativo` y sesión.
* Devuelve solo id, nombre y apellido; nunca documento ni contacto.
* Un paciente de otra clínica se omite sin error (no confirma que existe).
* Valida la lista: vacía, demasiado larga o con identificadores inválidos → 422.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def test_nombres_por_lotes_respetan_permiso_ambito_y_esquema(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    ruta = f"{api}/pacientes/nombres"
    ajena = Clinica(nombre="Clinica ajena sintetica", identificacion_fiscal=uuid.uuid4().hex[:12])
    sesion.add(ajena)
    await sesion.flush()
    de_otra = Paciente(
        clinica_id=ajena.id,
        tipo_documento="CEDULA",
        numero_documento=f"8{uuid.uuid4().int % 10**9:09d}",
        nombre="Ajeno",
        apellido="Sintetico",
    )
    sesion.add(de_otra)
    await sesion.flush()
    params = [("ids", str(paciente.id)), ("ids", str(de_otra.id)), ("ids", str(paciente.id))]

    assert (await cliente.get(ruta, params=params)).status_code == 401

    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    sin_permiso = await cliente.get(
        ruta, params=params, headers=await cabecera_bearer(cliente, usuario, clinica)
    )
    assert sin_permiso.status_code == 403

    await conceder_permisos(
        sesion, usuario, clinica, "paciente.leer_administrativo", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(ruta, params=params, headers=cabeceras)
    assert respuesta.status_code == 200, respuesta.text
    # Sin duplicados, sin el paciente de otra clínica y sin campos sensibles.
    assert respuesta.json() == [
        {"id": str(paciente.id), "nombre": paciente.nombre, "apellido": paciente.apellido}
    ]

    for invalidos in (
        [],
        [("ids", "no-es-uuid")],
        [("ids", str(uuid.uuid4())) for _ in range(201)],
    ):
        assert (await cliente.get(ruta, params=invalidos, headers=cabeceras)).status_code == 422
