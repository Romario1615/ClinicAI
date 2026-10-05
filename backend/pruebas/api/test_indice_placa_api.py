"""Índice de placa de O'Leary.

* El porcentaje lo calcula el servidor: 3 superficies con placa sobre
  2 piezas x 4 superficies = 37,50 %.
* Piezas o caras inválidas y placa en piezas no evaluadas → 422.
* Un registro no se modifica ni se borra (disparador).
* Sin permiso de odontograma o sin relación asistencial no se accede.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.odontologia.modelos import RegistroPlaca
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def cabeceras(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    paciente: Paciente,
) -> dict[str, str]:
    sesion.add(
        RelacionAsistencial(paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA")
    )
    await sesion.flush()
    await conceder_permisos(
        sesion, usuario, clinica, "odontograma.leer", "odontograma.escribir", sedes=(sede.id,)
    )
    return await cabecera_bearer(cliente, usuario, clinica)


def _ruta(api: str, paciente: Paciente) -> str:
    return f"{api}/odontologia/pacientes/{paciente.id}/indice-placa"


async def test_calcula_el_porcentaje_y_conserva_la_serie(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras: dict[str, str],
    paciente: Paciente,
) -> None:
    respuesta = await cliente.post(
        _ruta(api, paciente),
        headers=cabeceras,
        json={
            "piezas_evaluadas": [16, 36],
            "superficies_con_placa": {"16": ["M", "V"], "36": ["D"]},
            "observacion": "Control sintetico",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total_superficies"] == 8
    assert cuerpo["total_con_placa"] == 3
    assert Decimal(cuerpo["porcentaje"]) == Decimal("37.50")
    assert cuerpo["superficies_con_placa"]["16"] == ["V", "M"]

    serie = await cliente.get(_ruta(api, paciente), headers=cabeceras)
    assert serie.status_code == 200
    assert len(serie.json()) == 1

    fila = (
        await sesion.execute(
            sa.select(RegistroPlaca).where(RegistroPlaca.paciente_id == paciente.id)
        )
    ).scalar_one()
    with pytest.raises(DBAPIError):
        async with sesion.begin_nested():
            await sesion.execute(
                sa.update(RegistroPlaca).where(RegistroPlaca.id == fila.id).values(porcentaje=0)
            )


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"piezas_evaluadas": [99]},
        {"piezas_evaluadas": [16, 16]},
        {"piezas_evaluadas": [16], "superficies_con_placa": {"36": ["V"]}},
        {"piezas_evaluadas": [16], "superficies_con_placa": {"16": ["O"]}},
        {"piezas_evaluadas": []},
    ],
)
async def test_datos_invalidos_se_rechazan(
    cliente: AsyncClient,
    api: str,
    cabeceras: dict[str, str],
    paciente: Paciente,
    cuerpo: dict[str, object],
) -> None:
    respuesta = await cliente.post(_ruta(api, paciente), headers=cabeceras, json=cuerpo)
    assert respuesta.status_code == 422


async def test_sin_permiso_no_se_lee(
    cliente: AsyncClient, api: str, usuario: Usuario, clinica: Clinica, paciente: Paciente
) -> None:
    respuesta = await cliente.get(
        _ruta(api, paciente), headers=await cabecera_bearer(cliente, usuario, clinica)
    )
    assert respuesta.status_code == 403


async def test_sin_relacion_asistencial_no_se_escribe(
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
        sesion, usuario, clinica, "odontograma.leer", "odontograma.escribir", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.post(
        _ruta(api, paciente), headers=cabeceras, json={"piezas_evaluadas": [16]}
    )
    assert respuesta.status_code == 403
