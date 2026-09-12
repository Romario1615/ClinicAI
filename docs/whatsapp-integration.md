# Integración con WhatsApp Business Cloud API

> **Última actualización:** 2026‑09‑12 · Fase 4.
>
> **El camino real no está verificado.** Todo lo descrito aquí se ha ejecutado contra el
> adaptador sandbox y contra PostgreSQL real; **ni un solo mensaje ha salido hacia Meta**,
> porque no hay credenciales y no se inventan (CLAUDE.md, regla 3). Ver
> [limitación E‑1](known-limitations.md).

---

## 1. Lo único que se usa, y por qué

**WhatsApp Business Cloud API.** Nada más.

No se automatiza WhatsApp Web, ni se controla un cliente de escritorio, ni se usa una
librería no oficial (CLAUDE.md, regla 9). El motivo práctico —además de que la política de
WhatsApp lo prohíbe— es que esas técnicas dependen de que el número siga vinculado a un
teléfono encendido, y se rompen con cada actualización del cliente. Una clínica que pierde
el canal de recordatorios el lunes por la mañana no tiene a quién reclamar.

Fuera de la ventana de 24 horas, la Cloud API **solo** permite iniciar conversación con
**plantillas aprobadas por Meta**. No es una restricción que el sistema pueda sortear: es
la razón de que todo el texto saliente viva en un catálogo cerrado.

---

## 2. Ninguna notificación lleva datos clínicos

Es la regla 10 de CLAUDE.md y el requisito RF‑K07, y el motivo no es normativo: **la
pantalla bloqueada de un teléfono es un canal público**. Un recordatorio que diga «su cita
de oncología» lo lee quien pase al lado en el autobús.

### Cómo se hace cumplir

Todo el texto que sale de este sistema hacia una persona está en un solo archivo,
[`app/mensajeria/plantillas.py`](../backend/app/mensajeria/plantillas.py), y se puede leer
entero de una sentada. Cada plantilla declara sus huecos:

```python
TipoMensajeOutbox.TOMA_RECORDATORIO: Plantilla(
    nombre_meta="toma_recordatorio",
    texto=(
        "Hola {nombre}. Es hora de una de las tomas que le indico su profesional.\n\n"
        "Responda TOMADA cuando la haya hecho. Puede ver el detalle en {enlace}."
    ),
    variables_permitidas=frozenset({"nombre", "enlace"}),
),
```

Tres controles, en este orden:

1. **Al construir la plantilla.** Declarar una variable de `VARIABLES_PROHIBIDAS`
   (`diagnostico`, `medicamento`, `dosis`, `motivo_consulta`…) lanza `ValueError` al
   importar el módulo. Falla ahí y no al enviar: si fallara al enviar, el error aparecería
   cuando un paciente ya no recibió su aviso.
2. **Al redactar.** Pasar una variable no declarada es un error, no se ignora. Ignorarlo
   permitiría creer que el dato se está enviando —o que se enviaría si alguien añade el
   hueco después.
3. **En las pruebas.** 26 casos recorren **todas** las plantillas del catálogo verificando
   que ninguna admite ni menciona contenido clínico. No se desactivan.

### El caso que más cuesta aceptar

El recordatorio de medicación **no dice qué medicamento es**. Sería mucho más útil si lo
dijera. No lo dice porque el nombre de un fármaco en una pantalla de bloqueo revela la
condición de quien lo toma —y hay diagnósticos cuya revelación involuntaria cuesta un
empleo o una relación.

El paciente ve el detalle entrando al sistema, que sí tiene control de acceso.

---

## 3. El camino saliente

