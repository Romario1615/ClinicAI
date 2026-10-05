# ClinicAI — Plataforma de gestión clínica

Sistema de gestión clínica multi‑sede con agenda, agente de WhatsApp, sincronización de
calendarios, lista de espera inteligente, historia clínica versionada, recetas con
seguimiento de adherencia, base de conocimiento con RAG, pagos asistidos, dashboard y
auditoría.

> **Estado actual:** las fases 0 y 0b están documentadas; las fases funcionales 1 a 9 siguen en desarrollo y verificación. La lista de espera permite reagendar, encadenar turnos con un límite y resolver aceptaciones concurrentes; rollback y diez respuestas HTTP simultáneas ya están probados contra PostgreSQL. La fase 10 de preparación para producción no está cerrada.
>
> **Nota de vigencia (2026-10-05):** las fases describen el alcance funcional local; no equivalen a preparación de producción. Esta revisión completó el reagendamiento desde la lista de espera y la cadena de turnos liberados, limitada y probada con diez aceptaciones simultáneas.
>
> Implementado y verificado, con evidencia de ejecución real: infraestructura local
> (PostgreSQL 16 + pgvector 0.8.6, Redis), migraciones reversibles, autenticación y RBAC
> con ámbito de cuatro dimensiones, la **protección anti doble‑reserva en el motor de base
> de datos** —comprobada con 50 participantes simultáneos—, historia clínica append‑only,
> recetas con calendario de tomas, lista de espera, el **outbox de entrega con el webhook
> de WhatsApp**, la **sincronización de calendarios con reconciliación de cambios
> externos**, la base de conocimiento con RAG que **sabe decir que no sabe**, la **capa de
> herramientas del agente** con su frontera clínica, pagos administrativos, dashboard, y la
> **restauración de respaldos verificada de extremo a extremo**.
>
> La API expone más de 60 rutas HTTP y Angular define 17 rutas de pantalla. El mapa funcional
> de abajo distingue los módulos conectados de los flujos sintéticos.
>
> La suite backend completa del 2026‑10‑05 aprobó **1510 pruebas y omitió 3** integraciones
> opcionales de LLM. La validación del 2026‑10‑05 aprobó **256 casos frontend**, **34 escenarios
> E2E** contra navegador, API y PostgreSQL, y 55 pruebas focalizadas de lista de espera. Carga: 2 314 peticiones con **0 reservas duplicadas** bajo
> contienda, y la **restauración de respaldos verificada** con 11 comprobaciones.
>
> La cobertura frontend también supera sus umbrales: líneas 87,99 % (80 % requerido) y ramas
> 74,24 % (70 % requerido); `npm run test:ci` termina correctamente.
>
> **Lo que no está verificado, dicho sin rodeos:** ni un mensaje ha salido hacia Meta ni un
> evento hacia Google —no hay credenciales y no se inventan—, no existe el adaptador real
> de Google Calendar, la última suite omitió las tres pruebas que llaman a un modelo externo,
> así que esta ejecución no verificó esa integración; el webhook de WhatsApp aún no invoca
> el circuito del agente. **Nada vigila** los eventos que el sistema emite, el procedimiento
> de incidentes **no se ha ensayado**, la
> carga se midió en un portátil y no dice nada de producción, y **no hay validación
> jurídica**.
>
> El estado real frente a los criterios de producción está en
> [`docs/production-readiness.md`](docs/production-readiness.md), y los riesgos residuales
> en [`docs/known-limitations.md`](docs/known-limitations.md).
> Este sistema **no está aprobado para uso con datos de pacientes reales**.

---

## Aviso de seguridad y alcance

* **Nunca** se usan datos reales de pacientes en desarrollo, pruebas o demostraciones.
  Todo dato de trabajo es sintético, generado con Faker en español.
* La información clínica se trata como información altamente sensible.
* El cumplimiento legal (LOPDP del Ecuador y normativa sanitaria) **no está validado**.
  Los puntos que requieren revisión de un profesional jurídico están listados en
  [`docs/security.md`](docs/security.md).
