# Backlog por fases, criterios de aceptación y dependencias

Entregable de la Fase 0. Cada tarea referencia los requisitos de
[`requirements.md`](requirements.md). Una tarea está **hecha** cuando su criterio de
aceptación se verifica con una prueba automatizada que se ejecuta en el pipeline, salvo
que se indique explícitamente que la verificación es manual.

Estado: `pendiente` · `en curso` · `hecho` · `bloqueado`

---

## Fase 0 — Análisis y fundación

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 0.1 | Inventario del entorno | — | Documentado en `plan` y en este repositorio, con versiones reales verificadas por comando | hecho |
| 0.2 | Repositorio independiente e inicializado | — | `git log` existe en `D:\Sistema IA de Clinicas`; el portafolio del usuario sin cambios | hecho |
| 0.3 | Arquitectura documentada | — | `architecture.md` con diagramas de componentes, autorización, frontera de IA y los tres flujos principales | hecho |
| 0.4 | Modelo de datos diseñado | Todos | `data-model.md` con diagrama de entidades y las restricciones de integridad declaradas | hecho |
| 0.5 | ADR 0001‑0015 | — | Cada decisión con contexto, alternativas y consecuencias, incluidas las negativas | hecho |
| 0.6 | Modelo de amenazas y matriz de riesgos | — | STRIDE por flujo, 30+ riesgos con probabilidad, impacto y mitigación | hecho |
| 0.7 | Matriz de permisos y políticas | RF‑B | `security.md` con matriz por rol, política de acceso y de retención | hecho |
| 0.8 | Registro de tratamiento y pendientes legales | — | 19 puntos de revisión jurídica en Ecuador, sin afirmar cumplimiento | hecho |
| 0.9 | Catálogo de requisitos | Todos | `requirements.md` con identificadores estables y prioridad | hecho |
| 0.10 | Backlog con criterios de aceptación | Todos | Este documento | hecho |
| 0.11 | `.env.example` sin valores reales | — | Ningún valor real; arranque que falla si falta un obligatorio | hecho |
| 0.12 | `.gitignore` que excluye secretos y datos | — | `.env`, claves, volcados y adjuntos excluidos | hecho |
| 0.13 | Guía de trabajo `CLAUDE.md` | — | Reglas no negociables y listas de verificación | hecho |
| 0.14 | Documentos de operación iniciales | — | `deployment`, `monitoring`, `backup-and-restore`, `incident-response`, `test-plan`, `known-limitations`, `production-readiness` creados y marcados con su estado real | pendiente |

## Fase 0b — Infraestructura local

| # | Tarea | Criterio de aceptación | Estado |
|---|---|---|---|
| 0b.1 | Variables de entorno de desarrollo dirigidas a D: | `PIP_CACHE_DIR`, `UV_CACHE_DIR`, `PLAYWRIGHT_BROWSERS_PATH` y caché de embeddings apuntan a D: | pendiente |
| 0b.2 | WSL2 con distribución en D: | `wsl -l -v` muestra la distribución; su disco virtual está bajo `D:\wsl` | pendiente |
| 0b.3 | Docker Engine y plugin Compose en WSL | `docker compose version` responde dentro de WSL | pendiente |
| 0b.4 | `docker-compose.dev.yml` con PostgreSQL 16 + pgvector y Redis 7 | `docker compose up -d` deja ambos servicios saludables | pendiente |
| 0b.5 | Extensiones verificadas | `SELECT extname FROM pg_extension` incluye `vector`, `btree_gist`, `pg_trgm`, `pgcrypto`, `unaccent` | pendiente |
| 0b.6 | Límites de memoria | `.wslconfig` y límites en compose acotan el consumo; el equipo sigue usable | pendiente |
| 0b.7 | Scripts de arriba y abajo | `infra-arriba.ps1` e `infra-abajo.ps1` idempotentes | pendiente |

