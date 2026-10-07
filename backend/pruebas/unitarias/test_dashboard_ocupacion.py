"""El porcentaje de ocupacion parte de intervalos de agenda verificables."""

from datetime import UTC, datetime

from app.modulos.agenda.disponibilidad import Intervalo
from app.modulos.dashboard.ocupacion import resumir_intervalos_ocupacion


def _intervalo(hora_inicio: int, minuto_inicio: int, hora_fin: int, minuto_fin: int) -> Intervalo:
    dia = datetime(2026, 10, 7, tzinfo=UTC)
    return Intervalo(
        dia.replace(hour=hora_inicio, minute=minuto_inicio),
        dia.replace(hour=hora_fin, minute=minuto_fin),
    )


def test_recorta_reservas_al_horario_y_no_cuenta_dos_veces_sedes_solapadas() -> None:
    disponibles = [
        _intervalo(8, 0, 12, 0),
        _intervalo(11, 0, 14, 0),
    ]
    reservas = [
        _intervalo(7, 30, 9, 0),
        _intervalo(9, 0, 10, 30),
        _intervalo(13, 30, 15, 0),
    ]

    assert resumir_intervalos_ocupacion(disponibles, reservas) == (360, 180, 50.0)


def test_periodo_sin_horario_no_inventa_porcentaje() -> None:
    assert resumir_intervalos_ocupacion([], [_intervalo(8, 0, 9, 0)]) == (0, 0, None)
