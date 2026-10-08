# Backlog por fases, criterios de aceptación y dependencias

Entregable de la Fase 0. Cada tarea referencia los requisitos de
[`requirements.md`](requirements.md). Una tarea está **hecha** cuando su criterio de
aceptación se verifica con una prueba automatizada que se ejecuta en el pipeline, salvo
que se indique explícitamente que la Verificación es manual.

Estado: `pendiente` · `en curso` · `hecho` · `bloqueado`

## Revisión de los pedidos de registros y documentos (2026-10-07)

| Pedido | Estado y acceso |
|---|---|
| CRUD de clínicas | Implementado y probado en navegador: Superadministrador → Clínicas → crear, consultar, editar, desactivar/reactivar. La baja conserva las referencias. |
| CRUD de usuarios | Implementado y probado en navegador: Administración → Usuarios y roles → crear, consultar, Editar datos, Gestionar accesos, Quitar/Restaurar acceso. Conserva el perfil profesional y el rol al editar identidad. Superadministración también gestiona las cuentas de cada clínica. |
| Atención desde la ficha según la cita | Implementada: la cita fija sede/especialidad; Atención y documentos integra la historia completa y enlaces a Agenda/Pagos. Cambiar entre sus pestañas directas conserva la cita seleccionada. |
| Faciograma | Implementado: 23 zonas interactivas, seguimiento manual, versiones, anulación, historial y PDF gráfico. Pestaña directa en la ficha. Se habilitó en la especialidad odontológica del acceso local; otras clínicas lo configuran desde Catálogo. |
| PDF de presupuesto, cotización y receta | Implementado: archivo real generado por el servidor, importes decimales y receta confirmada con su pauta y firmante. También desde los planes dentales. |
| Entrega por WhatsApp | Flujo privado con consentimiento y verificación de identidad, probado en sandbox. La entrega real con Meta sigue pendiente de configuración y prueba. |
| Manuales por rol | Actualizados en Ayuda con los accesos directos y la selección de la atención; se conserva un manual diferente por rol. |