```
servicio de negocio                worker ARQ                    Meta
      │                                │                          │
      │ encolar(SolicitudEnvio)        │                          │
      │──────────────┐                 │                          │
      │   MISMA TRANSACCIÓN            │                          │
      │   que la cita  │               │                          │
      ▼                ▼               │                          │
   ┌─────────────────────────┐         │                          │
   │ cita          (CONFIRMED)│        │                          │
   │ outbox_mensaje (PENDIENTE)│       │                          │
   └─────────────────────────┘         │                          │
          COMMIT único                 │                          │
                                       │ cada minuto              │
                                       │ FOR UPDATE SKIP LOCKED   │
                                       │─────────────────────────>│
                                       │      referencia_externa  │
                                       │<─────────────────────────│
                                  ENTREGADO                       │
                                       │   estado de entrega      │
                                       │<─────────────────────────│
                                       │        (webhook)         │
```

### Por qué el outbox y no una cola

Está razonado en [ADR‑0008](decisiones/0008-outbox-transaccional.md). En resumen: encolar
en Redis dentro del manejador de la petición es una escritura dual. Si la transacción de la
cita se confirma y el encolado falla, queda una cita confirmada sin recordatorio; al revés,
un recordatorio de una cita que nunca existió.

Aquí la intención de enviar se escribe **en la misma transacción** que el cambio de
negocio. Si la cita se revierte, el mensaje desaparece con ella. Redis pasa a ser un
planificador reemplazable.

### Deduplicación

`clave_deduplicacion` tiene restricción única, y se deriva de la **intención**, no del
momento: `sha256("recordatorio_24h" + cita_id)`. Encolar dos veces lo mismo no produce dos
mensajes.

El detalle que importa: el encolado usa `ON CONFLICT DO NOTHING`. Si la violación de la
clave única subiera, abortaría la transacción **de negocio** —un segundo intento de
confirmar la misma cita fallaría entero por un recordatorio duplicado. El duplicado no es
un error del usuario; es exactamente lo que la clave debe absorber en silencio.

Recibir dos recordatorios de la misma cita lleva al paciente a silenciar las
notificaciones, que es peor que no enviarlas.

### Reintentos

| Desenlace | Qué pasa |
|---|---|
| `ENTREGADO` | Se guarda `referencia_externa` para conciliar el estado de entrega |
| `FALLO_TEMPORAL` | Vuelve a `PENDIENTE` con retroceso exponencial (30 s × 2ⁿ, **tope 1 h**) |
| `FALLO_PERMANENTE` | `FALLIDO` con motivo. No se reintenta |
| Intentos agotados | `FALLIDO`. **No desaparece**: alguien creyó avisar y no ocurrió |

El tope del retroceso no es decorativo: sin él, el sexto intento caería a horas de
distancia y un recordatorio de la cita de mañana llegaría pasado mañana.

**Ante un código de error desconocido se reintenta.** La lista de
`CODIGOS_PERMANENTES` es corta a propósito: descartar un recordatorio por un error que era
temporal es peor que un reintento de más, y la deduplicación absorbe el duplicado.

Un timeout también se reintenta, aunque sea ambiguo —el mensaje pudo entregarse—, por lo
mismo.

### Mensajes huérfanos

Si el worker muere entre tomar un mensaje y registrar el desenlace, queda `EN_PROCESO`.
`recuperar_mensajes_huerfanos` lo devuelve a la cola pasados 15 minutos.

Esto **puede provocar un envío duplicado** si el worker murió justo después de entregar.
Es la elección deliberada: ante la duda, se prefiere que el paciente reciba dos veces un
recordatorio a que no lo reciba.

### El teléfono no se guarda en el outbox

Se resuelve **al entregar**, leyendo `paciente.telefono_whatsapp`. Copiarlo al encolar
sería más simple y se descartó por dos motivos:

* **Minimización.** El outbox conserva histórico de entregados. Copiar el teléfono en cada
  fila crea un segundo registro de datos de contacto, fuera de los controles de acceso y
  de la política de retención de la tabla `paciente`.
* **Corrección.** Entre encolar un recordatorio de 24 horas y entregarlo pasa un día. Si
  el paciente corrige su número, uno copiado enviaría el mensaje al antiguo —que puede
  pertenecer ya a otra persona.

El número se normaliza a solo dígitos en la entrega: la Cloud API rechaza
`+593 99 900 0333`, y ese rechazo llega como fallo sin explicación útil.