## Fase 1 — Prototipo visual con datos sintéticos

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 1.1 | Proyecto Angular 19 PWA con TS estricto | RNF‑08, RNF‑13 | `npm run build` sin errores; `tsc --noEmit` limpio; service worker registrado | pendiente |
| 1.2 | Sistema de diseño y componentes base | RNF‑07 | Componentes de tabla, formulario, diálogo, calendario y notificación, con estados de carga, error y vacío | pendiente |
| 1.3 | Login simulado y cambio de rol | RF‑A01, RF‑B02 | Se puede entrar como cada uno de los seis roles y la interfaz cambia según el rol | pendiente |
| 1.4 | Guards de rol y de ámbito | RF‑B08 | Navegar a una ruta sin permiso redirige; documentado que no es un control de seguridad | pendiente |
| 1.5 | Generador de datos sintéticos | — | Clínica con 2 sedes, 4 especialidades, 8 profesionales, 60 pacientes, 200 citas, recetas y documentos; nombres claramente ficticios | pendiente |
| 1.6 | Pantallas de configuración | RF‑C | Especialidades, servicios, horarios, feriados y bloqueos navegables | pendiente |
| 1.7 | Pantallas de profesionales y pacientes | RF‑D, RF‑E | Listado, detalle, creación y edición | pendiente |
| 1.8 | Vista de agenda | RF‑G | Vistas de día, semana y profesional; creación, cancelación y reprogramación simuladas | pendiente |
| 1.9 | Lista de espera | RF‑J | Cola, oferta con temporizador y resultado | pendiente |
| 1.10 | Historia clínica | RF‑F | Notas con versiones e historial visible; recepción no ve contenido clínico | pendiente |
| 1.11 | Recetas y adherencia | RF‑L | Receta, calendario de tomas y registro de respuestas | pendiente |
| 1.12 | Base de conocimiento | RF‑M | Listado con estados y flujo de aprobación simulado | pendiente |
| 1.13 | Dashboard | RF‑Q | KPIs y gráficos con los filtros exigidos | pendiente |
| 1.14 | Accesibilidad | RNF‑07 | Navegación completa por teclado, foco visible, contraste y etiquetas; auditoría automatizada sin incidencias graves | pendiente |
| 1.15 | Pruebas de componentes | RNF‑06 | `npm test` en verde con la cobertura mínima | pendiente |

## Fase 2 — Backend, seguridad y auditoría

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 2.1 | Esqueleto FastAPI con configuración validada | — | Falla al arrancar si falta un obligatorio o si producción tiene valores de desarrollo | pendiente |
| 2.2 | Capa de base de datos y migración inicial | RF‑N | `alembic upgrade head` y `downgrade base` sin error; extensiones creadas | pendiente |
| 2.3 | Reloj inyectable y regla de lint | RF‑G10 | El lint falla si aparece `datetime.now()` en `app/` | pendiente |
| 2.4 | Usuarios, contraseñas Argon2id y política | RF‑A01, RF‑A04 | Pruebas de hash, verificación y política | pendiente |
| 2.5 | Tokens, rotación y revocación | RF‑A02, RF‑A06, RF‑A07 | Reutilizar un refresco rotado revoca la familia; prueba dedicada | pendiente |
| 2.6 | Segundo factor TOTP | RF‑A08 | Rol configurado sin 2FA recibe 403 con código específico | pendiente |
| 2.7 | Bloqueo por intentos y límite de tasa | RF‑A09 | Al sexto intento se bloquea; el límite de tasa responde 429 | pendiente |
| 2.8 | RBAC con permisos y ámbito | RF‑B01…RF‑B06 | Matriz de permisos verificada por prueba parametrizada para los seis roles | pendiente |
| 2.9 | Protección IDOR | RF‑B04 | Recurso de otra sede devuelve 404 para cada rol; prueba por endpoint | pendiente |
| 2.10 | Auditoría append‑only | RF‑A10 | La aplicación no puede actualizar ni borrar auditoría; prueba de privilegios | pendiente |
| 2.11 | Módulos de clínica, sede, especialidad y servicio | RF‑C01…RF‑C03 | CRUD con permisos y pruebas de API | pendiente |
| 2.12 | Módulo de pacientes y consentimientos | RF‑E01, RF‑E05, RF‑E06 | Consentimiento revocado detiene envíos; prueba de integración | pendiente |
| 2.13 | Logs estructurados con redacción | RNF‑14 | Prueba que provoca errores y verifica que no aparecen datos personales | pendiente |
| 2.14 | Cabeceras de seguridad y CORS | — | Prueba de presencia de cabeceras; comodín rechazado en producción | pendiente |
| 2.15 | OpenAPI y pruebas de contrato | — | `schemathesis` sin fallos sobre el esquema | pendiente |
| 2.16 | Pipeline de CI en verde | — | Todas las comprobaciones del pipeline pasan | pendiente |

