"""Reglas de fechas para la recurrencia de citas en la zona de la sede."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.modulos.agenda.servicios import generar_instantes_serie
from app.nucleo.errores import ReglaNegocioViolada


def test_semanal_conserva_la_hora_local_al_cruzar_el_horario_de_verano() -> None:
    inicio = datetime(2026, 3, 1, 9, 0, tzinfo=ZoneInfo("America/New_York"))

    instantes = generar_instantes_serie(inicio, "America/New_York", "SEMANAL", 3)
    locales = [instante.astimezone(ZoneInfo("America/New_York")) for instante in instantes]

    assert [instante.hour for instante in locales] == [9, 9, 9]
    assert [instante.utcoffset() for instante in locales] == [
        timedelta(hours=-5),
        timedelta(hours=-4),
        timedelta(hours=-4),
    ]
    assert all(instante.tzinfo is UTC for instante in instantes)


def test_mensual_mantiene_el_dia_y_usa_el_ultimo_dia_si_el_mes_es_mas_corto() -> None:
    inicio = datetime(2026, 1, 31, 10, 0, tzinfo=ZoneInfo("America/Guayaquil"))

    instantes = generar_instantes_serie(inicio, "America/Guayaquil", "MENSUAL", 4)

    assert [
        instante.astimezone(ZoneInfo("America/Guayaquil")).date().isoformat()
        for instante in instantes
    ] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
        "2026-04-30",
    ]


def test_rechaza_una_ocurrencia_que_caeria_en_una_hora_inexistente() -> None:
    inicio = datetime(2026, 2, 8, 2, 30, tzinfo=ZoneInfo("America/New_York"))

    with pytest.raises(ReglaNegocioViolada, match="hora local inexistente"):
        generar_instantes_serie(inicio, "America/New_York", "MENSUAL", 2)


def test_limita_las_series_mensuales_a_un_ano() -> None:
    inicio = datetime(2026, 1, 10, 10, 0, tzinfo=UTC)

    with pytest.raises(ReglaNegocioViolada, match="superar un año"):
        generar_instantes_serie(inicio, "America/Guayaquil", "MENSUAL", 14)
