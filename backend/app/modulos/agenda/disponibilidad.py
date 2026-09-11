"""Motor de disponibilidad: calculo de turnos libres.

Este modulo es **puro**: recibe datos y devuelve turnos.  No consulta la base
de datos, no mira el reloj del sistema y no tiene efectos.  Esa decision es
deliberada y es lo que hace el calculo verificable: las pruebas pueden
recorrer cientos de combinaciones de horarios, descansos, feriados y bloqueos
sin montar una base de datos, y el resultado es siempre el mismo.

El modelo de tiempo
-------------------
Hay dos mundos y la conversion entre ambos es la fuente de error mas comun de
una agenda medica:

* **Reglas locales.**  «Atiende de 08:00 a 13:00 los lunes» es una afirmacion
  en la hora local de la sede.  Sigue siendo cierta aunque cambie el
  desplazamiento de la zona horaria.
* **Instantes.**  Una cita concreta ocurre en un momento absoluto, y se
  almacena en UTC.

Las reglas se proyectan a instantes **por cada dia**, con la zona horaria de
la sede.  Proyectar una vez y sumar dias seria incorrecto en cualquier zona
con horario de verano: el segundo domingo cambiaria de hora.

Que resta disponibilidad
------------------------
1. Fuera de las franjas de atencion.
2. Descansos dentro de la franja.
3. Feriados, completos o de media jornada.
4. Bloqueos: vacaciones, ausencias, mantenimiento.
5. Citas activas, incluido su tiempo de preparacion.
6. Antelacion minima: no se ofrece un turno que empieza en diez minutos.

El tiempo de preparacion
------------------------
Se suma DESPUES del turno, no antes.  Un servicio de 30 minutos con 10 de
preparacion ocupa 40 minutos desde su inicio.  Por eso dos turnos ofrecidos
consecutivos deben ir separados por la duracion total, no solo por la
duracion de la consulta; si no, el segundo empezaria mientras la sala todavia
se esta limpiando.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

# Dia de la semana en convencion ISO: 1 = lunes, 7 = domingo.
#
# Se elige ISO y no la de Python (`weekday()`, 0 = lunes) ni la de PostgreSQL
# (`dow`, 0 = domingo) para tener UNA convencion explicita en todo el
# sistema.  Mezclarlas desplaza la agenda un dia entero, y es un error que no
# se nota hasta que alguien se presenta el dia equivocado.
LUNES = 1
DOMINGO = 7


class MotivoNoDisponible(StrEnum):
    """Por que un turno no se ofrece.

    Se devuelve junto al hueco descartado porque la interfaz necesita
    explicarlo: «el profesional esta de vacaciones» es una respuesta util,
    «no hay turnos» no lo es.  Tambien sirve al agente de WhatsApp para
    responder algo mejor que un no seco.
    """

    FUERA_DE_HORARIO = "FUERA_DE_HORARIO"
    DESCANSO = "DESCANSO"
    FERIADO = "FERIADO"
    BLOQUEO = "BLOQUEO"
    CITA_EXISTENTE = "CITA_EXISTENTE"
    ANTELACION_INSUFICIENTE = "ANTELACION_INSUFICIENTE"
    FUERA_DEL_RANGO_SOLICITADO = "FUERA_DEL_RANGO_SOLICITADO"


# ---------------------------------------------------------------------------
#  Entradas del calculo
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FranjaLocal:
    """Franja de atencion en hora LOCAL de la sede."""

    dia_semana: int
    hora_inicio: time
    hora_fin: time
    granularidad_minutos: int = 15
    vigente_desde: date | None = None
    vigente_hasta: date | None = None

    def __post_init__(self) -> None:
        if not LUNES <= self.dia_semana <= DOMINGO:
            raise ValueError(
                f"dia_semana debe estar entre {LUNES} (lunes) y {DOMINGO} "
                f"(domingo) en convencion ISO; se recibio {self.dia_semana}."
            )
        if self.hora_fin <= self.hora_inicio:
            raise ValueError(
                f"La franja {self.hora_inicio}-{self.hora_fin} no tiene duracion. "
                "Para una franja que cruza la medianoche, declare dos franjas."
            )
        if self.granularidad_minutos <= 0:
            raise ValueError("La granularidad debe ser mayor que cero.")

    def esta_vigente(self, dia: date) -> bool:
        if self.vigente_desde is not None and dia < self.vigente_desde:
            return False
        return not (self.vigente_hasta is not None and dia > self.vigente_hasta)


@dataclass(frozen=True, slots=True)
class DescansoLocal:
    """Pausa dentro de una franja, en hora local."""

    dia_semana: int
    hora_inicio: time
    hora_fin: time
    motivo: str | None = None

    def __post_init__(self) -> None:
        if self.hora_fin <= self.hora_inicio:
            raise ValueError(f"El descanso {self.hora_inicio}-{self.hora_fin} no tiene duracion.")


@dataclass(frozen=True, slots=True)
class FeriadoLocal:
    """Dia sin atencion, en fecha local.

    Si `hora_inicio` y `hora_fin` son nulos, el feriado ocupa el dia completo.
    Con valores, es de media jornada: solo bloquea ese tramo.
    """

    fecha: date
    nombre: str = ""
    recurrente_anual: bool = False
    hora_inicio: time | None = None
    hora_fin: time | None = None

    def __post_init__(self) -> None:
        if (self.hora_inicio is None) != (self.hora_fin is None):
            raise ValueError(
                "Un feriado parcial necesita hora de inicio y de fin, o ninguna "
                "de las dos para indicar el dia completo."
            )
        if (
            self.hora_inicio is not None
            and self.hora_fin is not None
            and self.hora_fin <= self.hora_inicio
        ):
            raise ValueError("El tramo del feriado no tiene duracion.")

    @property
    def es_dia_completo(self) -> bool:
        return self.hora_inicio is None

    def aplica_a(self, dia: date) -> bool:
        if self.recurrente_anual:
            return (self.fecha.month, self.fecha.day) == (dia.month, dia.day)
        return self.fecha == dia


@dataclass(frozen=True, slots=True)
class Intervalo:
    """Intervalo semiabierto de instantes: [inicio, fin).

    Semiabierto igual que el `tstzrange` de la base de datos.  Con intervalos
    cerrados, una cita que acaba a las 10:00 y otra que empieza a las 10:00
    colisionarian, y la agenda perderia un turno entre cada par de citas.
    """

    inicio: datetime
    fin: datetime

    def __post_init__(self) -> None:
        if self.inicio.tzinfo is None or self.fin.tzinfo is None:
            raise ValueError(
                "Un intervalo exige instantes con zona horaria. Un instante sin "
                "zona es ambiguo (ADR-0010)."
            )
        if self.fin <= self.inicio:
            raise ValueError(f"El intervalo {self.inicio}-{self.fin} no tiene duracion.")

    @property
    def duracion(self) -> timedelta:
        return self.fin - self.inicio

    def se_solapa_con(self, otro: Intervalo) -> bool:
        """Solapamiento de intervalos semiabiertos."""
        return self.inicio < otro.fin and otro.inicio < self.fin

    def contiene(self, otro: Intervalo) -> bool:
        return self.inicio <= otro.inicio and otro.fin <= self.fin


@dataclass(frozen=True, slots=True)
class Ocupacion:
    """Tiempo ya comprometido: una cita o un bloqueo."""

    intervalo: Intervalo
    motivo: MotivoNoDisponible
    referencia_id: uuid.UUID | None = None
    detalle: str | None = None


# ---------------------------------------------------------------------------
#  Salida del calculo
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TurnoLibre:
    """Turno ofrecible.

    `intervalo` cubre la duracion total (consulta mas preparacion), que es lo
    que se reserva en la base de datos.  `fin_consulta` es cuando termina la
    atencion, que es lo que se muestra al paciente: decirle que su cita de
    30 minutos dura 40 seria confuso.
    """

    intervalo: Intervalo
    fin_consulta: datetime

    @property
    def inicio(self) -> datetime:
        return self.intervalo.inicio

    @property
    def fin(self) -> datetime:
        return self.intervalo.fin

    def en_zona(self, zona: str) -> tuple[datetime, datetime]:
        """Inicio y fin de consulta en la hora local de la sede."""
        tz = ZoneInfo(zona)
        return self.inicio.astimezone(tz), self.fin_consulta.astimezone(tz)


@dataclass(frozen=True, slots=True)
class HuecoDescartado:
    """Turno que existiria pero no se ofrece, con su motivo.

    Permite que la interfaz y el agente expliquen la ausencia de turnos en
    lugar de responder «no hay disponibilidad», que deja al paciente sin
    saber si insistir otro dia o llamar por telefono.
    """

    intervalo: Intervalo
    motivo: MotivoNoDisponible
    detalle: str | None = None


@dataclass(frozen=True, slots=True)
class ResultadoDisponibilidad:
    """Turnos libres y, opcionalmente, por que se descarto el resto."""

    turnos: tuple[TurnoLibre, ...]
    descartados: tuple[HuecoDescartado, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.turnos)

    def __bool__(self) -> bool:
        return bool(self.turnos)

    def motivos_de_descarte(self) -> dict[MotivoNoDisponible, int]:
        """Recuento por motivo. Sirve para explicar la ausencia de turnos."""
        recuento: dict[MotivoNoDisponible, int] = {}
        for hueco in self.descartados:
            recuento[hueco.motivo] = recuento.get(hueco.motivo, 0) + 1
        return recuento


# ---------------------------------------------------------------------------
#  Proyeccion de reglas locales a instantes
# ---------------------------------------------------------------------------
def _instante_local(dia: date, hora: time, zona: ZoneInfo) -> datetime:
    """Combina fecha y hora locales en un instante con zona.

    Nota sobre las transiciones de horario de verano: en la hora que no existe
    (el salto hacia adelante), `ZoneInfo` normaliza el resultado en lugar de
    fallar.  Es el comportamiento deseado aqui: una franja declarada a las
    02:30 en el dia del cambio se proyecta a un instante valido y no rompe el
    calculo del dia completo.  Ecuador no aplica horario de verano, pero el
    modelo admite mas sedes y no debe asumirlo.
    """
    return datetime.combine(dia, hora, tzinfo=zona)


def proyectar_franjas(
    franjas: Iterable[FranjaLocal],
    *,
    dia: date,
    zona: str,
) -> list[Intervalo]:
    """Convierte las franjas de un dia concreto en intervalos absolutos.

    Se proyecta **dia por dia**, no una vez para todo el rango.  En cualquier
    zona con horario de verano, proyectar el lunes y sumar siete dias daria
    una hora distinta el lunes siguiente.
    """
    tz = ZoneInfo(zona)
    dia_iso = dia.isoweekday()
    intervalos: list[Intervalo] = []

    for franja in franjas:
        if franja.dia_semana != dia_iso or not franja.esta_vigente(dia):
            continue
        intervalos.append(
            Intervalo(
                _instante_local(dia, franja.hora_inicio, tz),
                _instante_local(dia, franja.hora_fin, tz),
            )
        )

    return _fusionar(intervalos)


def proyectar_descansos(
    descansos: Iterable[DescansoLocal],
    *,
    dia: date,
    zona: str,
) -> list[Ocupacion]:
    tz = ZoneInfo(zona)
    dia_iso = dia.isoweekday()
    return [
        Ocupacion(
            Intervalo(
                _instante_local(dia, d.hora_inicio, tz),
                _instante_local(dia, d.hora_fin, tz),
            ),
            MotivoNoDisponible.DESCANSO,
            detalle=d.motivo,
        )
        for d in descansos
        if d.dia_semana == dia_iso
    ]


def proyectar_feriados(
    feriados: Iterable[FeriadoLocal],
    *,
    dia: date,
    zona: str,
) -> list[Ocupacion]:
    """Convierte los feriados del dia en ocupaciones.

    Un feriado de dia completo se proyecta como el dia local entero, de
    medianoche a medianoche, **no como 24 horas desde medianoche**.  En un dia
    con cambio de horario esas dos cosas difieren en una hora, y la diferencia
    dejaria una franja atendible al final del feriado.
    """
    tz = ZoneInfo(zona)
    ocupaciones: list[Ocupacion] = []

    for feriado in feriados:
        if not feriado.aplica_a(dia):
            continue
        if feriado.es_dia_completo:
            inicio = _instante_local(dia, time(0, 0), tz)
            fin = _instante_local(dia + timedelta(days=1), time(0, 0), tz)
        else:
            assert feriado.hora_inicio is not None  # garantizado por __post_init__
            assert feriado.hora_fin is not None
            inicio = _instante_local(dia, feriado.hora_inicio, tz)
            fin = _instante_local(dia, feriado.hora_fin, tz)
        ocupaciones.append(
            Ocupacion(
                Intervalo(inicio, fin),
                MotivoNoDisponible.FERIADO,
                detalle=feriado.nombre or None,
            )
        )

    return ocupaciones


def _fusionar(intervalos: Sequence[Intervalo]) -> list[Intervalo]:
    """Une los intervalos que se solapan o se tocan.

    Dos franjas contiguas (08:00-12:00 y 12:00-17:00) se fusionan en una.  Sin
    fusionar, la frontera partiria un turno que cabria a caballo de las dos y
    la agenda perderia capacidad sin motivo.
    """
    if not intervalos:
        return []

    ordenados = sorted(intervalos, key=lambda i: i.inicio)
    fusionados = [ordenados[0]]

    for actual in ordenados[1:]:
        ultimo = fusionados[-1]
        if actual.inicio <= ultimo.fin:
            if actual.fin > ultimo.fin:
                fusionados[-1] = Intervalo(ultimo.inicio, actual.fin)
        else:
            fusionados.append(actual)

    return fusionados


def restar(base: Sequence[Intervalo], ocupados: Sequence[Intervalo]) -> list[Intervalo]:
    """Resta los intervalos ocupados de los disponibles.

    Es la operacion central del motor.  Se implementa sobre intervalos
    fusionados y ordenados para que el resultado sea determinista: dos
    conjuntos de ocupaciones equivalentes, en cualquier orden de entrada,
    producen exactamente los mismos huecos.
    """
    if not base:
        return []
    if not ocupados:
        return list(base)

    bloqueados = _fusionar(ocupados)
    resultado: list[Intervalo] = []

    for libre in base:
        trozos = [libre]
        for bloqueo in bloqueados:
            siguientes: list[Intervalo] = []
            for trozo in trozos:
                if not trozo.se_solapa_con(bloqueo):
                    siguientes.append(trozo)
                    continue
                # Parte anterior al bloqueo.
                if trozo.inicio < bloqueo.inicio:
                    siguientes.append(Intervalo(trozo.inicio, bloqueo.inicio))
                # Parte posterior al bloqueo.
                if bloqueo.fin < trozo.fin:
                    siguientes.append(Intervalo(bloqueo.fin, trozo.fin))
            trozos = siguientes
            if not trozos:
                break
        resultado.extend(trozos)

    return sorted(resultado, key=lambda i: i.inicio)


# ---------------------------------------------------------------------------
#  Calculo de turnos
# ---------------------------------------------------------------------------
def generar_turnos_en_hueco(
    hueco: Intervalo,
    *,
    duracion_minutos: int,
    minutos_preparacion: int,
    granularidad_minutos: int,
    zona: str,
    alinear_a_hora_local: bool = True,
) -> list[TurnoLibre]:
    """Divide un hueco en turnos ofrecibles.

    El paso entre turnos es la **duracion total** (consulta mas preparacion),
    no la granularidad.  Si se avanzara de granularidad en granularidad se
    ofrecerian turnos solapados entre si, y reservar uno invalidaria los
    demas: el paciente veria diez opciones y nueve fallarian.

    `alinear_a_hora_local` hace que los turnos empiecen en minutos redondos de
    la hora local (09:00, 09:15...) en lugar de heredar el desfase del hueco.
    Importa cuando un hueco empieza a las 09:07 porque una cita anterior
    terminaba ahi: sin alinear, toda la tarde quedaria descuadrada y el
    paciente veria horas como las 11:37.
    """
    if duracion_minutos <= 0:
        raise ValueError("La duracion debe ser mayor que cero.")
    if minutos_preparacion < 0:
        raise ValueError("La preparacion no puede ser negativa.")
    if granularidad_minutos <= 0:
        raise ValueError("La granularidad debe ser mayor que cero.")

    duracion = timedelta(minutes=duracion_minutos)
    total = timedelta(minutes=duracion_minutos + minutos_preparacion)

    inicio = hueco.inicio
    if alinear_a_hora_local:
        inicio = _alinear_hacia_arriba(inicio, granularidad_minutos, zona)

    turnos: list[TurnoLibre] = []
    while inicio + total <= hueco.fin:
        turnos.append(TurnoLibre(Intervalo(inicio, inicio + total), inicio + duracion))
        inicio = inicio + total
        if alinear_a_hora_local:
            inicio = _alinear_hacia_arriba(inicio, granularidad_minutos, zona)

    return turnos


def _alinear_hacia_arriba(instante: datetime, granularidad_minutos: int, zona: str) -> datetime:
    """Redondea hacia arriba al siguiente multiplo de la granularidad.

    El redondeo se hace sobre la hora LOCAL, no sobre UTC.  En una zona con
    desplazamiento de media hora (India, partes de Australia) redondear en UTC
    produciria horas locales como las 09:07, que no es lo que nadie espera ver
    en una agenda.
    """
    tz = ZoneInfo(zona)
    local = instante.astimezone(tz)
    minutos_del_dia = local.hour * 60 + local.minute
    resto = minutos_del_dia % granularidad_minutos

    if resto == 0 and local.second == 0 and local.microsecond == 0:
        return instante

    avance = granularidad_minutos - resto
    alineado = local.replace(second=0, microsecond=0) + timedelta(minutes=avance)
    return alineado.astimezone(instante.tzinfo)


def _turnos_de_un_dia(
    *,
    dia: date,
    rango: Intervalo,
    zona: str,
    tz: ZoneInfo,
    franjas: Sequence[FranjaLocal],
    descansos: Sequence[DescansoLocal],
    feriados: Sequence[FeriadoLocal],
    ocupaciones: Sequence[Ocupacion],
    duracion_minutos: int,
    minutos_preparacion: int,
    granularidad_minutos: int,
    registrar_descartes: bool,
) -> tuple[list[TurnoLibre], list[HuecoDescartado]]:
    """Calcula los turnos de un unico dia local.

    Se extrae del bucle principal porque el orden de las cuatro operaciones
    es la parte delicada del motor y merece leerse junta: proyectar, recortar
    al rango, restar ocupaciones y solo entonces dividir en turnos.

    Restar antes de dividir es lo que evita ofrecer un turno que cabe en la
    franja pero pisa una cita.
    """
    atencion = proyectar_franjas(franjas, dia=dia, zona=zona)
    if not atencion:
        return [], []

    descartados: list[HuecoDescartado] = []

    # 1. Recorte al rango solicitado.
    atencion_en_rango: list[Intervalo] = []
    for franja in atencion:
        inicio = max(franja.inicio, rango.inicio)
        fin = min(franja.fin, rango.fin)
        if fin > inicio:
            atencion_en_rango.append(Intervalo(inicio, fin))
        elif registrar_descartes:
            descartados.append(
                HuecoDescartado(franja, MotivoNoDisponible.FUERA_DEL_RANGO_SOLICITADO)
            )

    if not atencion_en_rango:
        return [], descartados

    # 2. Ocupaciones del dia: descansos y feriados proyectados, mas las que
    #    llegan ya como instantes (citas y bloqueos).
    del_dia: list[Ocupacion] = [
        *proyectar_descansos(descansos, dia=dia, zona=zona),
        *proyectar_feriados(feriados, dia=dia, zona=zona),
    ]
    limite_dia = Intervalo(
        _instante_local(dia, time(0, 0), tz),
        _instante_local(dia + timedelta(days=1), time(0, 0), tz),
    )
    del_dia.extend(
        ocupacion for ocupacion in ocupaciones if ocupacion.intervalo.se_solapa_con(limite_dia)
    )

    # 3. Resta.
    libres = restar(atencion_en_rango, [o.intervalo for o in del_dia])

    if registrar_descartes:
        descartados.extend(
            HuecoDescartado(o.intervalo, o.motivo, o.detalle)
            for o in del_dia
            if any(o.intervalo.se_solapa_con(f) for f in atencion_en_rango)
        )

    # 4. Division en turnos.
    turnos: list[TurnoLibre] = []
    for hueco in libres:
        turnos.extend(
            generar_turnos_en_hueco(
                hueco,
                duracion_minutos=duracion_minutos,
                minutos_preparacion=minutos_preparacion,
                granularidad_minutos=granularidad_minutos,
                zona=zona,
            )
        )

    return turnos, descartados


def calcular_disponibilidad(
    *,
    desde: datetime,
    hasta: datetime,
    zona: str,
    franjas: Sequence[FranjaLocal],
    duracion_minutos: int,
    minutos_preparacion: int = 0,
    granularidad_minutos: int | None = None,
    descansos: Sequence[DescansoLocal] = (),
    feriados: Sequence[FeriadoLocal] = (),
    ocupaciones: Sequence[Ocupacion] = (),
    ahora: datetime | None = None,
    minutos_antelacion_minima: int = 0,
    registrar_descartes: bool = False,
) -> ResultadoDisponibilidad:
    """Calcula los turnos libres en un rango.

    `ahora` se pasa como argumento y no se lee del reloj del sistema: es lo
    que permite probar la antelacion minima de forma determinista (ADR-0010).

    El orden de las operaciones importa:

    1. Proyectar las franjas del dia a instantes, con la zona de la sede.
    2. Recortar al rango solicitado.
    3. Restar descansos, feriados, bloqueos y citas.
    4. Dividir los huecos resultantes en turnos.
    5. Descartar los que no cumplen la antelacion minima.

    Restar antes de dividir, y no al contrario, evita ofrecer un turno que
    cabe en el hueco pero pisa una cita existente.
    """
    if desde.tzinfo is None or hasta.tzinfo is None:
        raise ValueError("El rango exige instantes con zona horaria (ADR-0010).")
    if hasta <= desde:
        raise ValueError("`hasta` debe ser posterior a `desde`.")
    if ahora is not None and ahora.tzinfo is None:
        raise ValueError("`ahora` exige zona horaria (ADR-0010).")

    tz = ZoneInfo(zona)
    rango = Intervalo(desde, hasta)

    # Granularidad: la del servicio si se indica, o la de las franjas.
    if granularidad_minutos is None:
        granularidad_minutos = min((f.granularidad_minutos for f in franjas), default=15)

    turnos: list[TurnoLibre] = []
    descartados: list[HuecoDescartado] = []

    # Se recorren los dias LOCALES del rango.  Se amplia un dia por cada
    # extremo porque un dia local puede empezar antes o acabar despues del
    # rango en UTC: en Guayaquil, el 16 de abril local empieza a las 05:00 UTC
    # de ese dia, y el 15 local aun no ha terminado a las 02:00 UTC del 16.
    primer_dia = desde.astimezone(tz).date() - timedelta(days=1)
    ultimo_dia = hasta.astimezone(tz).date() + timedelta(days=1)

    dia = primer_dia
    while dia <= ultimo_dia:
        turnos_del_dia, descartes_del_dia = _turnos_de_un_dia(
            dia=dia,
            rango=rango,
            zona=zona,
            tz=tz,
            franjas=franjas,
            descansos=descansos,
            feriados=feriados,
            ocupaciones=ocupaciones,
            duracion_minutos=duracion_minutos,
            minutos_preparacion=minutos_preparacion,
            granularidad_minutos=granularidad_minutos,
            registrar_descartes=registrar_descartes,
        )
        turnos.extend(turnos_del_dia)
        descartados.extend(descartes_del_dia)
        dia += timedelta(days=1)

    # Antelacion minima y limites del rango.
    limite_antelacion = ahora + timedelta(minutes=minutos_antelacion_minima) if ahora else None

    admitidos: list[TurnoLibre] = []
    for turno in turnos:
        if not rango.contiene(turno.intervalo):
            if registrar_descartes:
                descartados.append(
                    HuecoDescartado(turno.intervalo, MotivoNoDisponible.FUERA_DEL_RANGO_SOLICITADO)
                )
            continue
        if limite_antelacion is not None and turno.inicio < limite_antelacion:
            if registrar_descartes:
                descartados.append(
                    HuecoDescartado(turno.intervalo, MotivoNoDisponible.ANTELACION_INSUFICIENTE)
                )
            continue
        admitidos.append(turno)

    # Se ordenan y se eliminan duplicados: dos franjas del mismo dia podrian
    # producir el mismo turno si se solapaban antes de fusionarse.
    unicos = {t.intervalo.inicio: t for t in admitidos}
    ordenados = tuple(unicos[clave] for clave in sorted(unicos))

    return ResultadoDisponibilidad(ordenados, tuple(descartados))


def granularidad_incompatible(
    *, duracion_minutos: int, minutos_preparacion: int, granularidad_minutos: int
) -> str | None:
    """Avisa si la granularidad desperdicia capacidad de agenda.

    El problema, con un ejemplo concreto: un servicio de 30 minutos con 10 de
    preparacion ocupa 40, y con granularidad de 15 los turnos empiezan a las
    08:00, 08:45 y 09:30.  Cada turno pierde 5 minutos en el redondeo, y en
    una jornada de cinco horas eso son 35 minutos tirados: casi un turno
    entero.

    Ocurre porque la duracion total no es multiplo de la granularidad.  El
    motor prioriza horas redondas frente a apurar la agenda -- ofrecer las
    08:40 y las 09:20 confunde al paciente y aumenta las inasistencias -- pero
    la perdida no deberia ser invisible.

    Devuelve un mensaje para mostrar al configurar el servicio, o `None` si
    los valores encajan.  No lanza excepcion: la configuracion es valida, solo
    subptima, y bloquearla obligaria a la clinica a cambiar duraciones que
    tienen sentido clinico por una restriccion tecnica.
    """
    total = duracion_minutos + minutos_preparacion
    if granularidad_minutos <= 0:
        raise ValueError("La granularidad debe ser mayor que cero.")
    if total % granularidad_minutos == 0:
        return None

    desperdicio = granularidad_minutos - (total % granularidad_minutos)
    sugerencias = sorted(
        {
            divisor
            for divisor in (5, 10, 15, 20, 30, 60)
            if total % divisor == 0 and divisor <= granularidad_minutos
        },
        reverse=True,
    )
    texto_sugerencia = (
        f" Con una granularidad de {sugerencias[0]} minutos no se perderia nada."
        if sugerencias
        else f" Una granularidad de {total} minutos evitaria la perdida."
    )
    return (
        f"La duracion total del servicio ({total} min = {duracion_minutos} de "
        f"consulta + {minutos_preparacion} de preparacion) no es multiplo de la "
        f"granularidad ({granularidad_minutos} min). Cada turno perdera "
        f"{desperdicio} minutos al redondear la hora de inicio." + texto_sugerencia
    )


def hay_solapamiento(turnos: Sequence[TurnoLibre]) -> bool:
    """Comprueba si alguna pareja de turnos se solapa.

    Existe para las pruebas: ofrecer turnos solapados haria que reservar uno
    invalidara los demas, y el paciente veria opciones que fallan al elegirlas.
    """
    ordenados = sorted(turnos, key=lambda t: t.inicio)
    return any(
        ordenados[i].intervalo.se_solapa_con(ordenados[i + 1].intervalo)
        for i in range(len(ordenados) - 1)
    )