## Fase 3 — Agenda

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 3.1 | Modelo de cita con columna generada y restricciones de exclusión | RF‑G06 | Migración aplicada; prueba que verifica el rechazo del solapamiento a nivel SQL | pendiente |
| 3.2 | Motor de disponibilidad | RF‑G01, RF‑G02 | Pruebas con Hypothesis: horario menos citas, bloqueos, feriados, descansos y buffers, sin solapes ni huecos negativos | pendiente |
| 3.3 | Zonas horarias | RF‑G10 | Pruebas con varias zonas, incluido cambio de horario de verano | pendiente |
| 3.4 | Bloqueo temporal y expiración | RF‑G05 | Un `HELD` vencido libera el turno; prueba con reloj fijo | pendiente |
| 3.5 | Creación, cancelación y reprogramación | RF‑G04 | Máquina de estados con transiciones inválidas rechazadas | pendiente |
| 3.6 | Idempotencia | RF‑G07 | Misma clave y cuerpo devuelve la respuesta original; cuerpo distinto devuelve 409 | pendiente |
| 3.7 | **Concurrencia de reservas** | RF‑G06, RNF‑05 | 50 intentos simultáneos sobre el mismo turno producen 1 cita y 49 rechazos claros | pendiente |
| 3.8 | Historial de cita | RF‑G08 | Toda transición registrada con actor y motivo | pendiente |
| 3.9 | Recursos y consultorios | RF‑G03 | Restricción de exclusión también por consultorio; prueba de concurrencia | pendiente |
| 3.10 | Citas recurrentes | RF‑G09 | Serie generada con cada instancia validada por la restricción | pendiente |

## Fase 4 — WhatsApp y calendarios

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 4.1 | Outbox transaccional y procesador | RF‑K06 | Prueba que mata el worker a media entrega y verifica entrega posterior sin duplicado | pendiente |
| 4.2 | Verificación y firma del webhook | RF‑H04 | Firma inválida devuelve 403 y no procesa; prueba dedicada | pendiente |
| 4.3 | Deduplicación y desorden | RF‑H05 | Webhook repetido no produce efecto doble; mensajes desordenados terminan en el estado correcto | pendiente |
| 4.4 | Adaptador sandbox de WhatsApp | ADR‑0012 | Suite de contrato común a real y sandbox; modos de fallo reproducibles | pendiente |
| 4.5 | Plantillas, opt‑in y opt‑out | RF‑H09, RF‑H10 | Opt‑out detiene envíos proactivos de inmediato; mensaje proactivo sin plantilla es rechazado | pendiente |
| 4.6 | Agente conversacional y herramientas | RF‑H01, RF‑H02 | Cada herramienta con prueba de autorización y de argumentos inválidos | pendiente |
| 4.7 | Transferencia a humano | RF‑H08 | La conversación pasa a `EN_ESPERA_HUMANO` y aparece en la bandeja | pendiente |
| 4.8 | Recordatorios de cita | RF‑K01…RF‑K05 | Programación, reprogramación y cancelación de recordatorios verificadas con reloj fijo | pendiente |
| 4.9 | **Notificaciones sin datos clínicos** | RF‑K07 | Prueba que recorre todas las plantillas y falla si alguna incluye diagnóstico o medicamento | pendiente |
| 4.10 | OAuth de calendario y cifrado de tokens | RF‑D04, RF‑D05, RF‑I01 | Token nunca en claro en la base; prueba de cifrado y descifrado | pendiente |
| 4.11 | Sincronización de eventos | RF‑I04, RF‑I05 | Alta, cambio y baja reflejados; relación de identificadores conservada | pendiente |
| 4.12 | Reconciliación y conflictos | RF‑I06 | Evento borrado o movido externamente se detecta y genera alerta sin perder la cita | pendiente |
| 4.13 | **Resiliencia del calendario** | RF‑I08 | Con el proveedor caído, la cita se confirma y el evento se entrega al recuperarse | pendiente |

