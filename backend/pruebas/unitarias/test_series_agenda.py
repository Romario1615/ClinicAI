"""Reglas de fechas para la recurrencia de citas en la zona de la sede."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import get_args
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.modulos.agenda.disponibilidad import (
    FranjaLocal,
    Intervalo,
    MotivoNoDisponible,
    Ocupacion,
    calcular_disponibilidad,
    calcular_huecos_libres,
)
from app.modulos.agenda.esquemas import (
    MAXIMO_CITAS_SERIE_POR_FRECUENCIA,
    SEMANAS_ENTRE_CITAS_SERIE,
    FrecuenciaSerieCitas,
    PeticionSerieReserva,
)
from app.modulos.agenda.servicios import generar_instantes_serie
from app.nucleo.errores import ReglaNegocioViolada

pytestmark = pytest.mark.unitaria

GUAYAQUIL = "America/Guayaquil"


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


def test_mensual_repite_el_mismo_dia_de_la_semana_cada_cuatro_semanas() -> None:
    """MENSUAL = cada 28 días, no el mismo número de día de cada mes.

    Sustituye a la prueba anterior, que fijaba «mismo número de día o el
    último del mes»: con esa semántica el lunes 12/10 seguía en jueves 12/11,
    sábado 12/12 y martes 12/01, días que las franjas semanales no cubren.
    """
    inicio = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo(GUAYAQUIL))

    instantes = generar_instantes_serie(inicio, GUAYAQUIL, "MENSUAL", 4)
    locales = [instante.astimezone(ZoneInfo(GUAYAQUIL)) for instante in instantes]

    assert [local.date().isoformat() for local in locales] == [
        "2026-10-12",
        "2026-11-09",
        "2026-12-07",
        "2027-01-04",
    ]
    assert {local.isoweekday() for local in locales} == {1}
    assert {(local.hour, local.minute) for local in locales} == {(10, 0)}


@pytest.mark.parametrize("dia_inicial", [date(2026, 10, 12) + timedelta(days=n) for n in range(5)])
def test_mensual_empezando_entre_semana_nunca_cae_en_fin_de_semana(dia_inicial: date) -> None:
    """Con franjas de lunes a viernes, ninguna fecha de la serie sale de ellas."""
    inicio = datetime.combine(dia_inicial, time(9, 30), tzinfo=ZoneInfo(GUAYAQUIL))

    instantes = generar_instantes_serie(
        inicio, GUAYAQUIL, "MENSUAL", MAXIMO_CITAS_SERIE_POR_FRECUENCIA["MENSUAL"]
    )

    dias = {instante.astimezone(ZoneInfo(GUAYAQUIL)).isoweekday() for instante in instantes}
    assert dias == {dia_inicial.isoweekday()}


def test_rechaza_una_ocurrencia_que_caeria_en_una_hora_inexistente() -> None:
    # Domingo 08/02/2026 02:30 + 4 semanas = domingo 08/03/2026, día del salto
    # de horario en Nueva York: las 02:30 locales no existen.
    inicio = datetime(2026, 2, 8, 2, 30, tzinfo=ZoneInfo("America/New_York"))

    with pytest.raises(ReglaNegocioViolada, match="hora local inexistente"):
        generar_instantes_serie(inicio, "America/New_York", "MENSUAL", 2)


def test_limita_las_series_mensuales_a_un_ano() -> None:
    inicio = datetime(2026, 1, 10, 10, 0, tzinfo=UTC)

    with pytest.raises(ReglaNegocioViolada, match="superar un año"):
        generar_instantes_serie(inicio, "America/Guayaquil", "MENSUAL", 14)


# ---------------------------------------------------------------------------
#  Tabla única de máximos por frecuencia
# ---------------------------------------------------------------------------
def test_la_tabla_de_maximos_cubre_exactamente_las_frecuencias_admitidas() -> None:
    frecuencias = set(get_args(FrecuenciaSerieCitas))
    assert set(MAXIMO_CITAS_SERIE_POR_FRECUENCIA) == frecuencias
    assert set(SEMANAS_ENTRE_CITAS_SERIE) == frecuencias
    # Los números que replica la interfaz (maximoCitasSerie).
    assert dict(MAXIMO_CITAS_SERIE_POR_FRECUENCIA) == {
        "SEMANAL": 53,
        "QUINCENAL": 27,
        "MENSUAL": 13,
    }


@pytest.mark.parametrize("frecuencia", ["SEMANAL", "QUINCENAL", "MENSUAL"])
def test_el_maximo_de_cada_frecuencia_cabe_en_un_ano(frecuencia: str) -> None:
    inicio = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo(GUAYAQUIL))
    maximo = MAXIMO_CITAS_SERIE_POR_FRECUENCIA[frecuencia]

    instantes = generar_instantes_serie(inicio, GUAYAQUIL, frecuencia, maximo)

    assert len(instantes) == maximo
    assert instantes[-1] - instantes[0] < timedelta(days=365)


@pytest.mark.parametrize("frecuencia", ["SEMANAL", "QUINCENAL", "MENSUAL"])
def test_una_cita_mas_que_el_maximo_se_rechaza_en_el_servicio(frecuencia: str) -> None:
    inicio = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo(GUAYAQUIL))

    with pytest.raises(ReglaNegocioViolada, match="superar un año"):
        generar_instantes_serie(
            inicio, GUAYAQUIL, frecuencia, MAXIMO_CITAS_SERIE_POR_FRECUENCIA[frecuencia] + 1
        )


def test_quincenal_admite_27_y_rechaza_28_en_el_servicio() -> None:
    """Antes aceptaba 53: dos años de citas pese a anunciar un año."""
    inicio = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo(GUAYAQUIL))

    assert len(generar_instantes_serie(inicio, GUAYAQUIL, "QUINCENAL", 27)) == 27
    with pytest.raises(ReglaNegocioViolada, match="superar un año"):
        generar_instantes_serie(inicio, GUAYAQUIL, "QUINCENAL", 28)


def test_una_sola_cita_no_es_una_serie() -> None:
    inicio = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo(GUAYAQUIL))

    with pytest.raises(ReglaNegocioViolada, match="al menos 2"):
        generar_instantes_serie(inicio, GUAYAQUIL, "SEMANAL", 1)


def _peticion(frecuencia: str, cantidad: int) -> dict[str, object]:
    return {
        "paciente_id": str(uuid.uuid4()),
        "profesional_id": str(uuid.uuid4()),
        "servicio_id": str(uuid.uuid4()),
        "sede_id": str(uuid.uuid4()),
        "inicio": "2026-10-12T10:00:00-05:00",
        "frecuencia": frecuencia,
        "cantidad": cantidad,
    }


@pytest.mark.parametrize(
    ("frecuencia", "maximo"),
    [("SEMANAL", 53), ("QUINCENAL", 27), ("MENSUAL", 13)],
)
def test_el_esquema_usa_la_misma_tabla_de_maximos(frecuencia: str, maximo: int) -> None:
    aceptada = PeticionSerieReserva.model_validate(_peticion(frecuencia, maximo))
    assert aceptada.cantidad == maximo

    with pytest.raises(ValidationError):
        PeticionSerieReserva.model_validate(_peticion(frecuencia, maximo + 1))


# ---------------------------------------------------------------------------
#  Huecos libres frente a rejilla de turnos
# ---------------------------------------------------------------------------
def test_un_horario_libre_fuera_de_la_rejilla_cabe_en_los_huecos() -> None:
    """Reproduce el hallazgo: la rejilla depende de las citas de cada día.

    Franja de lunes 09:00-13:00, servicio de 30 + 10 minutos, granularidad 15
    y una cita previa el 12/10 de 09:00 a 10:10.  El 12/10 se ofrecen 10:15,
    11:00 y 11:45; el 19/10, sin citas, 09:00, 09:45, 10:30, 11:15 y 12:00.
    Las 10:15 del 19/10 no son un turno ofrecido, pero están libres: la serie
    debe comprobar contención en los huecos, no pertenencia a la rejilla.
    """
    tz = ZoneInfo(GUAYAQUIL)
    franjas = [FranjaLocal(dia_semana=1, hora_inicio=time(9), hora_fin=time(13))]
    cita_previa = Ocupacion(
        Intervalo(
            datetime(2026, 10, 12, 9, 0, tzinfo=tz),
            datetime(2026, 10, 12, 10, 10, tzinfo=tz),
        ),
        MotivoNoDisponible.CITA_EXISTENTE,
    )
    desde = datetime(2026, 10, 12, tzinfo=tz)
    hasta = datetime(2026, 10, 20, tzinfo=tz)

    turnos = calcular_disponibilidad(
        desde=desde,
        hasta=hasta,
        zona=GUAYAQUIL,
        franjas=franjas,
        duracion_minutos=30,
        minutos_preparacion=10,
        granularidad_minutos=15,
        ocupaciones=[cita_previa],
    )
    ofrecidos = {turno.inicio.astimezone(tz).replace(tzinfo=None) for turno in turnos.turnos}
    assert datetime(2026, 10, 12, 10, 15) in ofrecidos
    assert datetime(2026, 10, 19, 10, 15) not in ofrecidos

    huecos = calcular_huecos_libres(
        desde=desde, hasta=hasta, zona=GUAYAQUIL, franjas=franjas, ocupaciones=[cita_previa]
    )
    assert [(h.inicio.astimezone(tz).time(), h.fin.astimezone(tz).time()) for h in huecos] == [
        (time(10, 10), time(13, 0)),
        (time(9, 0), time(13, 0)),
    ]
    for dia in (12, 19):
        inicio = datetime(2026, 10, dia, 10, 15, tzinfo=tz)
        cita = Intervalo(inicio, inicio + timedelta(minutes=40))
        assert any(hueco.contiene(cita) for hueco in huecos)

    # Y lo ocupado sigue sin caber.
    pisa_la_cita = Intervalo(
        datetime(2026, 10, 12, 9, 45, tzinfo=tz), datetime(2026, 10, 12, 10, 25, tzinfo=tz)
    )
    assert not any(hueco.contiene(pisa_la_cita) for hueco in huecos)