* La IA **no puede** modificar la base de datos por sí misma, ni crear o cambiar
  recetas, dosis o tratamientos. La frontera está en
  [`CLAUDE.md`](CLAUDE.md) (reglas 4 y 5) y en
  [`docs/decisiones/0017-frontera-de-la-automatizacion-entrante.md`](docs/decisiones/0017-frontera-de-la-automatizacion-entrante.md).
* Un teléfono **no identifica a una persona**. Cuando un número corresponde a varios
  pacientes, el sistema ofrece la lista y espera a que quien escribe elija; elegir
  desambigua pero **no verifica identidad**
  ([ADR‑0020](docs/decisiones/0020-identidad-de-quien-escribe-por-whatsapp.md)).

---

## Arquitectura en una línea

Angular 19 PWA → FastAPI (Python 3.11) → PostgreSQL 16 + pgvector · Redis · worker de
tareas con outbox transaccional en PostgreSQL. Proveedores de LLM y embeddings detrás de
interfaces abstractas. Detalle completo en [`docs/architecture.md`](docs/architecture.md).

---

## Contexto vigente para continuar el desarrollo

Esta sección resume el alcance acordado y el estado del trabajo para que una persona o un
agente de código —incluido Claude Code— pueda continuar desde la implementación existente.
Actualizarla cuando cambie el comportamiento, las rutas o las limitaciones descritas.

### Dirección del producto

ClinicAI es una plataforma clínica multi‑clínica con acceso definido por **roles, permisos y
ámbito**. El superadministrador puede registrar clínicas desde `/plataforma/clinicas`; el alta
crea en una sola transacción la clínica, su sede principal y una cuenta de administrador que
deberá cambiar su contraseña al entrar. Ese administrador asigna al personal de su clínica los
roles y módulos disponibles en Usuarios y roles. Las solicitudes usan la clínica de la sesión
autenticada; no se debe pedir ni confiar en un
`clinica_id` enviado por la interfaz para decidir el ámbito. Cada consulta del backend debe
filtrar por el principal y sus permisos.

La aplicación es un sistema conectado al backend real. Las pantallas con datos sintéticos
deben seguir identificadas como demostración; no presentar datos de demostración como si
fueran operación de una clínica.

### Funcionalidad existente relevante

