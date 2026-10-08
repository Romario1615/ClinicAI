from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita
from app.modulos.dashboard.capturas import CapturaIndicadores
from app.modulos.organizacion.modelos import Clinica, Sede, Servicio
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import Profesional
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos
from pruebas.conftest import INSTANTE_REFERENCIA

pytestmark = [pytest.mark.api, pytest.mark.seguridad, pytest.mark.asyncio]


async def test_analitica_aprende_solo_historia_completa(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
    servicio: Servicio,
    profesional: Profesional,
    paciente: Paciente,
) -> None:
    await conceder_permisos(
        sesion, usuario, clinica, "dashboard.leer", "agenda.leer", sedes=(sede.id,)
    )
    h = await cabecera_bearer(cliente, usuario, clinica)
    for i in range(1, 101):
        inicio = INSTANTE_REFERENCIA - timedelta(days=i)
        for j in range(1 + int(inicio.weekday() < 5)):
            sesion.add(
                Cita(
                    clinica_id=clinica.id,
                    sede_id=sede.id,
                    paciente_id=paciente.id,
                    profesional_id=profesional.id,
                    servicio_id=servicio.id,
                    inicio=inicio + timedelta(hours=j),
                    duracion_minutos=20,
                    estado="COMPLETED",
                    origen="PANEL",
                    creado_en=inicio - timedelta(days=2),
                )
            )
    # El futuro y el día incompleto no se usan en entrenamiento.
    sesion.add(
        Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=INSTANTE_REFERENCIA + timedelta(days=1),
            duracion_minutos=20,
            estado="CONFIRMED",
            origen="PANEL",
            creado_en=INSTANTE_REFERENCIA,
        )
    )
    await sesion.flush()
    r = await cliente.get(f"{api}/dashboard/analitica?dias=180&horizonte=14", headers=h)
    assert r.status_code == 200, r.text
    datos = r.json()
    k = {x["clave"]: x for x in datos["kpis"]}
    assert k["citas"]["total"] == sum(
        1 + int((INSTANTE_REFERENCIA - timedelta(days=i)).weekday() < 5) for i in range(1, 101)
    )
    assert k["citas"]["evidencia"]["algoritmo"] == "Patrón semanal aprendido"
    assert len(k["citas"]["prediccion"]) == 14
    assert "cobros" not in k and "gastos" not in k
    assert all(p["fecha"] < "2026-04-15" for p in k["citas"]["historia"])
    assert all(p["fecha"] >= "2026-04-15" for p in k["citas"]["prediccion"])
    assert not any("paciente_id" in x for x in datos["kpis"])
    captura = (await sesion.execute(select(CapturaIndicadores))).scalar_one()
    assert captura.actor_id == usuario.id and captura.clinica_id == clinica.id
    assert "agenda.citas_proximos_7_dias" in captura.valores
    assert "estado.agenda.citas_proximos_7_dias" in k
    assert not k["estado.agenda.citas_proximos_7_dias"]["prediccion"]
    assert k["estado.agenda.citas_proximos_7_dias"]["evidencia"]["estado"] == "insuficiente"
    # Solo las capturas del mismo actor y ámbito alimentan una serie de estados.
    sesion.add(
        CapturaIndicadores(
            clinica_id=clinica.id,
            actor_id=usuario.id,
            ambito_hash=captura.ambito_hash,
            fecha=INSTANTE_REFERENCIA.date() - timedelta(days=1),
            capturado_en=INSTANTE_REFERENCIA - timedelta(days=1),
            valores={"agenda.citas_proximos_7_dias": 3},
        )
    )
    sesion.add(
        CapturaIndicadores(
            clinica_id=clinica.id,
            actor_id=usuario.id,
            ambito_hash="f" * 64,
            fecha=INSTANTE_REFERENCIA.date() - timedelta(days=2),
            capturado_en=INSTANTE_REFERENCIA - timedelta(days=2),
            valores={"agenda.citas_proximos_7_dias": 999},
        )
    )
    await sesion.flush()
    r = await cliente.get(f"{api}/dashboard/analitica", headers=h)
    historico = next(
        x for x in r.json()["kpis"] if x["clave"] == "estado.agenda.citas_proximos_7_dias"
    )["historia"]
    assert [p["valor"] for p in historico if p["valor"] is not None] == [3]


async def test_sin_permisos_y_rangos(
    cliente: AsyncClient,
    sesion: AsyncSession,
    api: str,
    usuario: Usuario,
    clinica: Clinica,
    sede: Sede,
) -> None:
    h = await cabecera_bearer(cliente, usuario, clinica)
    assert (await cliente.get(f"{api}/dashboard/analitica", headers=h)).status_code == 403
    await conceder_permisos(sesion, usuario, clinica, "dashboard.leer", sedes=(sede.id,))
    h = await cabecera_bearer(cliente, usuario, clinica)
    r = await cliente.get(f"{api}/dashboard/analitica", headers=h)
    assert r.status_code == 200 and not r.json()["kpis"]
    for consulta in ["dias=500", "dias=0", "horizonte=31", "horizonte=0"]:
        assert (
            await cliente.get(f"{api}/dashboard/analitica?{consulta}", headers=h)
        ).status_code == 422
