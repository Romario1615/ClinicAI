"""Reloj inyectable.

Motivo (ADR-0010): ninguna parte del codigo llama a `datetime.now()` de forma
directa.  El tiempo entra siempre por esta abstraccion, por dos razones que en
una agenda clinica no son negociables:

1. **Determinismo en las pruebas.**  La expiracion de un bloqueo temporal, el
   vencimiento de una oferta de lista de espera o el calculo de un calendario
   de tomas solo se pueden probar de verdad si el tiempo se puede fijar y
   adelantar a voluntad.  Con `datetime.now()` habria que esperar en tiempo
   real o aceptar pruebas fragiles.

2. **Zonas horarias explicitas.**  `datetime.now()` sin argumento devuelve un
   instante sin zona, y un instante sin zona en una agenda medica termina en
   citas desplazadas una hora.  Aqui solo existen instantes con zona.

La regla esta aplicada por el linter: `ruff` prohibe `datetime.now` y
`datetime.utcnow` en todo `app/` salvo en este modulo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class Reloj(ABC):
    """Fuente de tiempo de la aplicacion."""

    @abstractmethod
    def ahora(self) -> datetime:
        """Instante actual en UTC, siempre con zona horaria."""

    def ahora_en(self, zona: str) -> datetime:
        """Instante actual expresado en la zona horaria indicada.

        Se usa para las decisiones que dependen de la hora local de una sede:
        si un horario de atencion esta abierto, si una fecha es feriado o a
        que hora enviar el resumen diario.
        """
        return self.ahora().astimezone(ZoneInfo(zona))

    def hoy_en(self, zona: str) -> date:
        """Fecha local de la sede.

        No coincide necesariamente con la fecha UTC: a las 02:00 UTC en
        Guayaquil todavia es el dia anterior.  Confundirlas desplaza un dia
        entero la agenda y los feriados.
        """
        return self.ahora_en(zona).date()


class RelojSistema(Reloj):
    """Reloj real. Es el que se usa en ejecucion."""

    def ahora(self) -> datetime:
        return datetime.now(UTC)


class RelojFijo(Reloj):
    """Reloj controlado, para pruebas.

    Permite fijar un instante y adelantarlo de forma explicita, de modo que
    una prueba de expiracion no necesite esperar.
    """

    def __init__(self, instante: datetime) -> None:
        if instante.tzinfo is None:
            raise ValueError(
                "RelojFijo exige un instante con zona horaria. "
                "Un instante sin zona es ambiguo (ADR-0010)."
            )
        self._instante = instante.astimezone(UTC)

    def ahora(self) -> datetime:
        return self._instante

    def fijar(self, instante: datetime) -> None:
        """Coloca el reloj en un instante concreto."""
        if instante.tzinfo is None:
            raise ValueError("Se exige un instante con zona horaria.")
        self._instante = instante.astimezone(UTC)

    def avanzar(self, **delta: float) -> datetime:
        """Adelanta el reloj.

        Acepta los argumentos de `timedelta`: `avanzar(minutes=11)` para
        comprobar que un bloqueo de diez minutos ya expiro.
        """
        self._instante = self._instante + timedelta(**delta)
        return self._instante