| Área | Estado actual | Código principal |
|---|---|---|
| Marca e interfaz | Marca ClinicAI, recursos visuales del sitio y acceso diseñado para ocupar el viewport. | `frontend/public/images/`, `frontend/src/app/compartido/marca.component.ts`, `frontend/src/app/paginas/acceso/` |
| Sesión, roles y permisos | Autorización RBAC en el backend; cada clínica puede gestionar usuarios, asignar roles y permisos y crear roles propios dentro de sus capacidades. La navegación solo oculta opciones: el servidor siempre revalida. | `backend/app/modulos/usuarios/`, `backend/app/nucleo/autorizacion.py`, `frontend/src/app/paginas/usuarios/` |
| Administración global de clínicas y accesos | El superadministrador lista clínicas y personal, provisiona organizaciones y asigna cuentas nuevas o existentes a una clínica y sus roles/módulos. Al cambiar la asignación, los permisos se reemplazan, los refrescos se revocan y los JWT de acceso quedan inválidos inmediatamente. La operación queda auditada. | `backend/app/modulos/organizacion/plataforma.py`, `frontend/src/app/paginas/plataforma/`, `backend/app/modulos/usuarios/servicios.py` |
| Administración de clínica | La ruta `/configuracion` reúne el perfil de la clínica y sus integraciones; enlaza a Usuarios y roles para reutilizar la gestión ya existente. El perfil permite editar nombre, identificación fiscal, teléfono, correo, idioma, moneda y zona horaria, sin aceptar un ID de clínica en la ruta. | `backend/app/modulos/organizacion/rutas.py`, `frontend/src/app/paginas/configuracion/` |
| Credenciales por clínica | Anthropic, WhatsApp Cloud API, Google Calendar y SMTP se configuran desde la interfaz. Las claves se cifran en el servidor, se guardan por clínica y las respuestas solo revelan si existe una clave; nunca devuelven su valor. Los cambios quedan auditados. | `backend/app/modulos/configuracion/rutas.py`, `backend/app/modulos/organizacion/modelos.py`, `frontend/src/app/paginas/configuracion/` |
| Base de conocimiento | Carga, revisión, aprobación, búsqueda y ACL por rol, usuario, sede o especialidad desde la interfaz contra PostgreSQL/pgvector. Las reglas se auditan; denegaciones directas prevalecen sobre grants heredados. Sin reglas se aplica el alcance general. Sin embeddings configurados se usa el proveedor simulado, que no ofrece relevancia semántica de producción. | `backend/app/modulos/conocimiento/`, `frontend/src/app/paginas/conocimiento/` |
| Agenda y seguimiento | El panel usa citas dentro del ámbito, presenta tareas de hoy y carga por profesional. Las métricas incluyen citas por estado, pacientes distintos, inasistencia, tiempo medio de espera, pacientes actualmente esperando y los que superan 15 minutos; los importes requieren `pago.leer`. La ocupación porcentual no se inventa sin horarios disponibles como denominador. | `backend/app/modulos/dashboard/`, `frontend/src/app/paginas/panel/panel.component.ts`, `frontend/src/app/nucleo/utilidades/pendientes.ts` |
| Lista de espera | Recepción registra profesional, fechas, días y franja horaria; el motor compara esas preferencias en la zona local de la sede. Una oferta sin consentimiento aparece como llamada pendiente. El recorrido de punta a punta está probado con API y navegador, sin enviar mensajes externos. | `backend/app/modulos/lista_espera/`, `frontend/src/app/paginas/lista-espera/lista-espera.component.ts`, `pruebas-e2e/escenarios/09-lista-espera.spec.ts` |
| Análisis opcional con IA | Un usuario con `dashboard.leer` y `configuracion.escribir` puede solicitar análisis operativo con Anthropic. Solo se envían métricas agregadas del periodo seleccionado; no se incluyen nombres ni identificadores de pacientes. Se requiere la integración Anthropic habilitada y una clave configurada. El análisis queda auditado, no ejecuta acciones ni ofrece decisiones clínicas. | `backend/app/modulos/dashboard/rutas.py`, `frontend/src/app/paginas/panel/panel.component.ts` |
| Notificaciones en la aplicación | La campana de la cabecera agrupa tareas reales del día: turnos por vencer, citas sin confirmar y ofertas de lista de espera sin avisar. Cada aviso enlaza a la pantalla operativa correspondiente. | `frontend/src/app/app.component.html`, `frontend/src/app/nucleo/servicios/pendientes.service.ts` |

### Estado de la instancia local

El proceso API que ya estaba escuchando en el puerto `8000` no recargó las rutas de alertas. El
arranque `infra/scripts/demo-local.ps1` ahora comprueba una ruta del OpenAPI actual, además del
estado de salud, para no anunciar una instancia antigua como lista. Si detecta ese caso, detén
la instancia anterior desde la terminal o servicio que la inició y vuelve a ejecutar el script.
No inicies otra instancia mientras el puerto siga ocupado. La base local ya tiene las migraciones
actuales.

La base de datos y Redis locales respondieron como saludables durante la suite completa.

