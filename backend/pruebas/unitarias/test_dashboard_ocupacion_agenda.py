"""Capacidad del indicador de ocupacion: bloqueos por dia, sin recorrer todo el periodo."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.modulos.agenda.disponibilidad import FranjaLocal, Intervalo
from app.modulos.dashboard import ocupacion_agenda
from app.modulos.dashboard.esquemas import FiltroDashboard
from app.modulos.dashboard.ocupacion import unir_intervalos

pytestmark = pytest.mark.unitaria

ZONA = "America/Guayaquil"
# Lunes 5 de octubre de 2026, 00:00 locales (UTC-5).
INICIO = datetime(2026, 10, 5, 5, 0, tzinfo=UTC)


def _horario_laborable() -> list[FranjaLocal]:
    return [
        FranjaLocal(
            dia_semana=dia,
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            granularidad_minutos=15,
            vigente_desde=None,
            vigente_hasta=None,
        )
        for dia in range(1, 6)
    ]


def _bloqueo(
    inicio: datetime,
    fin: datetime,
    *,
    profesional_id: uuid.UUID | None = None,
    sede_id: uuid.UUID | None = None,
    consultorio_id: uuid.UUID | None = None,
) -> Any:
    return SimpleNamespace(
        inicio=inicio,
        fin=fin,
        profesional_id=profesional_id,
        sede_id=sede_id,
        consultorio_id=consultorio_id,
    )


def _capacidad(
    profesional: uuid.UUID, sede: uuid.UUID, bloqueos: list[Any], dias: int
) -> list[Intervalo]:
    resultado = ocupacion_agenda._disponibles_por_profesional(
        pares={(profesional, sede): ZONA},
        plantillas={},
        horarios_sede={sede: _horario_laborable()},
        descansos_sede={},
        feriados_clinica=[],
        feriados_sede={},
        bloqueos=bloqueos,
        filtro=FiltroDashboard(desde=INICIO, hasta=INICIO + timedelta(days=dias)),
    )
    return unir_intervalos(resultado.get(profesional, []))


def _minutos(intervalos: list[Intervalo]) -> int:
    return sum(int(i.duracion.total_seconds() // 60) for i in intervalos)


def test_selecciona_solo_los_bloqueos_que_solapan_la_ventana() -> None:
    hora = timedelta(hours=1)
    ordenados = ocupacion_agenda._BloqueosOrdenados(
        [
            Intervalo(INICIO, INICIO + hora),
            # Se toca con el anterior: quedan fusionados en uno solo.
            Intervalo(INICIO + hora, INICIO + 2 * hora),
            Intervalo(INICIO + 5 * hora, INICIO + 50 * hora),
            Intervalo(INICIO + 60 * hora, INICIO + 61 * hora),
        ]
    )

    # Semiabierto: un bloqueo que termina justo cuando empieza la ventana no la toca.
    assert ordenados.que_solapan(Intervalo(INICIO + 2 * hora, INICIO + 5 * hora)) == []
    assert ordenados.que_solapan(Intervalo(INICIO + hora, INICIO + 3 * hora)) == [
        Intervalo(INICIO, INICIO + 2 * hora)
    ]
    # Un bloqueo de varios dias aparece en cada dia que cubre.
    assert ordenados.que_solapan(Intervalo(INICIO + 30 * hora, INICIO + 31 * hora)) == [
        Intervalo(INICIO + 5 * hora, INICIO + 50 * hora)
    ]
    assert ordenados.que_solapan(Intervalo(INICIO + 49 * hora, INICIO + 61 * hora)) == [
        Intervalo(INICIO + 5 * hora, INICIO + 50 * hora),
        Intervalo(INICIO + 60 * hora, INICIO + 61 * hora),
    ]


def test_cada_dia_recibe_solo_sus_bloqueos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con un bloqueo por dia durante un ano, cada dia resta uno, no 365.

    Antes cada dia recorria todos los bloqueos del periodo y `restar` los
    fusionaba de nuevo: el coste crecia con pares por dias por bloqueos.
    """
    profesional, sede = uuid.uuid4(), uuid.uuid4()
    bloqueos = [
        _bloqueo(
            INICIO + timedelta(days=dia, hours=14),
            INICIO + timedelta(days=dia, hours=15),
            profesional_id=profesional,
            sede_id=sede,
        )
        for dia in range(365)
    ]
    tamanos: list[int] = []
    restar_original = ocupacion_agenda.restar

    def _restar_espia(base: Any, cierres: Any) -> Any:
        tamanos.append(len(cierres))
        return restar_original(base, cierres)

    monkeypatch.setattr(ocupacion_agenda, "restar", _restar_espia)

    capacidad = _capacidad(profesional, sede, bloqueos, dias=365)

    assert tamanos, "Debe haber dias laborables en el periodo."
    assert max(tamanos) == 1
    # 261 dias laborables de 10 h, menos 1 h de bloqueo en cada uno.
    assert _minutos(capacidad) == 261 * 9 * 60


def test_bloqueo_de_sala_no_resta_y_el_de_sede_si() -> None:
    profesional, sede, otra_sede = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lunes_9 = INICIO + timedelta(hours=9)
    lunes_11 = INICIO + timedelta(hours=11)

    sin_bloqueos = _minutos(_capacidad(profesional, sede, [], dias=1))
    de_sala = _capacidad(
        profesional,
        sede,
        [_bloqueo(lunes_9, lunes_11, sede_id=sede, consultorio_id=uuid.uuid4())],
        dias=1,
    )
    de_otra_sede = _capacidad(
        profesional, sede, [_bloqueo(lunes_9, lunes_11, sede_id=otra_sede)], dias=1
    )
    de_sede = _capacidad(profesional, sede, [_bloqueo(lunes_9, lunes_11, sede_id=sede)], dias=1)

    assert sin_bloqueos == 600
    assert _minutos(de_sala) == 600
    assert _minutos(de_otra_sede) == 600
    assert _minutos(de_sede) == 480
