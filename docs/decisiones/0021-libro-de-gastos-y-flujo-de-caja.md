# ADR-0021 — Libro de gastos y flujo de caja en base de caja

* **Estado:** aceptada
* **Fecha:** 2026-10-07
* **Decidida por:** el equipo de desarrollo, con supuestos seguros y reversibles
  (CLAUDE.md, regla 11: ambigüedad que no bloquea la seguridad clínica)
* **Relacionada con:** [ADR-0008](0008-outbox-transaccional.md) (idempotencia de
  escrituras), [ADR-0011](0011-historia-clinica-append-only.md) (inmutabilidad)

---

## Contexto

El README listaba como pendiente «libro de gastos, flujo de caja, conciliación y
utilidad neta», con una advertencia: no estimarlos a partir de pagos brutos. El
panel solo sumaba pagos. Una clínica necesita saber en qué se fue el dinero y
cómo quedó la caja de un periodo, sin esperar a la contabilidad del mes.

## Decisión

1. **Una tabla `gasto` de solo anulación.** Un gasto no se edita ni se borra: se
   anula con motivo (una sola vez) y se registra el correcto. Un disparador de
   PostgreSQL (`gasto_solo_anulacion`) rechaza con SQLSTATE `42501` cualquier
   `UPDATE` que no sea esa transición y cualquier `DELETE`; otro rechaza
   `TRUNCATE`. Una restricción `CHECK` obliga a que la anulación lleve quién,
   cuándo y por qué.
2. **Fecha local del comprobante**, no instante: `fecha` es un `date` del día en
   que se pagó. No puede ser futura respecto del día local de la sede (o de la
   clínica).
3. **Moneda USD**, como los pagos (`CHECK moneda = 'USD'`). Ecuador opera en
   dólares; otra moneda exigiría tipo de cambio y no hay definición para ello.
4. **Permisos separados de pagos:** `gasto.leer` y `gasto.registrar`. Quien cobra
   en el mostrador no es necesariamente quien lleva el libro de egresos.
   Asignación inicial, la más restrictiva razonable: superadministración y
   administración de clínica tienen ambos; auditoría solo lectura; recepción,
   profesional y asistente ninguno. Cada clínica puede crear un rol propio con
   ellos (por ejemplo, caja chica en recepción).
5. **Ámbito por sede.** Un gasto con sede se ve con ámbito sobre esa sede; un
   gasto de toda la clínica (sin sede) solo con ámbito de todas las sedes, y
   solo quien lo tiene puede registrarlo. Fuera de ámbito, 404.
6. **Flujo de caja en base de caja.** `GET /gastos/flujo` exige además
   `pago.leer`: ingresos son los pagos `CONFIRMED` agrupados por la fecha local
   de registro (la misma regla que el CSV de Pagos), gastos son los vigentes por
   su fecha. Resultado = ingresos − gastos; margen = resultado / ingresos. Se
   llama **resultado de caja**, no utilidad, y la respuesta lo dice en `base`.
7. **Idempotencia en el alta** con `Idempotency-Key`: el doble clic o el
   reintento tras un corte no duplican un egreso.

## Alternativas descartadas

* **Editar gastos con historial de versiones.** Más flexible, pero un libro que
  cambia sus importes complica la conciliación. Anular y volver a registrar deja
  el mismo rastro con un modelo más simple.
* **Llamar «utilidad neta» al resultado.** Sería falso: no hay devengos,
  depreciaciones, impuestos ni cuentas por pagar. La pantalla y la API lo dicen.
* **Reutilizar `pago.validar` para registrar gastos.** Mezclaría dos funciones
  que una clínica puede querer separar.

## Consecuencias

* El panel puede mostrar un resultado de caja honesto sin inventar costos.
* Sigue pendiente: adjuntar comprobantes a los gastos (hoy se anota la
  referencia), cuentas por pagar, presupuestos de gasto, conciliación bancaria,
  exportación contable y facturación electrónica SRI (requiere credenciales y
  revisión legal). Nada de esto se simula.