---

## 4. El camino entrante: el webhook

`POST /api/v1/whatsapp/webhook` es **el único endpoint público sin autenticación del
sistema**.

### Lo que lo protege

| Control | Dónde |
|---|---|
| Firma HMAC‑SHA256 sobre el **cuerpo crudo** | [`firma.py`](../backend/app/mensajeria/firma.py) |
| Deduplicación por `external_id` (restricción única) | `mensaje_entrante` |
| Límite de tasa por IP (120/min, falla abierto) | [`rutas.py`](../backend/app/mensajeria/rutas.py) |
| Tope de 1 MB en el cuerpo | `rutas.py` |
| Auditoría de firma inválida, con alerta | `webhook.firma_invalida` |

### La firma se calcula sobre los bytes crudos

Dos detalles que suelen hacerse mal:

1. **Cuerpo crudo, no JSON reserializado.** `json.dumps` de un cuerpo parseado cambia
   espacios, orden de claves y escapes, y el HMAC deja de coincidir. La ruta hace
   `await peticion.body()` **antes** de parsear. Hay una prueba
   (`test_el_cuerpo_reserializado_no_valida`) que fija la expectativa para que nadie
   «simplifique» la ruta pasando el cuerpo parseado.
2. **Comparación en tiempo constante.** `hmac.compare_digest`. Comparar con `==` filtra,
   por el tiempo de respuesta, cuántos bytes iniciales acertó el atacante, y eso permite
   construir la firma byte a byte.

Sin esta verificación, un tercero en internet podría inyectar cancelaciones de citas de
pacientes que nunca las pidieron. Una firma inválida devuelve **403** y no escribe nada.

`WHATSAPP_VALIDAR_FIRMA=false` existe para trabajar sin secreto en desarrollo. Está
**prohibido en producción** —`configuracion.py` lo valida al arrancar— y registra un aviso
en cada petición.

### Por qué devuelve 200 casi siempre

Meta reintenta las entregas con error y, si persisten, **deshabilita la suscripción del
webhook**. Perder la suscripción significa dejar de recibir las respuestas de **todos** los
pacientes, y recuperarla es manual.

Por eso un cuerpo deforme, un JSON ilegible o un número sin clínica asociada se acusan con
200 y una alerta en el log, no con un 5xx. La única excepción es la firma inválida: esa
petición no viene de Meta, y Meta nunca verá el 403.

Por lo mismo, el parseo se hace a mano y no con Pydantic estricto: Meta añade campos y
tipos de mensaje sin previo aviso, y un esquema que rechace lo desconocido costaría la
suscripción. Trece pruebas envían formas deformes para comprobar que ninguna rompe el
endpoint.

### Verificación inicial

`GET /api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…`

Devuelve el reto **en texto plano**. Si devolviera JSON, Meta lo rechazaría y el webhook
quedaría sin registrar, con el síntoma confuso de que «responde 200 pero no llegan
mensajes».

### Qué se ejecuta al recibir un mensaje

Esto está razonado en
[ADR‑0017](decisiones/0017-frontera-de-la-automatizacion-entrante.md), y es la decisión
más importante de esta fase:

| El paciente escribe | El sistema |
|---|---|
| `CONFIRMAR`, `CANCELAR`, `SI`, `TOMADA` | Reconoce, registra y **deriva a una persona** |
| `ALTA` | Reconoce, registra y **deriva** |
| `BAJA`, `STOP`, `no molestar` | **Ejecuta**: revoca el consentimiento y cierra el hilo |
| Cualquier otra cosa | Registra y **deriva** |

**Nada que cambie el estado de una cita se ejecuta sin una persona.** El webhook solo trae
un número de teléfono, y en este sistema un teléfono no identifica a una persona: una madre
gestiona las citas de sus tres hijos desde el mismo número. Cancelar la cita equivocada de
una familia es un daño real, y el paciente afectado no se enteraría.