En una base local que ya tenía la clínica sintética antes de añadir el portal, se puede habilitar
la opción **Superadministrador** ejecutando desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.semillas.cargar --habilitar-superadministrador-local
```

El comando se limita a local/desarrollo, exige encontrar una única clínica marcada como sintética
y crea una cuenta sintética de acceso por rol; no es un procedimiento para crear cuentas en
producción.

### Cobertura funcional tomada de la presentación de referencia

La presentación **Odontozen** de 39 páginas se usa como inventario de capacidades y referencia
de jerarquía visual. No es una especificación técnica ni se copian sus textos, marca, precios,
testimonios, métricas comerciales o ejemplos de personas. Los nombres y cifras que aparecen
en sus mockups no son datos de ClinicAI. La petición del producto es cubrir las capacidades
relevantes con flujos propios y un diseño visual más claro, consistente, accesible y adaptable.

| Capacidad que ilustra la referencia | Cobertura real de ClinicAI hoy |
|---|---|
| Google Calendar por profesional, sincronización y avisos de cambios | Existe OAuth, modelo de conexión y cola de sincronización. El adaptador real de Google no está implementado; el modo actual es sandbox. La pantalla de claves de OAuth no conecta por sí misma el calendario. |
| Equipo, disponibilidad compartida y comisiones por profesional | Existen profesionales, sedes, servicios, permisos y calendario. La gestión completa de perfiles/disponibilidad requiere completar flujos administrativos. Las reglas y liquidación de comisiones están pendientes. |
| Recordatorios y respuestas de WhatsApp | Las citas confirmadas crean avisos durables de 24 h y 3 h. Las recetas confirmadas crean avisos genéricos para tomas futuras de pauta fija; los PRN no se programan, y suspender la receta o registrar la toma invalida los avisos pendientes. El worker exige el consentimiento específico de medicación y enlaza al acceso mediante FRONTEND_URL. La entrega real a Meta sigue pendiente y las credenciales por clínica aún necesitan adaptador por clínica. |
| Bandeja de atención de WhatsApp | Los mensajes entrantes derivados a una persona se listan en `/conversaciones`, con permisos `conversacion.leer`, ámbito de clínica/paciente y nivel N2, más auditoría de conteo, listado y detalle. Incluye insignia de pendientes y notificación global. Es de solo lectura; responder requiere el proveedor real y sus controles de ventana/plantillas. |
| Fichas, búsqueda e historial de pacientes entre sedes | CRUD y búsqueda segura de pacientes existen. Hay aislamiento por clínica/ámbito. Compartir una ficha entre clínicas o sedes debe ser una política explícita con permiso y auditoría; no asumir intercambio global. |
| Historia clínica con Formulario 033 MSP, anamnesis configurable y exportación PDF | Historia clínica versionada y notas de evolución existen. El formulario oficial MSP 033, diseñador de anamnesis y exportación PDF oficial están pendientes. |
| Odontograma interactivo FDI, hallazgos por pieza/cara e historial | API versionada con auditoría y control de relación asistencial; mapa inicial integrado en historia clínica. Pruebas API de permisos, historial y conflicto de versiones. Falta ampliar vocabulario, mejorar navegación accesible y cubrir E2E. Ver `docs/plan-modulo-dental.md`. |
| Planes dentales, plantillas, presupuesto y progreso por procedimiento | API e interfaz auditadas para crear/proponer planes, registrar constancia del documento firmado en la clínica, completar/cancelar procedimientos con actualización versionada del odontograma, usar plantillas y registrar controles. Desde el plan se agenda cada procedimiento de la siguiente fase; la cita valida clínica, paciente, servicio y estado, y queda vinculada atómicamente. Impide una cita activa duplicada y libera el vínculo al cancelar. API y E2E cubren el ciclo. Firma electrónica sigue pendiente. |
| Diario clínico, evolución y alertas de seguimiento posterior | Notas de evolución versionadas existen. El worker evalúa diariamente a las 09:20 (Ecuador) tomas omitidas de recetas confirmadas (mínimo 4, al menos 25 %); mantiene una sola alerta abierta por receta. La API limita lectura y atención por clínica, ámbito y relación asistencial, registra auditoría, y las notificaciones y pantalla de medicación muestran el seguimiento. El profesional puede programar un control al completar un procedimiento, ver el pendiente en el plan y registrar su atención auditada. El E2E cubre ambos recorridos. Siguen pendientes las alertas derivadas de problemas reportados por pacientes. |
| Radiografías, fotos, documentos y galería clínica por paciente/pieza | La API y galería autenticada permiten cargar imágenes saneadas y cifradas, filtrar por tipo/pieza, volver a verlas con permiso/auditoría y anularlas con motivo; incluye foto de perfil separada. E2E de carga y visualización verificado. En desarrollo, sin ClamAV, quedan marcadas `NO_DISPONIBLE`; producción rechaza cargas hasta habilitar antivirus. Documentos generales requieren verificar sus endpoints y pantallas antes de darlos por cubiertos. |
| Recetas con membrete, PDF, QR y firmas | Crear/confirmar recetas y calendario de tomas existe. Receta imprimible con marca de clínica, QR verificable y firma electrónica con validez jurídica no están implementados como la capacidad comercial descrita. |
| Consentimientos informados digitales por especialidad y firma en pantalla | La base contiene consentimientos generales para controlar comunicaciones. Plantillas de consentimiento clínico, firma del paciente/profesional y PDF trazable siguen pendientes. No confundir ambos tipos de consentimiento. |
| Presupuestos, abonos, saldos, cobros vencidos y reportes | Existe registro y revisión de pagos asociado a cita; el modelo actual limita a un pago por cita. Presupuestos, pagos parciales, saldos por paciente, vencimientos y exportables requieren un módulo financiero más completo. |
| Contabilidad de ingresos/gastos, caja y utilidad | El panel expone algunas sumas de pagos autorizadas. Libro de gastos, flujo de caja, conciliación y utilidad neta no existen todavía; no estimarlos a partir de pagos brutos. |
| Facturación electrónica SRI, notas de crédito y modos de prueba/producción | Pendiente. Requiere diseño fiscal, credenciales seguras, firma, homologación con proveedor autorizado y revisión legal/técnica ecuatoriana; no simular facturas autorizadas. |
| Inventario dental, movimientos, lotes, caducidad y proveedores | Pendiente. Hace falta definir catálogo, kardex, unidades, alertas, vencimientos y trazabilidad antes de crear indicadores. |
| Dashboard: producción, cobros, citas, pacientes nuevos, conversión, ocupación y gastos | Hay conteos por estado, pacientes distintos, inasistencia, espera promedio y alertas de pacientes en sala, pagos por estado y carga diaria. Nuevos pacientes, embudo de presupuestos, conversión, horas disponibles, gastos y ganancias requieren datos/modelos que aún no existen. |
| Estadísticas de agenda: horarios pico, tasas y tendencias | Parcial: conteos por estados y comparativa de inasistencia. Distribución por día/hora, retención, cancelaciones comparables y tendencias confiables requieren consultas y definiciones métricas adicionales. |
| Segmentación de pacientes, retención, demografía y tratamientos populares | Pendiente en dashboard. No enviar atributos clínicos a campañas ni usar diagnóstico/tratamiento para publicidad. Definir base legal y consentimiento antes de segmentar. |
| Productividad y exportes Excel/CSV/PDF | Pendiente en vista de eficiencia y exportación funcional por permisos. Nunca exportar campos fuera del ámbito del usuario. |
| Ajustes de marca, logo y preferencias por clínica/sede | Perfil institucional e integraciones básicas existen. Subida de logo, aplicación en documentos, preferencias funcionales y configuración heredada por sede están pendientes. |
| Ortodoncia, endodoncia, periodoncia y armonización facial | Pendientes como módulos clínicos especializados. El soporte dental común (odontograma/planes) es base de dominio, no sustituye formularios ni flujos específicos de cada especialidad. |
| Varias clínicas/sucursales, recursos y políticas de pacientes compartidos | La base soporta clínicas y sedes, y las consultas se limitan por ámbito. Debe completarse/revisarse el portal de administración global para asignar clínica y módulos, aprovisionamiento de sedes y la elección explícita entre fichas compartidas o aisladas. |
| Roles por módulo y permisos granulares | RBAC, gestión de usuarios y roles configurables ya existe. No copiar el conteo «136+» de la presentación; el catálogo real es el de `backend/app/nucleo/autorizacion.py`. Revisar permisos para cada endpoint nuevo. |
| Respaldo, exportación de datos, cifrado y firmas trazables | El proyecto tiene flujos documentados de backup/restore y controles de cifrado/auditoría. Exportación de datos de la clínica y firma electrónica de documentos requieren implementación. SSL/TLS depende también de la configuración de despliegue; no afirmar cumplimiento legal sin revisión. |
| Planes comerciales, límites, precios, prueba gratis y cancelación | No hay facturación de suscripciones ni portal comercial terminado. No copiar precios, descuentos, límites, testimonios ni cifras de Odontozen; cualquier oferta de ClinicAI necesita decisión del responsable y sustento real. |

### Guía de diseño frente a la referencia

Usar el PDF para entender tareas y jerarquía de información, no para replicar capturas. Los
nuevos módulos deben seguir el sistema visual ClinicAI ya aplicado al inicio de sesión,
navegación, pacientes y panel: ancho de pantalla aprovechado, tipografía y espaciado coherentes,
tablas legibles, acciones primarias claras, estados vacíos útiles y diseño responsive para
recepción y consultorio. Los flujos odontológicos deben ofrecer controles visuales accesibles,
operables con teclado y con etiquetas además del color. No incluir datos personales reales en
mockups ni diseños; usar contenido sintético y señalizar cualquier demostración.

La hoja de ruta de especialidades de [`docs/plan-modulo-dental.md`](docs/plan-modulo-dental.md)
precede a esta referencia y aún declara fuera de alcance varias especialidades. Para este
objetivo ampliado esa exclusión queda supersedida: antes de implementar cada especialidad,
definir con el equipo profesional sus campos, estados, permisos, auditoría y criterios clínicos.

### Límites conocidos y siguientes pasos

* Las tarjetas de seguimiento automático usan reglas explícitas sobre métricas. El análisis
  generado por IA es optativo y se solicita al pulsar el botón; no se ejecuta en segundo plano.
* La bandeja actual es un centro de avisos operativos derivado de la cola diaria. No tiene
  todavía persistencia de leído/no leído, preferencias por usuario, avisos por correo ni
  notificaciones push.
* El endpoint de análisis IA usa la credencial de Anthropic por clínica. Las claves de
  WhatsApp, Google Calendar y SMTP ya pueden guardarse con cifrado, pero cada proveedor aún
  requiere que su adaptador de ejecución consuma la configuración por clínica. Guardar una
  clave no demuestra que el servicio externo esté conectado.
* Las métricas disponibles son las que exponen actualmente las consultas del dashboard. Antes
  de añadir indicadores nuevos, comprobar que existen datos y permisos para calcularlos; no
  presentar estimaciones como hechos ni enviar información clínica a un modelo.
* El análisis del repositorio y la implementación de estas funciones no equivalen a aprobación
  para datos de pacientes reales ni a validación legal o clínica.

### Verificación de esta actualización

El 5 de octubre de 2026 se ejecutaron `npm run build`, Ruff sobre los módulos de organización,
dashboard y auditoría, comprobación de formato e importación de `app.main`. La compilación
frontend y las comprobaciones estáticas/importación finalizaron correctamente. No se ejecutó
la suite de pruebas en esta actualización; las cifras de pruebas de la cabecera corresponden
a la evidencia que ya estaba documentada y no se deben interpretar como pruebas de estas
últimas funciones.

---

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `backend/` | API FastAPI, dominio, capa de IA, tareas, migraciones Alembic y pruebas |
| `frontend/` | Aplicación Angular 19 PWA |
| `infra/` | Dockerfiles, ficheros compose, aprovisionamiento de WSL2 y scripts |
| `pruebas-e2e/` | Escenarios Playwright de extremo a extremo |
| `pruebas-carga/` | Escenarios de carga k6 |
| `datos-sinteticos/` | Semillas y generadores de datos sintéticos |
| `docs/` | Arquitectura, seguridad, modelo de amenazas, operación y decisiones (ADR) |
| `.github/workflows/` | Pipeline de integración y entrega continua |

---

## Requisitos

| Herramienta | Versión verificada en el entorno de desarrollo |
|---|---|
| Python | 3.11.9 |
| Node.js / npm | 22.23.1 / 11.2.0 |
| Git | 2.44 |
| Docker + Compose | Dentro de WSL2 (ver nota de Windows) |

### Nota para Windows

En el equipo de desarrollo actual Docker Desktop **no es viable** (disco C: sin espacio) y
pgvector **no compila de forma nativa** (sin MSVC). Por eso la infraestructura de datos se
ejecuta dentro de **WSL2 con Docker Engine**, con el sistema de archivos en `D:`.
La distribución se llama **`clinica`**. El procedimiento está en
[`docs/deployment.md`](docs/deployment.md) y los scripts en [`infra/wsl/`](infra/wsl/). Razonamiento en
[`docs/decisiones/0002-infraestructura-local-wsl2-docker.md`](docs/decisiones/0002-infraestructura-local-wsl2-docker.md).
La instancia comprobada hoy corre `clinica-pg` y `clinica-redis` dentro de esa distribución
(`wsl -d clinica docker ps`). Docker Desktop usa otro contexto y puede mostrar cero servicios;
abrir su panel no inicia los contenedores que consume la aplicación.

---

## Puesta en marcha local

```powershell
# 1. Configuración
Copy-Item .env.example .env
#    Complete .env. Genere los secretos así (no reutilice valores de ejemplo):
#    python -c "import secrets; print(secrets.token_urlsafe(64))"
#    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#    Configure FRONTEND_URL como dirección HTTPS pública al desplegar; los
#    recordatorios de medicación enlazan al acceso del portal.

