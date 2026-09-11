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