El reconocimiento es **coincidencia exacta de frase normalizada**, sin ningún modelo de
lenguaje. Una interpretación probabilística de «no creo que pueda ir» no es base suficiente
para cancelar la cita de nadie.

`BAJA` es la excepción porque es el único caso donde no hacer nada es peor que
equivocarse, y porque el error se corrige volviendo a dar de alta.

### El formato del número: dónde estuvo el fallo

Toda comparación contra `paciente.telefono_whatsapp` pasa por `telefono_normalizado()`, que
reduce la columna a dígitos **en el `WHERE`**, con el índice funcional
`ix_paciente_whatsapp_normalizado` detrás.

No es una comodidad. El panel guarda el número como lo escribió el personal
(«+593 99 900 0333»); el webhook entrega solo dígitos. Comparar las dos formas en crudo no
encuentra a nadie, y la consecuencia real era que **un paciente que respondía `BAJA` no
quedaba dado de baja** y el sistema le seguía escribiendo —el fallo exacto que ADR‑0017 dice
que no puede ocurrir.

Se encontró ejerciendo el sistema con las semillas reales, con 891 pruebas en verde. Hay seis
pruebas de regresión, y la parametrizada recorre los formatos que produce copiar un número de
una agenda, de un mensaje o de un documento.

### Multi‑clínica

El `phone_number_id` de la carga decide a qué clínica pertenece el mensaje. La asociación
vive en `configuracion_clinica`, no en el entorno:

```sql
INSERT INTO configuracion_clinica (clinica_id, clave, valor, version, vigente)
VALUES ('<uuid de la clinica>', 'whatsapp.id_numero_telefono',
        '{"valor": "<phone_number_id de Meta>"}', 1, true);
```

Sin esa fila, los mensajes de ese número se descartan con `whatsapp.numero_sin_clinica` a
nivel `error`: hay pacientes escribiendo a un número que el sistema no sabe a quién
pertenece, y eso exige intervención.

---

## 5. Consentimiento

Ningún envío proactivo a un paciente sale sin consentimiento vigente. Se comprueba **al
encolar**, no al entregar: si se comprobara al entregar, la operación de negocio parecería
haber avisado al paciente y el aviso se descartaría en silencio horas después.

| Tipo de mensaje | Consentimiento exigido |
|---|---|
| Citas, ofertas de turno | `COMUNICACION_WHATSAPP` |
| Recordatorios de toma y seguimiento | `RECORDATORIOS_MEDICACION` |

Son distintos a propósito: **aceptar avisos de cita no es aceptar que le escriban sobre su
medicación**.

La revocación marca `revocado_en` y **no borra la fila**. Hay que poder demostrar que hubo
consentimiento durante el periodo en que se enviaron los mensajes.

---

## 6. Configuración

Ninguna de estas variables tiene valor en `.env.example` (CLAUDE.md, regla 2).

| Variable | Para qué |
|---|---|
| `MODO_WHATSAPP` | `sandbox` (por defecto) o `cloud_api`. **`sandbox` está prohibido en producción** |
| `WHATSAPP_ID_NUMERO_TELEFONO` | `phone_number_id` de Meta |
| `WHATSAPP_ID_CUENTA_NEGOCIO` | WABA id |
| `WHATSAPP_TOKEN_ACCESO` | Token del sistema. **Secreto** |
| `WHATSAPP_TOKEN_VERIFICACION` | Token del reto inicial. **Secreto** |
| `WHATSAPP_SECRETO_APP` | Secreto de la app, para la firma. **Secreto** |
| `WHATSAPP_VERSION_API` | `v21.0` |
| `WHATSAPP_VALIDAR_FIRMA` | `true`. Solo `false` en desarrollo |

En modo `sandbox` los mensajes se registran en memoria y **no salen a la red**. El worker
avisa en el arranque (`outbox.canal_en_sandbox`) para que nadie confunda una entrega
simulada con una real.

