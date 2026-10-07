# Monitoreo

> **Estado:** la API expone métricas Prometheus agregadas en `/metrics`: tráfico
> HTTP por patrón de ruta, duración y estado de solicitudes, estados del outbox,
> antigüedad de la cola pendiente y fallo al consultar PostgreSQL. No incluye
> identificadores de ruta, clínicas ni contenido clínico. Hay una configuración
> opcional local de Prometheus con retención de 15 días y cuatro reglas; la
> interfaz solo escucha en `127.0.0.1:9090`.
>
> Este perfil no es monitoreo de producción: no incluye Alertmanager, destinatarios,
> guardia, métricas de auditoría/Redis ni agregación de registros. Nadie recibe una
> notificación si una regla se activa.

---

## 1. Las sondas que ya existen

| Sonda | Qué responde | Qué hacer si falla |
|---|---|---|
| `GET /salud/vivo` | El proceso responde | Reiniciarlo. No consulta la base: si lo hiciera, una caída de PostgreSQL provocaría reinicios en bucle que no arreglan nada |
| `GET /salud/listo` | Además, la base responde y tiene las extensiones | **Sacarlo del balanceador, no reiniciarlo.** El proceso está sano; lo que falta es una dependencia |

Esa separación es el motivo de que existan dos. Confundirlas produce el peor
comportamiento posible durante un incidente de base de datos: todos los
procesos reiniciándose a la vez.

---

## 2. Lo que hay que vigilar, en orden de daño

### 2.1 Daño a un paciente

| Señal | Qué significa | Umbral sugerido |
|---|---|---|
| **Cola `FALLIDO` del outbox** | Mensajes que agotaron sus reintentos. Cada uno es un recordatorio que un paciente **no** recibió | Cualquier valor > 0 sostenido 15 min |
| **Antigüedad del mensaje más viejo en `PENDIENTE`** | El worker no está procesando. La cola crece sin que nada falle visiblemente | > 10 min |
| **`outbox.huerfanos_recuperados`** | El worker murió a medio envío. Puede haber duplicados (E‑14) | Cualquiera. Investigar por qué murió |
| **Tomas vencidas sin registrar, en aumento** | La adherencia deja de medirse | Tendencia, no umbral |

El primero es el que más importa y el que menos se nota: nada falla, nadie ve
un error, y un paciente no llega a su cita.

### 2.2 Señales de ataque

Todas estas acciones están en `ACCIONES_CON_ALERTA` (`app/nucleo/auditoria.py`)
y **ya se registran**. Lo que falta es que alguien las mire.

| Acción auditada | Por qué alerta |
|---|---|
| `TOKEN_REUTILIZADO` | Un refresco presentado dos veces: token robado hasta que se demuestre lo contrario |
| `WEBHOOK_FIRMA_INVALIDA` | Alguien llama al webhook sin la firma de Meta |
| `INYECCION_DETECTADA` | Un documento ingerido contenía algo que parece una instrucción |
| `HERRAMIENTA_DENEGADA` | El agente pidió una herramienta que no existe o sin permiso. **Nombres inventados repetidos no son una errata** |
| `ACCESO_EMERGENCIA` | Alguien se saltó la relación asistencial. Legítimo a veces; siempre revisable |
| `EXPORTACION_TITULAR` | Salida masiva de datos de un paciente |
| `AMBITO_MODIFICADO` | Alguien amplió lo que otro puede ver |

| Evento de registro | Por qué alerta |
|---|---|
| `whatsapp.firma_no_verificada` | Igual que arriba, visto desde el canal |
| `calendario.oauth.estado_reutilizado` | Intento de reutilizar un `state`: posible CSRF sobre el flujo de OAuth |
| `agente.herramienta_inexistente` | El modelo pidió algo que no está en el catálogo |

### 2.3 Degradación silenciosa

Estas no rompen nada. Ese es el problema.

| Señal | Qué se degrada sin avisar |
|---|---|
| **`limite_tasa.sin_contador.permitido`** | Redis no responde y el límite de tasa **falla abierto** fuera de autenticación (E‑11). Un cliente autenticado puede exceder su cuota mientras dure |
| **`outbox.canal_en_sandbox`** en el arranque | Un canal marca entregado sin que salga nada (E‑16). Si aparece en producción, los mensajes no se envían |

### Métricas exportadas por la API

| Serie | Etiquetas | Interpretación |
|---|---|---|
| `clinicai_http_solicitudes_total` | método, patrón de ruta, estado HTTP | Volumen y errores por operación. Los parámetros dinámicos se sustituyen por la plantilla de FastAPI; las rutas sin coincidencia usan `no_encontrada` |
| `clinicai_http_duracion_segundos` | método, patrón de ruta | Histograma para calcular percentiles de latencia |
| `clinicai_outbox_mensajes` | estado | Conteo actual por estado; `FALLIDO > 0` requiere revisión |
| `clinicai_outbox_pendiente_mas_antiguo_segundos` | ninguna | Edad de la fila pendiente más antigua; `> 600` sugiere worker detenido |
| `clinicai_outbox_lectura_fallida` | ninguna | `1` indica que no fue posible consultar PostgreSQL durante el scrape |

El endpoint no exporta clínica, destino, contenido, UUID ni ruta solicitada sin
normalizar. El scrape consulta la base para renovar los gauges; ante un fallo de
esa consulta devuelve las métricas del proceso y pone
`clinicai_outbox_lectura_fallida` en `1`.

### Recolector opcional de desarrollo