# 2. Infraestructura de datos (PostgreSQL + pgvector + Redis)
.\infra\wsl\aprovisionar.ps1                     # solo la primera vez
#    Anclar la distribución: sin esto WSL se apaga entre comandos y reinicia
#    los contenedores, con fallos de conexión aparentemente aleatorios.
#    Explicación en docs/deployment.md
.\infra\scripts\mantener-wsl.ps1 -SegundoPlano
.\infra\scripts\infra-arriba.ps1

# 3. Backend
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install uv; uv sync
uv run python -m herramientas.esperar_bd            # espera a que la BD responda
uv run alembic upgrade head
uv run python -m app.semillas.cargar                # catálogos + datos sintéticos
uv run uvicorn app.main:crear_aplicacion --factory --reload
uv run arq app.tareas.worker.ConfiguracionWorker   # trabajos periodicos

# 4. Frontend
cd ..\frontend
npm ci
npm start
```

* API y documentación OpenAPI: `http://localhost:8000/docs`
* Aplicación web: `http://localhost:4200`
* Comprobación de salud: `http://localhost:8000/salud/listo` (la API está lista y PostgreSQL responde)

Credenciales de los usuarios sintéticos: se imprimen al ejecutar la carga de semillas.
No existen credenciales por defecto embebidas en el código.