El adaptador real **falla al construirse** si faltan las credenciales, no al primer envío:
arrancar mal configurado significa descubrirlo cuando un paciente no recibió su
recordatorio.

---

## 7. Qué falta para poner esto en producción

Se enumera sin rodeos porque es lo que hay que exigir antes de operar con pacientes:

1. **Cuenta de WhatsApp Business y número verificado.** Los aporta la clínica.
2. **Aprobación de las plantillas por Meta.** Las 10 plantillas de WhatsApp del catálogo
   deben registrarse con el `nombre_meta` que declara `plantillas.py` y el mismo texto. Si
   divergen, el envío falla con «template does not exist».
3. **Verificación del camino real contra el entorno de pruebas de Meta.** Es lo que cierra
   la limitación E‑1. Hasta entonces, la lógica alrededor del envío está verificada y **el
   envío mismo no**.
4. **Repetir la suite con `MODO_WHATSAPP=cloud_api`** y comprobar, como mínimo: entrega
   real, estado de entrega por webhook, firma real de Meta, rechazo de un número inválido,
   comportamiento fuera de la ventana de 24 horas.
5. **Revisión jurídica** del texto de consentimiento y de las plantillas (limitación E‑2,
   [`security.md`](security.md)).
6. **Monitorización** de la cola `FALLIDO` del outbox. Un mensaje fallido significa que
   alguien creyó avisar a un paciente y no ocurrió; si nadie mira esa cola, el estado
   `FALLIDO` no sirve de nada.

---

## 8. Evidencia de las pruebas

Ejecutadas el 2026‑09‑12 contra PostgreSQL 16 + pgvector 0.8.6 en contenedor.

| Suite | Casos | Qué cubre |
|---|---|---|
| `test_plantillas.py` | 40 | Regla 10 sobre el catálogo completo |
| `test_webhook_firma.py` | 13 | Firma válida, alterada, reserializada, sin cabecera, sin secreto; reto inicial |
| `test_carga_whatsapp.py` | 26 | Texto, botón, lista, audio, estados de entrega y 14 formas deformes |
| `test_intenciones.py` | 41 | Lo que se reconoce y, sobre todo, lo que se deriva |
| `test_adaptadores_whatsapp.py` | 32 | Cuerpo de la Cloud API, clasificación de errores, selección por entorno |
| `test_normalizacion_telefono.py` | 6 | Formato que exige el proveedor |
| `test_outbox.py` | 25 | Deduplicación, rollback, reintentos, huérfanos, conciliación, consentimiento |
| `test_destinatarios.py` | 16 | Resolución de contacto en las tres tablas |
| `test_tareas_outbox.py` | 3 | El trabajo periódico completo |
| `test_webhook_whatsapp_api.py` | 34 | El endpoint real: firma, deduplicación, baja, frontera clínica, robustez, **formato del número** |

```
uv run pytest -q                    →  899 passed
uv run pytest --cov=app             →  91,65 %
uv run ruff check . ; uv run mypy app  →  sin hallazgos
uv run alembic upgrade head ; downgrade -1 ; upgrade head  →  correcto
```

Cobertura de los módulos de esta fase: `plantillas.py` y `firma.py` 100 %,
`servicios.py` 98 %, `destinatarios.py` 98 %, `conversaciones/servicios.py` 100 %,
`intenciones.py` 94 %, `adaptadores.py` 93 %, `carga_whatsapp.py` 90 %, `rutas.py` 90 %.

Además, **33 comprobaciones sobre la API arrancada** contra la base con datos sintéticos:
encolado, deduplicación, entrega por el worker, normalización del destino, reto de
verificación, firma inválida sin efecto y auditada, reintento de Meta, apertura de hilo,
`CANCELAR` derivado, estado de entrega conciliado, `BAJA` aplicada y tres cuerpos deformes.

Ese ejercicio es el que encontró el fallo del formato del número. **Una suite verde no
sustituye a ejercer el sistema**, y ninguno de los dos sustituye a verificar el camino real
del proveedor. Ver [`test-plan.md`](test-plan.md).
