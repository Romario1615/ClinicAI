"""El resumen del dashboard calcula ocupacion desde los horarios de sede.

Escenario comun: miercoles 15 de abril de 2026, horario de la sede de 09:00 a
13:00 (America/Guayaquil, UTC-5) con una pausa de 11:00 a 11:30, y un periodo
consultado de 09:00 a 14:00 locales (14:00-19:00 UTC).  Sin nada mas, la
capacidad es de 210 minutos.  La cita base empieza a las 09:30 locales y dura
30 minutos mas 15 de preparacion: ocupa 45.

Cada caso parametrizado cambia una sola cosa (feriado, bloqueo, plantilla,
ambito o estado de las citas) y comprueba los minutos **exactos**.  Comprobar
solo que el porcentaje «baja» dejaria pasar un bloqueo de sala tratado como
cierre de sede o una cita atendida que deja de contar.
"""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modulos.agenda.modelos import BloqueoAgenda, Cita, EstadoCita, OrigenCita
from app.modulos.dashboard import ocupacion_agenda as modulo_ocupacion
from app.modulos.dashboard import repositorio as repositorio_dashboard
from app.modulos.organizacion.modelos import (
    Clinica,
    ConfiguracionClinica,
    Consultorio,
    Descanso,
    Feriado,
    HorarioAtencion,
    Sede,
    Servicio,
)
from app.modulos.pacientes.modelos import Paciente
from app.modulos.profesionales.modelos import AgendaPlantilla, Profesional, ProfesionalSede
from app.modulos.usuarios.modelos import Usuario
from pruebas.api.conftest import cabecera_bearer, conceder_permisos

DETALLE_CALCULADO = (
    "Citas activas, atendidas e inasistencias frente al horario disponible; "
    "descuenta pausas, feriados y bloqueos."
)
DETALLE_SIN_CAPACIDAD = "Sin horarios configurados para calcular capacidad en este periodo."
DETALLE_SIN_AGREGADO = "La ocupación se muestra a roles con acceso al agregado completo de agenda."
PERIODO = {"desde": "2026-04-15T14:00:00Z", "hasta": "2026-04-15T19:00:00Z"}
DIA = date(2026, 4, 15)


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
        "detalle": DETALLE_CALCULADO,
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


# ===========================================================================
#  Casos parametrizados con valores exactos
# ===========================================================================
@dataclass(frozen=True, slots=True)
class Escenario:
    sesion: AsyncSession
    clinica: Clinica
    sede: Sede
    otra_sede: Sede
    profesional: Profesional
    servicio: Servicio
    paciente: Paciente
    cita_base: Cita


def _utc(hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 4, 15, hora, minuto, tzinfo=UTC)


def _nueva_cita(
    *,
    clinica: Clinica,
    sede: Sede,
    paciente: Paciente,
    profesional: Profesional,
    servicio: Servicio,
    inicio: datetime,
    estado: EstadoCita,
) -> Cita:
    return Cita(
        clinica_id=clinica.id,
        sede_id=sede.id,
        paciente_id=paciente.id,
        profesional_id=profesional.id,
        servicio_id=servicio.id,
        inicio=inicio,
        duracion_minutos=30,
        minutos_preparacion=15,
        estado=estado.value,
        origen=OrigenCita.PANEL.value,
        motivo_cancelacion=(
            "Cancelacion sintetica de prueba" if estado is EstadoCita.CANCELLED else None
        ),
    )


def _cita(escenario: Escenario, sede: Sede, inicio: datetime, estado: EstadoCita) -> Cita:
    return _nueva_cita(
        clinica=escenario.clinica,
        sede=sede,
        paciente=escenario.paciente,
        profesional=escenario.profesional,
        servicio=escenario.servicio,
        inicio=inicio,
        estado=estado,
    )


async def _sin_cambios(_escenario: Escenario) -> None:
    return None


async def _feriado_de_clinica(escenario: Escenario) -> None:
    # Media jornada de 12:00 a 13:00 locales para toda la clinica.
    escenario.sesion.add(
        Feriado(
            clinica_id=escenario.clinica.id,
            fecha=DIA,
            nombre="Feriado sintetico de clinica",
            hora_inicio=time(12, 0),
            hora_fin=time(13, 0),
        )
    )