El perfil `observabilidad` en `infra/compose/docker-compose.dev.yml` arranca
Prometheus local. Guarda muestras durante 15 días en un volumen Docker. Las cuatro
reglas declaradas cubren scrape fallido, mensajes del outbox fallidos, cola con más
de diez minutos y error al consultar el outbox. Prometheus evalúa las reglas y las
muestra en `http://127.0.0.1:9090/alerts`; no las entrega a personas.

Con el backend disponible en `0.0.0.0:8000` para que WSL pueda alcanzarlo, inicie
el perfil desde la distribución `clinica`. El script calcula la puerta de enlace de
Windows en cada ejecución y la pasa al contenedor; no reutilice una IP fija:

```powershell
wsl -d clinica -- bash -lc "cd '/mnt/d/Sistema IA de Clinicas' && bash infra/wsl/observabilidad.sh up -d prometheus"
# Ver estado del recolector
wsl -d clinica -- bash -lc "cd '/mnt/d/Sistema IA de Clinicas' && bash infra/wsl/observabilidad.sh ps prometheus"
# Detener solo Prometheus y conservar sus muestras
wsl -d clinica -- bash -lc "cd '/mnt/d/Sistema IA de Clinicas' && bash infra/wsl/observabilidad.sh stop prometheus"
```

El destino configurado es `host.docker.internal:8000`. Confirme en
`http://127.0.0.1:9090/targets` que `clinicai-api` esté `UP`; `docker compose ps`
por sí solo solo confirma que el contenedor está activo.
| **`whatsapp.numero_sin_clinica`** | Llega un mensaje a un número que no corresponde a ninguna clínica |
| **`error.bd.no_traducido`** | Un error del motor que la capa de traducción no reconoce: el paciente ve un 500 genérico donde debería ver una causa |
| **`agente.herramienta_error_inesperado`** | Un fallo de programación en una herramienta. El paciente recibe «le paso con una persona» y el fallo queda solo aquí (E‑24) |
| **`calendario.desconectado` / `reflejos_detectados`** | El calendario externo dejó de reflejar la agenda |

### 2.4 Salud del servicio

Lo habitual, y lo último de la lista a propósito: latencia por endpoint, tasa
de 5xx, conexiones de PostgreSQL, memoria del worker, espacio en disco.

Un cuadro de mandos que solo tenga esta sección da la impresión de que todo va
bien mientras ocurre cualquier cosa de las tres secciones anteriores.

---

## 3. Lo que ya está preparado

* **Registro estructurado** (`app/nucleo/registro.py`): JSON con
  `correlacion_id` en cada línea. Ese identificador viaja en la respuesta de
  error, así que un paciente que reporta un problema trae consigo la clave para
  encontrar su traza exacta.
* **Auditoría con `requiere_alerta`**: `EntradaAuditoria` ya expone la
  propiedad. Solo hay que consumirla.
* **Errores con `codigo` estable**: se puede agrupar por código en lugar de por
  texto, que cambia al reescribirlo.
* **Exportador Prometheus** (`GET /metrics`): contadores e histogramas HTTP con
  etiquetas de cardinalidad acotada y gauges del outbox consultados al hacer
  scrape. La ruta es configurable con `RUTA_METRICAS` y se puede desactivar con
  `METRICAS_HABILITADAS=false`. En producción exige `METRICAS_TOKEN` de al menos
  32 caracteres y valida `Authorization: Bearer …`; el proxy también debe
  mantenerla en la red privada del recolector.

## 4. Lo que falta

| Pendiente | Consecuencia de no tenerlo |
|---|---|
| Recolector Prometheus de producción, con retención acordada | El perfil local conserva muestras 15 días; no demuestra retención ni disponibilidad de producción |
| Alertmanager, destinatario y guardia | Prometheus evalúa cuatro reglas locales, pero **nadie recibe nada** cuando se activan |
| Alertas de eventos de seguridad y degradación de Redis | Las acciones de auditoría y fallos de contador todavía no se exportan como métricas ni reglas |
| Agregación de registros | Buscar un `correlacion_id` exige entrar al servidor |
| Cuadro de mandos operativo | Sin él, la cola del outbox se mira cuando alguien se acuerda |
| Retención de registros | Un registro que se rota a los 3 días no sirve para investigar un incidente de la semana pasada |
| Definición de guardia | Una alerta sin destinatario a las 3 de la mañana es un registro más |

---

## 5. Lo mínimo antes de operar con pacientes reales

No hace falta una pila completa. Hace falta que **estas cuatro cosas despierten
a alguien**:

1. `/salud/listo` fallando más de 2 minutos. La regla local actual detecta scrape fallido de `/metrics`, no distingue esta sonda.
2. `clinicai_outbox_mensajes{estado="FALLIDO"}` por encima de 0 durante 15 minutos. La regla ya está definida localmente.
3. Cualquier acción de `ACCIONES_CON_ALERTA`; falta instrumentación y su regla.
4. `limite_tasa.sin_contador.permitido`, que significa que un control de
   seguridad está desactivado sin que nadie lo haya decidido.

También conviene alertar si `clinicai_outbox_pendiente_mas_antiguo_segundos > 600`
o `clinicai_outbox_lectura_fallida > 0`. Las tres reglas del outbox ya están definidas
y se verifican por configuración; sigue faltando entregar todos estos avisos a un
destinatario y acordar guardias antes de atender pacientes reales.

Todo lo demás puede esperar a que haya tiempo. Esto no.

Ver también [`incident-response.md`](incident-response.md) y
[`known-limitations.md`](known-limitations.md).
