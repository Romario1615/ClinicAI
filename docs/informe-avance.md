# Informe de avance

> **Fecha:** 2026‑09‑12 · 29 commits · Fases 0, 0b, 3 y **4 (WhatsApp)** cerradas;
> **Fase 6 (conocimiento y RAG) cerrada.** 1, 2, 5 y 7 en curso. Del calendario externo
> queda pendiente el adaptador real de Google y la renovación automática del token; del
> RAG, el agente que lo use.

Este informe cubre los 18 puntos exigidos. Está escrito para ser contrastado: cada cifra
procede de una ejecución real cuyo comando se indica, y lo que no se ha verificado se dice
que no se ha verificado.

---

## 1. Qué se implementó

| Área | Estado |
|---|---|
| Infraestructura local (WSL2 + Docker, PostgreSQL 16 + pgvector, Redis) | operativa |
| Modelo de datos | **49 tablas** migradas, reversibles |
| Autenticación (Argon2id, JWT, refresco rotativo, TOTP, bloqueo) | completa |
| RBAC con ámbito de 4 dimensiones + relación asistencial | completo |
| Auditoría append‑only con redacción activa | completa |
| Agenda: disponibilidad, reserva, ciclo de estados, anti doble‑reserva | completa |
| Worker ARQ: expiración de bloqueos temporales | completo |
| Catálogo y pacientes (lectura) | completo |
| Historia clínica versionada, recetas, tomas, adherencia | servicios y API completos |
| Lista de espera con oferta única por turno | servicios completos |
| Outbox de entrega: deduplicación, reintentos con retroceso, huérfanos, estados de entrega | completo |
| Plantillas de notificación sin datos clínicos (regla 10, RF‑K07) | completo · 15 plantillas |
| Webhook de WhatsApp: firma HMAC, deduplicación, opt‑out, derivación a persona | completo |
| Adaptador WhatsApp Cloud API | escrito · **camino real sin verificar** (E‑1) |
| Calendario externo: OAuth, tokens cifrados, publicación, reconciliación de cambios externos | completo con sandbox · **adaptador real de Google no implementado** (E‑1, E‑19) |
| Base de conocimiento con pgvector: búsqueda híbrida con los filtros en el SQL, ciclo de vida, anti inyección | completo · **calidad medida con el proveedor simulado** (E‑9) |
| Agente conversacional | **no existe** |
| API HTTP | **48 operaciones** en 45 caminos |
| Frontend Angular 19 PWA | 9 pantallas; agenda conectada al backend real |
| CI/CD con puertas de fallo | completo, **sin ejecutar en GitHub** |

**No implementado:** calendarios externos, RAG, dashboard, predicciones, pagos, E2E,
pruebas de carga, y la preparación de producción.

---

## 2. Archivos y módulos tocados

```
backend/app/
  nucleo/        configuracion · seguridad · autorizacion · auditoria · bd · errores
                 errores_bd · idempotencia · registro · reloj · dependencias · limite_tasa
  api/           middleware · manejadores
  mensajeria/    plantillas · adaptadores · firma · carga_whatsapp · destinatarios
                 servicios (outbox) · rutas (webhook)
  ia/            embeddings · saneamiento · recuperador
  modulos/calendario/  eventos · adaptadores · oauth · seleccion
                 servicios · esquemas · rutas
  modulos/conocimiento/  modelos · fragmentacion · repositorio
                 servicios · esquemas · rutas
  modulos/       agenda · auditoria · conversaciones · historia · lista_espera
                 organizacion · outbox · pacientes · profesionales · usuarios
  tareas/        worker ARQ · contexto · agenda · outbox · calendario
  semillas/      catalogos · sinteticos · cargar
frontend/src/app/
  nucleo/        modelos · servicios · guardias · interceptores · utilidades
  compartido/    estados · insignia-estado
  paginas/       acceso · agenda · demostracion
infra/           compose · docker (backend, worker, postgres) · scripts · wsl
.github/workflows/ci.yml
docs/            20 documentos + 18 ADR
```

---

## 3. Decisiones tomadas

Las 18 ADR están en [`docs/decisiones/`](decisiones/). Las que más condicionan el sistema:

