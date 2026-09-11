# ADR‑0012 — Adaptadores sandbox para integraciones sin credenciales

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

El sistema depende de WhatsApp Business Cloud API y de Google Calendar. El entorno **no
tiene** credenciales de ninguno de los dos, y la instrucción es clara: no inventar
credenciales, tokens, números de WhatsApp ni calendarios; si falta una credencial
externa, crear una integración segura con modo sandbox o mock.

## Decisión

Cada integración externa se define como una interfaz con **dos** implementaciones que
cumplen el mismo contrato:

| Interfaz | Implementación real | Implementación sandbox |
|---|---|---|
| `ClienteWhatsApp` | `MODO_WHATSAPP=cloud_api` | `MODO_WHATSAPP=sandbox` |
| `ClienteCalendario` | `MODO_CALENDARIO=google` | `MODO_CALENDARIO=sandbox` |
| `ClienteCorreo` | `MODO_CORREO=smtp` | `MODO_CORREO=consola` |

El adaptador sandbox **no es un `return True`**. Reproduce el comportamiento observable
del proveedor, incluidos sus modos de fallo, porque es ahí donde está el valor de la
prueba:

* Persiste los mensajes «enviados» en una tabla inspeccionable, para que las pruebas de
  extremo a extremo comprueben qué se envió, a quién y con qué plantilla.
* Emite webhooks simulados con **firma HMAC válida** calculada igual que Meta, de modo
  que la ruta de validación de firma se ejercita de verdad.
* Sabe fallar a demanda: firma inválida, mensaje duplicado, plantilla inexistente,
  número inválido, error de cuota, error temporal con reintento, token vencido, evento
  borrado externamente, conflicto de horario.
* Respeta la ventana de 24 horas de WhatsApp y exige plantilla aprobada para mensajes
  proactivos, igual que el proveedor real.

Se mantiene una **suite de pruebas de contrato** común que se ejecuta contra ambas
implementaciones, para que el sandbox no se desvíe del contrato real.

## Consecuencias

* Todos los flujos —reserva por WhatsApp, recordatorios, ofertas de lista de espera,
  sincronización de calendario— son desarrollables y probables de extremo a extremo hoy.
* El código de producción no contiene ninguna rama `if es_prueba`. La selección ocurre en
  la inyección de dependencias según el entorno.
* **Limitación que se declara explícitamente:** las rutas reales contra Meta y Google
  quedan **sin verificar contra el proveedor**. El sandbox demuestra que nuestra lógica es
  correcta frente al contrato documentado, no que el contrato documentado coincida al
  detalle con el comportamiento real. Antes de producción hace falta una verificación con
  credenciales reales en preproducción; está en
  [`../production-readiness.md`](../production-readiness.md) como criterio pendiente.
* El arranque en `ENTORNO=produccion` **falla** si algún modo sigue en `sandbox`, para que
  nadie ponga en marcha una clínica creyendo que envía recordatorios.
