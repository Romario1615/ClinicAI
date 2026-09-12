# Integración con calendarios externos

> **Última actualización:** 2026‑09‑12 · Fase 4.
>
> **El adaptador real de Google no existe todavía.** Lo implementado es el flujo completo
> con adaptador sandbox: OAuth con `state` firmado, tokens cifrados, publicación,
> reconciliación de cambios externos y el trabajo periódico. No hay credenciales de Google
> y no se inventan (CLAUDE.md, regla 3). Ver [limitación E‑1](known-limitations.md).

---

## 1. La regla de la que se deriva todo

**La agenda interna es la fuente de verdad. El calendario externo es un reflejo.**
(CLAUDE.md sección 6, RF‑I08.)

Esa frase decide cada caso dudoso sin tener que pensarlo dos veces:

| Situación | Qué hace el sistema | Por qué |
|---|---|---|
| El proveedor no responde | Reintenta el reflejo | La cita ya está confirmada en la base. Nadie pierde su turno porque Google estuviera caído |
| El profesional **borra** el evento en su teléfono | Lo vuelve a crear | Borrar el reflejo no cancela la atención de un paciente |
| El profesional **mueve** el evento de hora | Marca **conflicto**, no sobrescribe | Ese cambio es intencionado. Puede significar que no estará disponible, y resolverlo puede implicar reprogramar a un paciente: eso no lo decide una máquina |
| El token caduca | Marca `TOKEN_VENCIDO` y deja los eventos pendientes | Distinto de `DESCONECTADO`: el primero exige que alguien vuelva a autorizar |
| La cita se cancela | Retira el evento | Dejarlo haría que el profesional viera ocupado un hueco libre |

---

## 2. El evento no contiene datos clínicos

Razonado en [ADR‑0018](decisiones/0018-evento-externo-sin-datos-clinicos.md). En resumen: el
calendario de Google es un tercero, y lo que se escribe ahí sale del control de acceso del
sistema y queda en la cuenta personal del profesional y en todos sus dispositivos.

**El nombre del servicio basta por sí solo para revelar un diagnóstico.** La especialidad es
información de salud.

| Se publica | No se publica |
|---|---|
| Título fijo «Cita reservada» | Paciente, iniciales, documento |
| Sede y consultorio | Servicio, especialidad |
| Inicio y fin | Motivo, diagnóstico, medicación |
| Enlace a la cita en el sistema | Notas, teléfono |

El título **no es parametrizable**: en cuanto admita una variable, alguien pondrá el
servicio ahí. La sede y el consultorio sí son texto libre del operador, así que se validan —
una sede llamada «Centro Oncológico» revelaría lo mismo, y por una vía que las demás
comprobaciones no cubren.

---

## 3. OAuth: el `state` es un control de seguridad

### El ataque que detiene

El error habitual es usar `state` como campo informativo: meter ahí el identificador del
profesional y leerlo tal cual al volver. Eso permite que un tercero prepare una URL de
callback con el `state` de **otra** persona y consiga que el sistema asocie su propio
calendario de Google a la cuenta de esa persona —o al contrario, quedarse con el calendario
de un compañero y con la copia permanente de sus horarios de trabajo.

### Cómo está implementado

`state` es un valor **firmado con HMAC-SHA256** que lleva dentro el profesional, el instante
de emisión y un valor aleatorio. Al volver:

1. **Firma verificada** en tiempo constante (`hmac.compare_digest`). Sin firma válida no se
   sigue.
2. **Vigencia de 15 minutos.** Suficiente para completar la pantalla de consentimiento sin
   prisa; corto para que un valor filtrado del historial del navegador no sirva mañana. Un
   `state` emitido en el futuro también se rechaza.
3. **Un solo uso.** Se consume registrándolo en `clave_idempotencia`, cuya restricción única
   `(alcance, clave)` es la garantía real —no un `SELECT` previo, que dejaría pasar dos
   pestañas del mismo flujo abiertas a la vez.

El orden importa: **primero se consume el `state`, después se canjea el código**. Al
contrario, un `state` reutilizado gastaría una llamada al proveedor antes de rechazarse.

### `access_type=offline` y `prompt=consent`

Sin el primero, Google no entrega token de refresco y la conexión deja de funcionar en una
hora. El segundo fuerza que lo vuelva a entregar a quien ya había autorizado antes —que es
el caso en el que se pierde el refresco y nadie entiende por qué la sincronización «dejó de
ir».

Si la respuesta no trae `refresh_token`, el sistema **falla de forma explícita** en lugar de
guardar solo el de acceso: una conexión sin refresco parece funcionar durante una hora y
luego se rompe, y el síntoma no apunta a su causa.

---

## 4. Los tokens

Se guardan cifrados con **AES-GCM y el `profesional_id` como contexto autenticado**.