* **ADR‑0009** — El anti doble‑reserva es una restricción de exclusión `gist` de
  PostgreSQL, no lógica de aplicación.
* **ADR‑0010** — Todo en `timestamptz` UTC; reloj inyectable, con una regla de lint que
  prohíbe `datetime.now()` fuera de `reloj.py`.
* **ADR‑0011** — Historia clínica append‑only, sostenida por un disparador.
* **ADR‑0016** — El token de refresco viaja en el cuerpo, no en cookie; la defensa es
  detectar su duplicado, no ocultarlo.
* **ADR‑0017** (nueva) — **Ninguna intención entrante que cambie el estado de una cita se
  ejecuta sin una persona.** El webhook solo trae un número de teléfono, y en este sistema
  un teléfono no identifica a una persona: es familiar con frecuencia. La única excepción
  es `BAJA`, porque es el único caso donde no hacer nada es peor que equivocarse.
* **ADR‑0018** (nueva) — **El evento del calendario externo no lleva paciente, servicio ni
  especialidad.** El calendario de Google es un tercero: lo que se escribe ahí sale del
  control de acceso del sistema y queda en la cuenta personal del profesional y en todos
  sus dispositivos. Y el nombre del servicio basta por sí solo para revelar un diagnóstico:
  la especialidad **es** información de salud.

Decisiones no cubiertas por ADR pero con consecuencia:

* Las reglas que pueden dañar a un paciente viven en el **motor**, no en el servicio: tres
  disparadores y varias restricciones `CHECK`. Un servicio se puede rodear añadiendo otro
  camino de escritura; un disparador no.
* **Ámbito vacío = sin acceso**, en las cuatro dimensiones y sin excepciones.
* El límite de tasa **falla cerrado en autenticación** y abierto en el resto.

---

## 4. Pruebas ejecutadas, con sus comandos y resultados reales

```
cd backend
uv run pytest --cov=app -q            1140 passed · cobertura 92,03 %
uv run pytest -m unitaria -q          583
uv run pytest -m integracion -q       372
uv run pytest -m api -q               182
uv run pytest -m concurrencia -q       12
uv run pytest -m seguridad -q         504
uv run pytest -m rag -q                80
uv run ruff check .                   All checks passed
uv run ruff format --check .          132 files already formatted
uv run mypy app                       no issues found in 79 source files
uv run bandit -r app -ll              sin hallazgos de severidad media o alta
uv run alembic upgrade head           aplicada
uv run alembic downgrade -1 && upgrade head    reversible
uv run alembic check                  No new upgrade operations detected

cd frontend
npm run lint                          All files pass linting
npx tsc --noEmit                      sin errores
npm run test:ci                       67 SUCCESS (sin cambios: la fase no toca el frontend)
npm run build                         299.92 kB inicial · 86.50 kB transferidos
```

Los marcadores se solapan: una prueba de IDOR cuenta como `api` y como `seguridad`.

**Las 236 pruebas nuevas de esta fase**, por archivo y por lo que cubren:

| Suite | Casos | Qué garantiza |
|---|:--:|---|
| `test_plantillas.py` | 40 | Regla 10 sobre el catálogo **completo**: ninguna plantilla admite ni menciona diagnóstico, medicamento ni motivo de consulta |
| `test_intenciones.py` | 41 | Que un mensaje clínico, ambiguo o negado **no** se reconoce y va a una persona |
| `test_adaptadores_whatsapp.py` | 32 | Forma del cuerpo de la Cloud API y clasificación de errores; que en `sandbox` no se construye el adaptador real |
| `test_carga_whatsapp.py` | 26 | Parseo del webhook, incluidas **14 formas deformes** que no deben romperlo |
| `test_webhook_whatsapp_api.py` | 34 | El endpoint real: firma, deduplicación, opt‑out, frontera clínica, robustez, **formato del número** |
| `test_outbox.py` | 25 | Deduplicación, rollback, reintentos, huérfanos, conciliación, consentimiento |
| `test_destinatarios.py` | 16 | Resolución de contacto en las tres tablas de destinatario |
| `test_webhook_firma.py` | 13 | Firma válida, alterada, **reserializada**, sin cabecera, sin secreto |
| `test_normalizacion_telefono.py` | 6 | Formato que exige el proveedor |
| `test_tareas_outbox.py` | 3 | El trabajo periódico completo, con su contexto de worker |

