# ADR-0031 · No se cierra una cita antes de su hora

Fecha: 2026-10-13 · Estado: aceptada

## Contexto

La auditoría de interfaz (anexo K) mostró hasta 9 citas solapadas de un mismo
profesional. Causa: se podía marcar como atendida (`COMPLETED`) o inasistencia
(`NO_SHOW`) una cita futura. `COMPLETED` no está entre los estados que ocupan
la agenda (ADR-0009), así que el turno quedaba libre y podía reservarse otra
vez. Una inasistencia futura tampoco tiene sentido. El software odontológico
del mercado no permite completar procedimientos con fecha futura.

## Decisión

En `ServicioAgenda._cerrar`, si `ahora < cita.inicio`:

* `NO_SHOW` → 409 «No se puede marcar inasistencia antes de la hora de la cita.»
* `COMPLETED` → 409 «La cita aún no empieza: inicie la atención antes de
  marcarla como atendida.», **salvo** que la atención ya se haya iniciado
  (`atencion_iniciada_en`), caso del paciente que llega antes.

La hora viene del reloj inyectado (`app/nucleo/reloj.py`).

## Consecuencias

* Desaparece la doble reserva por citas futuras «atendidas».
* La interfaz debe ocultar o deshabilitar con explicación «Marcar atendida» e
  «Inasistencia» en citas futuras (prevención de errores, Nielsen).
* Las pruebas que cerraban citas futuras adelantan el reloj o inician la
  atención; ninguna aserción se relaja.