Esto verifica los registros solicitados. El inventario de pendientes de otras
especialidades, facturación e inventario sigue detallado en las fases siguientes.
Evidencia: [informe](verificacion-2026-10-07.md#faciograma-visible-y-documentos-desde-la-ficha).

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
| 0.13 | Guía de trabajo `CLAUDE.md` | — | Reglas no negociables y listas de Verificación | hecho |
| 0.14 | Documentos de operación iniciales | — | `deployment`, `monitoring`, `backup-and-restore`, `incident-response`, `test-plan`, `known-limitations`, `production-readiness` creados y marcados con su estado real | hecho: los siete documentos existen y distinguen procedimientos probados de los no ejecutados; restauración, monitoreo, incidentes y preparación de producción declaran límites y evidencia local. |

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
| 1.1 | Proyecto Angular 22 PWA con TS estricto | RNF‑08, RNF‑13 | `npm run build` sin errores; `tsc --noEmit` limpio; service worker registrado; migración oficial 19→20→21→22 validada | hecho: build de producción, TypeScript y lint pasan en Angular 22.2.1; 443 pruebas Vitest superan cobertura mínima y `npm audit` no reporta vulnerabilidades. |
| 1.2 | Sistema de diseño y componentes base | RNF‑07 | Componentes de tabla, formulario, diálogo, calendario y notificación, con estados de carga, error y vacío | en curso (2026‑10‑07): sistema visual de vidrio líquido con tokens en `styles.scss`, contraste calculado en el peor caso y respaldos para transparencia reducida y alto contraste; capa de movimiento con Motion (`nucleo/movimiento/`) y gráficos en movimiento. Ver [`recursos-visuales.md`](recursos-visuales.md). Falta un catálogo de componentes documentado aparte |
| 1.3 | Login simulado y cambio de rol | RF‑A01, RF‑B02 | Se puede entrar como cada uno de los seis roles y la interfaz cambia según el rol | pendiente |
| 1.4 | Guards de rol y de ámbito | RF‑B08 | Navegar a una ruta sin permiso redirige; documentado que no es un control de seguridad | pendiente |
| 1.5 | Generador de datos sintéticos | — | Clínica con 2 sedes, 4 especialidades, 8 profesionales, 60 pacientes, 200 citas, recetas y documentos; nombres claramente ficticios | pendiente |
| 1.6 | Pantallas de configuración | RF‑C | Especialidades, servicios, horarios semanales, pausas, feriados y bloqueos por sede están conectados a la API; la administración de bloqueos respeta el alcance de profesionales | en curso |
| 1.7 | Pantallas de profesionales y pacientes | RF‑D, RF‑E | Perfiles con alta, edición, asignación de sedes y activación; vínculo único perfil/cuenta desde Usuarios y roles; CRUD administrativo de pacientes con permisos, auditoría e idempotencia; disponibilidad individual conectada. Ver pruebas API `test_profesionales_gestion_api.py`, `test_usuarios_api.py`, `test_catalogo_api.py`, `test_demo_operativa.py`, pruebas de componentes y E2E de equipo/pacientes. | hecho |
| 1.8 | Vista de agenda | RF‑G | Agenda conectada a PostgreSQL con vistas día, semana, mes y lista; filtro por profesional; reserva manual desde hueco, cancelación y reprogramación con transiciones auditadas. Cubierto por pruebas de `CalendarioAgendaComponent` y escenarios E2E `05-demo-operativa.spec.ts`: reserva, reprograma/cancela y consulta persistencia por API. | hecho |
| 1.9 | Lista de espera | RF‑J | Cola, Oferta con temporizador y resultado | hecho: la interfaz registra pacientes, Preferencias y citas previas; ofrece turnos liberados en orden de prioridad, muestra vencimiento/respuestas y resuelve aceptación, rechazo, expiración o retiro. API/UI aplican permisos y alcance, y aceptación reprograma la cita previa de forma atómica sin doble reserva. El E2E `09-lista-espera.spec.ts` recorre alta, Oferta, falta de consentimiento y reagendamiento; suite frontend cubre pantalla y estados. Los avisos al paciente siguen limitados al canal/adaptador configurado. |
| 1.10 | Historia clínica | RF‑F | Notas con versiones e historial visible; recepción no ve contenido clínico; alergias, antecedentes y anamnesis configurable cargados desde la API | hecho: notas versionadas, acceso por relación, antecedentes/alergias y cuestionarios por clínica conectados y cubiertos por API, componente y suite frontend. Formulario MSP 033 y PDF clínico trazable quedan como tareas separadas en Fase 7. |
| 1.11 | Recetas y adherencia | RF‑L | Receta, calendario de tomas y registro de respuestas | parcial: receta firmada genera calendario; pacientes/equipo registran tomas y el worker genera alertas abiertas por omisiones. Lectura clínica usa permiso y relación asistencial. Las cinco respuestas cerradas por WhatsApp ya procesan toma, aplazamiento, omisión, ayuda y revisión clínica; siguen pendientes reglas adicionales de prioridad/escalado y la entrega real del proveedor |
| 1.12 | Base de conocimiento | RF‑M | Listado con estados y flujo de aprobación simulado | hecho: carga y revisión de texto/PDF, ACL, auditoría, análisis de riesgo y búsqueda híbrida conectados a PostgreSQL; la recuperación se limita a la versión vigente aprobada. La fuente y el trabajo de ingesta son durables; un worker los reanuda automáticamente y el reenvío manual permite recuperar fallos controlados del proveedor. OCR, ClamAV local y embeddings semánticos reales siguen pendientes. Evidencia por revisión en `docs/test-plan.md`. |
| 1.13 | Dashboard | RF‑Q | KPIs y Gráficos con fechas personalizadas y filtros de catálogos dentro del ámbito autorizado | parcial: fechas rápidas/personalizadas, filtros y tendencias locales; cubre pacientes nuevos/recurrentes, recuperación de turnos, adherencia bajo permisos y ocupación con horarios reales, pausas, feriados y bloqueos. El porcentaje se oculta con filtro de estado o ámbito parcial de pacientes. Faltan visualizaciones adicionales, predicciones e informes comerciales. |
| 1.14 | Accesibilidad | RNF‑07 | Navegación completa por teclado, foco visible, contraste y etiquetas; auditoría automatizada sin incidencias graves | en curso: axe-core WCAG 2.2 A/AA analiza acceso, panel, agenda, historia clínica y configuración, y recorre todas las secciones visibles de los seis roles; una aserción de cobertura comprueba la unión de las 20 rutas del menú. Diez escenarios pasan sin infracciones. La auditoría encontró y corrigió contraste insuficiente en Conocimiento y Catálogo, y falta de foco por teclado en la tabla horizontal de cargos. También se prueba salto al contenido, landmark único en acceso, grupo de roles nombrado y `aria-current="page"`. Siguen pendientes otros estados interactivos y revisión manual con lector de pantalla y zoom. Comando: `cd pruebas-e2e; npm run test:a11y`. |
| 1.15 | Pruebas de componentes | RNF‑06 | `npm test` en verde con la cobertura mínima | hecho: suite Vitest completa actual sobre `claude/friendly-gates-o240sb`: 605/605 en 83 archivos. Sentencias 86,12 %, ramas 72,88 %, funciones 81,60 % y líneas 88,31 %, superiores a los mínimos (80/70/80/80). La composición declarativa de rutas queda fuera del cálculo y sus guardias se prueban en `app.routes.spec.ts`. Lint y build pasan; 462,85 kB iniciales. Chromium 62/62 incluye pantallas de trabajo y formularios accesibles; ver `verificacion-2026-10-07.md`. |

## Fase 2 — Backend, seguridad y auditoría

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 2.1 | Esqueleto FastAPI con configuración validada | — | Falla al arrancar si falta un obligatorio o si producción tiene valores de desarrollo | hecho: `Configuración` valida combinaciones de producción, secretos obligatorios y valores de ejemplo antes de crear la aplicación; errores enumeran los campos que deben corregirse. `test_configuración.py`: 53 pruebas, incluidos secretos vacíos/cortos, proveedores simulados, CORS inseguro y variables desconocidas. |
| 2.2 | Capa de base de datos y migración inicial | RF‑N | `alembic upgrade head` y `downgrade base` sin error; extensiones creadas | hecho: en una base PostgreSQL desechable se crearon `vector`, `btree_gist`, `pg_trgm`, `pgcrypto` y `unaccent`; la cadena completa aplicó, revirtió a `base` y volvió a `head` (`20261006_028`). CI repetirá `downgrade base → upgrade head → check` antes de cargar catálogos. La base temporal se eliminó. |
| 2.3 | Reloj inyectable y regla de lint | RF‑G10 | El lint falla si aparece `datetime.now()` en `app/` | hecho: `TID251` quedó activada en Ruff y solo se exceptúa `app/nucleo/reloj.py`, que implementa el reloj de sistema. Se verificó que una muestra con `datetime.now()` falla el lint. Las semillas reciben reloj opcional; una prueba con `RelojFijo` confirma que las fechas generadas respeten el reloj. `test_semillas.py`: 30 pasaron. |
| 2.4 | Usuarios, contraseñas Argon2id y política | RF‑A01, RF‑A04 | Pruebas de hash, Verificación y política | hecho: Argon2id con sal aleatoria, parámetros de coste y rehash gradual; Verificación incorrecta o hash malformado falla cerrado. Una prueba compara un hash de parámetros antiguos con el actual. La política comprueba longitud, composición y contraseñas comunes; el alta API rechaza contraseñas débiles sin guardar la cuenta ni reflejar el valor recibido. Primitivas y alta: 63 pruebas. |
| 2.5 | Tokens, rotación y revocación | RF‑A02, RF‑A06, RF‑A07 | Reutilizar un refresco rotado revoca la familia; prueba dedicada | hecho: API comprueba que la reutilización del refresco anterior responde 401 y que el nuevo también deja de funcionar; integración confirma que se revocan todas las sesiones de la familia, se genera auditoría de alerta y el token posterior recibe rechazo. `test_autenticacion_api.py` + `test_autenticacion.py`: 70 pasaron. |
| 2.6 | Segundo factor TOTP | RF‑A08 | Rol configurado sin 2FA recibe 403 con código específico | hecho: prueba HTTP parametriza el rol que exige 2FA y verifica 403 `SEGUNDO_FACTOR_REQUERIDO`, sin tokens ni sesión. Integración cubre secreto cifrado, código válido/inválido, intento auditado y herencia de Verificación al rotar. |
| 2.7 | Bloqueo por intentos y límite de tasa | RF‑A09 | Al sexto intento se bloquea; el límite de tasa responde 429 | hecho: integración comprueba bloqueo al alcanzar el máximo, rechazo aun con contraseña correcta y limpieza tras expirar; API verifica 429 y `Retry-After`. Suite de autenticación API + integración: 71 pasaron. |
| 2.8 | RBAC con permisos y ámbito | RF‑B01…RF‑B06 | Matriz de permisos verificada por prueba parametrizada para los seis roles | hecho: la prueba lee la matriz de `docs/security.md`, exige cobertura única de todo el catálogo y compara concesiones y denegaciones del backend para los seis roles base. La comprobación reveló permisos omitidos y declaraciones incorrectas de acceso clínico/financiero; se corrigió la matriz sin ampliar permisos. `pruebas/unitarias/test_autorizacion.py`: 35 pruebas pasan; 15 cubren matriz y cobertura. |
| 2.9 | Protección IDOR | RF‑B04 | Recurso de otra sede devuelve 404 para cada rol; prueba por endpoint | parcial: Agenda y catálogo prueban aislamiento por sede. En Historia clínica, notas y resumen de un paciente de otra clínica devuelven el mismo 404 que un UUID inexistente para un rol sin permiso clínico y otro con permiso pero sin relación asistencial. En Pagos, comprobante, listado e historial responden 404 después de salir de sede. Automatizaciones ahora prueba que un cambio de configuración en una clínica no altera lo que ve otra. Las pruebas API focalizadas de Historia, Pagos y Automatizaciones pasan; la matriz exhaustiva por endpoint, rol y transición sigue pendiente. |
| 2.10 | Auditoría append‑only | RF‑A10 | PostgreSQL rechaza cambios directos al registro de auditoría | hecho: disparadores impiden `UPDATE`, `DELETE` y `TRUNCATE`, también con el rol propietario usado localmente. Tres pruebas SQL directas comprueban SQLSTATE `42501`; migración `20261006_028`. Sigue pendiente la cuenta de aplicación separada del dueño del esquema para producción (10.12), que debe impedir desactivar o retirar los disparadores. |
| 2.11 | Módulos de clínica, sede, especialidad y servicio | RF‑C01…RF‑C03 | Datos de clínica editables; sedes aprovisionadas por el portal y editables localmente dentro del ámbito con `sede.gestionar`; especialidades y servicios con CRUD, ámbito de clínica, permisos y auditoría. Cubierto por 28 pruebas API de catálogo y el recorrido E2E de sedes | hecho |
| 2.12 | Módulo de pacientes y consentimientos | RF‑E01, RF‑E05, RF‑E06 | Consentimiento revocado detiene envíos; prueba de integración | hecho: además de impedir nuevos encolados, el worker vuelve a validar el consentimiento vigente antes de enviar; una revocación mientras el mensaje está pendiente lo marca `DESCARTADO`. Prueba de integración con PostgreSQL y adaptador sandbox; API verifica otorgar/revocar y conserva evidencia. `pruebas/integracion/test_outbox.py` y `pruebas/api/test_consentimientos_api.py`. |
| 2.13 | Logs estructurados con redacción | RNF‑14 | Prueba que provoca errores y verifica que no aparecen datos personales | hecho: la ruta real de `structlog` y la de `logging` externo se ejercitan con excepciones que incluyen cédula, correo, teléfono y campos identificativos; se verifica que los identificadores de paciente se conservan y los datos personales no aparecen en JSON. `pruebas/unitarias/test_registro.py`, 55 pruebas. |
| 2.14 | Cabeceras de seguridad y CORS | — | Prueba de presencia de cabeceras; comodín rechazado en producción | hecho: las pruebas HTTP confirman cabeceras de seguridad y correlación en respuesta normal y 404; preflight valida origen, método y cabeceras permitidas y rechaza un origen ajeno. La validación de configuración de producción rechaza `ORIGENES_CORS=*` (13 casos parametrizados). `pruebas/api/test_seguridad_http_api.py`, `pruebas/unitarias/test_configuración.py`. |
| 2.15 | OpenAPI y pruebas de contrato | — | `schemathesis` sin fallos sobre el esquema | hecho: valida el documento completo y genera/contrasta un caso por cada operación OpenAPI (100+), por ASGI y sin credenciales. Se documentó el sobre común de errores HTTP y la Verificación alternativa de indicaciones posconsulta; los proveedores quedan simulados y las transacciones de prueba se revierten. `pruebas/api/test_contrato_openapi.py`, 2 pruebas. |
| 2.16 | Pipeline de CI en verde | — | Todas las comprobaciones del pipeline pasan | en curso: frontend 538/538, lint, tipos y build; backend global 1806 aprobadas, 3 pruebas de Anthropic omitidas por credenciales; una corrida anterior con cobertura midió 87,45 % (mínimo 80 %); `pip-audit`, Ruff, mypy, Bandit, Gitleaks y Trivy de ambas imágenes pasan. La aserción aleatoria corregida pasa en la repetición global. Falta ejecutar el pipeline CI completo en una sola corrida y cerrar cualquier diferencia que aparezca. Evidencia en `docs/test-plan.md`. |

## Fase 3 — Agenda

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 3.1 | Modelo de cita con columna generada y restricciones de exclusión | RF‑G06 | Migración aplicada; prueba que verifica el rechazo del solapamiento a nivel SQL | hecho: esquema PostgreSQL migrado hasta `20261007_030`; la restricción GiST y las reservas con intervalos solapados se verifican contra PostgreSQL en `pruebas/integracion/test_servicio_agenda.py` y `pruebas/concurrencia/test_reserva_concurrente.py`. |
| 3.2 | Motor de disponibilidad | RF‑G01, RF‑G02 | Pruebas con Hypothesis: horario menos citas, bloqueos, feriados, descansos y buffers, sin solapes ni huecos negativos | hecho: 62 pruebas unitarias de disponibilidad y series; Hypothesis explora horarios, pausas, feriados, bloqueos, buffers y solapes en `pruebas/unitarias/test_disponibilidad.py`. |
| 3.3 | Zonas horarias | RF‑G10 | Pruebas con varias zonas, incluido cambio de horario de verano | hecho: Hypothesis cubre zonas y cambios horarios; `test_series_agenda.py` valida horario local y rechaza horas inexistentes durante el cambio de verano. |
| 3.4 | Bloqueo temporal y expiración | RF‑G05 | Un `HELD` vencido libera el turno; prueba con reloj rijo | hecho: integración y API verifican expiración, rechazo al confirmar un bloqueo vencido y liberación del horario usando reloj controlado. |
| 3.5 | Creación, cancelación y reprogramación | RF‑G04 | Máquina de estados con transiciones inválidas rechazadas | hecho: integración y API cubren creación, cancelación, reprogramación, transición inválida y conservación del identificador. |
| 3.6 | Idempotencia | RF‑G07 | Misma clave y cuerpo devuelve la respuesta original; cuerpo distinto devuelve 409 | hecho: pruebas de servicio/API verifican repetición de citas y series sin duplicados y conflicto ante un cuerpo distinto. |
| 3.7 | **Concurrencia de reservas** | RF‑G06, RNF‑05 | 50 intentos simultáneos sobre el mismo turno producen 1 cita y 49 rechazos claros | hecho: `pruebas/concurrencia/test_reserva_concurrente.py` ejecutó los casos con conexiones PostgreSQL independientes; también cubre intervalos solapados, turnos consecutivos y conflicto de consultorio. |
| 3.8 | Historial de cita | RF‑G08 | Toda transición registrada con actor y motivo | hecho: pruebas de integración comprueban historial de creación, cambio de estado, cancelación y reprogramación con actor y motivo. |
| 3.9 | Recursos y consultorios | RF‑G03 | Catálogo CRUD de consultorios por sede con ámbito RBAC y auditoría; la restricción GiST y la prueba de carrera entre dos profesionales protegen una misma sala | hecho |
| 3.10 | Citas recurrentes | RF‑G09 | Serie generada con cada instancia validada por la restricción | hecho: `POST /agenda/citas/series` valida cada horario con el motor y persiste la serie completa o ninguna cita; conserva la hora local, aplica idempotencia y enlaza auditoría y recordatorios. Modal Liquid Glass integrado en Agenda; pruebas unitarias, integración, API y navegador. Migración de índice `20261007_030`, encadenada después de `20261007_029` (Gastos). |
| 3.11 | Gestión navegable de bloqueos | RF‑G02, RF‑G03 | Crear, listar, editar y eliminar vacaciones, ausencias, capacitaciones y mantenimientos para sede, profesional o consultorio; filtrar por permisos y ámbito; advertir y confirmar las citas activas afectadas; auditar cambios | hecho |
| 3.12 | Disponibilidad semanal por profesional | RF‑G01, RF‑G02, RF‑G10 | CRUD de franjas particulares por sede, profesional, granularidad y vigencia; solapamientos rechazados; ámbitos de rol comprobados; agenda usada por el cálculo de disponibilidad en la zona local de la sede | hecho |

## Fase 4 — WhatsApp y calendarios

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 4.1 | Outbox transaccional y procesador | RF‑K06 | Prueba que mata el worker a media entrega y verifica entrega posterior sin duplicado | pendiente |
| 4.2 | Verificación y firma del webhook | RF‑H04 | Firma inválida devuelve 403 y no procesa; prueba dedicada | pendiente |
| 4.3 | Deduplicación y desorden | RF‑H05 | Webhook repetido no produce erecto doble; mensajes desordenados terminan en el estado correcto | pendiente |
| 4.4 | Adaptador sandbox de WhatsApp | ADR‑0012 | Suite de contrato común a real y sandbox; modos de rallo reproducibles | pendiente |
| 4.5 | Plantillas, opt‑in y opt‑out | RF‑H09, RF‑H10 | Opt‑out detiene envíos proactivos de inmediato; mensaje proactivo sin plantilla es rechazado | pendiente |
| 4.6 | Agente conversacional y herramientas | RF‑H01, RF‑H02 | Cada herramienta de datos exige permiso; argumentos incompletos se deniegan y derivan; handoff no exige permiso | hecho: las ocho herramientas rechazan argumentos incompletos con auditoría y derivación obligatoria; las siete herramientas de datos rechazan al principal sin permisos antes de ejecutar. Pruebas de integración en `test_herramientas_agente.py::TestDespachador`, junto a las pruebas existentes del ciclo de agenda y handoff. |
| 4.7 | transferencia a humano | RF‑H08 | La conversación pasa a `EN_ESPERA_HUMANO` y aparece en la bandeja | pendiente |
| 4.8 | Recordatorios de cita | RF‑K01…RF‑K05 | Programación, reprogramación y cancelación de recordatorios verificadas con reloj rijo | pendiente |
| 4.9 | **Notificaciones sin datos clínicos** | RF‑K07 | Prueba que recorre todas las plantillas y falla si alguna incluye diagnóstico o medicamento | pendiente |
| 4.10 | OAuth de calendario y cifrado de tokens | RF‑D04, RF‑D05, RF‑I01 | Token nunca en claro en la base; prueba de cifrado y descifrado | pendiente |
| 4.11 | Sincronización de eventos | RF‑I04, RF‑I05 | Alta, cambio y baja reflejados; relación de identificadores conservada | pendiente |
| 4.12 | Reconciliación y conflictos | RF‑I06 | Evento borrado o movido externamente se detecta y genera alerta sin perder la cita | pendiente |
| 4.13 | **Resiliencia del calendario** | RF‑I08 | Con el proveedor caído, la cita se confirma y el evento se entrega al recuperarse | pendiente |

## Fase 5 — Lista de espera

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 5.1 | Registro y Preferencias | RF‑J01 | Preferencias respetadas en la selección de candidatos | hecho: interfaz y API guardan profesional, intervalo de fechas, días, franja horaria local y antelación; integración y E2E verifican persistencia y filtrado de turnos |
| 5.2 | Turno liberado transaccional | RF‑J02 | La cancelación y el turno liberado se confirman juntos o no se confirman | hecho: transacción y rollback inducido verificados contra la restricción EXCLUDE real de PostgreSQL; ante la carrera, la cita nueva no se crea y la Oferta continúa activa |
| 5.3 | Selección de candidatos | RF‑J03 | Prueba con casos que deben y no deben coincidir | hecho: pruebas de sede, servicio, profesional, prioridad, antelación y disponibilidad en `test_lista_espera.py` |
| 5.4 | **Oferta única por turno** | RF‑J04 | El índice único parcial impide dos ofertas activas; prueba de concurrencia | hecho: índice parcial más prueba concurrente de duplicado en `test_oferta_concurrente.py` |
| 5.5 | Contenido y plazo de la Oferta | RF‑J05 | La Oferta incluye todos los campos exigidos y su tiempo límite | hecho en outbox: plantilla sin datos clínicos, consentimiento y plazo probados; entrega real a WhatsApp sigue fuera del entorno local |
| 5.6 | Expiración y siguiente candidato | RF‑J06 | Tras expirar, se ofrece al siguiente; prueba con reloj rijo | hecho: expiración, nuevo candidato y reintento sin duplicar están probados en `test_tareas_lista_espera.py` |
| 5.7 | Aceptación y reagendamiento | RF‑J07 | Se crea la cita nueva y se libera la anterior en una transacción | hecho: cita anterior opcional validada para paciente, clínica, sede y servicio; la aceptación crea la nueva y cancela la previa atómicamente; integración, API y E2E cubren aceptación y turno ocupado |
| 5.8 | Cadena de liberaciones | RF‑J08 | El turno liberado por un reagendamiento genera una nueva Oferta; con límite de profundidad | hecho: el horario anterior se ofrece al siguiente paciente, con profundidad máxima de cinco liberaciones; integración y E2E verifican la cadena |
| 5.9 | **Aceptación simultánea** | RF‑J09 | 2 y 10 aceptaciones concurrentes producen 1 ganador; el resto recibe mensaje adecuado | hecho: diez sesiones y solicitudes HTTP concurrentes producen una cita (200) y nueve respuestas 409; las ofertas perdedoras vuelven a la cola. Probado contra PostgreSQL real |

## Fase 6 — Conocimiento y RAG

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 6.1 | Tablas de conocimiento y pgvector | RF‑N01, RF‑N02 | Migración con índice HNSW y GIN; prueba de integración | hecho: documentos, versiones inmutables, trabajos, fragmentos, embeddings y ACL; búsqueda textual GIN y vectorial HNSW verificados contra PostgreSQL. |
| 6.2 | Carga de documentos y validación de archivos | RF‑M01, RF‑E08 | Tipo real Verificado por contenido; tamaño limitado; prueba de archivo malicioso | parcial: endpoint multipart extrae PDF con límite configurable de bytes, 200 páginas y 500 000 caracteres; rechaza acciones activas, cifrado, falsos PDF y documentos sin texto; ingiere solo el texto y audita el tipo, sin guardar el binario. ClamAV es obligatorio en producción; desarrollo registra `NO_DISPONIBLE`. Ver `test_conocimiento_archivos.py` (10 pruebas) y pruebas API PDF (2). Falta verificar escaneo real con ClamAV y OCR para PDF escaneados. |
| 6.3 | Versionado y flujo de aprobación | RF‑M02…RF‑M04 | Transiciones de estado con permisos separados de carga y aprobación | hecho: versionado, aprobación humana, revisión de riesgo, publicación, retirada para corregir y archivado terminal; permisos de carga/aprobación separados y auditados. |
| 6.4 | Ingesta, fragmentación y embeddings | — | Trabajo reanudable; reinicio a media ingesta no duplica fragmentos | hecho: `20261006_027` guarda de forma durable la fuente y el trabajo antes de vectorizar; el worker recoge cada minuto hasta 10 trabajos pendientes con `FOR UPDATE SKIP LOCKED`, y el indexado transaccional es idempotente. La prueba fuerza estado pendiente, verifica recuperación, borrado de la fuente al completar y ausencia de duplicados en el siguiente barrido. Un rallo controlado del proveedor queda `FALLIDA` y requiere reenviar el contenido después de corregir la configuración. La recuperación por versión vigente está en `20261006_026`. |
| 6.5 | Búsqueda híbrida con pre‑filtro | RF‑N03, RF‑N04, RF‑O02 | Los filtros están en el `WHERE`; prueba de arquitectura que impide otras consultas a las tablas | hecho: ramas vectorial y textual comparten filtros SQL de clínica, sede, especialidad, vigencia, sensibilidad, estado y ACL; prueba AST permite una sola puerta de lectura. |
| 6.6 | **Cero rugas** | RF‑O08 | Pruebas negativas: otra sede, otra especialidad, otro paciente, archivado y vencido nunca se recuperan | hecho: pruebas negativas por clínica, sede, especialidad, ámbito vacío, sensibilidad, estado, vigencia y ACL; contenido y metadatos se filtran juntos. |
| 6.7 | Flujo RAG con exigencia de fuente | RF‑O04, RF‑O06 | Sin fuente sobre el umbral, responde que no tiene información aprobada y ofrece derivación | hecho: el recuperador descarta resultados debajo del umbral y devuelve `MENSAJE_SIN_FUENTE`; evaluación incluye consultas negativas. |
| 6.8 | **Defensa anti inyección de prompt** | RF‑O07 | Corpus malicioso: ninguna invocación de herramienta ni cambio de ámbito; prueba bloqueante | hecho: el modelo carece de escritura directa; herramientas usan permisos del solicitante. Contenido se delimita, analiza y riesgo alto exige revisión humana antes de aprobar; suite de saneamiento y arquitectura. |
| 6.9 | Detección en la ingesta | — | Texto oculto y patrones de inyección marcan el documento para revisión | parcial: la extracción PDF se hace en servidor y el texto pasa por el análisis de inyección existente; riesgo alto bloquea aprobación hasta revisión. Detección de texto visualmente oculto en el PDF (capas/posición) continúa pendiente. |
| 6.10 | Arnés de evaluación | RF‑O08 | Informe con Hit@K, precisión, fundamentación y tasa sin fuente, publicado en `rag.md` | hecho para embeddings simulados: Hit@1/3/5, recuperación mínima/media/máxima y consulta sin documentación; evaluar con el modelo real sigue pendiente. |
| 6.11 | SSRF en ingesta por URL | — | Destinos privados y metadatos de nube bloqueados; prueba dedicada | pendiente |

## Fase 7 — Historia clínica y medicamentos

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 7.1 | Notas versionadas | RF‑F01…RF‑F03 | Editar crea versión; motivo obligatorio; sin `UPDATE` ni `DELETE`; prueba de privilegios | hecho: corrección crea una rila nueva, requiere motivo y conserva la versión anterior; restricciones e inmutabilidad se comprueban en PostgreSQL. API e integración: `TestCorreccion`, `TestVersionado` y `test_historia_clinica.py::TestNotas`. |
| 7.2 | Control de acceso clínico | RF‑F06, RF‑B06 | Recepción recibe 404; profesional sin relación asistencial recibe 404 | hecho: las consultas a notas y al resumen clínico responden 404 indistinguible ante paciente inexistente, fuera de ámbito, rol sin permiso clínico o profesional sin relación vigente; la denegación por falta de permiso queda auditada. El acceso temporal sigue disponible con motivo, caducidad y aviso administrativo, y la interfaz usa texto genérico sin confirmar la causa. API de notas, resumen e integración de servicio actualizadas. |
| 7.3 | Nivel de sensibilidad | RF‑F07 | N3 exige permiso adicional; acceso registrado de forma reforzada | parcial: antecedentes, versiones de notas, recetas, imágenes clínicas, odontogramas y planes dentales admiten N2/N3; los procedimientos heredan la clasificación del plan. Crear y leer N3 requiere `historia_clinica.leer_sensible`; listados, detalle, historial, resumen e indicadores filtran N3 en SQL. El odontograma conserva N3 en versiones manuales y hallazgos de procedimientos; un plan y sus procedimientos quedan N3 desde su creación. También se bloquean fotos asociadas y avisos automáticos por fases para esos planes; no se exporta el contenido al redactor. La auditoría registra el nivel en alta, lectura, transición y acceso a recursos vinculados, también cuando N3 queda filtrado. Migraciones `20261006_022` a `20261006_025`; pruebas API cubren permisos, filtros y auditoría. El índice de placa y otros registros aún no tienen sensibilidad configurable por registro. |
| 7.4 | Acceso de emergencia | RF‑B07 | Exige motivo, caduca, se audita y notifica | hecho: un profesional activo puede solicitarlo desde Historia con un motivo mínimo de 12 caracteres; la relación expira a los 30 minutos y se confirma en auditoría. Se crea una notificación administrativa sin datos del paciente ni motivo, visible en la campana y en Seguridad clínica; su revisión queda auditada. API: `test_acceso_emergencia_es_temporal_auditado_y_notifica_sin_datos_del_paciente`; migración `20261006_012`. |
| 7.5 | Recetas versionadas | RF‑L01 | Versión inmutable con motivo de cambio | hecho: `POST /historia/recetas/{id}/versiones` enlaza la receta anterior, conserva su contenido, exige motivo y firma profesional; los disparadores y restricciones de PostgreSQL (migraciones `008`/`009`) protegen líneas, contenido, transiciones de estado y firma. API: `test_versionar_conserva_historial_y_reemplaza_solo_tomas_futuras`; integración: `TestRecetaConfirmada` comprueba reescritura, borrado, reapertura, firma anticipada y campos de suspensión |
| 7.6 | **Solo receta confirmada genera tomas** | RF‑L02 | Un borrador no genera ninguna toma; prueba dedicada | hecho: el `CHECK`/disparador de PostgreSQL y las pruebas de integración rechazan insertar tomas desde borradores; las pruebas API confirman que solo la confirmación crea el calendario (`test_historia_clinica.py::TestRecetaConfirmada`, `test_historia_api.py`) |
| 7.7 | Cálculo del calendario de tomas | RF‑L03 | Pruebas de cada tipo de frecuencia, con inicio, rin y zona horaria | hecho: seis casos de integración verifican frecuencias de 6, 8, 12, 24 y 168 horas; conversión de 10:30 en America/Guayaquil a UTC; duración de la pauta y paso al día siguiente si la hora indicada ya ocurrió. El archivo completo de servicio clínico pasa 41 pruebas contra PostgreSQL. |
| 7.8 | **PRN sin horarios automáticos** | RF‑L08 | `CHECK` en base de datos y prueba que intenta violarlo | hecho: restricciones PostgreSQL impiden frecuencia rija en PRN y tomas programadas; servicio los omite al generar calendario; integración/API verifican los rechazos (`test_historia_clinica.py::TestMedicamentoPRN`, `test_historia_api.py`) |
| 7.9 | Recordatorios de toma y respuestas | RF‑L04, RF‑L05 | Las cinco respuestas registradas; «recordarme después» reprograma | hecho en el flujo local: `TOMADA` registra la dosis pendiente; `RECORDARME DESPUÉS` crea un recordatorio a 30 minutos sin cambiar la hora prescrita; `NO PUDE TOMARLA` registra omisión y deriva al equipo; `AYUDA` deriva a una persona; las fases explícitas de problema crean revisión clínica y derivación. Solo se ejecuta con paciente inequívoco y una toma dentro de ventana; las acciones quedan auditadas. Pruebas unitarias, API e integración aprobadas. El outbox queda persistido; envío real requiere configurar y validar Meta y su plantilla aprobada. |
| 7.10 | Alertas de adherencia y seguimiento | RF‑L06 | Alertas por omisiones autorizadas y atendibles; control posterior de procedimientos con fecha elegida por el profesional, cierre auditado y recorrido E2E | parcial: alertas por omisiones y control posterior del procedimiento están implementados. Siete fases explícitas de problema con tratamiento se etiquetan `PROBLEMA_TRATAMIENTO`, crean un aviso persistente en la misma transacción del mensaje y llegan a la bandeja clínica sin resolver la identidad del número. El equipo con permisos puede confirmar la revisión; creación, lectura y confirmación quedan auditadas. Migraciones `20261006_010` y `20261006_011`. Siguen pendientes cobertura de expresiones libres y reglas de prioridad/escalado; confirmar revisión no clasifica gravedad ni confirma un resultado clínico. |
| 7.11 | **Cambio de receta cancela recordatorios futuros** | RF‑L09 | Suspender una receta cancela tomas y avisos futuros pendientes y conserva los registros pasados; una modificación versionada deberá aplicar la misma regla | hecho: la sustitución atómica cancela las tomas futuras pendientes y los recordatorios anteriores, conserva las tomas vencidas, firma la pauta nueva y genera sus tomas/avisos; API verifica estados y auditoría en `test_historia_api.py::TestRecetas::test_versionar_conserva_historial_y_reemplaza_solo_tomas_futuras` |
| 7.12 | **Límite clínico de la IA** | RF‑L07 | Pruebas de arquitectura: no hay herramientas para escribir contenido clínico; mensajes clínicos del webhook se derivan sin interpretarlos | hecho: catálogo cerrado de ocho herramientas, sin receta/dosis/diagnóstico ni escritura en tablas clínicas; `test_arquitectura_agente.py` prueba esas propiedades. Las pruebas de límites cubren mensajes de paciente y el webhook verifica que una consulta sobre síntomas pasa a revisión humana (`test_limites_agente.py` y `test_webhook_whatsapp_api.py`; 82 pruebas unitarias y 35 pruebas API del webhook aprobadas el 2026‑10‑06). |
| 7.13 | Registro de alergias y antecedentes | RF‑E09 | Solo profesional con permiso y relación asistencial puede registrar; rechazar alergia activa duplicada, conservar motivo al desactivarla y auditar sin copiar texto clínico a metadatos | hecho: formularios en el resumen clínico para alergias y antecedentes; categorías y severidad validadas; API aplica clínica, ámbito y relación. 5 pruebas API cubren rechazo sin relación, alta, duplicados, reflejo en resumen, desactivación y trazabilidad sin contenido clínico en metadatos; componente cubierto en la suite frontend. |
| 7.14 | Diseñador configurable de anamnesis | RF‑F | Administrador configura y versiona preguntas por clínica; profesional captura respuestas versionadas solo con relación asistencial; N3 refuerza permiso/auditoría; respuestas no se sobrescriben | hecho: tipos de pregunta validados, borrador/publicación/versionado, congelación en PostgreSQL, respuestas append-only, ámbito y permiso N3. Migraciones `018`/`019`; 3 pruebas API y componentes de configuración/captura; suite frontend 415/415. |
| 7.15 | Formulario MSP 033/2021 y PDF clínico trazable | RF‑F | Usar SNS‑MSP/HCU‑form.033/2021, contrastado con el anexo matriz; capturar secciones A–P sin duplicar datos maestros; previsualizar e imprimir A4 a doble cara por paciente/atención con autor, fecha, versión, control de acceso y auditoría de exportación; no afirmar validez jurídica antes de revisión competente | parcial: API y pantalla capturan y versionan A–P, muestran historial, y enlazan paciente, sede y profesional con relación asistencial, auditoría y permiso sensible N3. La identidad se resuelve desde el expediente autorizado; no es editable en el navegador. La captura se presenta en una ventana Liquid Glass de alto completo con pie fijo; Vitest prueba su apertura, envío asociado, errores y permanencia del diálogo; el E2E con axe, Escape y viewports 390/320 px pasó en la suite actual de 62 escenarios. El personal puede asociar cita, nota, odontograma e índice de placa desde la interfaz; las consultas respetan permisos y módulo, las citas se limitan al profesional actual y se excluyen canceladas/no asistidas, y el registro conserva las fuentes. La nota solo prellena motivo y relato subjetivo bajo acción explícita y en campos vacíos; odontograma y placa quedan como referencias sin conversión automática. La copia clínica imprimible tiene vista A4 de dos páginas con identidad congelada, secciones registradas, autor, fecha, versión y fuentes; el servidor vuelve a autorizar y audita la versión N3 solicitada antes de mostrarla. El navegador permite imprimir o guardar PDF; el personal elige doble cara en su diálogo de impresión. Pendientes: cotejo del diseño contra el anexo matriz y revisión institucional antes de afirmar validez jurídica. SERCOP corrobora el código y la impresión, pero las copias públicas no sustituyen el anexo. La higiene oral simplificada es distinta del índice O'Leary; ver `docs/formulario-033-fuentes.md`. |

## Fase 8 — Dashboard y predicciones

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 8.1 | Agregados diarios y cohortes de registro | RF‑Q02, RF‑Q04 | Métricas de agenda, altas registradas, pacientes nuevos/recurrentes, cohortes, demografía agregada y retorno operativo verificadas contra valores conocidos | parcial: nuevo/recurrente se define por la primera atención completada. Las altas administrativas activas se agrupan por mes y se cuentan con/sin cita bajo filtros y ámbitos actuales; no devuelven identidades y se ocultan al filtrar por estado. La demografía separa rangos de edad y sexo registrado para pacientes activos con citas visibles; edad al cierre local del rango, sin fecha de nacimiento ni valores exactos. Celdas de 1–4 y una celda complementaria se suprimen; poblaciones menores de 5 no muestran desglose. El retorno a 30 días usa la primera atención completada de la cohorte, 720 horas de observación y otra cita completada; protege grupos pequeños y no etiqueta pacientes perdidos. `test_dashboard_retorno_30_dias_solo_usa_cohortes_maduras_y_completadas` y seis casos unitarios prueban fórmula, ventana y supresión; el panel lo presenta en Liquid Glass. Siguen pendientes la definición validada de “paciente perdido” de la referencia y los tratamientos populares. |
| 8.2 | Endpoints con filtros y ámbito | RF‑Q01 | Filtros de fecha, sede, especialidad, profesional, servicio y estado aplicados sobre el ámbito autorizado; un profesional solo ve sus propias métricas | hecho: rango inclusivo de hasta 366 días y filtros aplicados en resumen, espera y análisis local; la IA opcional recibe los mismos filtros. `test_dashboard_aplica_filtros_de_especialidad_servicio_y_estado` contrasta dos profesionales y confirma la intersección sede/profesional/especialidad/servicio/estado, incluida una sede fuera del ámbito. `test_dashboard_profesional_usa_su_ambito_sin_filtro_explicito` inicia sesión como profesional y verifica que solo obtiene su cita aun sin mandar `profesional_id`; al pedir otro profesional recibe cero. `test_dashboard_analisis_ia_aplica_filtros_y_ambito` simula Anthropic en memoria y prueba que el agregado cambia de 1 a 2 citas al retirar el filtro de profesional y queda en cero para una sede no autorizada, sin llamada externa. La interfaz convierte fechas a UTC según clínica/sede y ofrece catálogos autorizados; componente verifica Guayaquil, Pacific/Kiritimati, análisis local y rango inválido. |
| 8.3 | Visualizaciones | RF‑Q | Gráficos accesibles, con estados de carga, error y vacío | hecho: tendencias por día, día de semana y hora usan encabezados y listas con fecha/etiqueta y valor textual; las barras son decorativas para lectores de pantalla. Carga anuncia estado, error limpia cifras obsoletas y cada tendencia muestra vacío cuando no hay datos. Pruebas de componente para los tres estados |
| 8.4 | Registro de modelos | RF‑R06 | Modelo, versión, variables, confianza y explicación persistidos | pendiente |
| 8.5 | Modelos de referencia | RF‑R01…RF‑R05 | Modelo base entrenado sobre datos sintéticos, con métricas reportadas honestamente | pendiente |
| 8.6 | **Límites de las predicciones** | RF‑R07 | Prueba de arquitectura: ninguna predicción puede modificar citas, recetas ni accesos | pendiente |
| 8.7 | Exportación del resumen de agenda | `reporte.exportar`, RF‑Q | CSV agregado por fecha local y estado; filtros de sede/profesional/servicio; permiso de agenda y exportación; ámbito en SQL; auditoría y sin identidad de pacientes. Verificado con `TestExportarResumen` (3 pruebas), matriz de roles, compilación frontend y suite E2E vigente 62/62. | hecho |
| 8.8 | Tendencias de agenda por fecha y horario local | RF‑Q | Conteos agregados por día, hora y día de semana según la zona de cada sede; visualización accesible sin datos de pacientes | hecho: API deriva el huso desde sede/clínica; prueba con `Pacific/Kiritimati`; barras etiquetadas y estado vacío en el panel; dashboard focalizado 5/5 |
| 8.9 | Resumen operativo disponible sin proveedor de IA | RF‑Q, RF‑Q01 | Lectura clara de citas, inasistencias, espera y pagos autorizados; sin datos personales ni llamadas externas | hecho: `POST /dashboard/analisis-local` genera hasta cuatro hallazgos deterministas bajo el ámbito del dashboard y solo incluye importes cuando está concedido `pago.leer`; panel ofrece resumen local y mantiene Anthropic como acción opcional. Pruebas unitarias, API y componente |
| 8.10 | Recuperación de turnos de lista de espera | RF‑Q03 | Cuenta cancelaciones, aceptaciones de ofertas sobre las citas liberadas y demora media entre cancelación y aceptación; misma autorización y filtros de sede/profesional/especialidad/servicio | hecho: cohortes por instante del evento (cancelación u Oferta aceptada), filtros del turno liberado y ámbito de agenda. Se oculta con filtro de estado. Incluida en panel, resumen local y agregado para IA opcional; pruebas API/UI/local |
| 8.11 | Registro agregado de adherencia | RF‑Q06 | Tomas registradas, omitidas, porcentaje de registros positivos y alertas abiertas; permiso clínico independiente, ámbito de historia y sin datos identificables | hecho: el dashboard agrega solo estados y conteos, exclusivamente con `adherencia.leer`; las alertas reflejan pendientes actuales y las dosis el periodo seleccionado. Sede/servicio limitan a recetas vinculadas a una cita; sin datos clínicos identificables y excluido del envío opcional a IA. API prueba permiso, agregación y filtro por estado; panel y resumen local cubiertos |
| 8.12 | Ocupación de agenda | RF‑Q04 | Reservas activas frente a minutos configurados disponibles; restar pausas, feriados y bloqueos; no duplicar horario solapado del mismo profesional | hecho: minutos se calculan en la zona de cada sede desde plantilla profesional o horario de sede. Se oculta con filtro de estado o ámbito parcial de pacientes. API PostgreSQL comprueba 210 minutos disponibles, 45 ocupados y 21,4 %; dos pruebas unitarias y una de componente cubren intervalos y presentación accesible. |

## Fase 9 — Pagos

| # | Tarea | Requisitos | Criterio de aceptación | Estado |
|---|---|---|---|---|
| 9.1 | Máquina de estados de pago | RF‑P02 | Transiciones inválidas rechazadas; prueba exhaustiva | hecho: transiciones permitidas fijadas para los seis estados y comparación exhaustiva de la matriz; la API también prueba un ciclo válido y rechaza retrocesos (`pruebas/unitarias/test_pagos_reglas.py`, `test_demo_operativa.py::test_pago_ciclo_e_idempotencia`) |
| 9.2 | Comprobantes | RF‑P01 | Validación de archivo y análisis antivirus | hecho: acepta PDF/JPEG/PNG/WebP por firma real; limita tamaño, valida PDFs y rechaza JavaScript/acciones activas; ejecuta ClamAV si está configurado y falla cerrado en producción si falta. Guarda cifrado, audita carga/lectura, limita descargas al ámbito del pago y hace metadatos append‑only. En desarrollo marca `NO_DISPONIBLE` cuando no hay antivirus. Pruebas de PDF activo y recorrido API con aislamiento por sede. |
| 9.3 | Validación manual | RF‑P03 | Registro de validador, fecha y comentarios | hecho: el ciclo API comprueba actor y fecha; cada comentario se conserva en el evento inmutable y se muestra en Pagos |
| 9.4 | **Sin datos financieros sensibles** | RF‑P04 | Prueba que inspecciona el esquema y falla si aparece una columna de tarjeta, clave u OTP | hecho: prueba de esquema comprueba la ausencia de PAN/tarjeta, CVV/CVC, OTP, clave, password, token y credenciales financieras |
| 9.5 | Auditoría de pagos | RF‑P05 | Historial append‑only | hecho: migración `20261006_013` crea y rellena el historial; `20261006_014` agrega secuencia única estable; un trigger rechaza `UPDATE` y `DELETE`. API de lectura filtrada por ámbito y panel para lectura/revisión; test verifica idempotencia, orden, actor, comentarios e inmutabilidad |
| 9.6 | Vencimiento y cartera vencida por cita | RF‑P01, RF‑Q05 | Fijar fecha explícita una sola vez, mostrar y filtrar saldos vencidos según zona local de sede y dejar de marcarlos al liquidarse | hecho: migración `20261006_017`; fecha auditable con permiso de validación, saldos históricos sin fechas inferidas y filtro API/interfaz. 34 pruebas API de pagos/operación; suite frontend actual 385/385. Presupuestos formales y recordatorios automáticos siguen pendientes. |
| 9.7 | Aviso interno de cartera vencida | RF‑P01, RF‑Q05 | Quien tenga `pago.leer` ve el recuento de cargos vencidos desde la campana, filtrado por el ámbito del backend y enlazado a Pagos | hecho: cuenta cargos con saldo vencido al cargar la sesión y refresca al abrir la campana; oculta y limpia el dato sin permiso. Pruebas de servicio y componente. No envía mensajes a pacientes. |
| 9.8 | Presupuesto imprimible desde plan dental | RF‑P01 | El plan propuesto/aceptado genera una vista con clínica, paciente, referencia estable, procedimientos e importes, imprimible o guardable como PDF sin exponer datos fiscales | hecho: usa el plan persistido; fecha por zona de clínica y datos del paciente ya cargado. No inventa vigencia, impuestos ni condiciones. 29 pruebas API del catálogo y prueba de componente; lint y compilación frontend. |
| 9.10 | Libro de gastos y flujo de caja | RF‑P06, RF‑Q05 | Registrar egresos por sede o de toda la clínica, anularlos con motivo sin borrarlos y calcular el resultado de caja del periodo (pagos confirmados − gastos vigentes) sin presentarlo como contabilidad | hecho (2026‑10‑07): migración `20261007_029` con disparador de solo anulación; permisos `gasto.leer`/`gasto.registrar`; alta idempotente, ámbito por sede en SQL, flujo por día y categoría ([ADR‑0021](decisiones/0021-libro-de-gastos-y-flujo-de-caja.md)). 12 pruebas API (autorización, IDOR, idempotencia, entrada inválida, anulación única, disparador SQL, flujo) y 5 de componente. Pendientes: adjuntos de comprobante, cuentas por pagar, conciliación bancaria y exportación contable. |
| 9.9 | Resumen financiero CSV | RF‑P06, `pago.leer`, `reporte.exportar` | Exporta conteos e importes agrupados por fecha local, estado y método; filtra por sede; la consulta aplica el ámbito del servidor, no incluye pacientes y audita la exportación | hecho: API agrupa según la zona horaria de la sede, limita periodos a 366 días y responde CSV sin datos identificables; pantalla Pagos ofrece descarga desde/hasta. 9 pruebas API de pagos pasan, incluidas agregación, fecha local, aislamiento de sede y rango inválido; 2 pruebas de componente cubren acceso y descarga. |

## Fase 10 — Preparación de producción

| # | Tarea | Criterio de aceptación | Estado |
|---|---|---|---|
| 10.1 | SAST y análisis de dependencias | Sin hallazgos críticos o altos sin justificación y plan | pendiente |
| 10.2 | DAST sobre la instancia en ejecución | Informe con hallazgos y correcciones | pendiente |
| 10.3 | Escaneo de contenedores | Imágenes sin vulnerabilidad crítica | pendiente |
| 10.4 | Detección de secretos en todo el historial | `gitleaks` limpio | hecho: historial completo sin hallazgos tras revisar valores sintéticos de pruebas y dejar exclusiones por huella con motivo en `.gitleaksignore`; la ejecución desde la raíz del repositorio pasa. |
| 10.5 | Pruebas de carga | Objetivos de RNF‑01…RNF‑04 medidos y publicados | pendiente |
| 10.6 | Pruebas de recuperación | Caída de Redis, PostgreSQL, worker, WhatsApp, calendario y LLM sin pérdida de datos | pendiente |
| 10.7 | **Respaldo y restauración verificada** | Restauración real en una instancia limpia, con recuento de filas comparado | hecho: ciclo ejecutado contra PostgreSQL local con base desechable; 11 comprobaciones, recuentos coincidentes, cifrado, clave incorrecta, pgvector/HNSW y restricciones de exclusión. Evidencia detallada en `docs/backup-and-restore.md`; programación, retención y recuperación a un punto en el tiempo siguen abiertas. |
| 10.8 | Procedimiento de rollback probado | Rollback de versión y de migración ejecutados en preproducción | pendiente |
| 10.9 | Monitoreo y alertas | Métricas, paneles y alertas activas con umbrales definidos | en curso: `/metrics`, recolector Prometheus local (retención 15 días) y cuatro reglas quedaron probados con el objetivo Windows/WSL en `UP`; falta Alertmanager, destinatarios, guardia, señales de auditoría/Redis y despliegue de producción |
| 10.10 | Pruebas de aceptación con escenarios de clínica | Los 21 escenarios de extremo a extremo en verde | pendiente |
| 10.11 | Informe final de riesgos | Riesgos residuales, limitaciones y pendientes legales | pendiente |
| 10.12 | Cuenta PostgreSQL de mínimo privilegio | El runtime no es dueño del esquema ni puede ejecutar DDL; la app no puede modificar/eliminar auditoría ni desactivar sus disparadores | pendiente: la configuración local comparte propietario de esquema y usuario de aplicación. Los disparadores bloquean `UPDATE`, `DELETE` y `TRUNCATE`; falta separar credenciales/roles en despliegue y probar los privilegios efectivos del usuario runtime. |

## Fase 11 — Ayuda y documentación para usuarios

| # | Tarea | Criterio de aceptación | Estado |
|---|---|---|---|
| 11.1 | Centro de ayuda con manuales únicos por rol | Al cerrar los flujos de producto, una pestaña visible de Ayuda/Documentación ofrece una guía independiente para cada rol del sistema (`superadministrador`, `administrador_clinica`, `recepcion`, `asistente`, `auditor`, `profesional`) y para cada rol personalizado configurado por una clínica. Cada manual explica tareas, rutas, permisos, límites y pasos de ese rol; no se reutiliza ni se repite el contenido de un manual genérico entre roles. La selección respeta la sesión y el manual nunca describe acciones o datos que el rol no pueda usar. | hecho (2026‑10‑07): `GET /api/v1/ayuda/manuales` devuelve un manual por rol vigente de la sesión; seis manuales escritos para los roles del sistema y uno compuesto con los permisos reales de cada rol propio. Cada sección exige los permisos que describe, cruzados con los efectivos de la sesión. Pruebas: unicidad de títulos y pasos entre todos los manuales, alcanzabilidad de cada sección con los permisos del rol, rutas citadas existentes en `app.routes.ts`, roles administrativos sin secciones clínicas, roles propios, 2FA y agente (26 unitarias); 7 de API (401, sistema, propio que sigue a sus permisos en vivo, rol de otra clínica, parámetros ignorados); 5 de componente. Pantalla `/ayuda` con pestañas por rol y búsqueda. Mantener `manuales.py` cuando cambie una pantalla. |

---

## Dependencias externas

| Dependencia | Necesaria para | Estado | Bloquea |
|---|---|---|---|
| **Cuenta de WhatsApp Business + número Verificado** | Envío y recepción reales | **Ausente** | Verificación real de la Fase 4. El desarrollo continúa con sandbox |
| **Plantillas aprobadas por Meta** | Mensajes proactivos | **Ausente** | Recordatorios reales. La aprobación de plantillas tarda días y la decide Meta |
| **Proyecto de Google Cloud con OAuth configurado** | Sincronización de calendarios | **Ausente** | Verificación real de la Fase 4 |
| **Pantalla de consentimiento de Google verificada** | Uso fuera de modo de prueba | **Ausente** | Producción. La Verificación de Google puede tardar semanas |
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
3. ⚠ **¿Qué nivel de Verificación exige la clínica para entregar información clínica por
   WhatsApp?** Decisión provisional, la más restrictiva: el teléfono nunca basta; se exige
   Verificación por documento. Solo la clínica puede relajarlo, y hacerlo tiene
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
| M‑01 | Evaluar la actualización a la última versión mayor de Angular | ADR‑0005; realizado: Angular 22.2.1 migrado por los esquemas oficiales el 2026‑10‑07 |
| M‑02 | Migrar las pruebas de componentes a Vitest cuando el constructor lo soporte de forma estable | ADR‑0006; realizado: 443/443 pruebas y cobertura CI en Vitest el 2026‑10‑07 |
| M‑03 | Reevaluar el proveedor de embeddings si la evaluación de RAG no alcanza el umbral | ADR‑0007 |
| M‑04 | Revisar trimestralmente cuentas, roles y ámbitos | `security.md` |
| M‑05 | Rotar los secretos según el procedimiento documentado | `security.md` |