**Y las 85 del calendario externo:**

| Suite | Casos | Qué garantiza |
|---|:--:|---|
| `test_oauth_calendario.py` | 23 | Que un `state` manipulado para nombrar a otro profesional no pasa |
| `test_calendario.py` | 22 | Cifrado ligado al profesional, borrado externo, cambio externo, token vencido |
| `test_calendario_api.py` | 17 | Autorización, 404 vs 403, tokens fuera de la respuesta, `state` de un solo uso |
| `test_eventos_calendario.py` | 16 | RF‑I09: que la función **no admite** datos de paciente ni de servicio |
| `test_tareas_calendario.py` | 4 | El trabajo periódico completo e idempotente |
| `test_seleccion_calendario.py` | 3 | Que en sandbox no se construye el adaptador real |

**Y las 118 de conocimiento y RAG:**

| Suite | Casos | Qué garantiza |
|---|:--:|---|
| `test_saneamiento.py` | 34 | Patrones de inyección, evasiones por formato e invisibles, y que el **texto clínico legítimo no se marca** |
| `test_conocimiento.py` | 22 | Ciclo de vida y que la propagación a los fragmentos no deja una ventana |
| `test_conocimiento_api.py` | 21 | Que **quien carga no aprueba**, y que quien sube no levanta su propia alerta |
| `test_rag_fugas.py` | 21 | Siete casos negativos, cada uno con su prueba de control |
| `test_fragmentacion.py` | 19 | Cortes, solape y parámetros inválidos |
| `test_embeddings.py` | 13 | Determinismo, del que dependen todas las pruebas de recuperación |
| `test_recuperador.py` | 9 | Contexto citado y la respuesta sin fuente |
| `test_evaluacion_rag.py` | 7 | Hit@K y casos negativos deliberados |
| `test_arquitectura_rag.py` | 6 | Que **no hay otra vía** de consulta a `knowledge_chunks` |

Tres de esas pruebas son las que más valen, porque comprueban una **ausencia**:

* `test_una_firma_invalida_no_produce_ningun_efecto` — no basta el 403: se verifica que no
  se escribió nada y que el consentimiento del paciente sigue vigente.
* `test_ninguna_intencion_de_estado_se_ejecuta_sin_una_persona` — ni `CANCELAR`, ni
  `CONFIRMAR`, ni `SI`, ni `TOMADA` cambian nada por sí solos.
* `test_el_webhook_no_devuelve_datos_del_paciente` — el cuerpo de la respuesta lo lee Meta,
  no la clínica: cualquier dato ahí sale del sistema sin control de acceso.

**Verificación de extremo a extremo** contra la base con datos sintéticos, con la API
arrancada de verdad:

```
login recepción            200 · 21 permisos · ámbito de 1 sede
catálogo                   1 sede · 4 especialidades · 8 servicios · 4 profesionales
disponibilidad             200 · 5 turnos · zona America/Guayaquil
reserva                    201 · CONFIRMED · fin calculado por el disparador
misma clave idempotencia   201 · mismo identificador
otra clave, mismo turno    409 TURNO_NO_DISPONIBLE
cancelación                200 · CANCELLED con motivo
cita ajena                 404 RECURSO_NO_ENCONTRADO
paciente ajeno             404 RECURSO_NO_ENCONTRADO
```

---

## 5. Cobertura

**Backend 92,03 %** (umbral del pipeline 80 %, RNF‑06). **Frontend 95,41 % sentencias,
87,3 % ramas, 90,69 % funciones** (umbrales 80/70/80).

### La cifra anterior estaba mal medida

`app/modulos/conversaciones/servicios.py` aparecía al **65 %** con 26 pruebas de API que lo
recorren entero. No era el código ni las pruebas: **SQLAlchemy async ejecuta el código que
rodea a cada consulta dentro de un greenlet** (`greenlet_spawn`), y `coverage` no traza esas
líneas sin `concurrency = ["thread", "greenlet"]`.