## Fase 5 — Lista de espera

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 5.1 | Registro y preferencias | RF‑J01 | Preferencias respetadas en la selección de candidatos | hecho: interfaz y API guardan profesional, intervalo de fechas, días, franja horaria local y antelación; integración y E2E verifican persistencia y filtrado de turnos |
| 5.2 | Turno liberado transaccional | RF‑J02 | La cancelación y el turno liberado se confirman juntos o no se confirman | hecho: transacción y rollback inducido verificados contra la restricción EXCLUDE real de PostgreSQL; ante la carrera, la cita nueva no se crea y la oferta continúa activa |
| 5.3 | Selección de candidatos | RF‑J03 | Prueba con casos que deben y no deben coincidir | hecho: pruebas de sede, servicio, profesional, prioridad, antelación y disponibilidad en `test_lista_espera.py` |
| 5.4 | **Oferta única por turno** | RF‑J04 | El índice único parcial impide dos ofertas activas; prueba de concurrencia | hecho: índice parcial más prueba concurrente de duplicado en `test_oferta_concurrente.py` |
| 5.5 | Contenido y plazo de la oferta | RF‑J05 | La oferta incluye todos los campos exigidos y su tiempo límite | hecho en outbox: plantilla sin datos clínicos, consentimiento y plazo probados; entrega real a WhatsApp sigue fuera del entorno local |
| 5.6 | Expiración y siguiente candidato | RF‑J06 | Tras expirar, se ofrece al siguiente; prueba con reloj fijo | hecho: expiración, nuevo candidato y reintento sin duplicar están probados en `test_tareas_lista_espera.py` |
| 5.7 | Aceptación y reagendamiento | RF‑J07 | Se crea la cita nueva y se libera la anterior en una transacción | hecho: cita anterior opcional validada para paciente, clínica, sede y servicio; la aceptación crea la nueva y cancela la previa atómicamente; integración, API y E2E cubren aceptación y turno ocupado |
| 5.8 | Cadena de liberaciones | RF‑J08 | El turno liberado por un reagendamiento genera una nueva oferta; con límite de profundidad | hecho: el horario anterior se ofrece al siguiente paciente, con profundidad máxima de cinco liberaciones; integración y E2E verifican la cadena |
| 5.9 | **Aceptación simultánea** | RF‑J09 | 2 y 10 aceptaciones concurrentes producen 1 ganador; el resto recibe mensaje adecuado | hecho: diez sesiones y solicitudes HTTP concurrentes producen una cita (200) y nueve respuestas 409; las ofertas perdedoras vuelven a la cola. Probado contra PostgreSQL real |