async def _feriado_de_sede(escenario: Escenario) -> None:
    escenario.sesion.add_all(
        [
            Feriado(
                clinica_id=escenario.clinica.id,
                sede_id=escenario.sede.id,
                fecha=DIA,
                nombre="Feriado sintetico de sede",
                hora_inicio=time(12, 0),
                hora_fin=time(13, 0),
            ),
            # El feriado de otra sede no toca esta agenda.
            Feriado(
                clinica_id=escenario.clinica.id,
                sede_id=escenario.otra_sede.id,
                fecha=DIA,
                nombre="Feriado sintetico de otra sede",
            ),
        ]
    )


async def _feriado_recurrente_de_dia_completo(escenario: Escenario) -> None:
    # Fecha de otro ano: el feriado recurrente se repite por dia y mes.
    escenario.sesion.add(
        Feriado(
            clinica_id=escenario.clinica.id,
            fecha=date(2020, 4, 15),
            nombre="Feriado sintetico recurrente",
            recurrente_anual=True,
        )
    )


async def _bloqueo_de_profesional(escenario: Escenario) -> None:
    # 10:00-11:00 locales: recorta la capacidad y tambien la cola de la cita
    # base (09:30-10:15), que solo cuenta dentro del horario disponible.
    escenario.sesion.add(
        BloqueoAgenda(
            clinica_id=escenario.clinica.id,
            sede_id=escenario.sede.id,
            profesional_id=escenario.profesional.id,
            tipo="AUSENCIA",
            inicio=_utc(15),
            fin=_utc(16),
        )
    )


async def _bloqueo_de_sede(escenario: Escenario) -> None:
    escenario.sesion.add(
        BloqueoAgenda(
            clinica_id=escenario.clinica.id,
            sede_id=escenario.sede.id,
            tipo="MANTENIMIENTO",
            inicio=_utc(17),
            fin=_utc(18),
        )
    )


async def _bloqueo_de_consultorio(escenario: Escenario) -> None:
    # Asi lo guarda la ruta de bloqueos: con `sede_id` y el consultorio.  Cerrar
    # una sala no cierra la sede; el panel no filtra por sala.
    sala = Consultorio(sede_id=escenario.sede.id, nombre="Sala sintetica")
    escenario.sesion.add(sala)
    await escenario.sesion.flush()
    escenario.sesion.add(
        BloqueoAgenda(
            clinica_id=escenario.clinica.id,
            sede_id=escenario.sede.id,
            consultorio_id=sala.id,
            tipo="MANTENIMIENTO",
            inicio=_utc(14),
            fin=_utc(16),
        )
    )


async def _plantilla_propia(escenario: Escenario) -> None:
    # La plantilla del profesional reemplaza el horario de la sede (10-12); la
    # pausa de la sede sigue aplicando.
    escenario.sesion.add(
        AgendaPlantilla(
            profesional_id=escenario.profesional.id,
            sede_id=escenario.sede.id,
            dia_semana=3,
            hora_inicio="10:00",
            hora_fin="12:00",
        )
    )


async def _profesional_en_dos_sedes(escenario: Escenario) -> None:
    # La otra sede tiene horario de 00:00 a 23:59 todos los dias (fixture) y
    # una cita de 12:00 a 12:45 locales.
    escenario.sesion.add(
        ProfesionalSede(profesional_id=escenario.profesional.id, sede_id=escenario.otra_sede.id)
    )
    escenario.sesion.add(
        _cita(escenario, escenario.otra_sede, _utc(17), EstadoCita.CONFIRMED),
    )


async def _completadas_e_inasistencias(escenario: Escenario) -> None:
    # Flujo normal al cerrar la jornada: la cita base queda atendida, otra
    # termina en inasistencia y una cancelada no ocupa nada.
    escenario.cita_base.estado = EstadoCita.COMPLETED.value
    escenario.sesion.add_all(
        [
            _cita(escenario, escenario.sede, _utc(17), EstadoCita.NO_SHOW),
            _cita(escenario, escenario.sede, _utc(15, 30), EstadoCita.CANCELLED),
        ]
    )


Preparar = Callable[[Escenario], Awaitable[None]]
Ambito = Callable[[Escenario], dict[str, Any]]