Corregirlo subió la cobertura total de 89,18 % a 91,63 % **sin añadir una sola prueba**, y
dejó a la vista dos huecos reales que el ruido tapaba: `destinatarios.py` al 41 % y la
cancelación de recordatorios sin cubrir. Ambos cerrados (98 % y cubierta).

El síntoma era peligroso porque empujaba en la dirección contraria: invitaba a escribir
pruebas para líneas ya probadas y ocultaba las que de verdad faltaban. Queda anotado como
principio en [`test-plan.md`](test-plan.md).

### Módulos de esta fase

| Módulo | Cobertura |
|---|:--:|
| `mensajeria/plantillas.py` · `mensajeria/firma.py` | 100 % |
| `modulos/conversaciones/servicios.py` · `modelos.py` | 100 % |
| `mensajeria/servicios.py` · `mensajeria/destinatarios.py` | 98 % |
| `tareas/outbox.py` | 96 % |
| `modulos/conversaciones/intenciones.py` | 94 % |
| `mensajeria/adaptadores.py` | 93 % |
| `mensajeria/carga_whatsapp.py` | 90 % |
| `mensajeria/rutas.py` | 90 % |

Lo no cubierto en `rutas.py` son las ramas de configuración degradada
(`WHATSAPP_VALIDAR_FIRMA=false`, cuerpo mayor de 1 MB), que no se pueden ejercer sin
levantar una segunda aplicación mal configurada a propósito.

Módulos por debajo del 80 % que persisten: `nucleo/bd.py` (ciclo de vida del motor, se
ejercita al arrancar) y `agenda/repositorio.py` (ramas de feriados y descansos).

---

## 6. Vulnerabilidades encontradas y corregidas

`pip-audit` encontró **44 vulnerabilidades conocidas en 3 paquetes** la primera vez que se
ejecutó la puerta:

| Paquete | Vulns | Acción |
|---|:--:|---|
| `cryptography` 46.0.7 | 7 | Subido a 50.0.1. **Cifra los secretos de 2FA y los tokens OAuth en reposo** |
| `pytest` 8.4.2 | 2 | Subido a 9.x (obligó a subir `pytest-asyncio` a 1.4) |
| `pillow` 11.3.0 | 35 | **Eliminado del árbol.** `fastembed` lo capa a `<12.0` y la corrección está en 12.1.1; entraba solo por el extra `[pil]` de `qrcode`, y el único uso de QR —el código TOTP— no lo necesita si se genera SVG |

Estado actual: `pip-audit --strict` → **No known vulnerabilities found**.

### Fallos de seguridad propios, encontrados y corregidos

1. **El filtro de ámbito de la agenda no filtraba con la lista vacía.** La condición era
   `if not todos_los_profesionales **and** profesionales`: con la lista vacía la rama no se
   ejecutaba y el principal veía las citas de todos. Igual con pacientes. Y la dimensión de
   especialidad **no se aplicaba en absoluto**.
2. **El control de relación asistencial era inerte por HTTP.** El principal nunca llevaba
   `profesional_id`, y ese campo es lo que lo activa. Cualquiera con
   `historia_clinica.leer` habría leído la historia de cualquier paciente de su clínica.
3. **El registro estructurado reventaba en ejecución.** Toda línea lanzaba
   `AttributeError`; en la API habría sido un 500 en la primera petición. Además, los
   registros de librerías no pasaban por la redacción, y SQLAlchemy escribe las sentencias
   con sus parámetros —nombres, documentos y teléfonos de pacientes.
4. **`WWW-Authenticate` faltaba en la mayoría de los 401.**
5. **Las pruebas de seguridad de la Fase 4 no llevaban su marcador** y quedaban fuera de la
   puerta `-m seguridad` del pipeline. La firma del webhook, la regla 10 y la frontera
   clínica son controles de seguridad, no pruebas funcionales. Corregido: la puerta pasa de
   235 a **419** pruebas (las del calendario tambien la llevan). Un control verificado por una prueba que la puerta no ejecuta no
   está protegido contra una regresión.

Los tres primeros aparecieron **ejerciendo el sistema**, no ejecutando la suite: vivían en
el espacio entre lo que las fixtures suponían y lo que los datos reales tienen. Está
anotado como principio en `test-plan.md`.

