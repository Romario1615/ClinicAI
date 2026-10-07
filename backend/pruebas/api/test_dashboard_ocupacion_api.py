"""El resumen del dashboard calcula ocupacion desde los horarios de sede."""

from datetime import UTC, datetime, time

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import Cita, EstadoCita, OrigenCita
from app.modulos.organizacion.modelos import Descanso, HorarioAtencion
from app.modulos.profesionales.modelos import ProfesionalSede
from pruebas.api.conftest import cabecera_bearer, conceder_permisos


@pytest.mark.api
@pytest.mark.asyncio
async def test_ocupacion_usa_horario_pausas_y_buffer_de_citas(
    api: str,
    cliente: AsyncClient,
    sesion: AsyncSession,
    clinica,
    sede,
    profesional,
    servicio,
    paciente,
    usuario,
) -> None:
    await sesion.execute(
        sa.delete(HorarioAtencion).where(
            HorarioAtencion.propietario_tipo == "SEDE",
            HorarioAtencion.propietario_id == sede.id,
        )
    )
    horario = HorarioAtencion(
        propietario_tipo="SEDE",
        propietario_id=sede.id,
        dia_semana=3,
        hora_inicio=time(9, 0),
        hora_fin=time(13, 0),
        granularidad_minutos=15,
    )
    sesion.add_all([horario, ProfesionalSede(profesional_id=profesional.id, sede_id=sede.id)])
    await sesion.flush()
    sesion.add(
        Descanso(horario_atencion_id=horario.id, hora_inicio=time(11, 0), hora_fin=time(11, 30))
    )
    sesion.add(
        Cita(
            clinica_id=clinica.id,
            sede_id=sede.id,
            paciente_id=paciente.id,
            profesional_id=profesional.id,
            servicio_id=servicio.id,
            inicio=datetime(2026, 4, 15, 14, 30, tzinfo=UTC),
            duracion_minutos=30,
            minutos_preparacion=15,
            estado=EstadoCita.CONFIRMED.value,
            origen=OrigenCita.PANEL.value,
        )
    )
    await sesion.flush()
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "dashboard.leer",
        todas_las_sedes=True,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.get(
        f"{api}/dashboard/",
        params={
            "desde": "2026-04-15T14:00:00Z",
            "hasta": "2026-04-15T19:00:00Z",
        },
        headers=cabeceras,
    )

    assert respuesta.status_code == 200, respuesta.text
    ocupacion = respuesta.json()["ocupacion_agenda"]
    assert ocupacion == {
        "minutos_disponibles": 210,
        "minutos_ocupados": 45,
        "porcentaje": 21.4,
        "detalle": "Reservas activas frente al horario disponible; incluye pausas, feriados y bloqueos.",
    }

    respuesta_por_estado = await cliente.get(
        f"{api}/dashboard/",
        params={
            "desde": "2026-04-15T14:00:00Z",
            "hasta": "2026-04-15T19:00:00Z",
            "estado": "CONFIRMED",
        },
        headers=cabeceras,
    )
    assert respuesta_por_estado.status_code == 200, respuesta_por_estado.text
    assert respuesta_por_estado.json()["ocupacion_agenda"] == {
        "minutos_disponibles": None,
        "minutos_ocupados": None,
        "porcentaje": None,
        "detalle": "Selecciona todos los estados para obtener una ocupación comparable.",
    }
