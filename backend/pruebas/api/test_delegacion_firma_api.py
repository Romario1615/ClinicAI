"""Firma de recetas por delegación registrada.

* Sin delegación, firmar a nombre de otro profesional → 403.
* Con delegación vigente → se crea la receta firmada por el delegante, y la
  auditoría marca la firma como delegada.
* Revocada o vencida → 403 otra vez.
* Solo `profesional.gestionar` crea delegaciones.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.organizacion.modelos import Clinica, Especialidad, Sede
from app.modulos.pacientes.modelos import Paciente, RelacionAsistencial
from app.modulos.profesionales.modelos import DelegacionFirma, Profesional
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from app.nucleo.reloj import RelojFijo
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]

RECETA = {
    "indicaciones_generales": None,
    "medicamentos": [
        {
            "nombre": "Medicamento sintetico A",
            "dosis": "1 unidad",
            "via": "ORAL",
            "frecuencia_horas": 8,
            "duracion_dias": 3,
        }
    ],
}


@pytest_asyncio.fixture
async def adjunto(
    sesion: AsyncSession, clinica: Clinica, especialidad: Especialidad
) -> Profesional:
    fila = Profesional(
        clinica_id=clinica.id,
        especialidad_id=especialidad.id,
        nombre="Adjunta",
        apellido="Sintetica",
        numero_registro_profesional=f"REG-{uuid.uuid4().hex[:8]}",
    )
    sesion.add(fila)
    await sesion.flush()
    return fila


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
        sesion,
        usuario,
        clinica,
        "receta.crear",
        "receta.confirmar",
        "receta.leer",
        "profesional.gestionar",
        sedes=(sede.id,),
    )
    return await cabecera_bearer(cliente, usuario, clinica)


def _receta(paciente: Paciente, firmante: Profesional) -> dict[str, object]:
    return {**RECETA, "paciente_id": str(paciente.id), "profesional_id": str(firmante.id)}


async def test_sin_delegacion_no_se_firma_por_otro(
    cliente: AsyncClient,
    api: str,
    cabeceras: dict[str, str],
    paciente: Paciente,
    adjunto: Profesional,
) -> None:
    respuesta = await cliente.post(
        f"{api}/historia/recetas", headers=cabeceras, json=_receta(paciente, adjunto)
    )
    assert respuesta.status_code == 403


async def test_con_delegacion_vigente_se_firma_y_se_audita(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    reloj: RelojFijo,
    cabeceras: dict[str, str],
    paciente: Paciente,
    profesional: Profesional,
    adjunto: Profesional,
) -> None:
    ahora = reloj.ahora()
    alta = await cliente.post(
        f"{api}/profesionales/delegaciones",
        headers=cabeceras,
        json={
            "delegante_id": str(adjunto.id),
            "delegado_id": str(profesional.id),
            "vigente_desde": (ahora - timedelta(days=1)).isoformat(),
            "vigente_hasta": (ahora + timedelta(days=30)).isoformat(),
            "motivo": "Residencia de prueba",
        },
    )
    assert alta.status_code == 201, alta.text
    assert alta.json()["vigente"] is True

    mias = await cliente.get(f"{api}/profesionales/delegaciones/mias", headers=cabeceras)
    assert [d["delegante_id"] for d in mias.json()] == [str(adjunto.id)]

    receta = await cliente.post(
        f"{api}/historia/recetas", headers=cabeceras, json=_receta(paciente, adjunto)
    )
    assert receta.status_code == 201, receta.text
    assert receta.json()["profesional_id"] == str(adjunto.id)

    confirmada = await cliente.post(
        f"{api}/historia/recetas/{receta.json()['id']}/confirmacion",
        headers=cabeceras,
        json={"profesional_id": str(adjunto.id)},
    )
    assert confirmada.status_code == 200, confirmada.text
    entrada = (
        await sesion.execute(
            sa.select(Auditoria).where(
                Auditoria.accion == AccionAuditada.RECETA_CONFIRMADA.value,
                Auditoria.paciente_id == paciente.id,
            )
        )
    ).scalar_one()
    assert entrada.metadatos["firma_delegada"] is True

    revocada = await cliente.post(
        f"{api}/profesionales/delegaciones/{alta.json()['id']}/revocacion", headers=cabeceras
    )
    assert revocada.status_code == 200
    otra = await cliente.post(
        f"{api}/historia/recetas", headers=cabeceras, json=_receta(paciente, adjunto)
    )
    assert otra.status_code == 403


async def test_delegacion_vencida_no_vale(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    reloj: RelojFijo,
    clinica: Clinica,
    cabeceras: dict[str, str],
    paciente: Paciente,
    profesional: Profesional,
    adjunto: Profesional,
) -> None:
    ahora = reloj.ahora()
    sesion.add(
        DelegacionFirma(
            clinica_id=clinica.id,
            delegante_id=adjunto.id,
            delegado_id=profesional.id,
            vigente_desde=ahora - timedelta(days=10),
            vigente_hasta=ahora - timedelta(days=1),
            motivo="Residencia terminada",
        )
    )
    await sesion.flush()
    respuesta = await cliente.post(
        f"{api}/historia/recetas", headers=cabeceras, json=_receta(paciente, adjunto)
    )
    assert respuesta.status_code == 403


async def test_crear_delegacion_exige_permiso(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    profesional: Profesional,
    adjunto: Profesional,
    reloj: RelojFijo,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "receta.crear", sedes=(sede.id,))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    ahora = reloj.ahora()
    respuesta = await cliente.post(
        f"{api}/profesionales/delegaciones",
        headers=cabeceras,
        json={
            "delegante_id": str(adjunto.id),
            "delegado_id": str(profesional.id),
            "vigente_desde": ahora.isoformat(),
            "vigente_hasta": (ahora + timedelta(days=1)).isoformat(),
            "motivo": "Intento sin permiso",
        },
    )
    assert respuesta.status_code == 403