### Los dos fallos que destapo medir el RAG

El arnés de evaluación (RF‑O08) destapó que **una pregunta sin documentación que la
cubriera devolvía el corpus entero**. Dos causas, y cada una tapaba a la otra:

1. **`RAG_UMBRAL_SIMILITUD` estaba en la configuración desde la Fase 0 y no se aplicaba.**
   Sin umbral, la rama vectorial ordena por distancia y entrega los `n` primeros por lejos
   que estén: siempre devuelve algo. Eso significa que **«no tengo información aprobada»
   (RF‑O06) no se habría disparado casi nunca**, y el agente habría citado como fuente el
   documento menos irrelevante que encontrase. Es exactamente el fallo que esa regla existe
   para impedir.

2. **`websearch_to_tsquery` une los términos con `AND`.** La pregunta «cuántas horas de ayuno
   necesito para el examen de sangre» solo encontraba un documento que contuviera *todas*
   esas palabras —casi ninguno—. La rama textual no aportaba nada, y no se notaba porque la
   vectorial devolvía todo.

Al corregir el primero, las pruebas de fuga fallaron y eso dejó ver el segundo.

**Medido después de las dos correcciones:** Hit@1 80 %, Hit@3 100 %, media de 2,5 resultados
por consulta sobre un corpus de 5 documentos, y **0 resultados** para una pregunta sin
documentación —antes, los 5—.

**Y un tercero, del mismo tipo que el de los consentimientos:** la base de conocimiento
estaba **vacía** en desarrollo, así que el RAG no se podía demostrar ni ejercitar. Las
semillas cargan ahora 9 documentos en los cinco estados; dos existen solo para poder
comprobar a mano que un borrador y un archivado **no** se recuperan. Al sembrarlos, el
`CHECK aprobado_con_responsable` rechazó la primera versión —dejaba el autor opcional—, y la
prueba de arquitectura detectó el módulo nuevo. Las dos hicieron su trabajo.

Ninguno de los dos aparece ejecutando la suite: aparecen al **medir**. Es el mismo patrón que
el fallo del formato del teléfono, con otra forma.

### El fallo que encontro ejercer el sistema

Con **891 pruebas en verde**, arrancar la API y recorrer el flujo real contra las
semillas destapó un fallo serio: **un paciente que respondía `BAJA` por WhatsApp no
quedaba dado de baja.**

`paciente.telefono_whatsapp` guarda el número como lo escribió el personal
(«+593 99 900 0333»), porque es lo legible en un panel; el webhook entrega solo dígitos
(«593999000333»). La comparación literal no encontraba a nadie, así que la revocación de
consentimiento no revocaba nada y el sistema **seguía escribiendo a quien pidió que
pararan**. Es el fallo exacto que ADR‑0017 dice que no puede ocurrir, y afecta al único
camino que esa ADR permite ejecutar sin intervención humana.

**Por qué la suite no lo veía:** sus fixtures guardaban el número ya normalizado, que es
justo lo que el panel no hace. Las 26 pruebas del webhook pasaban por el motivo equivocado.

Corregido con una expresión única —`telefono_normalizado()`— que comparten la consulta y un
índice funcional nuevo, verificado con `EXPLAIN`
(`Index Scan using ix_paciente_whatsapp_normalizado`). Seis pruebas de regresión, una de
ellas parametrizada sobre los formatos que produce copiar un número de una agenda, de un
mensaje o de un documento.

En el mismo ejercicio aparecieron dos defectos de las propias pruebas: usaban un
`phone_number_id` **fijo**, lo que las acoplaba al contenido de la base de desarrollo (bastó
una fila de configuración con ese valor para que 20 fallaran por datos ajenos), y dos
contaban filas de la tabla entera suponiéndola vacía. Ambos corregidos.

Y un tercero en los datos: **las semillas creaban 60 pacientes con número de WhatsApp y cero
consentimientos**, así que ningún recordatorio podía salir y el flujo no se podía ejercitar
ni demostrar en desarrollo. Ahora crean 60 vigentes, 6 revocados y dejan 7 pacientes sin
ninguna fila, para que los tres caminos que el código distingue tengan datos.