### Acceso rápido por roles para desarrollo local

Cuando `ENTORNO=local` o `ENTORNO=desarrollo`, la pantalla de acceso muestra botones
para las cuentas sintéticas activas disponibles: administración de clínica, recepción,
asistencia clínica, auditoría y profesional de salud. En ese modo la pantalla de acceso
oculta el formulario de contraseña para facilitar la revisión por rol. Los roles que
requieren 2FA pueden abrirse mediante este acceso temporal; el endpoint normal de sesión
se conserva para los flujos existentes de la API.

El backend selecciona la cuenta; el navegador solo envía el código del rol. Solo son
elegibles usuarios activos con `[SINTETICO]` en el apellido y roles base del sistema. Cada
entrada queda en la auditoría como `login.rol_local`. La ruta de acceso rápido no emite
sesiones en preproducción ni producción. En esos entornos se mantiene el inicio normal
con correo, contraseña y el segundo factor que corresponda. Cambiar de modo requiere
reiniciar el backend después de ajustar `ENTORNO`.

Rutas locales: `GET /api/v1/autenticacion/accesos-locales` informa qué botones están
disponibles y `POST /api/v1/autenticacion/sesion-local` inicia la sesión del rol elegido.
Si no hay cuentas sintéticas cargadas, la pantalla conserva el formulario de contraseña.