## Fase 6 — Conocimiento y RAG

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 6.1 | Tablas de conocimiento y pgvector | RF‑N01, RF‑N02 | Migración con índice HNSW y GIN; prueba de integración | pendiente |
| 6.2 | Carga de documentos y validación de archivos | RF‑M01, RF‑E08 | Tipo real verificado por contenido; tamaño limitado; prueba de archivo malicioso | pendiente |
| 6.3 | Versionado y flujo de aprobación | RF‑M02…RF‑M04 | Transiciones de estado con permisos separados de carga y aprobación | pendiente |
| 6.4 | Ingesta, fragmentación y embeddings | — | Trabajo reanudable; reinicio a media ingesta no duplica fragmentos | pendiente |
| 6.5 | Búsqueda híbrida con pre‑filtro | RF‑N03, RF‑N04, RF‑O02 | Los filtros están en el `WHERE`; prueba de arquitectura que impide otras consultas a las tablas | pendiente |
| 6.6 | **Cero fugas** | RF‑O08 | Pruebas negativas: otra sede, otra especialidad, otro paciente, archivado y vencido nunca se recuperan | pendiente |
| 6.7 | Flujo RAG con exigencia de fuente | RF‑O04, RF‑O06 | Sin fuente sobre el umbral, responde que no tiene información aprobada y ofrece derivación | pendiente |
| 6.8 | **Defensa anti inyección de prompt** | RF‑O07 | Corpus malicioso: ninguna invocación de herramienta ni cambio de ámbito; prueba bloqueante | pendiente |
| 6.9 | Detección en la ingesta | — | Texto oculto y patrones de inyección marcan el documento para revisión | pendiente |
| 6.10 | Arnés de evaluación | RF‑O08 | Informe con Hit@K, precisión, fundamentación y tasa sin fuente, publicado en `rag.md` | pendiente |
| 6.11 | SSRF en ingesta por URL | — | Destinos privados y metadatos de nube bloqueados; prueba dedicada | pendiente |

## Fase 7 — Historia clínica y medicamentos

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 7.1 | Notas versionadas | RF‑F01…RF‑F03 | Editar crea versión; motivo obligatorio; sin `UPDATE` ni `DELETE`; prueba de privilegios | pendiente |
| 7.2 | Control de acceso clínico | RF‑F06, RF‑B06 | Recepción recibe 404; profesional sin relación asistencial recibe 404 | pendiente |
| 7.3 | Nivel de sensibilidad | RF‑F07 | N3 exige permiso adicional; acceso registrado de forma reforzada | pendiente |
| 7.4 | Acceso de emergencia | RF‑B07 | Exige motivo, caduca, se audita y notifica | pendiente |
| 7.5 | Recetas versionadas | RF‑L01 | Versión inmutable con motivo de cambio | pendiente |
| 7.6 | **Solo receta confirmada genera tomas** | RF‑L02 | Un borrador no genera ninguna toma; prueba dedicada | pendiente |
| 7.7 | Cálculo del calendario de tomas | RF‑L03 | Pruebas de cada tipo de frecuencia, con inicio, fin y zona horaria | pendiente |
| 7.8 | **PRN sin horarios automáticos** | RF‑L08 | `CHECK` en base de datos y prueba que intenta violarlo | pendiente |
| 7.9 | Recordatorios de toma y respuestas | RF‑L04, RF‑L05 | Las cinco respuestas registradas; «recordarme después» reprograma | pendiente |
| 7.10 | Alertas de adherencia y seguimiento | RF‑L06 | Alertas por omisiones autorizadas y atendibles; control posterior de procedimientos con fecha elegida por el profesional, cierre auditado y recorrido E2E | parcial: ambos flujos anteriores están implementados; siguen pendientes alertas clínicas estructuradas ante problemas reportados por el paciente |
| 7.11 | **Cambio de receta cancela recordatorios futuros** | RF‑L09 | Suspender una receta cancela tomas y avisos futuros pendientes y conserva los registros pasados; una modificación versionada deberá aplicar la misma regla | parcial: suspensión, cancelación de tomas/avisos y conservación del historial tienen cobertura de integración y API; modificar/versionar una receta aún no está disponible |
| 7.12 | **Lista negra clínica de la IA** | RF‑L07 | Prueba que verifica la ausencia de herramientas de escritura clínica y la derivación obligatoria | pendiente |