**Evidencia del ejercicio:** 33 comprobaciones sobre la API arrancada, 0 fallos, tras la
corrección.

### Sobre esta fase en particular

`pip-audit --strict` sigue en **No known vulnerabilities found**; la fase no añadió
dependencias (`httpx` ya estaba en el árbol para el cliente de pruebas). `bandit -r app -ll`
no reporta hallazgos de severidad media o alta.

Decisiones de seguridad que conviene poder contrastar:

* La firma se calcula sobre el **cuerpo crudo** y se compara con `hmac.compare_digest`.
  Hay una prueba (`test_el_cuerpo_reserializado_no_valida`) cuyo único propósito es impedir
  que alguien «simplifique» la ruta pasando el cuerpo ya parseado.
* Una firma inválida se audita **en su propia confirmación** antes de propagar el error,
  porque la transacción de la petición se descarta al lanzar y `webhook.firma_invalida` es
  una de las acciones con alerta.
* El webhook **responde 200 ante cualquier otro fallo**, a propósito. Es una decisión
  contraintuitiva: Meta deshabilita la suscripción ante errores persistentes, y perderla
  deja al sistema sin recibir las respuestas de **ningún** paciente.
* El destino de un envío **no se registra en el log**: es un número de teléfono, y un log
  de aplicación no es el sitio de un dato de contacto.

---

## 7. Riesgos pendientes

Los 22 riesgos residuales están en [`known-limitations.md`](known-limitations.md). Los que
más pesan:

* **E‑2** El cumplimiento legal no está validado. **El sistema no puede operar con
  pacientes reales.** 19 puntos pendientes de revisión jurídica en `security.md`.
* **E‑10** La verificación TOTP usa el reloj de pared: el servidor **necesita NTP**, o el
  personal con 2FA obligatorio no podrá entrar.
* **E‑11** El límite de tasa falla abierto fuera de autenticación.
* **E‑7** La auditoría es inalterable desde la aplicación, no frente a un superusuario de
  base de datos.
* **E‑1** El camino real de WhatsApp **no está verificado**: ni un mensaje ha salido hacia
  Meta. Lo verificado es todo lo que rodea al envío; lo que falta es concreto y está
  enumerado en la sección 7 de [`whatsapp-integration.md`](whatsapp-integration.md).
* **E‑13** Ninguna intención entrante que cambie el estado de una cita se ejecuta sola
  (ADR‑0017). **Consecuencia operativa real: cada respuesta de un paciente genera trabajo
  para recepción.** No es un defecto; es el precio de no cancelar la cita equivocada de una
  familia.
* **E‑14** La recuperación de mensajes huérfanos puede duplicar un envío si el worker muere
  justo después de entregar. Ventana: 15 minutos.
* **E‑16** Los canales de correo y calendario usan el adaptador sandbox: un mensaje de
  canal `CORREO` se marca `ENTREGADO` **sin que salga nada**.
* **E‑9** La calidad de recuperación del RAG está medida con el proveedor **simulado**.
  Ese número mide el suelo, no la calidad; los casos negativos sí son concluyentes.
  `RAG_UMBRAL_SIMILITUD` está hoy **fijado a ojo** y hay que recalibrarlo con el modelo real.
* **E‑20** `knowledge_permissions` existe y **no se aplica**: un documento no se puede
  restringir a un rol concreto ni marcar como «legible pero no citable por el agente».
* **D‑1** El disco C: del equipo de desarrollo está al límite por causas ajenas al
  proyecto (`C:\Windows\WinSxS`).

---

## 8. Credenciales que faltan

| Servicio | Estado | Consecuencia |
|---|---|---|
| WhatsApp Business Cloud API | **ausente** | El adaptador real está escrito y **no se ha ejecutado contra Meta**. Faltan: cuenta de WhatsApp Business, número verificado y aprobación de las 10 plantillas |
| Google Calendar (OAuth) | **ausente** | El módulo de calendario no está implementado |
| Embeddings en la nube | ausente | Se usará `fastembed` local (ADR‑0007) |
| `ANTHROPIC_API_KEY` | presente en el entorno | Suficiente para la Fase 6 |

