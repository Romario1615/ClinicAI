# ADR-0027 · Google Calendar y renovación de credenciales

Fecha: 2026-10-10. Estado: aceptado; integración con una cuenta real pendiente.

## Contexto

La agenda interna y la cola de reflejos existían, pero el modo `google`
lanzaba `NotImplementedError`. Los tokens vencidos exigían autorización manual.
Las claves ingresadas por clínica en Integraciones no llegaban al flujo OAuth.

## Decisión

- `AdaptadorGoogleCalendario` implementa Google Calendar v3 mediante HTTPX,
  sin nuevas dependencias. El modo sandbox conserva su aislamiento de red.
- La configuración vigente de la clínica prevalece sobre el entorno. Si se
  desactiva o falta su secreto, no se utiliza la cuenta global. Las claves
  se descifran con el contexto autenticado de esa clínica.
- El profesional autoriza únicamente su calendario. El `state` conserva
  profesional y calendario elegido, tiene firma, caducidad y consumo único.
- Google se abre por un enlace en otra pestaña con `noopener noreferrer`.
  Así se conserva la sesión en memoria de la aplicación. El callback HTML
  informa que se puede cerrar esa pestaña; el consumidor JSON sigue recibiendo
  el esquema de conexión sin tokens. La devolución HTML no se almacena en caché.
- La renovación se realiza antes de la caducidad o tras un 401, con un intento
  por conexión y lote. Los nuevos tokens se cifran con el profesional como
  contexto; un bloqueo de fila evita renovaciones simultáneas de la conexión.
- `invalid_grant` exige nueva autorización; un fallo temporal conserva la cita
  y el evento pendiente. El worker vuelve a intentarlo en su siguiente ciclo.
- Una inserción usa UUID determinista. Tras un 409 se comprueba el evento; una
  respuesta perdida no permite insertarlo con otro ID. Un borrado confirmado
  avanza a una generación determinista, con límite de cinco generaciones.
- Las modificaciones utilizan `If-Match`. Un cambio externo, una marca de origen
  ausente o una referencia ajena produce conflicto y necesita revisión humana.
- Los fallos de consulta nunca se interpretan como borrados. Los mensajes de
  error no contienen el cuerpo de Google ni credenciales.
- La sincronización manual detecta citas y procesa únicamente la conexión
  propia solicitada. Permite reintentar errores; conserva conflictos. Conexión,
  desconexión y sincronización manual dejan auditoría.

## Consecuencias y límites

La reserva no depende de Google. Los eventos contienen título neutro, horario,
ubicación autorizada y referencia UUID; no incluyen pacientes ni invitados.
La comprobación remota continúa siendo una lectura por evento. `syncToken`,
reconciliación incremental y resolución de conflictos desde la interfaz siguen
pendientes. El botón manual no sobrescribe un conflicto.

HTTP simulado comprueba los contratos y PostgreSQL comprueba persistencia y
aislamiento. Ninguno acredita que una cuenta de Google acepte el intercambio,
los permisos y los eventos: la aceptación externa requiere credenciales reales.

## Referencias

- [Inserción y formato del identificador](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).
- [Errores y precondiciones](https://developers.google.com/workspace/calendar/api/guides/errors).
- [OAuth y renovación](https://developers.google.com/identity/protocols/oauth2/web-server#offline).
- [Guía de operación](../calendar-integration.md).