## Fase 8 — Dashboard y predicciones

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 8.1 | Agregados diarios | RF‑Q | Métricas verificadas contra un conjunto sintético de valores conocidos | pendiente |
| 8.2 | Endpoints con filtros y ámbito | RF‑Q01 | Un profesional solo ve sus propias métricas | pendiente |
| 8.3 | Visualizaciones | RF‑Q | Gráficos accesibles, con estados de carga, error y vacío | pendiente |
| 8.4 | Registro de modelos | RF‑R06 | Modelo, versión, variables, confianza y explicación persistidos | pendiente |
| 8.5 | Modelos de referencia | RF‑R01…RF‑R05 | Modelo base entrenado sobre datos sintéticos, con métricas reportadas honestamente | pendiente |
| 8.6 | **Límites de las predicciones** | RF‑R07 | Prueba de arquitectura: ninguna predicción puede modificar citas, recetas ni accesos | pendiente |

## Fase 9 — Pagos

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 9.1 | Máquina de estados de pago | RF‑P02 | Transiciones inválidas rechazadas; prueba exhaustiva | pendiente |
| 9.2 | Comprobantes | RF‑P01 | Validación de archivo y análisis antivirus | pendiente |
| 9.3 | Validación manual | RF‑P03 | Registro de validador, fecha y comentarios | pendiente |
| 9.4 | **Sin datos financieros sensibles** | RF‑P04 | Prueba que inspecciona el esquema y falla si aparece una columna de tarjeta, clave u OTP | pendiente |
| 9.5 | Auditoría de pagos | RF‑P05 | Historial append‑only | pendiente |

## Fase 10 — Preparación de producción

| # | Tarea | Criterio de aceptación | Estado |
|---|---|---|---|
| 10.1 | SAST y análisis de dependencias | Sin hallazgos críticos o altos sin justificación y plan | pendiente |
| 10.2 | DAST sobre la instancia en ejecución | Informe con hallazgos y correcciones | pendiente |
| 10.3 | Escaneo de contenedores | Imágenes sin vulnerabilidad crítica | pendiente |
| 10.4 | Detección de secretos en todo el historial | `gitleaks` limpio | pendiente |
| 10.5 | Pruebas de carga | Objetivos de RNF‑01…RNF‑04 medidos y publicados | pendiente |
| 10.6 | Pruebas de recuperación | Caída de Redis, PostgreSQL, worker, WhatsApp, calendario y LLM sin pérdida de datos | pendiente |
| 10.7 | **Respaldo y restauración verificada** | Restauración real en una instancia limpia, con recuento de filas comparado | pendiente |
| 10.8 | Procedimiento de rollback probado | Rollback de versión y de migración ejecutados en preproducción | pendiente |
| 10.9 | Monitoreo y alertas | Métricas, paneles y alertas activas con umbrales definidos | pendiente |
| 10.10 | Pruebas de aceptación con escenarios de clínica | Los 21 escenarios de extremo a extremo en verde | pendiente |
| 10.11 | Informe final de riesgos | Riesgos residuales, limitaciones y pendientes legales | pendiente |

---

## Dependencias externas

| Dependencia | Necesaria para | Estado | Bloquea |
|---|---|---|---|
| **Cuenta de WhatsApp Business + número verificado** | Envío y recepción reales | **Ausente** | Verificación real de la Fase 4. El desarrollo continúa con sandbox |
| **Plantillas aprobadas por Meta** | Mensajes proactivos | **Ausente** | Recordatorios reales. La aprobación de plantillas tarda días y la decide Meta |
| **Proyecto de Google Cloud con OAuth configurado** | Sincronización de calendarios | **Ausente** | Verificación real de la Fase 4 |
| **Pantalla de consentimiento de Google verificada** | Uso fuera de modo de prueba | **Ausente** | Producción. La verificación de Google puede tardar semanas |
| Clave de proveedor de LLM | Agente conversacional real | **Presente** (`ANTHROPIC_API_KEY`) | Nada |
| Proveedor de embeddings | RAG | **Resuelto en local** con fastembed | Nada |
| Servidor SMTP | Verificación de correo y recuperación | **Ausente** | Uso real. En desarrollo se imprime por consola |
| Dominio y certificado TLS | Webhooks y producción | **Ausente** | Producción. Meta exige HTTPS público para el webhook |
| Entorno de alojamiento | Staging y producción | **Sin definir** | Fase 10 |
| Antivirus (clamd) | Análisis de archivos | **Ausente** | Producción. En desarrollo se registra como no disponible |
| **Revisión jurídica en Ecuador** | Operar con pacientes reales | **Ausente** | **Producción. Es el bloqueo de mayor prioridad (L‑01)** |
| Acuerdo con la clínica sobre retención y consentimientos | Política de datos | **Ausente** | Producción |

