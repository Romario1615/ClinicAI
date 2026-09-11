"""Pruebas del motor de disponibilidad.

Dos estrategias complementarias:

* **Casos concretos** para las reglas de negocio: que un feriado bloquee el
  dia, que el buffer ocupe el turno siguiente, que la antelacion minima
  descarte lo inmediato.
* **Propiedades con Hypothesis** para las invariantes que deben cumplirse con
  CUALQUIER combinacion de horarios, descansos y citas.  Es donde aparecen los
  errores que un caso escrito a mano no cubre: un descanso que empieza justo
  al cerrar, una cita que sobresale de la franja, una granularidad que no
  divide la jornada.

Las invariantes que se verifican son las que hacen util una agenda:

1. Ningun turno ofrecido se solapa con otro.
2. Ningun turno pisa una ocupacion.
3. Todo turno cae dentro de una franja de atencion.
4. Todo turno cae dentro del rango solicitado.
5. La duracion de cada turno es exactamente la esperada.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.modulos.agenda.disponibilidad import (
    DescansoLocal,
    FeriadoLocal,
    FranjaLocal,
    Intervalo,
    MotivoNoDisponible,
    Ocupacion,
    calcular_disponibilidad,
    generar_turnos_en_hueco,
    granularidad_incompatible,
    hay_solapamiento,
    proyectar_feriados,
    proyectar_franjas,
    restar,
)

pytestmark = pytest.mark.unitaria

GUAYAQUIL = "America/Guayaquil"
MADRID = "Europe/Madrid"

# Miercoles 15 de abril de 2026.  Se elige un miercoles laborable para que
# caiga dentro de cualquier horario de atencion razonable.
MIERCOLES = date(2026, 4, 15)
MIERCOLES_ISO = 3


def _rango_del_dia(dia: date, zona: str = GUAYAQUIL) -> tuple[datetime, datetime]:
    """Rango que cubre un dia local completo, en instantes absolutos."""
    tz = ZoneInfo(zona)
    inicio = datetime.combine(dia, time(0, 0), tzinfo=tz)
    return inicio, inicio + timedelta(days=1)


def _franja(
    hora_inicio: int = 8,
    hora_fin: int = 13,
    *,
    dia: int = MIERCOLES_ISO,
    granularidad: int = 15,
) -> FranjaLocal:
    return FranjaLocal(
        dia_semana=dia,
        hora_inicio=time(hora_inicio, 0),
        hora_fin=time(hora_fin, 0),
        granularidad_minutos=granularidad,
    )


def _instante(dia: date, hora: int, minuto: int = 0, zona: str = GUAYAQUIL) -> datetime:
    return datetime.combine(dia, time(hora, minuto), tzinfo=ZoneInfo(zona))


# ===========================================================================
#  Operaciones sobre intervalos
# ===========================================================================
class TestIntervalo:
    def test_exige_zona_horaria(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            Intervalo(
                datetime(2026, 4, 15, 8, 0),
                datetime(2026, 4, 15, 9, 0, tzinfo=UTC),
            )

    def test_exige_duracion_positiva(self) -> None:
        instante = datetime(2026, 4, 15, 8, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="no tiene duracion"):
            Intervalo(instante, instante)

    def test_los_intervalos_son_semiabiertos(self) -> None:
        """Dos intervalos consecutivos NO se solapan.

        Con intervalos cerrados, una cita que acaba a las 10:00 y otra que
        empieza a las 10:00 colisionarian, y la agenda perderia un turno
        entre cada par de citas.
        """
        primero = Intervalo(_instante(MIERCOLES, 9), _instante(MIERCOLES, 10))
        segundo = Intervalo(_instante(MIERCOLES, 10), _instante(MIERCOLES, 11))
        assert not primero.se_solapa_con(segundo)
        assert not segundo.se_solapa_con(primero)

    @pytest.mark.parametrize(
        ("inicio_b", "fin_b", "se_solapa"),
        [
            (9, 10, True),  # identicos
            (9, 11, True),  # b contiene a a
            (8, 12, True),  # b envuelve a a
            (9, 10, True),  # identicos
            (8, 9, False),  # b acaba cuando a empieza
            (10, 11, False),  # b empieza cuando a acaba
            (11, 12, False),  # separados
        ],
    )
    def test_solapamiento(self, inicio_b: int, fin_b: int, se_solapa: bool) -> None:
        a = Intervalo(_instante(MIERCOLES, 9), _instante(MIERCOLES, 10))
        b = Intervalo(_instante(MIERCOLES, inicio_b), _instante(MIERCOLES, fin_b))
        assert a.se_solapa_con(b) is se_solapa


class TestRestar:
    def test_sin_ocupaciones_devuelve_la_base(self) -> None:
        base = [Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 13))]
        assert restar(base, []) == base

    def test_una_ocupacion_en_el_medio_parte_el_hueco(self) -> None:
        base = [Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 13))]
        ocupado = [Intervalo(_instante(MIERCOLES, 10), _instante(MIERCOLES, 11))]
        resultado = restar(base, ocupado)
        assert len(resultado) == 2
        assert resultado[0].fin == _instante(MIERCOLES, 10)
        assert resultado[1].inicio == _instante(MIERCOLES, 11)

    def test_una_ocupacion_que_cubre_todo_no_deja_nada(self) -> None:
        base = [Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 13))]
        ocupado = [Intervalo(_instante(MIERCOLES, 7), _instante(MIERCOLES, 14))]
        assert restar(base, ocupado) == []

    def test_ocupaciones_contiguas_se_fusionan(self) -> None:
        """Dos bloqueos seguidos no deben dejar un hueco de cero minutos."""
        base = [Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 13))]
        ocupado = [
            Intervalo(_instante(MIERCOLES, 9), _instante(MIERCOLES, 10)),
            Intervalo(_instante(MIERCOLES, 10), _instante(MIERCOLES, 11)),
        ]
        resultado = restar(base, ocupado)
        assert len(resultado) == 2
        assert resultado[0] == Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 9))
        assert resultado[1] == Intervalo(_instante(MIERCOLES, 11), _instante(MIERCOLES, 13))

    def test_el_orden_de_las_ocupaciones_no_altera_el_resultado(self) -> None:
        """El resultado debe ser determinista.

        Las ocupaciones llegan de consultas distintas (citas, bloqueos,
        descansos) y su orden no esta garantizado.
        """
        base = [Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 18))]
        ocupaciones = [
            Intervalo(_instante(MIERCOLES, 14), _instante(MIERCOLES, 15)),
            Intervalo(_instante(MIERCOLES, 9), _instante(MIERCOLES, 10)),
            Intervalo(_instante(MIERCOLES, 11), _instante(MIERCOLES, 12)),
        ]
        assert restar(base, ocupaciones) == restar(base, list(reversed(ocupaciones)))


# ===========================================================================
#  Proyeccion de reglas locales
# ===========================================================================
class TestProyeccion:
    def test_la_franja_se_proyecta_a_la_hora_local_correcta(self) -> None:
        intervalos = proyectar_franjas([_franja(8, 13)], dia=MIERCOLES, zona=GUAYAQUIL)
        assert len(intervalos) == 1
        # 08:00 en Guayaquil (UTC-5) son las 13:00 UTC.
        assert intervalos[0].inicio == datetime(2026, 4, 15, 13, 0, tzinfo=UTC)
        assert intervalos[0].fin == datetime(2026, 4, 15, 18, 0, tzinfo=UTC)

    def test_una_franja_de_otro_dia_no_se_proyecta(self) -> None:
        # Lunes, y se pide el miercoles.
        assert proyectar_franjas([_franja(dia=1)], dia=MIERCOLES, zona=GUAYAQUIL) == []

    def test_la_vigencia_se_respeta(self) -> None:
        franja = FranjaLocal(
            dia_semana=MIERCOLES_ISO,
            hora_inicio=time(8, 0),
            hora_fin=time(13, 0),
            vigente_desde=date(2026, 5, 1),
        )
        assert proyectar_franjas([franja], dia=MIERCOLES, zona=GUAYAQUIL) == []

    def test_las_franjas_contiguas_se_fusionan(self) -> None:
        """08:00-12:00 y 12:00-17:00 son una jornada continua.

        Sin fusionar, la frontera partiria un turno que cabria a caballo de
        las dos y la agenda perderia capacidad sin motivo.
        """
        intervalos = proyectar_franjas(
            [_franja(8, 12), _franja(12, 17)], dia=MIERCOLES, zona=GUAYAQUIL
        )
        assert len(intervalos) == 1
        assert intervalos[0].duracion == timedelta(hours=9)

    def test_el_feriado_de_dia_completo_cubre_el_dia_local(self) -> None:
        ocupaciones = proyectar_feriados(
            [FeriadoLocal(MIERCOLES, "Prueba")], dia=MIERCOLES, zona=GUAYAQUIL
        )
        assert len(ocupaciones) == 1
        intervalo = ocupaciones[0].intervalo
        assert intervalo.inicio == _instante(MIERCOLES, 0)
        assert intervalo.fin == _instante(MIERCOLES + timedelta(days=1), 0)
        assert intervalo.duracion == timedelta(days=1)

    def test_el_feriado_recurrente_aplica_cualquier_ano(self) -> None:
        feriado = FeriadoLocal(date(2020, 4, 15), "Recurrente", recurrente_anual=True)
        assert proyectar_feriados([feriado], dia=MIERCOLES, zona=GUAYAQUIL)

    def test_el_feriado_no_recurrente_solo_su_fecha(self) -> None:
        feriado = FeriadoLocal(date(2020, 4, 15), "Puntual")
        assert not proyectar_feriados([feriado], dia=MIERCOLES, zona=GUAYAQUIL)

    def test_un_feriado_parcial_exige_las_dos_horas(self) -> None:
        with pytest.raises(ValueError, match="hora de inicio y de fin"):
            FeriadoLocal(MIERCOLES, "Medio dia", hora_inicio=time(12, 0))


# ===========================================================================
#  Generacion de turnos
# ===========================================================================
class TestGeneracionDeTurnos:
    def test_el_paso_es_la_duracion_total_no_la_granularidad(self) -> None:
        """Es la decision central del generador.

        Si se avanzara de granularidad en granularidad se ofrecerian turnos
        solapados: el paciente veria diez opciones y nueve fallarian al
        elegirlas, porque reservar una invalidaria las demas.
        """
        hueco = Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 10))
        turnos = generar_turnos_en_hueco(
            hueco,
            duracion_minutos=30,
            minutos_preparacion=0,
            granularidad_minutos=15,
            zona=GUAYAQUIL,
        )
        # Dos horas divididas en turnos de 30 minutos = 4, no 8.
        assert len(turnos) == 4
        assert not hay_solapamiento(turnos)

    def test_el_buffer_reduce_los_turnos_que_caben(self) -> None:
        hueco = Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 10))
        sin_buffer = generar_turnos_en_hueco(
            hueco,
            duracion_minutos=30,
            minutos_preparacion=0,
            granularidad_minutos=15,
            zona=GUAYAQUIL,
        )
        con_buffer = generar_turnos_en_hueco(
            hueco,
            duracion_minutos=30,
            minutos_preparacion=15,
            granularidad_minutos=15,
            zona=GUAYAQUIL,
        )
        assert len(sin_buffer) == 4
        # 45 minutos por turno, multiplo de la granularidad: caben 2 en dos
        # horas (08:00-08:45 y 08:45-09:30) y el tercero se saldria.
        assert len(con_buffer) == 2

    def test_una_granularidad_incompatible_cuesta_capacidad(self) -> None:
        """Documenta una tension real del diseno.

        Un servicio de 30 minutos con 10 de preparacion ocupa 40, y con
        granularidad de 15 los turnos empiezan a las 08:00, 08:45, 09:30:
        cada uno pierde 5 minutos en el redondeo.

        El motor prioriza horas redondas frente a apurar la agenda, porque
        ofrecer las 08:40 y las 09:20 confunde al paciente.  Pero la perdida
        no debe ser invisible: `granularidad_incompatible` la reporta para
        avisar al configurar el servicio.
        """
        hueco = Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 10))
        turnos = generar_turnos_en_hueco(
            hueco,
            duracion_minutos=30,
            minutos_preparacion=10,
            granularidad_minutos=15,
            zona=GUAYAQUIL,
        )
        inicios = [t.en_zona(GUAYAQUIL)[0].strftime("%H:%M") for t in turnos]
        # Sin alineacion cabrian tres (08:00, 08:40, 09:20); con horas
        # redondas caben dos.
        assert inicios == ["08:00", "08:45"]

        aviso = granularidad_incompatible(
            duracion_minutos=30, minutos_preparacion=10, granularidad_minutos=15
        )
        assert aviso is not None
        assert "5 minutos" in aviso

    @pytest.mark.parametrize(
        ("duracion", "buffer_minutos", "granularidad"),
        [
            (30, 0, 15),  # 30 es multiplo de 15
            (30, 15, 15),  # 45 es multiplo de 15
            (20, 10, 30),  # 30 es multiplo de 30
            (60, 0, 20),  # 60 es multiplo de 20
        ],
    )
    def test_una_granularidad_compatible_no_avisa(
        self, duracion: int, buffer_minutos: int, granularidad: int
    ) -> None:
        assert (
            granularidad_incompatible(
                duracion_minutos=duracion,
                minutos_preparacion=buffer_minutos,
                granularidad_minutos=granularidad,
            )
            is None
        )

    def test_el_aviso_sugiere_una_granularidad_valida(self) -> None:
        """El mensaje debe decir que hacer, no solo que algo esta mal."""
        aviso = granularidad_incompatible(
            duracion_minutos=25, minutos_preparacion=5, granularidad_minutos=20
        )
        assert aviso is not None
        # 30 minutos de total: 10 es divisor y no supera la granularidad.
        assert "10 minutos" in aviso

    def test_el_fin_de_consulta_excluye_el_buffer(self) -> None:
        """Al paciente se le dice cuando acaba su consulta, no la limpieza.

        Decirle que su cita de 30 minutos dura 40 seria confuso.
        """
        hueco = Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 10))
        turno = generar_turnos_en_hueco(
            hueco,
            duracion_minutos=30,
            minutos_preparacion=10,
            granularidad_minutos=15,
            zona=GUAYAQUIL,
        )[0]
        assert turno.fin_consulta == _instante(MIERCOLES, 8, 30)
        # Pero el intervalo reservado cubre los 40.
        assert turno.fin == _instante(MIERCOLES, 8, 40)

    def test_un_hueco_menor_que_la_duracion_no_produce_turnos(self) -> None:
        hueco = Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 8, 20))
        assert (
            generar_turnos_en_hueco(
                hueco,
                duracion_minutos=30,
                minutos_preparacion=0,
                granularidad_minutos=15,
                zona=GUAYAQUIL,
            )
            == []
        )

    def test_los_turnos_se_alinean_a_la_hora_local(self) -> None:
        """Un hueco que empieza a las 09:07 no debe descuadrar la tarde.

        Ocurre cuando una cita anterior termina en un minuto raro.  Sin
        alinear, el paciente veria horas como las 11:37.
        """
        hueco = Intervalo(_instante(MIERCOLES, 9, 7), _instante(MIERCOLES, 12))
        turnos = generar_turnos_en_hueco(
            hueco,
            duracion_minutos=30,
            minutos_preparacion=0,
            granularidad_minutos=15,
            zona=GUAYAQUIL,
        )
        primero = turnos[0].en_zona(GUAYAQUIL)[0]
        assert primero.minute % 15 == 0
        assert primero.hour == 9 and primero.minute == 15

    def test_rechaza_parametros_invalidos(self) -> None:
        hueco = Intervalo(_instante(MIERCOLES, 8), _instante(MIERCOLES, 10))
        for kwargs, patron in (
            ({"duracion_minutos": 0}, "duracion"),
            ({"minutos_preparacion": -5}, "preparacion"),
            ({"granularidad_minutos": 0}, "granularidad"),
        ):
            base = {
                "duracion_minutos": 30,
                "minutos_preparacion": 0,
                "granularidad_minutos": 15,
                "zona": GUAYAQUIL,
            }
            base.update(kwargs)
            with pytest.raises(ValueError, match=patron):
                generar_turnos_en_hueco(hueco, **base)  # type: ignore[arg-type]


# ===========================================================================
#  Calculo completo
# ===========================================================================
class TestCalculoCompleto:
    def test_jornada_simple(self) -> None:
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 13)],
            duracion_minutos=30,
        )
        assert len(resultado) == 10
        assert not hay_solapamiento(resultado.turnos)
        primero, _ = resultado.turnos[0].en_zona(GUAYAQUIL)
        assert (primero.hour, primero.minute) == (8, 0)

    def test_el_descanso_parte_la_jornada(self) -> None:
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 14)],
            duracion_minutos=60,
            descansos=[DescansoLocal(MIERCOLES_ISO, time(10, 0), time(11, 0), "Cafe")],
        )
        horas = [t.en_zona(GUAYAQUIL)[0].hour for t in resultado.turnos]
        assert 10 not in horas, "El turno de las 10:00 cae en el descanso."
        assert horas == [8, 9, 11, 12, 13]

    def test_un_feriado_deja_el_dia_sin_turnos(self) -> None:
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 13)],
            duracion_minutos=30,
            feriados=[FeriadoLocal(MIERCOLES, "Dia de prueba")],
        )
        assert len(resultado) == 0

    def test_un_feriado_de_media_jornada_deja_la_otra_mitad(self) -> None:
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 16)],
            duracion_minutos=60,
            feriados=[
                FeriadoLocal(
                    MIERCOLES, "Media jornada", hora_inicio=time(12, 0), hora_fin=time(23, 59)
                )
            ],
        )
        horas = [t.en_zona(GUAYAQUIL)[0].hour for t in resultado.turnos]
        assert horas == [8, 9, 10, 11]

    def test_una_cita_existente_libera_el_resto(self) -> None:
        desde, hasta = _rango_del_dia(MIERCOLES)
        ocupacion = Ocupacion(
            Intervalo(_instante(MIERCOLES, 9), _instante(MIERCOLES, 10)),
            MotivoNoDisponible.CITA_EXISTENTE,
        )
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 12)],
            duracion_minutos=60,
            ocupaciones=[ocupacion],
        )
        horas = [t.en_zona(GUAYAQUIL)[0].hour for t in resultado.turnos]
        assert horas == [8, 10, 11]

    def test_el_buffer_de_una_cita_bloquea_el_turno_siguiente(self) -> None:
        """La ocupacion ya incluye el buffer: llega calculada del modelo.

        Una cita de 30 minutos con 15 de preparacion ocupa 45, asi que el
        turno de las 09:30 no se puede ofrecer aunque la consulta acabara ahi.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        ocupacion = Ocupacion(
            Intervalo(_instante(MIERCOLES, 9), _instante(MIERCOLES, 9, 45)),
            MotivoNoDisponible.CITA_EXISTENTE,
        )
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 11)],
            duracion_minutos=30,
            granularidad_minutos=30,
            ocupaciones=[ocupacion],
        )
        inicios = [t.en_zona(GUAYAQUIL)[0].strftime("%H:%M") for t in resultado.turnos]
        assert "09:30" not in inicios
        assert inicios == ["08:00", "08:30", "10:00", "10:30"]

    def test_la_antelacion_minima_descarta_lo_inmediato(self) -> None:
        """No se ofrece un turno que empieza en diez minutos.

        `ahora` se pasa como argumento, no se lee del reloj del sistema: es lo
        que hace la prueba determinista (ADR-0010).
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        ahora = _instante(MIERCOLES, 9, 50)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 13)],
            duracion_minutos=30,
            granularidad_minutos=30,
            ahora=ahora,
            minutos_antelacion_minima=60,
        )
        inicios = [t.en_zona(GUAYAQUIL)[0].strftime("%H:%M") for t in resultado.turnos]
        # Con 60 minutos de antelacion desde las 09:50, el primero valido es
        # el de las 11:00.
        assert inicios[0] == "11:00"

    def test_los_turnos_no_salen_del_rango_solicitado(self) -> None:
        """Pedir solo la manana no debe devolver turnos de la tarde."""
        resultado = calcular_disponibilidad(
            desde=_instante(MIERCOLES, 8),
            hasta=_instante(MIERCOLES, 10),
            zona=GUAYAQUIL,
            franjas=[_franja(8, 18)],
            duracion_minutos=30,
        )
        for turno in resultado.turnos:
            assert turno.inicio >= _instante(MIERCOLES, 8)
            assert turno.fin <= _instante(MIERCOLES, 10)

    def test_rechaza_un_rango_sin_zona_horaria(self) -> None:
        with pytest.raises(ValueError, match="zona horaria"):
            calcular_disponibilidad(
                desde=datetime(2026, 4, 15, 8, 0),
                hasta=datetime(2026, 4, 15, 18, 0, tzinfo=UTC),
                zona=GUAYAQUIL,
                franjas=[_franja()],
                duracion_minutos=30,
            )

    def test_rechaza_un_rango_invertido(self) -> None:
        desde, hasta = _rango_del_dia(MIERCOLES)
        with pytest.raises(ValueError, match="posterior"):
            calcular_disponibilidad(
                desde=hasta,
                hasta=desde,
                zona=GUAYAQUIL,
                franjas=[_franja()],
                duracion_minutos=30,
            )

    def test_los_descartes_se_registran_con_su_motivo(self) -> None:
        """La interfaz necesita explicar por que no hay turnos.

        «El profesional esta de vacaciones» es una respuesta util; «no hay
        turnos» deja al paciente sin saber si insistir otro dia.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(8, 13)],
            duracion_minutos=30,
            feriados=[FeriadoLocal(MIERCOLES, "Dia de prueba")],
            registrar_descartes=True,
        )
        assert len(resultado) == 0
        motivos = resultado.motivos_de_descarte()
        assert motivos.get(MotivoNoDisponible.FERIADO, 0) >= 1


