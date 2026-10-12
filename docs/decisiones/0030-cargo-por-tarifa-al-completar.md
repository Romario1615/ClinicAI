# ADR-0030 · Cargo por tarifa al completar la atención

Fecha: 2026-10-11 · Estado: aceptada

## Contexto

La prueba de uso real como odontólogo (`pruebas-e2e/escenarios/43-dia-odontologo.spec.ts`,
informe `tmp/recorrido-odontologo.md`) mostró que una cita podía marcarse como
atendida sin dejar ningún cobro pendiente: recepción tenía que escribir el total
al registrar el primer abono. El usuario pidió resolver las decisiones como lo
hace el software odontológico del mercado. En Open Dental y similares, completar
un procedimiento genera el cargo con la tarifa del arancel.

## Decisión

Al pasar una cita a `COMPLETED`, si su servicio tiene `precio > 0` y la cita aún
no tiene `cargo_pago`, se crea uno con `total_acordado = servicio.precio`,
`origen = 'PACTADO'`, en la misma transacción y auditado como
`cargo_pago.creado` con `origen_total = TARIFA_SERVICIO`.

* Un cargo ya pactado o abonado no se modifica.
* Sin precio en el servicio no se inventa importe.
* Recepción ajusta descuentos o convenios con `PATCH /pagos/cargos/{id}/total`.
* No toca datos clínicos ni decisiones clínicas: es un importe administrativo.

## Consecuencias

* Recepción ve el pendiente en Pagos tras la atención, sin teclear el total.
* La tarifa vigente al completar queda congelada en el cargo; cambiar después el
  precio del servicio no reescribe cobros pasados.
* Se reutiliza `origen = 'PACTADO'` para no migrar la restricción
  `origen_coherente`; la auditoría distingue el origen por tarifa.