---

## Preguntas bloqueantes

Ninguna de estas preguntas detiene el desarrollo. Las decisiones provisionales tomadas
son seguras y reversibles, y están documentadas. Las marcadas con ⚠ **sí deben
responderse antes de operar con pacientes reales**.

### Requieren confirmación antes de producción

1. ⚠ **¿Qué plazo de conservación aplica a la historia clínica y a las recetas?**
   Decisión provisional: no se implementa borrado automático. Un borrado automático mal
   configurado sobre historia clínica es irreversible.
2. ⚠ **¿La receta electrónica requiere firma electrónica del profesional en Ecuador?**
   Decisión provisional: el módulo registra al profesional que confirma y conserva
   versiones inmutables, lo que permitiría añadir firma sin rediseñar. Si la firma es
   obligatoria, el módulo de recetas cambia.
3. ⚠ **¿Qué nivel de verificación exige la clínica para entregar información clínica por
   WhatsApp?** Decisión provisional, la más restrictiva: el teléfono nunca basta; se exige
   verificación por documento. Solo la clínica puede relajarlo, y hacerlo tiene
   consecuencias de privacidad.
4. ⚠ **¿Acepta la clínica que el texto de las conversaciones se procese por un proveedor
   externo de LLM?** Decisión provisional: el agente no envía historia clínica al modelo.
   Aun así hay transferencia internacional que requiere base legal.
5. ⚠ **¿Quién es el responsable clínico que aprueba los documentos de la base de
   conocimiento?** Decisión provisional: el permiso existe y se asigna por especialidad;
   la persona concreta la define la clínica.

### Decididas provisionalmente, revisables sin coste

6. ¿Se ofrecen citas recurrentes? Provisional: el modelo las soporta y la interfaz queda
   para el final de la Fase 3.
7. ¿Una cita puede tener varios servicios? Provisional: no, un servicio por cita. Añadir
   varios afectaría al cálculo de duración.
8. ¿Se permite sobreagendamiento deliberado? Provisional: no. La restricción de exclusión
   lo impide por diseño; permitirlo exigiría un estado nuevo exento.
9. ¿Cuántas veces se puede ofrecer un turno a la misma persona? Provisional: se registra
   `veces_ofrecido` y el límite es configurable.
10. ¿Qué antigüedad máxima tiene un documento «vigente» sin revisión? Provisional:
    `effective_until` opcional; sin él, el documento no caduca. Se recomienda a la clínica
    fijar caducidad a los protocolos.
11. ¿El paciente puede cancelar por WhatsApp sin límite de antelación? Provisional: la
    política de cancelación es configurable y por defecto exige antelación.
12. ¿Moneda y redondeo? Provisional: USD con dos decimales, coherente con Ecuador.

---

## Tareas de mantenimiento registradas

| # | Tarea | Origen |
|---|---|---|
| M‑01 | Evaluar la actualización a la última versión mayor de Angular | ADR‑0005 |
| M‑02 | Migrar las pruebas de componentes a Vitest cuando el constructor lo soporte de forma estable | ADR‑0006 |
| M‑03 | Reevaluar el proveedor de embeddings si la evaluación de RAG no alcanza el umbral | ADR‑0007 |
| M‑04 | Revisar trimestralmente cuentas, roles y ámbitos | `security.md` |
| M‑05 | Rotar los secretos según el procedimiento documentado | `security.md` |