Eso significa que un token copiado de una fila a otra **no descifra**. Si alguien con acceso
de lectura a la base intenta mover la conexión de un profesional a otro para usar su
calendario, obtiene un error de autenticación, no los datos. Hay una prueba que lo hace
literalmente: copia los campos cifrados a la conexión de otro profesional y comprueba que
el servicio no obtiene credenciales.

Además:

* Los tokens **nunca** aparecen en una respuesta HTTP, ni cifrados. Un token cifrado en una
  respuesta sigue siendo material sensible en un log de acceso, en la caché de un proxy y en
  el historial del navegador.
* `Credenciales.__repr__` y `TokensObtenidos.__repr__` están sobrescritos para que ni un
  traceback los vuelque.
* Al desconectar, los tokens **se ponen a nulo**. Un token que ya no se usa y sigue guardado
  es solo superficie de ataque. La fila se conserva porque los eventos creados la
  referencian y hay que poder explicar de dónde salieron.
* El error del proveedor **no incluye el cuerpo de su respuesta**: puede contener fragmentos
  del código de autorización.

---

## 5. Quién puede conectar un calendario, y sobre quién

Solo el profesional, y **solo el suyo**.

El permiso `profesional.conectar_calendario` lo tiene únicamente el rol profesional, y todas
las rutas derivan el profesional del **principal**, nunca de un parámetro de la petición. Si
el identificador viniera en el cuerpo, un profesional podría conectar su calendario a la
agenda de un compañero.

La conexión de otro profesional devuelve **404 y no 403**, igual que en el resto del
sistema: un 403 confirmaría que existe, y eso permite enumerar.

| Endpoint | Permiso |
|---|---|
| `GET /calendario/conexiones` | `profesional.conectar_calendario` · solo las propias |
| `POST /calendario/oauth/inicio` | Ídem |
| `GET /calendario/oauth/callback` | **Público**, autorizado por el `state` firmado |
| `POST /calendario/conexiones/{id}/desconexion` | Ídem · exige motivo, se audita |
| `POST /calendario/conexiones/{id}/sincronizacion` | Ídem |
| `GET /calendario/conexiones/{id}/eventos` | Ídem · solo estados, sin datos de la cita |

---

## 6. Cómo llega una cita al calendario

```
          ┌──────────────────────────────────────────┐
          │  La agenda NO sabe que existen los       │
          │  calendarios. Es una propiedad, no un    │
          │  olvido: ver más abajo.                  │
          └──────────────────────────────────────────┘

worker, cada 2 min
      │
      │ 1. detectar_citas_sin_reflejo
      │    (citas futuras en HELD/CONFIRMED/RESCHEDULED
      │     sin fila de calendario_evento)
      ▼
   calendario_evento (PENDIENTE)
      │
      │ 2. sincronizar_pendientes  →  proveedor
      ▼
   SINCRONIZADO (external_event_id + etag)

worker, cada hora
      │
      │ 3. reconciliar  →  proveedor (una lectura por evento)
      ▼
   ELIMINADO_EXTERNAMENTE  ·  CONFLICTO
```

### Por qué por detección y no desde el servicio de agenda

Sería más directo que `ServicioAgenda.confirmar` llamara a `registrar_cita`. Se hace al
revés a propósito:

1. **RF‑I08.** El anti doble‑reserva y el ciclo de estados de la agenda están verificados
   bajo concurrencia real con 50 participantes. Añadirles una dependencia del calendario
   introduce una vía por la que un fallo del reflejo podría afectar a la reserva de un
   paciente. Que la agenda no sepa que existen los calendarios es una propiedad que conviene
   conservar.
2. **Cubre las citas anteriores a la conexión.** Un profesional que conecta su calendario
   hoy espera ver su agenda de la semana que viene, no solo lo que se reserve a partir de
   ahora. Un enganche en la confirmación no daría eso.

El coste es latencia: el reflejo aparece en el siguiente barrido, no en el instante de
confirmar. Para un calendario es aceptable —y para eso está el botón de sincronización
manual, porque un profesional que acaba de conectar espera verlo poblado.

Solo se reflejan **citas futuras**. Reflejar el pasado llenaría el calendario de histórico
que no sirve y gastaría cuota del proveedor en eventos que nadie mirará.

### Las cadencias, y por qué son distintas

| Trabajo | Cadencia | Motivo |
|---|---|---|
| `sincronizar_calendarios` | cada 2 min | Un reflejo no tiene una hora concreta a la que deba salir; solo tiene que estar antes de que el profesional mire su agenda |
| `reconciliar_calendarios` | cada hora | **Consume una lectura del proveedor por evento**: es el trabajo más caro en cuota de API, y su ventana de detección aceptable se mide en horas |

---

## 7. El conflicto: lo que el sistema no decide

Cuando el profesional mueve un evento a mano, el sistema **no lo sobrescribe**. Lo marca
`CONFLICTO` y lo deja.

El control que lo detecta es el `etag` (el `If-Match` del proveedor). Sin él, la
actualización pisaría el cambio sin enterarse.