---

## Pruebas

```powershell
# Backend
cd backend
uv run ruff check . ; uv run ruff format --check .
uv run mypy app
uv run pytest -m unitaria -q
uv run pytest -m "integracion or api" -q     # requiere la infraestructura arriba
uv run pytest -m concurrencia -q
uv run pytest -m rag -q
uv run pytest --cov=app --cov-report=term-missing

# Frontend
cd ..\frontend
npm run lint ; npx tsc --noEmit ; npm test -- --watch=false ; npm run build

# Extremo a extremo y carga
cd ..\pruebas-e2e  ; npx playwright test
cd ..\pruebas-carga ; k6 run reservas.js
```

El plan de pruebas completo, con los escenarios obligatorios y los resultados de la
última ejecución, está en [`docs/test-plan.md`](docs/test-plan.md).

---

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Arquitectura, componentes y flujos |
| [`docs/requirements.md`](docs/requirements.md) | Requisitos y criterios de aceptación |
| [`docs/data-model.md`](docs/data-model.md) | Modelo de datos y diagrama de entidades |
| [`docs/security.md`](docs/security.md) | Controles, política de acceso y retención |
| [`docs/threat-model.md`](docs/threat-model.md) | Modelo de amenazas y matriz de riesgos |
| [`docs/rag.md`](docs/rag.md) | Recuperación, permisos y anti prompt injection |
| [`docs/agente.md`](docs/agente.md) | Las siete herramientas, la frontera clínica y lo que aún falta |
| [`docs/backup-and-restore.md`](docs/backup-and-restore.md) | Respaldo cifrado y la restauración **ya verificada** |
| [`docs/monitoring.md`](docs/monitoring.md) | Qué vigilar y por qué; qué emite ya el sistema |
| [`docs/incident-response.md`](docs/incident-response.md) | Clasificación por daño al paciente y guías por tipo |
| [`docs/whatsapp-integration.md`](docs/whatsapp-integration.md) | Webhooks, plantillas y entrega |
| [`docs/calendar-integration.md`](docs/calendar-integration.md) | OAuth, sincronización y reconciliación |
| [`docs/deployment.md`](docs/deployment.md) | Despliegue local, staging, producción y rollback |
| `docs/backup-and-restore.md` | Respaldo y restauración verificada — **pendiente** |
| `docs/monitoring.md` | Métricas, logs y alertas — **pendiente** |
| `docs/incident-response.md` | Respuesta a incidentes — **pendiente** |
| [`docs/production-readiness.md`](docs/production-readiness.md) | Estado real frente a los criterios de producción |
| [`docs/test-plan.md`](docs/test-plan.md) | Qué se prueba, con qué, por qué de esa forma, y la evidencia de la última ejecución |
| [`docs/known-limitations.md`](docs/known-limitations.md) | Limitaciones y riesgos residuales |
| [`docs/backlog.md`](docs/backlog.md) | Backlog por fases con criterios de aceptación |
| [`docs/decisiones/`](docs/decisiones/) | Registros de decisiones de arquitectura (ADR) |
| [`docs/informe-avance.md`](docs/informe-avance.md) | **Estado real del proyecto**, con los 18 puntos exigidos y sus evidencias |

---

## Licencia y titularidad

Proyecto privado. Sin licencia de distribución definida.
