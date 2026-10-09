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
    # Acotado a la clínica de la prueba: la base de desarrollo guarda otras capturas.
    captura = (
        await sesion.execute(
            select(CapturaIndicadores).where(CapturaIndicadores.clinica_id == clinica.id)
        )
    ).scalar_one()
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


async def test_totales_ponderados_personas_unicas_y_huecos_de_medicion(
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
    """Los KPI representan los registros; promediar promedios alteraría las cifras."""
    await conceder_permisos(
        sesion, usuario, clinica, "dashboard.leer", "agenda.leer", sedes=(sede.id,)
    )
    h = await cabecera_bearer(cliente, usuario, clinica)
    dias = [INSTANTE_REFERENCIA - timedelta(days=3), INSTANTE_REFERENCIA - timedelta(days=1)]
    for dia, realizadas, espera in [(dias[0], 1, 60), (dias[1], 5, 10)]:
        estados = ["COMPLETED"] * realizadas + ["NO_SHOW", "CANCELLED"]
        for i, estado in enumerate(estados):
            inicio = dia + timedelta(minutes=30 * i)
            sesion.add(
                Cita(
                    clinica_id=clinica.id,
                    sede_id=sede.id,
                    paciente_id=paciente.id,
                    profesional_id=profesional.id,
                    servicio_id=servicio.id,
                    inicio=inicio,
                    duracion_minutos=20,
                    estado=estado,
                    motivo_cancelacion="Cancelación sintética de QA"
                    if estado == "CANCELLED"
                    else None,
                    origen="PANEL",
                    creado_en=inicio - timedelta(days=2),
                    llegada_en=inicio - timedelta(minutes=espera)
                    if estado == "COMPLETED"
                    else None,
                    atencion_iniciada_en=inicio if estado == "COMPLETED" else None,
                )
            )
    await sesion.flush()
    r = await cliente.get(f"{api}/dashboard/analitica?dias=30", headers=h)
    assert r.status_code == 200, r.text
    k = {x["clave"]: x for x in r.json()["kpis"]}
    assert k["citas"]["total"] == 10
    assert k["atenciones"]["total"] == 6
    assert k["minutos_atendidos"]["total"] == 120
    assert k["pacientes_dia"]["total"] == 2  # La misma persona, estados distintos, dos días.
    assert k["tasa_asistencia"]["total"] == 75
    assert k["tasa_inasistencia"]["total"] == 25
    assert k["tasa_cancelacion"]["total"] == 20
    assert k["espera"]["total"] == pytest.approx(
        110 / 6, abs=0.005
    )  # La API redondea a centésimas.
    historia = {x["fecha"]: x for x in k["espera"]["historia"]}
    assert historia[dias[0].date().isoformat()]["muestras"] == 1
    assert historia[dias[1].date().isoformat()]["muestras"] == 5
    hueco = (INSTANTE_REFERENCIA - timedelta(days=2)).date().isoformat()
    assert historia[hueco]["valor"] is None and historia[hueco]["muestras"] == 0
    citas = {x["fecha"]: x for x in k["citas"]["historia"]}
    assert citas[hueco]["valor"] == 0  # Conteo cero sí observado después del primer registro.
    assert not k["espera"]["prediccion"]  # Dos días no justifican un modelo aprendido.