# ===========================================================================
#  Zonas horarias
# ===========================================================================
class TestZonasHorarias:
    def test_la_misma_franja_da_instantes_distintos_segun_la_zona(self) -> None:
        guayaquil = proyectar_franjas([_franja(8, 13)], dia=MIERCOLES, zona=GUAYAQUIL)
        madrid = proyectar_franjas([_franja(8, 13)], dia=MIERCOLES, zona=MADRID)
        # 08:00 local en Guayaquil (UTC-5) y en Madrid (UTC+2 en abril) son
        # instantes separados por siete horas.
        assert guayaquil[0].inicio - madrid[0].inicio == timedelta(hours=7)

    def test_el_cambio_de_horario_de_verano_no_descuadra_la_jornada(self) -> None:
        """En Madrid, el 29 de marzo de 2026 se adelanta el reloj.

        La franja de 08:00 a 13:00 local sigue siendo de cinco horas de
        atencion, aunque el desplazamiento respecto a UTC cambie.  Proyectar
        una vez y sumar dias daria una hora distinta a partir del cambio.
        """
        domingo_del_cambio = date(2026, 3, 29)
        franja = FranjaLocal(
            dia_semana=domingo_del_cambio.isoweekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(13, 0),
        )
        intervalos = proyectar_franjas([franja], dia=domingo_del_cambio, zona=MADRID)
        assert len(intervalos) == 1
        assert intervalos[0].duracion == timedelta(hours=5)

    def test_ecuador_no_cambia_de_horario(self) -> None:
        for mes in (1, 7):
            dia = date(2026, mes, 15)
            franja = FranjaLocal(
                dia_semana=dia.isoweekday(),
                hora_inicio=time(8, 0),
                hora_fin=time(13, 0),
            )
            intervalos = proyectar_franjas([franja], dia=dia, zona=GUAYAQUIL)
            assert intervalos[0].inicio.utcoffset() == timedelta(hours=-5)

    def test_un_dia_local_no_coincide_con_un_dia_utc(self) -> None:
        """La agenda se calcula por dias LOCALES.

        En Guayaquil, el miercoles local empieza a las 05:00 UTC.  Calcular
        por dias UTC desplazaria la agenda cinco horas y ofreceria turnos del
        dia equivocado.
        """
        desde = datetime(2026, 4, 15, 0, 0, tzinfo=UTC)  # 14 de abril 19:00 local
        hasta = datetime(2026, 4, 16, 0, 0, tzinfo=UTC)
        # Franja del martes (dia 2 ISO), que en UTC cae parcialmente el 15.
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=[_franja(19, 22, dia=2)],
            duracion_minutos=60,
        )
        # El martes 14 a las 19:00 local son las 00:00 UTC del 15: dentro del
        # rango UTC solicitado.
        assert len(resultado) == 3


