# ADR‑0009 — El anti doble‑reserva vive en la base de datos

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

Se exige «prevención de doble reserva» y «manejo de concurrencia», con pruebas
explícitas de dos pacientes intentando reservar el mismo horario y de dos pacientes
aceptando la misma oferta de lista de espera.

El enfoque habitual —comprobar en Python si el turno está libre y después insertar— es
una condición de carrera clásica. Entre la comprobación y la inserción, otra transacción
puede insertar la misma cita. Con el nivel de aislamiento por defecto de PostgreSQL
(`READ COMMITTED`) la comprobación no bloquea nada. Bajo dos peticiones concurrentes, el
resultado es una doble reserva: dos pacientes en el mismo minuto con el mismo médico.

## Decisión

La garantía se traslada al motor de base de datos.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE cita
  ADD COLUMN rango tstzrange
    GENERATED ALWAYS AS (
      tstzrange(inicio, inicio + duracion_total, '[)')
    ) STORED;

-- Un profesional no puede tener dos citas activas solapadas
ALTER TABLE cita
  ADD CONSTRAINT cita_sin_solape_profesional
  EXCLUDE USING gist (
    profesional_id WITH =,
    rango          WITH &&
  ) WHERE (estado IN ('HELD', 'CONFIRMED', 'RESCHEDULED'));

-- Ni un consultorio, ni un recurso
ALTER TABLE cita
  ADD CONSTRAINT cita_sin_solape_consultorio
  EXCLUDE USING gist (
    consultorio_id WITH =,
    rango          WITH &&
  ) WHERE (estado IN ('HELD', 'CONFIRMED', 'RESCHEDULED') AND consultorio_id IS NOT NULL);
```

`duracion_total` incluye la duración del servicio más el tiempo de preparación, de forma
que el buffer entre citas también queda protegido por la restricción y no depende de que
el código lo recuerde.

El servicio intenta la inserción y **trata la violación de la restricción como un
resultado esperado**, traduciéndola a un error de dominio «turno ya no disponible». No
es una excepción excepcional: es el mecanismo normal de resolución de la carrera.

Para la aceptación de ofertas de lista de espera, donde el conflicto es sobre un turno
que todavía no existe como fila, se usa `pg_advisory_xact_lock` sobre un hash de
`(profesional_id, inicio)`, más un índice único parcial que garantiza una sola oferta
activa por turno.

## Consecuencias

* Un error en la lógica de aplicación **no puede** producir una doble reserva: el motor
  la rechaza. Esto es lo que convierte la prueba de concurrencia en una verificación real
  y no en una comprobación de que el código «suele» funcionar.
* Requiere la extensión `btree_gist`, disponible en la imagen `pgvector/pgvector:pg16`.
* Las citas canceladas, completadas o marcadas como inasistencia quedan fuera de la
  restricción por la cláusula `WHERE`, así que el historial se conserva completo sin
  bloquear el turno.
* Cualquier migración futura sobre `cita` debe preservar la columna generada y la
  restricción. Hay una prueba de integración que falla si la restricción desaparece.
* Las citas recurrentes se insertan como filas individuales, cada una validada por la
  misma restricción; no hay un camino que las inserte sin verificación.

## Anexo (2026‑10‑07) — Series recurrentes

Decisiones tomadas al revisar `POST /api/v1/agenda/citas/series`. No afectan a la
garantía de la base de datos; precisan qué valida la aplicación antes de insertar.

* **Todas o ninguna.** Las citas de la serie se insertan en una sola transacción; si
  una fecha falla (validación previa o exclusión `gist`), no queda ninguna.
* **Contención, no rejilla.** Antes de insertar, cada fecha se comprueba contra los
  **huecos libres** del día (franjas menos descansos, feriados, bloqueos y citas,
  `calcular_huecos_libres`) y la antelación mínima de la sede. No se exige que la hora
  coincida con un turno ofrecido: la rejilla arranca al principio de cada hueco y
  cambia con las citas de cada día, así que una cita previa de otra duración la
  desplaza (el 12/10 se ofrece 10:15 y el 19/10 no, aunque esté libre). La reserva
  individual tampoco exige la rejilla.
* **`MENSUAL` = cada cuatro semanas, el mismo día de la semana.** Las franjas de
  atención son semanales; «el mismo número de día de cada mes» caía en jueves, sábado
  o martes y la serie se rechazaba en cuanto el profesional no atendía ese día. Se
  descartó «el n‑ésimo día de la semana del mes» porque el quinto lunes no existe en
  todos los meses. Consecuencia aceptada: en un año hay 13 citas «mensuales», no 12.
  La interfaz debe rotular la opción como «Cada 4 semanas».
* **Un año como máximo, en una sola tabla.** `MAXIMO_CITAS_SERIE_POR_FRECUENCIA` en
  `app/modulos/agenda/esquemas.py`: `SEMANAL` 53 (364 días), `QUINCENAL` 27 (364),
  `MENSUAL` 13 (336). La usan el esquema de entrada y el servicio; la interfaz replica
  los mismos números.
* **Clínica y ámbito antes de la agenda.** `cita` solo tiene FK simples, sin
  disparador de coherencia de clínica. El servicio exige que sede, paciente, servicio
  y profesional sean de la clínica del principal, y sede y paciente de su ámbito; si
  no, 404 con el mismo mensaje que un recurso inexistente. En una serie se comprueba
  el paciente una vez antes de validar fechas y de nuevo en cada inserción.