Ninguna se ha inventado. La Fase 4 se implementó con adaptador real **y** adaptador
sandbox seleccionable por entorno (ADR‑0012), y **se declara explícitamente que el camino
real no está verificado** (E‑1).

El adaptador real **falla al construirse** si faltan las credenciales, no al primer envío:
arrancar mal configurado significa descubrirlo cuando un paciente no recibió su
recordatorio. En modo `sandbox` el worker lo avisa en cada arranque
(`outbox.canal_en_sandbox`) para que nadie confunda una entrega simulada con una real.

---

## 9–11. Configuración de staging, producción y despliegue

Documentado en [`deployment.md`](deployment.md). Existen `Dockerfile.backend` y
`Dockerfile.worker` —dos etapas, usuario sin privilegios, `uv sync --frozen`—, y el
pipeline los construye y los pasa por Trivy.

**No existe entorno de staging** (D‑4). Los procedimientos están escritos y probados en
local; no en una infraestructura equivalente a producción.

---

## 12–13. Rollback y restauración

**Rollback de esquema:** verificado. Cada migración se prueba con
`upgrade → downgrade -1 → upgrade`, y el pipeline lo repite en cada ejecución.

**Restauración desde copia de seguridad: NO verificada.** Es trabajo de la Fase 10, y
hasta que una restauración real se ejecute y se compruebe, **no hay copia de seguridad
válida**. Es la afirmación que más conviene no adelantar.

---

## 14. Qué queda pendiente

| Fase | Estado |
|---|---|
| 1 · Prototipo visual | en curso · 6 de 9 pantallas con datos sintéticos |
| 2 · Backend y seguridad | en curso · falta escritura de pacientes y administración de usuarios |
| 4 · WhatsApp | **cerrada** · outbox, plantillas, webhook y adaptadores; camino real sin verificar (E‑1) |
| 4b · Calendarios externos | en curso · flujo completo con sandbox. Faltan el **adaptador real de Google** y la renovación automática del token (E‑19) |
| 5 · Lista de espera | en curso · faltan rutas HTTP y disparo automático; la oferta ya puede encolar por outbox |
| 6 · Conocimiento y RAG | **cerrada** · 80 pruebas `rag`. Falta el agente que use la recuperación |
| 7 · Historia clínica | en curso · el outbox ya existe; faltan programar los recordatorios de toma y la pantalla real |
| 8 · Dashboard y predicciones | **no empezada** |
| 9 · Pagos | **no empezada** |
| 10 · Producción | **no empezada** |

También pendientes: los 21 escenarios E2E con Playwright, las pruebas de carga con k6,
DAST, y cuatro documentos (`rag.md`, `monitoring.md`, `backup-and-restore.md`,
`incident-response.md`). `whatsapp-integration.md` y `calendar-integration.md` se entregan
con esta fase.

**Lo que la Fase 4 deja explícitamente para después**, no por olvido:

* **Programar los recordatorios de cita y de toma.** El outbox y las plantillas existen y
  están probados; lo que falta es el planificador que crea las filas de `recordatorio` al
  confirmar una cita o una receta. Es trabajo de las Fases 5 y 7.
* **Ejecutar las intenciones entrantes.** Requiere las herramientas del agente, que
  trabajan con principal y ámbito (ADR‑0017). Fase 6.
* **Responder al paciente dentro de la ventana de 24 horas.** El dato
  (`ventana_expira_en`) se guarda ya; falta la pantalla del personal para usarlo.
* **Los tres tipos de mensaje de calendario** (`CALENDARIO_*`) no tienen plantilla a
  propósito: llevan una operación sobre un evento, no texto para una persona. Hay una
  prueba que verifica esa ausencia para que sea una decisión visible y no un hueco.
* **El adaptador real de Google Calendar.** El flujo está completo con sandbox; falta
  hablar con la API v3 y renovar el token de acceso automáticamente (E‑19). Hoy, un token
  caducado exige volver a autorizar a mano —no se pierde ningún evento, pero la
  sincronización se detiene hasta que el profesional actúe.

---

## 15. Evaluación de preparación para producción

