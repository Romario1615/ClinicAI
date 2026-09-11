"""Pruebas del reloj inyectable.

Las fechas son la fuente de errores mas silenciosa de una agenda medica: un
desfase de una hora no rompe nada visiblemente, solo hace que el paciente
llegue tarde.  Estas pruebas fijan el contrato del ADR-0010.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.nucleo.reloj import Reloj, RelojFijo, RelojSistema

pytestmark = pytest.mark.unitaria

GUAYAQUIL = "America/Guayaquil"


class TestRelojSistema:
    def test_devuelve_instante_con_zona(self) -> None:
        """Un instante sin zona en una agenda medica desplaza citas."""
        ahora = RelojSistema().ahora()
        assert ahora.tzinfo is not None
        assert ahora.utcoffset() == timedelta(0)

    def test_es_un_reloj(self) -> None:
        assert isinstance(RelojSistema(), Reloj)


class TestRelojFijo:
    def test_devuelve_siempre_el_mismo_instante(self) -> None:
        instante = datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
        reloj = RelojFijo(instante)
        assert reloj.ahora() == instante
        assert reloj.ahora() == instante

    def test_rechaza_instante_sin_zona(self) -> None:
        """Construirlo con un instante ambiguo debe fallar de inmediato."""
        with pytest.raises(ValueError, match="zona horaria"):
            RelojFijo(datetime(2026, 4, 15, 14, 0))

    def test_normaliza_a_utc(self) -> None:
        """Se acepta cualquier zona de entrada, pero se almacena en UTC."""
        local = datetime(2026, 4, 15, 9, 0, tzinfo=ZoneInfo(GUAYAQUIL))
        reloj = RelojFijo(local)
        assert reloj.ahora() == datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
        assert reloj.ahora().tzinfo == UTC

    def test_avanzar_mueve_el_reloj(self) -> None:
        """Es lo que permite probar expiraciones sin esperar en tiempo real."""
        reloj = RelojFijo(datetime(2026, 4, 15, 14, 0, tzinfo=UTC))
        reloj.avanzar(minutes=11)
        assert reloj.ahora() == datetime(2026, 4, 15, 14, 11, tzinfo=UTC)

    def test_avanzar_acepta_varias_unidades(self) -> None:
        reloj = RelojFijo(datetime(2026, 4, 15, 14, 0, tzinfo=UTC))
        reloj.avanzar(days=1, hours=2, minutes=30)
        assert reloj.ahora() == datetime(2026, 4, 16, 16, 30, tzinfo=UTC)

    def test_fijar_reemplaza_el_instante(self) -> None:
        reloj = RelojFijo(datetime(2026, 4, 15, 14, 0, tzinfo=UTC))
        reloj.fijar(datetime(2026, 12, 31, 23, 59, tzinfo=UTC))
        assert reloj.ahora().year == 2026
        assert reloj.ahora().month == 12

    def test_fijar_rechaza_instante_sin_zona(self) -> None:
        reloj = RelojFijo(datetime(2026, 4, 15, 14, 0, tzinfo=UTC))
        with pytest.raises(ValueError, match="zona horaria"):
            reloj.fijar(datetime(2026, 4, 16, 10, 0))


class TestZonasHorarias:
    def test_guayaquil_va_cinco_horas_por_detras(self) -> None:
        """Ecuador esta en UTC-5 y no aplica horario de verano."""
        reloj = RelojFijo(datetime(2026, 4, 15, 14, 0, tzinfo=UTC))
        local = reloj.ahora_en(GUAYAQUIL)
        assert local.hour == 9
        assert local.utcoffset() == timedelta(hours=-5)

    def test_ecuador_no_cambia_en_verano_ni_invierno(self) -> None:
        """Se comprueba en enero y en julio: el desplazamiento no varia.

        Importa porque el modelo de datos admite mas sedes, y la logica no
        debe asumir que ninguna cambia de horario.
        """
        for mes in (1, 7):
            reloj = RelojFijo(datetime(2026, mes, 15, 14, 0, tzinfo=UTC))
            assert reloj.ahora_en(GUAYAQUIL).utcoffset() == timedelta(hours=-5)

    def test_fecha_local_puede_diferir_de_la_fecha_utc(self) -> None:
        """A las 02:00 UTC en Guayaquil sigue siendo el dia anterior.

        Confundir ambas fechas desplaza un dia entero la agenda y los
        feriados.  Es el error de zona horaria mas costoso de esta clase.
        """
        reloj = RelojFijo(datetime(2026, 4, 16, 2, 0, tzinfo=UTC))
        assert reloj.ahora().date() == date(2026, 4, 16)
        assert reloj.hoy_en(GUAYAQUIL) == date(2026, 4, 15)

    def test_medianoche_local_es_las_cinco_utc(self) -> None:
        reloj = RelojFijo(datetime(2026, 4, 16, 5, 0, tzinfo=UTC))
        local = reloj.ahora_en(GUAYAQUIL)
        assert local.hour == 0
        assert local.date() == date(2026, 4, 16)

    def test_zona_con_horario_de_verano_se_maneja(self) -> None:
        """Madrid cambia de horario; el reloj debe reflejarlo correctamente."""
        invierno = RelojFijo(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        verano = RelojFijo(datetime(2026, 7, 15, 12, 0, tzinfo=UTC))
        assert invierno.ahora_en("Europe/Madrid").utcoffset() == timedelta(hours=1)
        assert verano.ahora_en("Europe/Madrid").utcoffset() == timedelta(hours=2)

    def test_zona_invalida_lanza(self) -> None:
        reloj = RelojFijo(datetime(2026, 4, 15, 14, 0, tzinfo=UTC))
        with pytest.raises(Exception, match=r"No time zone found|Guayaquill"):
            reloj.ahora_en("America/Guayaquill")