# ===========================================================================
#  Propiedades con Hypothesis
# ===========================================================================
# Estrategias que generan combinaciones validas pero variadas.
_horas = st.integers(min_value=0, max_value=23)
_minutos_redondos = st.sampled_from([0, 15, 30, 45])
_duraciones = st.sampled_from([15, 20, 30, 45, 60, 90])
_granularidades = st.sampled_from([5, 10, 15, 20, 30, 60])
_buffers = st.sampled_from([0, 5, 10, 15, 30])


@st.composite
def _franja_valida(draw: st.DrawFn) -> FranjaLocal:
    inicio_hora = draw(st.integers(min_value=0, max_value=20))
    duracion_horas = draw(st.integers(min_value=1, max_value=23 - inicio_hora))
    return FranjaLocal(
        dia_semana=MIERCOLES_ISO,
        hora_inicio=time(inicio_hora, draw(_minutos_redondos)),
        hora_fin=time(inicio_hora + duracion_horas, draw(_minutos_redondos)),
        granularidad_minutos=draw(_granularidades),
    )


@st.composite
def _ocupacion_del_dia(draw: st.DrawFn) -> Ocupacion:
    hora = draw(st.integers(min_value=0, max_value=22))
    minuto = draw(_minutos_redondos)
    duracion = draw(st.integers(min_value=15, max_value=120))
    inicio = _instante(MIERCOLES, hora, minuto)
    return Ocupacion(
        Intervalo(inicio, inicio + timedelta(minutes=duracion)),
        MotivoNoDisponible.CITA_EXISTENTE,
    )