**No está listo para producción, y no está cerca.** Con evidencia, punto por punto:

| Criterio | Estado |
|---|:--:|
| Datos y migraciones reversibles | ✅ verificado |
| Autenticación y autorización | ✅ verificado, con 4 fallos propios corregidos |
| Anti doble‑reserva bajo concurrencia real | ✅ verificado con 50 participantes |
| Garantías clínicas en el motor | ✅ verificado atacándolas con SQL directo |
| Auditoría y redacción de registros | ✅ verificado |
| Pipeline con puertas de fallo | ⚠️ escrito y validado en local; **nunca ejecutado en GitHub** |
| Imágenes de contenedor | ⚠️ escritas; **nunca construidas**, no hay Docker en el anfitrión |
| Interfaz de usuario | ⚠️ prototipo; 6 de 9 pantallas son maquetas |
| Comunicación con pacientes (saliente) | ⚠️ **verificada contra sandbox**, no contra Meta (E‑1) |
| Comunicación con pacientes (entrante) | ⚠️ webhook verificado; **nada que cambie una cita se ejecuta solo** (E‑13) |
| Notificaciones sin datos clínicos | ✅ verificado sobre el catálogo completo |
| Eventos de calendario sin datos clínicos | ✅ verificado en la firma y en lo que sale al proveedor |
| Calendarios externos | ⚠️ flujo verificado con sandbox; **adaptador real no implementado** (E‑1, E‑19) |
| RAG sin fugas entre pacientes y especialidades | ✅ verificado con 21 casos negativos y una prueba de arquitectura |
| Calidad de recuperación | ⚠️ medida con el proveedor **simulado**, no con un modelo real (E‑9) |
| Agente conversacional | ❌ no existe |
| Historia clínica en la interfaz | ❌ maqueta |
| Pruebas E2E, carga, DAST, recuperación | ❌ no existen |
| Restauración de copias verificada | ❌ no existe |
| Validación legal (Ecuador) | ❌ no existe |

Lo que hay es una **columna vertebral sólida y verificada**: datos, seguridad, agenda,
núcleo clínico y ahora el canal de comunicación. Lo que falta sigue siendo cerca de la
mitad del alcance acordado.

Sobre la Fase 4 en concreto, la distinción que importa: **la lógica alrededor del envío
está verificada y el envío mismo no.** El outbox, la deduplicación, los reintentos, la
firma, la conciliación de estados y la frontera clínica se ejercen con 228 pruebas contra
PostgreSQL real. Que Meta acepte el cuerpo que se le construye es una afirmación que este
informe **no hace**.

---

## 16–18. Notas finales

**Lo que este informe no afirma.** No se dice en ningún punto que el sistema sea seguro,
que no tenga riesgos ni que cumpla la normativa. Se dice qué se probó, con qué comando y
con qué resultado.

**Sobre el pipeline.** El repositorio no tiene remoto configurado, así que el workflow no
se ha ejecutado nunca en GitHub. Su sintaxis YAML está validada y cada puerta se comprobó
a mano en local, una por una. Lo que no se ha verificado es el comportamiento de los
contenedores de servicio ni de las acciones de terceros en el ejecutor.

**Sobre la medición que estaba mal.** El hallazgo más útil de esta fase no fue código
nuevo: fue descubrir que la cobertura llevaba midiéndose mal desde el principio por el
greenlet de SQLAlchemy async. Un número que parece objetivo puede no serlo, y este llevaba
varias fases empujando el esfuerzo en la dirección equivocada. Se corrigió en su propio
commit, separado de la fase, porque afecta a todo el proyecto y no a esta parte.

**Sobre las seis pruebas mal escritas.** Durante el trabajo se descubrió que seis pruebas
propias estaban mal: tres asumían comportamientos de disponibilidad que el motor no tiene,
una ordenaba por un UUID aleatorio creyendo que era un orden estable, una esperaba 423
donde el diseño usa 401 a propósito, y una medía la caducidad del token creyendo que medía
la del bloqueo. Cada una se corrigió y se explicó en el mensaje del commit correspondiente.
Se listan aquí porque una suite verde cuyas pruebas nadie revisa no vale más que no tener
suite.
