"""La ficha pregunta si puede pedir datos clínicos antes de pedirlos.

Un profesional sin relación asistencial recibe `false` (200), no una cadena
de 404. Fuera de ámbito sigue siendo 404, sin permiso 403 y sin sesión 401.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def test_el_profesional_sabe_si_tiene_relacion_asistencial(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "paciente.leer_administrativo",
        "historia_clinica.leer",
        sedes=(sede.id,),
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    ruta = f"{api}/pacientes/{paciente.id}/acceso-clinico"

    sin_relacion = await cliente.get(ruta, headers=cabeceras)
    assert sin_relacion.status_code == 200, sin_relacion.text
    assert sin_relacion.json() == {"acceso_clinico": False}

    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    con_relacion = await cliente.get(ruta, headers=cabeceras)
    assert con_relacion.json() == {"acceso_clinico": True}


async def test_fuera_de_ambito_sin_permiso_y_sin_sesion(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    sin_sesion = await cliente.get(f"{api}/pacientes/{paciente.id}/acceso-clinico")
    assert sin_sesion.status_code == 401

    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    sin_permiso = await cliente.get(
        f"{api}/pacientes/{paciente.id}/acceso-clinico",
        headers=await cabecera_bearer(cliente, usuario, clinica),
    )
    assert sin_permiso.status_code == 403

    await conceder_permisos(
        sesion, usuario, clinica, "paciente.leer_administrativo", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    inexistente = await cliente.get(
        f"{api}/pacientes/{uuid.uuid4()}/acceso-clinico", headers=cabeceras
    )
    assert inexistente.status_code == 404


async def test_sin_ficha_profesional_no_exige_relacion(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
) -> None:
    """Asistencia clínica queda acotada por permiso y ámbito, como en la guardia."""
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "paciente.leer_administrativo",
        "historia_clinica.leer",
        sedes=(sede.id,),
    )
    respuesta = await cliente.get(
        f"{api}/pacientes/{paciente.id}/acceso-clinico",
        headers=await cabecera_bearer(cliente, usuario, clinica),
    )
    assert respuesta.json() == {"acceso_clinico": True}