class TestPropiedades:
    """Invariantes que deben cumplirse con cualquier combinacion de entradas.

    Son las que hacen util una agenda.  Si alguna se rompe, el sistema puede
    ofrecer turnos que fallan al reservarse, o perder capacidad sin motivo.
    """

    @settings(max_examples=200, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=3),
        duracion=_duraciones,
        buffer_minutos=_buffers,
        ocupaciones=st.lists(_ocupacion_del_dia(), max_size=6),
    )
    def test_los_turnos_nunca_se_solapan(
        self,
        franjas: list[FranjaLocal],
        duracion: int,
        buffer_minutos: int,
        ocupaciones: list[Ocupacion],
    ) -> None:
        """Invariante 1: ningun turno ofrecido se solapa con otro.

        Es la mas importante: si dos turnos ofrecidos se solapan, reservar uno
        invalida el otro y el paciente ve opciones que fallan al elegirlas.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=franjas,
            duracion_minutos=duracion,
            minutos_preparacion=buffer_minutos,
            ocupaciones=ocupaciones,
        )
        assert not hay_solapamiento(resultado.turnos)

    @settings(max_examples=200, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=3),
        duracion=_duraciones,
        buffer_minutos=_buffers,
        ocupaciones=st.lists(_ocupacion_del_dia(), min_size=1, max_size=6),
    )
    def test_ningun_turno_pisa_una_ocupacion(
        self,
        franjas: list[FranjaLocal],
        duracion: int,
        buffer_minutos: int,
        ocupaciones: list[Ocupacion],
    ) -> None:
        """Invariante 2: ningun turno se solapa con una cita o un bloqueo.

        Ofrecer un turno ocupado produce un rechazo al reservar, y el paciente
        no entiende por que le mostraron esa hora.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=franjas,
            duracion_minutos=duracion,
            minutos_preparacion=buffer_minutos,
            ocupaciones=ocupaciones,
        )
        for turno in resultado.turnos:
            for ocupacion in ocupaciones:
                assert not turno.intervalo.se_solapa_con(ocupacion.intervalo), (
                    f"El turno {turno.inicio} pisa la ocupacion "
                    f"{ocupacion.intervalo.inicio}-{ocupacion.intervalo.fin}"
                )

    @settings(max_examples=200, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=3),
        duracion=_duraciones,
        buffer_minutos=_buffers,
    )
    def test_todo_turno_cae_dentro_de_una_franja(
        self, franjas: list[FranjaLocal], duracion: int, buffer_minutos: int
    ) -> None:
        """Invariante 3: no se ofrece nada fuera del horario de atencion.

        Incluido el buffer: si la consulta acaba a la hora de cierre pero la
        limpieza se pasa, el turno no es ofrecible.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=franjas,
            duracion_minutos=duracion,
            minutos_preparacion=buffer_minutos,
        )
        atencion = proyectar_franjas(franjas, dia=MIERCOLES, zona=GUAYAQUIL)
        for turno in resultado.turnos:
            assert any(f.contiene(turno.intervalo) for f in atencion), (
                f"El turno {turno.inicio}-{turno.fin} no cabe en ninguna franja."
            )

    @settings(max_examples=150, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=2),
        duracion=_duraciones,
        buffer_minutos=_buffers,
    )
    def test_la_duracion_de_los_turnos_es_exacta(
        self, franjas: list[FranjaLocal], duracion: int, buffer_minutos: int
    ) -> None:
        """Invariante 5: cada turno dura exactamente lo esperado.

        Un turno mas corto de lo debido recorta la consulta; uno mas largo
        desperdicia agenda.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=franjas,
            duracion_minutos=duracion,
            minutos_preparacion=buffer_minutos,
        )
        esperada = timedelta(minutes=duracion + buffer_minutos)
        for turno in resultado.turnos:
            assert turno.intervalo.duracion == esperada
            assert turno.fin_consulta - turno.inicio == timedelta(minutes=duracion)

    @settings(max_examples=150, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=2),
        duracion=_duraciones,
        ocupaciones=st.lists(_ocupacion_del_dia(), max_size=5),
    )
    def test_anadir_ocupaciones_nunca_anade_turnos(
        self,
        franjas: list[FranjaLocal],
        duracion: int,
        ocupaciones: list[Ocupacion],
    ) -> None:
        """Propiedad de monotonia: ocupar tiempo no crea disponibilidad.

        Parece obvia, pero es justo la que rompen las implementaciones que
        dividen primero y restan despues: al recalcular sobre huecos partidos
        pueden aparecer turnos en posiciones nuevas.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        comunes = {
            "desde": desde,
            "hasta": hasta,
            "zona": GUAYAQUIL,
            "franjas": franjas,
            "duracion_minutos": duracion,
        }
        sin_ocupar = calcular_disponibilidad(**comunes)  # type: ignore[arg-type]
        con_ocupar = calcular_disponibilidad(**comunes, ocupaciones=ocupaciones)  # type: ignore[arg-type]
        assert len(con_ocupar) <= len(sin_ocupar)

    @settings(max_examples=150, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=3),
        duracion=_duraciones,
        ocupaciones=st.lists(_ocupacion_del_dia(), max_size=5),
    )
    def test_el_orden_de_las_entradas_no_altera_el_resultado(
        self,
        franjas: list[FranjaLocal],
        duracion: int,
        ocupaciones: list[Ocupacion],
    ) -> None:
        """El calculo debe ser determinista.

        Las franjas y las ocupaciones llegan de consultas distintas y su orden
        no esta garantizado.  Un resultado que dependa del orden produciria
        agendas distintas en peticiones identicas.
        """
        desde, hasta = _rango_del_dia(MIERCOLES)
        comunes = {
            "desde": desde,
            "hasta": hasta,
            "zona": GUAYAQUIL,
            "duracion_minutos": duracion,
        }
        directo = calcular_disponibilidad(
            **comunes,
            franjas=franjas,
            ocupaciones=ocupaciones,  # type: ignore[arg-type]
        )
        invertido = calcular_disponibilidad(
            **comunes,  # type: ignore[arg-type]
            franjas=list(reversed(franjas)),
            ocupaciones=list(reversed(ocupaciones)),
        )
        assert [t.inicio for t in directo.turnos] == [t.inicio for t in invertido.turnos]

    @settings(max_examples=100, deadline=None)
    @given(
        franjas=st.lists(_franja_valida(), min_size=1, max_size=2),
        duracion=_duraciones,
        minutos_antelacion=st.integers(min_value=0, max_value=600),
    )
    def test_la_antelacion_minima_se_respeta_siempre(
        self, franjas: list[FranjaLocal], duracion: int, minutos_antelacion: int
    ) -> None:
        """Invariante: ningun turno empieza antes del limite de antelacion."""
        desde, hasta = _rango_del_dia(MIERCOLES)
        ahora = _instante(MIERCOLES, 0)
        resultado = calcular_disponibilidad(
            desde=desde,
            hasta=hasta,
            zona=GUAYAQUIL,
            franjas=franjas,
            duracion_minutos=duracion,
            ahora=ahora,
            minutos_antelacion_minima=minutos_antelacion,
        )
        limite = ahora + timedelta(minutes=minutos_antelacion)
        for turno in resultado.turnos:
            assert turno.inicio >= limite

    @settings(max_examples=100, deadline=None)
    @given(
        base_horas=st.integers(min_value=1, max_value=12),
        ocupaciones=st.lists(_ocupacion_del_dia(), max_size=8),
    )
    def test_restar_nunca_produce_intervalos_invalidos(
        self, base_horas: int, ocupaciones: list[Ocupacion]
    ) -> None:
        """Los huecos resultantes siempre tienen duracion positiva y estan
        ordenados y sin solaparse entre si.
        """
        base = [
            Intervalo(
                _instante(MIERCOLES, 8), _instante(MIERCOLES, 8) + timedelta(hours=base_horas)
            )
        ]
        assume(base[0].fin <= _instante(MIERCOLES + timedelta(days=1), 0))

        huecos = restar(base, [o.intervalo for o in ocupaciones])

        for hueco in huecos:
            assert hueco.fin > hueco.inicio
            assert base[0].contiene(hueco)
        for i in range(len(huecos) - 1):
            assert huecos[i].fin <= huecos[i + 1].inicio, "Los huecos deben estar ordenados."
            assert not huecos[i].se_solapa_con(huecos[i + 1])
