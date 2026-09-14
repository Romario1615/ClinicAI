# Monitoreo

> **Estado:** este documento define **qué** hay que vigilar y por qué. La
> infraestructura que lo vigila —recolector de métricas, alertas, guardias— **no
> está montada**. Lo que sí existe es el sistema emitiendo los eventos, en
> formato estructurado y con `correlacion_id`.
>
> Se escribe antes de montar nada a propósito: una pila de monitoreo instalada
> sin decidir qué importa acaba mostrando uso de CPU mientras la cola de
> mensajes a pacientes se llena en silencio.

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

## 4. Lo que falta

| Pendiente | Consecuencia de no tenerlo |
|---|---|
| Recolección de métricas (Prometheus/OpenTelemetry) | No hay serie temporal: no se puede decir «esto empeoró el martes» |
| Agregación de registros | Buscar un `correlacion_id` exige entrar al servidor |
| Reglas de alerta y destinatario | **Nadie recibe nada.** Es lo que convierte esta lista en monitoreo real |
| Cuadro de mandos operativo | Sin él, la cola del outbox se mira cuando alguien se acuerda |
| Retención de registros | Un registro que se rota a los 3 días no sirve para investigar un incidente de la semana pasada |
| Definición de guardia | Una alerta sin destinatario a las 3 de la mañana es un registro más |

---

## 5. Lo mínimo antes de operar con pacientes reales

No hace falta una pila completa. Hace falta que **estas cuatro cosas despierten
a alguien**:

1. `/salud/listo` fallando más de 2 minutos.
2. Cola `FALLIDO` del outbox por encima de 0 durante 15 minutos.
3. Cualquier acción de `ACCIONES_CON_ALERTA`.
4. `limite_tasa.sin_contador.permitido`, que significa que un control de
   seguridad está desactivado sin que nadie lo haya decidido.

Todo lo demás puede esperar a que haya tiempo. Esto no.

Ver también [`incident-response.md`](incident-response.md) y
[`known-limitations.md`](known-limitations.md).
