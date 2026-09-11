# ADR‑0008 — Outbox transaccional en PostgreSQL para todo envío saliente

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

Los criterios de producción exigen que «los recordatorios sean persistentes y
reintentables», y las pruebas de recuperación obligan a verificar que no se pierden
recordatorios ni mensajes ante la caída de Redis, de WhatsApp, del calendario o del
propio worker.

El patrón habitual —encolar el envío en Redis dentro del manejador de la petición— tiene
dos fallos que en un contexto clínico son inaceptables:

1. **Escritura dual.** Si la transacción de la cita se confirma y el encolado en Redis
   falla (o al revés), el estado queda inconsistente: cita confirmada sin recordatorio, o
   recordatorio de una cita que nunca existió.
2. **Durabilidad de Redis.** Con la configuración por defecto, Redis puede perder los
   últimos segundos de escrituras al caer. Un recordatorio de medicación perdido no es un
   fallo cosmético.

## Decisión

Toda intención de comunicación saliente se escribe en una tabla `outbox_mensaje` de
PostgreSQL **dentro de la misma transacción** que el cambio de negocio que la origina.
Un procesador aparte lee las entradas pendientes y las entrega.

```
tabla outbox_mensaje
  id, tipo, destino_tipo, destino_id, canal
  carga_util (jsonb), clave_deduplicacion (única)
  estado: PENDIENTE | EN_PROCESO | ENTREGADO | FALLIDO | DESCARTADO
  intentos, max_intentos, proximo_intento_en
  creado_en, actualizado_en, ultimo_error
  entidad_origen_tipo, entidad_origen_id   -- trazabilidad
```

* Entrega **al menos una vez**, con idempotencia en el destino mediante
  `clave_deduplicacion`.
* Reintentos con retroceso exponencial más fluctuación aleatoria; tras agotar
  `max_intentos` pasa a `FALLIDO` y genera una alerta en lugar de desaparecer.
* La toma de trabajo usa `SELECT ... FOR UPDATE SKIP LOCKED`, de modo que varios workers
  pueden procesar en paralelo sin entregar dos veces el mismo mensaje.
* **Redis queda como planificador y acelerador**, no como fuente de verdad: si Redis se
  vacía, el procesador de outbox sigue encontrando en PostgreSQL todo lo pendiente.

## Consecuencias

**A favor**

* No hay escritura dual: la comunicación es tan durable como el dato de negocio.
* La caída de Redis, del worker o de un proveedor externo retrasa el envío, no lo pierde;
  eso es exactamente lo que verifican las pruebas de recuperación.
* Cada mensaje conserva la entidad que lo originó, lo que da una traza auditable de por
  qué se contactó a un paciente.

**En contra y mitigaciones**

* Latencia añadida por el intervalo de barrido (`OUTBOX_INTERVALO_SEGUNDOS`, 10 s por
  defecto). Para mensajes interactivos de WhatsApp, donde la latencia sí importa, el
  servicio notifica al worker por Redis tras la confirmación para que procese de
  inmediato; el barrido periódico queda como red de seguridad.
* Carga adicional de escritura en PostgreSQL. Mitigación: índice parcial sobre
  `(proximo_intento_en)` restringido a `estado = 'PENDIENTE'`, y purga de entregados
  según la política de retención.
* Complejidad mayor que encolar directamente. Se acepta: es el punto donde se gana la
  garantía que exige el requisito.
