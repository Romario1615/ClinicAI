"""Edades con que se propone la dentición inicial del odontograma.

* Quien ve el odontograma lee los cortes de **su** clínica; sin cambio
  guardado recibe los de omisión (6 mixta, 13 permanente).
* Solo quien gestiona especialidades los cambia, con motivo, versionado y
  auditoría.
* Un cambio en una clínica no afecta a otra.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.auditoria.modelos import Auditoria
from app.modulos.historia.denticion import CLAVE
from app.modulos.organizacion.modelos import Clinica, ConfiguracionClinica, Sede
from app.modulos.usuarios.modelos import Usuario
from app.nucleo.auditoria import AccionAuditada
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def test_lectura_exige_permiso_y_devuelve_los_cortes_por_omision(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    ruta = f"{api}/historia/denticion-por-edad"
    assert (await cliente.get(ruta)).status_code == 401

    await conceder_permisos(sesion, usuario, clinica, "agenda.leer", sedes=(sede.id,))
    sin_permiso = await cliente.get(ruta, headers=await cabecera_bearer(cliente, usuario, clinica))
    assert sin_permiso.status_code == 403

    await conceder_permisos(sesion, usuario, clinica, "odontograma.leer", sedes=(sede.id,))
    vista = await cliente.get(ruta, headers=await cabecera_bearer(cliente, usuario, clinica))
    assert vista.status_code == 200
    assert vista.json() == {"edad_mixta": 6, "edad_permanente": 13}


async def test_administracion_cambia_los_cortes_con_motivo_version_y_auditoria(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    ruta = f"{api}/catalogo/denticion-por-edad"
    cuerpo = {"edad_mixta": 6, "edad_permanente": 12, "motivo": "Criterio de odontopediatria"}
    assert (await cliente.put(ruta, json=cuerpo)).status_code == 401

    await conceder_permisos(sesion, usuario, clinica, "odontograma.leer", sedes=(sede.id,))
    sin_permiso = await cliente.put(
        ruta, headers=await cabecera_bearer(cliente, usuario, clinica), json=cuerpo
    )
    assert sin_permiso.status_code == 403

    await conceder_permisos(
        sesion, usuario, clinica, "odontograma.leer", "especialidad.gestionar", sedes=(sede.id,)
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)
    for invalido in (
        {"edad_mixta": 13, "edad_permanente": 6, "motivo": "Orden invertido"},
        {"edad_mixta": 6, "edad_permanente": 6, "motivo": "Cortes iguales"},
        {"edad_mixta": 0, "edad_permanente": 13, "motivo": "Fuera de rango"},
        {"edad_mixta": 6, "edad_permanente": 40, "motivo": "Fuera de rango"},
        {"edad_mixta": 6, "edad_permanente": 12},
    ):
        respuesta = await cliente.put(ruta, headers=cabeceras, json=invalido)
        assert respuesta.status_code == 422, invalido

    for permanente in (12, 14):
        cambio = await cliente.put(
            ruta, headers=cabeceras, json={**cuerpo, "edad_permanente": permanente}
        )
        assert cambio.status_code == 200, cambio.text
    assert cambio.json() == {"edad_mixta": 6, "edad_permanente": 14}
    leido = await cliente.get(f"{api}/historia/denticion-por-edad", headers=cabeceras)
    assert leido.json() == {"edad_mixta": 6, "edad_permanente": 14}

    versiones = (
        await sesion.execute(
            sa.select(ConfiguracionClinica.version, ConfiguracionClinica.vigente)
            .where(
                ConfiguracionClinica.clinica_id == clinica.id, ConfiguracionClinica.clave == CLAVE
            )
            .order_by(ConfiguracionClinica.version)
        )
    ).all()
    assert [tuple(v) for v in versiones] == [(1, False), (2, True)]
    auditado = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                Auditoria.accion == AccionAuditada.DENTICION_POR_EDAD_CAMBIADA.value,
                Auditoria.entidad_id == clinica.id,
            )
        )
    ).scalar_one()
    assert auditado == 2

    # Otra clínica conserva los cortes por omisión (sin fuga entre clínicas).
    ajena = Clinica(nombre="Clinica ajena sintetica", identificacion_fiscal=uuid.uuid4().hex[:12])
    sesion.add(ajena)
    await sesion.flush()
    de_la_ajena = (
        await sesion.execute(
            sa.select(sa.func.count()).where(
                ConfiguracionClinica.clinica_id == ajena.id, ConfiguracionClinica.clave == CLAVE
            )
        )
    ).scalar_one()
    assert de_la_ajena == 0


async def test_quien_configura_los_cortes_los_lee_sin_permiso_de_odontograma(
    cliente: AsyncClient,
    api: str,
    sesion: AsyncSession,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    await conceder_permisos(sesion, usuario, clinica, "especialidad.gestionar", sedes=(sede.id,))
    vista = await cliente.get(
        f"{api}/historia/denticion-por-edad",
        headers=await cabecera_bearer(cliente, usuario, clinica),
    )
    assert vista.status_code == 200
    assert vista.json() == {"edad_mixta": 6, "edad_permanente": 13}