Un evento en `CONFLICTO` **no vuelve a entrar en el barrido**: reintentarlo sería
sobrescribirlo por la puerta de atrás. Espera a una persona, y el worker avisa
(`calendario.conflictos_pendientes`) porque si nadie mira, la agenda interna y la externa
divergen en silencio.

**Esto es trabajo manual que la integración genera**, y conviene saberlo antes de
desplegarla: cada vez que un profesional mueve una cita en su Google Calendar en lugar de en
el sistema, alguien tiene que resolverlo.

---

## 8. Configuración

Ninguna de estas variables tiene valor en `.env.example` (CLAUDE.md, regla 2).

| Variable | Para qué |
|---|---|
| `MODO_CALENDARIO` | `sandbox` (por defecto) o `google`. **`sandbox` está prohibido en producción**; `google` **todavía falla**, porque el adaptador real no existe |
| `GOOGLE_CLIENT_ID` | Identificador de la aplicación OAuth |
| `GOOGLE_CLIENT_SECRET` | **Secreto** |
| `GOOGLE_REDIRECT_URI` | Debe coincidir exactamente con la registrada en Google |
| `GOOGLE_SCOPES` | `https://www.googleapis.com/auth/calendar.events` |
| `CLAVE_SECRETA` | Firma el `state` de OAuth. **Secreto** |
| `CLAVE_CIFRADO_DATOS` | Cifra los tokens en reposo. **Secreto** |

En modo `sandbox` el adaptador en memoria se registra **bajo el nombre del proveedor real**
(`google`), no bajo «sandbox»: la columna `calendario_conexion.proveedor` guarda el proveedor
de negocio, y si el registro usara otra clave, las conexiones creadas en desarrollo dejarían
de resolver al pasar a producción.

`MODO_CALENDARIO=google` **lanza `NotImplementedError` al arrancar**. Es deliberado: un
entorno configurado para hablar con Google que en realidad no sale a la red es peor que uno
que no arranca, porque parece funcionar.

---

## 9. Qué falta para poner esto en producción

1. **El adaptador real de Google Calendar.** No existe. Hay que implementar `crear`,
   `actualizar`, `eliminar` y `consultar` contra la API v3, con `If-Match` para el control
   optimista y `syncToken` para la reconciliación incremental —la columna
   `token_sincronizacion_incremental` ya está en el modelo para eso, y evitaría la lectura
   por evento que hoy hace caro el barrido.
2. **La renovación del token de acceso.** El token de refresco se guarda y la conexión se
   marca `TOKEN_VENCIDO` correctamente, pero **no hay código que lo canjee por uno nuevo**:
   hoy hace falta volver a autorizar a mano. `MARGEN_RENOVACION` está definido y sin usar.
3. **Credenciales de Google** y un proyecto OAuth con la URI de redirección registrada.
4. **Verificación del camino real**, que es lo que cierra E‑1.
5. **Revisión jurídica** de la transferencia de datos a un tercero (limitación E‑2), aunque
   el evento no lleve datos clínicos: la relación profesional‑fecha sigue siendo un dato
   personal que sale del país.
6. **Vigilar `calendario.conflictos_pendientes` y los eventos en `ERROR`.** Un evento en
   `ERROR` significa que la agenda externa de un profesional está desincronizada; si nadie
   mira esa cola, el estado no sirve de nada.

---

## 10. Evidencia de las pruebas

Ejecutadas el 2026‑09‑12 contra PostgreSQL 16 + pgvector 0.8.6 en contenedor.

| Suite | Casos | Qué cubre |
|---|---|---|
| `test_eventos_calendario.py` | 16 | RF‑I09: que la función **no admite** datos de paciente ni de servicio |
| `test_oauth_calendario.py` | 23 | Firma, manipulación del profesional, vigencia, emisión futura, intercambio |
| `test_calendario.py` | 22 | Cifrado ligado al profesional, borrado externo, cambio externo, token vencido, reintentos |
| `test_calendario_api.py` | 17 | Autorización, 404 vs 403, tokens fuera de la respuesta, `state` de un solo uso |
| `test_seleccion_calendario.py` | 3 | Que en sandbox no se construye el adaptador real |
| `test_tareas_calendario.py` | 4 | El trabajo periódico completo e idempotente |

```
uv run pytest -q                    →  984 passed
uv run pytest --cov=app             →  91,37 %
uv run ruff check . ; uv run mypy app  →  sin hallazgos
uv run alembic check                →  No new upgrade operations detected
```

Cobertura de los módulos: `eventos.py`, `esquemas.py` y `seleccion.py` 100 %,
`oauth.py` 94 %, `tareas/calendario.py` 93 %, `servicios.py` 88 %, `adaptadores.py` 85 %,
`rutas.py` 83 %.

Lo no cubierto en `rutas.py` es, en su mayoría, el camino que exige credenciales reales de
Google. **Una suite verde no sustituye a ejercer el sistema**, y ninguno de los dos sustituye
a verificar el camino real del proveedor. Ver [`test-plan.md`](test-plan.md).
