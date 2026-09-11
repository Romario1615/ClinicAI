# ADR‑0010 — UTC en almacenamiento, zona horaria por clínica en presentación

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

Se exige zona horaria configurable, con `America/Guayaquil` como valor inicial, y
pruebas unitarias específicas sobre zonas horarias. El modelo de datos debe soportar
varias sedes, que en el futuro pueden estar en husos distintos.

Guardar horas locales sin zona es la causa habitual de citas desplazadas una hora: el
mismo valor significa cosas distintas según quién lo lea, y las transiciones de horario
de verano producen instantes ambiguos o inexistentes. Ecuador no aplica horario de
verano, pero el modelo no puede asumirlo si va a admitir más sedes.

## Decisión

* **Almacenamiento:** todo instante en `TIMESTAMPTZ` (UTC). Ninguna columna de fecha y
  hora usa `TIMESTAMP` sin zona.
* **Presentación y entrada:** la zona horaria es un atributo de la **sede**, con valor
  heredado de la clínica y `America/Guayaquil` por defecto. La conversión se hace en el
  borde: al recibir y al responder.
* **Reglas locales de calendario** (horarios de atención, descansos, feriados,
  vacaciones) se almacenan como fecha y hora **locales** con la zona de la sede, porque
  «atiende de 08:00 a 13:00» es una afirmación local, no un instante. Se convierten a UTC
  al proyectar la disponibilidad.
* **Reloj inyectable:** ninguna parte del código llama a `datetime.now()` directamente.
  Se usa `app/nucleo/reloj.py`, que en pruebas se sustituye por un reloj fijo. Un
  `datetime` sin zona (naive) se rechaza con error de validación en Pydantic.
* El frontend envía y recibe ISO‑8601 con desplazamiento explícito.

## Consecuencias

* Los cálculos de disponibilidad son verificables con pruebas deterministas, incluidos
  los casos de cambio de horario de verano de otras zonas.
* Cruzar la medianoche local, los feriados definidos por fecha local y los turnos que
  empiezan un día y acaban el siguiente quedan bien definidos.
* Coste: hay que ser disciplinado en la frontera. Se mitiga con una regla de lint propia
  que prohíbe `datetime.now()` y `datetime.utcnow()` en `app/`, y con la validación de
  Pydantic que rechaza instantes sin zona.