def _todas_las_sedes(_escenario: Escenario) -> dict[str, Any]:
    return {"todas_las_sedes": True}


def _solo_la_sede(escenario: Escenario) -> dict[str, Any]:
    return {"sedes": (escenario.sede.id,)}


CASOS: list[Any] = [
    pytest.param(_sin_cambios, _todas_las_sedes, (210, 45, 21.4), id="horario_de_sede"),
    pytest.param(_feriado_de_clinica, _todas_las_sedes, (150, 45, 30.0), id="feriado_de_clinica"),
    pytest.param(_feriado_de_sede, _todas_las_sedes, (150, 45, 30.0), id="feriado_de_sede"),
    pytest.param(
        _feriado_recurrente_de_dia_completo,
        _todas_las_sedes,
        (0, 0, None),
        id="feriado_recurrente_de_dia_completo",
    ),
    pytest.param(
        _bloqueo_de_profesional, _todas_las_sedes, (150, 30, 20.0), id="bloqueo_de_profesional"
    ),
    pytest.param(_bloqueo_de_sede, _todas_las_sedes, (150, 45, 30.0), id="bloqueo_de_sede"),
    pytest.param(
        _bloqueo_de_consultorio, _todas_las_sedes, (210, 45, 21.4), id="bloqueo_de_consultorio"
    ),
    pytest.param(_plantilla_propia, _todas_las_sedes, (90, 15, 16.7), id="plantilla_propia"),
    pytest.param(
        _profesional_en_dos_sedes,
        _todas_las_sedes,
        (300, 90, 30.0),
        id="dos_sedes_con_ambito_completo",
    ),
    pytest.param(
        _profesional_en_dos_sedes,
        _solo_la_sede,
        (210, 45, 21.4),
        id="ambito_de_sede_restringido",
    ),
    pytest.param(
        _completadas_e_inasistencias,
        _todas_las_sedes,
        (210, 90, 42.9),
        id="completadas_e_inasistencias",
    ),
]


async def _preparar_escenario(
    sesion: AsyncSession,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    profesional: Profesional,
    servicio: Servicio,
    paciente: Paciente,
) -> Escenario:
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
    cita_base = _nueva_cita(
        clinica=clinica,
        sede=sede,
        paciente=paciente,
        profesional=profesional,
        servicio=servicio,
        inicio=_utc(14, 30),
        estado=EstadoCita.CONFIRMED,
    )
    sesion.add(cita_base)
    await sesion.flush()
    return Escenario(
        sesion=sesion,
        clinica=clinica,
        sede=sede,
        otra_sede=otra_sede,
        profesional=profesional,
        servicio=servicio,
        paciente=paciente,
        cita_base=cita_base,
    )


@pytest.mark.api
@pytest.mark.asyncio
@pytest.mark.parametrize(("preparar", "ambito", "esperado"), CASOS)
async def test_ocupacion_descuenta_cierres_y_respeta_ambito_con_valores_exactos(
    api: str,
    cliente: AsyncClient,
    sesion: AsyncSession,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    profesional: Profesional,
    servicio: Servicio,
    paciente: Paciente,
    usuario: Usuario,
    preparar: Preparar,
    ambito: Ambito,
    esperado: tuple[int, int, float | None],
) -> None:
    escenario = await _preparar_escenario(
        sesion, clinica, sede, otra_sede, profesional, servicio, paciente
    )
    await preparar(escenario)
    await sesion.flush()
    await conceder_permisos(sesion, usuario, clinica, "dashboard.leer", **ambito(escenario))
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.get(f"{api}/dashboard/", params=PERIODO, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    disponibles, ocupados, porcentaje = esperado
    assert respuesta.json()["ocupacion_agenda"] == {
        "minutos_disponibles": disponibles,
        "minutos_ocupados": ocupados,
        "porcentaje": porcentaje,
        "detalle": DETALLE_CALCULADO if disponibles else DETALLE_SIN_CAPACIDAD,
    }


@pytest.mark.api
@pytest.mark.asyncio
async def test_sin_acceso_a_todos_los_pacientes_la_ocupacion_no_se_calcula(
    api: str,
    cliente: AsyncClient,
    sesion: AsyncSession,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    profesional: Profesional,
    servicio: Servicio,
    paciente: Paciente,
    usuario: Usuario,
) -> None:
    """Un ambito parcial de pacientes veria solo parte de las reservas.

    Con la capacidad completa y solo una parte de las citas, el porcentaje
    saldria por debajo del real; por eso se devuelven nulos y no un numero.
    """
    await _preparar_escenario(sesion, clinica, sede, otra_sede, profesional, servicio, paciente)
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "dashboard.leer",
        todas_las_sedes=True,
        todos_los_pacientes=False,
    )
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    respuesta = await cliente.get(f"{api}/dashboard/", params=PERIODO, headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ocupacion_agenda"] == {
        "minutos_disponibles": None,
        "minutos_ocupados": None,
        "porcentaje": None,
        "detalle": DETALLE_SIN_AGREGADO,
    }


