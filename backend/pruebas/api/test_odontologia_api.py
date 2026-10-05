"""Seguridad y versionado HTTP del odontograma clínico."""

from __future__ import annotations

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.odontologia.modelos import Odontograma
from app.modulos.organizacion.modelos import Clinica, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

PERMISOS_ODONTOGRAMA = ("odontograma.leer", "odontograma.escribir")


def _ruta(api: str, paciente_id: str) -> str:
    return f"{api}/odontologia/pacientes/{paciente_id}/odontograma"


@pytest_asyncio.fixture
async def relacion(
    sesion: AsyncSession, paciente: Paciente, profesional: Profesional
) -> RelacionAsistencial:
    fila = RelacionAsistencial(
        paciente_id=paciente.id, profesional_id=profesional.id, origen="CITA"
    )
    sesion.add(fila)
    await sesion.flush()
    return fila


@pytest_asyncio.fixture
async def cabeceras_odonto(
    cliente: AsyncClient,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
) -> dict[str, str]:
    await conceder_permisos(sesion, usuario, clinica, *PERMISOS_ODONTOGRAMA, sedes=(sede.id,))
    return await cabecera_bearer(cliente, usuario, clinica)


def _contenido(**extra: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "denticion": "PERMANENTE",
        "piezas": {"36": {"pieza": None, "caras": {"O": "CARIES"}}},
    }
    cuerpo.update(extra)
    return cuerpo


async def test_sin_permiso_se_deniega(
    cliente: AsyncClient,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    paciente: Paciente,
) -> None:
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    respuesta = await cliente.get(_ruta(api, str(paciente.id)), headers=cabeceras)
    assert respuesta.status_code == 403


async def test_la_relacion_asistencial_se_exige(
    cliente: AsyncClient,
    api: str,
    cabeceras_odonto: dict[str, str],
    paciente: Paciente,
) -> None:
    respuesta = await cliente.post(
        _ruta(api, str(paciente.id)), headers=cabeceras_odonto, json=_contenido()
    )
    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "RELACION_ASISTENCIAL_REQUERIDA"


async def test_captura_y_versionado_conservan_el_historial(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    cabeceras_odonto: dict[str, str],
    relacion: RelacionAsistencial,
    paciente: Paciente,
    usuario: Usuario,
) -> None:
    ruta = _ruta(api, str(paciente.id))
    primera = await cliente.post(ruta, headers=cabeceras_odonto, json=_contenido())
    assert primera.status_code == 201, primera.text
    assert primera.json()["version"] == 1
    assert primera.json()["vigente"] is True

    segunda = await cliente.post(
        f"{ruta}/versiones",
        headers=cabeceras_odonto,
        json=_contenido(
            version_base=1,
            motivo="Corrección tras revisión presencial",
            piezas={"36": {"pieza": None, "caras": {"O": "OBTURACION_RESINA"}}},
        ),
    )
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["version"] == 2
    assert segunda.json()["vigente"] is True

    historica = await cliente.get(f"{ruta}?version=1", headers=cabeceras_odonto)
    actual = await cliente.get(ruta, headers=cabeceras_odonto)
    historial = await cliente.get(f"{ruta}/versiones", headers=cabeceras_odonto)
    assert historica.status_code == actual.status_code == 200
    assert historial.status_code == 200
    assert historica.json()["vigente"] is False
    assert historica.json()["piezas"]["36"]["caras"]["O"] == "CARIES"
    assert actual.json()["vigente"] is True
    assert actual.json()["piezas"]["36"]["caras"]["O"] == "OBTURACION_RESINA"
    assert [version["version"] for version in historial.json()] == [2, 1]

    filas = list(
        (await sesion.execute(sa.select(Odontograma).where(Odontograma.paciente_id == paciente.id)))
        .scalars()
        .all()
    )
    assert len(filas) == 2
    assert all(fila.creado_por == usuario.id for fila in filas)
    eventos = list(
        (
            await sesion.execute(
                sa.select(Auditoria.accion).where(
                    Auditoria.accion == AccionAuditada.ODONTOGRAMA_VERSIONADO.value,
                    Auditoria.paciente_id == paciente.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(eventos) == 2


async def test_no_se_pierden_cambios_con_una_version_base_vieja(
    cliente: AsyncClient,
    api: str,
    cabeceras_odonto: dict[str, str],
    relacion: RelacionAsistencial,
    paciente: Paciente,
) -> None:
    ruta = _ruta(api, str(paciente.id))
    creada = await cliente.post(ruta, headers=cabeceras_odonto, json=_contenido())
    assert creada.status_code == 201

    respuesta = await cliente.post(
        f"{ruta}/versiones",
        headers=cabeceras_odonto,
        json=_contenido(version_base=4, motivo="Edición concurrente descartada"),
    )
    assert respuesta.status_code == 409
    assert respuesta.json()["detalles"]["version_vigente"] == 1


@pytest.mark.parametrize(
    "contenido",
    [
        {"denticion": "PERMANENTE", "piezas": {"49": {}}},
        {"denticion": "PERMANENTE", "piezas": {"51": {}}},
        {"denticion": "TEMPORAL", "piezas": {"36": {}}},
        {
            "denticion": "PERMANENTE",
            "piezas": {"36": {"pieza": "AUSENTE", "caras": {"O": "CARIES"}}},
        },
    ],
)
async def test_rechaza_estados_fdi_incoherentes(
    cliente: AsyncClient,
    api: str,
    cabeceras_odonto: dict[str, str],
    paciente: Paciente,
    contenido: dict[str, object],
) -> None:
    respuesta = await cliente.post(
        _ruta(api, str(paciente.id)), headers=cabeceras_odonto, json=contenido
    )
    assert respuesta.status_code == 422