# ===========================================================================
#  Los analisis no calculan una ocupacion que no usan
# ===========================================================================
@pytest.mark.api
@pytest.mark.asyncio
async def test_los_analisis_local_e_ia_no_calculan_la_ocupacion(
    api: str,
    cliente: AsyncClient,
    sesion: AsyncSession,
    aplicacion: Any,
    clinica: Clinica,
    sede: Sede,
    otra_sede: Sede,
    profesional: Profesional,
    servicio: Servicio,
    paciente: Paciente,
    usuario: Usuario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`generar_hallazgos` y el agregado para la IA no leen la ocupacion.

    Calcularla igualmente recorre cada dia del periodo por profesional, que es
    trabajo de CPU en el bucle de eventos sin ningun resultado visible.
    """
    llamadas: list[str] = []
    original = modulo_ocupacion.resumir_ocupacion_agenda

    async def _espia(*argumentos: Any, **opciones: Any) -> Any:
        llamadas.append("ocupacion")
        return await original(*argumentos, **opciones)

    monkeypatch.setattr(repositorio_dashboard, "resumir_ocupacion_agenda", _espia)

    class _MensajesSimulados:
        async def create(self, **argumentos: Any) -> Any:
            agregado = json.loads(argumentos["messages"][0]["content"])
            assert "ocupacion_agenda" not in agregado
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="Resumen sintético.")])

    class _ClienteSimulado:
        def __init__(self, **_argumentos: Any) -> None:
            self.messages = _MensajesSimulados()

        async def __aenter__(self) -> _ClienteSimulado:
            return self

        async def __aexit__(self, *_argumentos: Any) -> None:
            return None

    modulo_anthropic: Any = types.ModuleType("anthropic")
    modulo_anthropic.AsyncAnthropic = _ClienteSimulado
    monkeypatch.setitem(sys.modules, "anthropic", modulo_anthropic)

    await _preparar_escenario(sesion, clinica, sede, otra_sede, profesional, servicio, paciente)
    await conceder_permisos(
        sesion,
        usuario,
        clinica,
        "dashboard.leer",
        "configuracion.escribir",
        todas_las_sedes=True,
    )
    clave = aplicacion.state.cifrador.cifrar(
        "clave-sintetica-sin-uso-externo",
        contexto=b"integracion:" + clinica.id.bytes + b":anthropic:api_key",
    )
    sesion.add(
        ConfiguracionClinica(
            clinica_id=clinica.id,
            clave="integracion.anthropic",
            valor={
                "habilitada": True,
                "secretos_cifrados": {"api_key": clave},
                "ajustes": {"modelo": "modelo-simulado"},
            },
            version=1,
            vigente=True,
        )
    )
    await sesion.flush()
    cabeceras = await cabecera_bearer(cliente, usuario, clinica)

    local = await cliente.post(f"{api}/dashboard/analisis-local", params=PERIODO, headers=cabeceras)
    assert local.status_code == 200, local.text
    ia = await cliente.post(f"{api}/dashboard/analisis-ia", params=PERIODO, headers=cabeceras)
    assert ia.status_code == 200, ia.text
    assert llamadas == []

    # Control: el resumen del panel si la calcula, con el mismo espia.
    panel = await cliente.get(f"{api}/dashboard/", params=PERIODO, headers=cabeceras)
    assert panel.status_code == 200, panel.text
    assert llamadas == ["ocupacion"]
    assert panel.json()["ocupacion_agenda"]["minutos_disponibles"] == 210
