# ClinicAI — Plataforma de gestión clínica

Sistema de gestión clínica multi‑sede con agenda, agente de WhatsApp, sincronización de
calendarios, lista de espera inteligente, historia clínica versionada, recetas con
seguimiento de adherencia, base de conocimiento con RAG, pagos asistidos, dashboard y
auditoría.

> **Estado actual:** las fases 0 y 0b están documentadas; las fases funcionales 1 a 9 siguen en desarrollo y verificación. La lista de espera permite reagendar, encadenar turnos con un límite y resolver aceptaciones concurrentes; rollback y diez respuestas HTTP simultáneas ya están probados contra PostgreSQL. La fase 10 de preparación para producción no está cerrada.

> **Frontend y dependencias (2026-10-07):** Angular se actualizó a 22.2.1 mediante los esquemas oficiales 19→20→21→22; Karma/Jasmine se migró a Vitest. En una instalación limpia: 443/443 pruebas, cobertura de 86,57 % en sentencias, 74,72 % ramas, 81,03 % funciones y 88,40 % líneas; lint, TypeScript y build de producción pasan; `npm audit` informa cero vulnerabilidades. CI usa `npm run test:ci`. Para aplicar localmente la actualización: `cd frontend; npm ci` y reiniciar cualquier servidor Angular que estuviera activo. La pestaña de Ayuda con un manual distinto por rol sigue siendo requisito de cierre (tarea 11.1), no está marcada como implementada.

> **Seguridad de documentos Word (2026-10-07):** la lectura del XML de DOCX usa `defusedxml` y rechaza DTD/entidades externas. La regresión de archivo malicioso y las pruebas DOCX pasan; Bandit completo no reporta hallazgos medianos o altos. Detalle en `docs/test-plan.md`.

> **Dependencias backend (2026-10-07):** el lock actualiza PyJWT a 2.15.1, pypdf a 6.19.0, urllib3 a 2.8.0 y Werkzeug a 3.1.9 tras detectar avisos nuevos; `pip-audit` vuelve a reportar cero vulnerabilidades. Las 835 unitarias, Ruff, mypy y Bandit pasan en un entorno de validación aislado. La batería API/integración todavía se está ejecutando.
>
> **Nota de vigencia (2026-10-06):** las fases describen el alcance funcional local; no equivalen a preparación de producción. La suite E2E vigente aprobó **55/55 pruebas en 4,1 minutos** contra una API iniciada desde el código actual en el puerto 8002, Angular y PostgreSQL local. Incluye accesibilidad axe en las 20 rutas del menú, recorridas según el acceso de cada rol. El detalle y el comando están en `pruebas-e2e/README.md`.
>
> **Accesibilidad (2026-10-06):** axe-core aplica reglas WCAG 2.2 A/AA al acceso, panel, agenda, historia clínica, configuración y a las secciones visibles para los seis roles. La unión del menú recorre y comprueba las **20 rutas**; pasan los diez escenarios. Se corrigieron contraste en Conocimiento y Catálogo y el acceso con teclado a la tabla horizontal de cargos. La revisión manual con lector de pantalla y zoom, y otros estados interactivos, sigue pendiente (`docs/backlog.md`, tarea 1.14; `npm run test:a11y` en `pruebas-e2e`).

> **Suite frontend (2026-10-06):** `npm run test:ci` aprobó **442/442 pruebas** con Chromium Headless y superó el umbral de cobertura: líneas 87,61 %, ramas 72,94 %, funciones 80,95 % y sentencias 85,71 %. Una ejecución aislada por componente no alcanza el mínimo global; la corrida CI completa sí lo verifica. Los detalles y el comando están en `docs/test-plan.md`.

> **Revocación de consentimiento (2026-10-06):** el worker vuelve a comprobar el permiso de comunicación inmediatamente antes de entregar cada mensaje proactivo. Si el paciente revoca su consentimiento mientras el mensaje sigue pendiente, el outbox lo marca `DESCARTADO` y no llama al proveedor. La prueba usa PostgreSQL y un adaptador sandbox; se aprobaron **29 pruebas** entre outbox y API de consentimientos, además de Ruff y formato. Esto verifica el flujo local; no se conectó ningún proveedor externo.

> **Cabeceras HTTP y CORS (2026-10-06):** pruebas contra la aplicación FastAPI confirman las cabeceras de seguridad y correlación en respuestas correctas y 404; el preflight acepta únicamente el origen configurado, los métodos y las cabeceras autorizadas, y rechaza orígenes ajenos. La configuración de producción rechaza CORS con comodín. Pasaron 3 pruebas HTTP y 13 casos de validación de configuración.

> **Matriz de roles RBAC (2026-10-06):** la suite compara `docs/security.md` con los permisos efectivos de superadministrador, administrador de clínica, recepción, profesional, asistente y auditor; también exige que cada permiso del catálogo aparezca una sola vez en la matriz. Detectó que faltaban 11 permisos documentados y que se atribuía lectura clínica/financiera a roles que no la reciben. Se corrigió la documentación, sin ampliar accesos. `test_autorizacion.py`: 35/35 pruebas pasan.

> **Auditoría append-only (2026-10-06):** una tercera prueba detectó que `TRUNCATE` podía eludir los disparadores previos de `UPDATE`/`DELETE`. La migración `20261006_028` instala un disparador para impedir también el vaciado total. Tres pruebas SQL directas contra PostgreSQL verifican el SQLSTATE de privilegios para las tres operaciones. La instancia local quedó en `20261006_028` y `alembic check` no detecta cambios de esquema faltantes. Sigue pendiente desplegar el proceso con una cuenta PostgreSQL separada del dueño del esquema para impedir que desactive disparadores.

> **Rotación de sesiones (2026-10-06):** se verificó por API e integración que cada refresco crea una sesión sucesora y anula el anterior; reutilizarlo revoca toda la familia, registra una alerta de auditoría y deja inutilizable también el par sucesor. Cerrado con **70 pruebas** de autenticación API e integración; no se usan proveedores externos.

> **Segundo factor y bloqueo de acceso (2026-10-06):** añadí una regresión HTTP para el rol que exige TOTP: si no lo ha configurado, responde 403 `SEGUNDO_FACTOR_REQUERIDO` y no crea una sesión. La suite también verifica bloqueo tras intentos fallidos, rechazo de la contraseña correcta durante el bloqueo, restablecimiento al expirar y límite por IP con 429. Autenticación API e integración: **71/71 pruebas**.

> **Aislamiento de Pagos por sede (2026-10-06):** amplié la regresión del comprobante para verificar que, después de mover la cita fuera del ámbito, el contenido, el listado de comprobantes y el historial devuelven 404. Las tres consultas habían respondido con acceso válido antes del cambio de sede. `test_pagos_listado_api.py`: 9/9; Ruff pasa. La matriz completa de IDOR por endpoint y rol continúa abierta.

> **IDOR clínico entre clínicas (2026-10-06):** extendí la comparación de 404 de notas y resumen para un rol administrativo sin permiso clínico y otro con permiso pero sin relación asistencial. Un paciente real de otra clínica y un UUID inexistente producen la misma respuesta que el caso no autorizado del mismo tenant. Las tres pruebas focalizadas pasan; siguen pendientes otros endpoints y roles de la matriz IDOR.

> **Aislamiento de automatizaciones (2026-10-06):** añadí dos clínicas con usuarios autorizados y comprobé por API que apagar un flujo en una clínica no cambia el estado que ve la otra. `test_automatizaciones_api.py`: 4/4; Ruff y formato pasan. La cobertura IDOR general continúa parcial.

> **Reloj inyectable y lint (2026-10-06):** activé `TID251` en Ruff, que rechaza `datetime.now()` en la aplicación salvo en el módulo que implementa el reloj de sistema. Verifiqué que el lint falla con una llamada de prueba. La carga sintética acepta `RelojFijo` para que sus fechas sean reproducibles; integración de semillas: **30/30**, Ruff y mypy pasan.

> **Hash y política de contraseñas (2026-10-06):** verifiqué Argon2id con sal aleatoria, hash/verificación, hash malformado, límites de longitud y rehash de parámetros antiguos. La política comprueba longitud, composición y contraseñas comunes; el alta rechaza una clave débil antes de crear la cuenta y no devuelve el valor enviado. Pruebas unitarias de seguridad y regresión API: **63/63**.

> **Configuración de producción (2026-10-06):** la validación previa al arranque rechaza secretos obligatorios vacíos o cortos, marcadores de ejemplo, proveedores simulados y opciones inseguras; también enumera los fallos simultáneos. La suite `test_configuracion.py` pasó **53/53**.

> **Ciclo de migraciones (2026-10-06):** una base PostgreSQL temporal con las cinco extensiones necesarias pasó `alembic upgrade head`, `downgrade base` y `upgrade head`, y terminó en `20261006_028`. La base de prueba se eliminó. Añadí el mismo ciclo completo como puerta de CI antes de cargar datos; el esquema se valida con `alembic check` al final.

> **Contrato de todas las operaciones API (2026-10-06):** Schemathesis genera y valida una solicitud por cada operación publicada (100+), incluidas respuestas de autorización, por ASGI contra el fixture transaccional; CI no usa credenciales ni entrega llamadas a proveedores. El barrido detectó errores HTTP no documentados y el requisito condicional de identidad en indicaciones posconsulta: OpenAPI ahora describe el sobre común de error y al menos uno de fecha de nacimiento/documento. `test_contrato_openapi.py`: **2/2**; API de posconsulta: **4/4**. Esto verifica una entrada por operación y el contrato de sus respuestas, no sustituye pruebas funcionales de autorización con identidades y datos para cada rol.
>
> **Panel de seguimiento (2026-10-06):** el dashboard admite fechas inclusivas personalizadas de hasta 366 días y calcula los límites con la zona horaria de la clínica o sede seleccionada. El rango se aplica a los agregados y al resumen local. Incluye pacientes nuevos/recurrentes por primera atención completada y turnos liberados/recuperados con tiempo medio hasta aceptar una oferta; estas métricas de cohorte se ocultan con filtro por estado. Para roles con `adherencia.leer`, agrega tomas registradas, omitidas y alertas abiertas sin datos de pacientes o medicamentos; ese agregado clínico no se envía a Anthropic. Las tendencias tienen etiquetas y valores textuales, estados de carga/error/vacío y no dejan cifras antiguas visibles al fallar la actualización. Frontend: **442/442 pruebas**, lint y build pasan; quedan pendientes visualizaciones avanzadas.
>
> **Respuestas de medicación por WhatsApp (2026-10-06):** el webhook reconoce rutas cerradas para registrar una toma, diferir su aviso 30 minutos, reportar una omisión, pedir ayuda o solicitar revisión clínica con frase explícita. Requiere paciente inequívoco y toma dentro de la ventana; registra auditoría y nunca cambia la hora prescrita. Pasaron **136 pruebas** focalizadas de intención, privacidad de plantillas, integración PostgreSQL y webhook. La prueba reveló y llevó a corregir una opción que infringía la regla de no exponer información clínica en la pantalla bloqueada. Se verificó el flujo local y el outbox, no el envío real de Meta: faltan credenciales y aprobación de plantilla.
>
> **Sensibilidad N3 en notas clínicas (2026-10-06):** cada versión de nota permite N2/N3. Crear y leer N3 requiere `historia_clinica.leer_sensible`; el filtro se aplica en SQL también al historial y al resumen. Corregir una nota no reduce N3, las lecturas/escrituras sensibles elevan auditoría y la redacción local nunca recibe notas N3. La migración 022 está aplicada en la base local. Backend focalizado: 72 pruebas; frontend: 439/439, lint y build.
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
> La suite backend completa con cobertura documentada aprobó **1682 pruebas y omitió 3** que requieren
> Anthropic, en 40 min 47 s; cobertura total **87,65 %** (80 % requerido). Ruff lint, formato
> y mypy pasan; `alembic check` no detectó operaciones nuevas. Informa advertencias existentes
> por el ciclo de claves foráneas de imágenes/planes y las columnas calculadas. Las corridas por marcador
> también aprobaron: 814 unitarias, 854 de integración/API, 15 de concurrencia, 635 de
> seguridad y 93 de RAG. Los marcadores se solapan, por lo que esos conteos no se suman.
> Después del vencimiento, pagos aprobó **34 pruebas focalizadas**; el reporte financiero pasó **9 pruebas API** y la gestión de anamnesis otras **5**. En esta continuación, el servicio clínico pasó **41 pruebas de integración** contra PostgreSQL; seis nuevas comprueban el calendario de medicamentos en varias frecuencias y la conversión de la hora local de Guayaquil a UTC. N3 en antecedentes exige permiso sensible, genera auditoría reforzada y se excluye de la redacción local. En esa revisión, la suite frontend aprobó **406 casos**
> (87,56 % líneas, 71,12 % ramas, 80,45 % funciones, 85,77 % sentencias); lint y build pasan. La suite API de resumen sensible cuenta con seis pruebas y se añadió una prueba de interfaz N3. En esta continuación, 114 pruebas API e integración clínica aprobaron el contrato 404 sin enumeración y su flujo de emergencia.
> La corrida E2E completa anterior a los cambios recientes de Pagos y anamnesis aprobó los **39 escenarios en 4,7 minutos**: acceso/autorización (12),
> pacientes (6), clínica e historia (8), agenda (6), conocimiento (2), imágenes (1),
> conversaciones (1), lista de espera (1), equipo (1) y sedes (1). Se corrigieron selectores de la Agenda,
> la galería de imágenes y campos obligatorios que no coincidían con la interfaz actual. La
> suite completa se ejecutó con el límite E2E configurado en 200; el límite normal de desarrollo
> continúa en 10. Carga:
> 2 314 peticiones con **0 reservas duplicadas** bajo
> contienda, y la **restauración de respaldos verificada** con 11 comprobaciones.
>
> El escenario de exportación verifica la descarga fechada y conteos por día/estado sin campos
> de pacientes; Recepción accede solo al permiso agregado y el servidor conserva el ámbito.
>
> El escenario de equipo se reejecutó el 2026‑10‑06 contra la API actualizada: crea el perfil,
> asigna el rol Profesional y vincula la cuenta desde Usuarios y roles, y después edita la
> ficha. La API verifica perfiles disponibles, cambio de vínculo, conflictos, permisos y alcance
> (`test_usuarios_api.py`, 5 pruebas; además pasaron 17 pruebas API de pacientes en esta revisión).
>
> La cobertura frontend más reciente es: líneas 87,56 % (80 % requerido), ramas
> 71,12 % (70 % requerido), funciones 80,45 % (80 % requerido) y sentencias 85,77 %; los 406 casos pasan. La
> compilación de producción termina con un chunk inicial de **451,55 kB**, por debajo del presupuesto
> de 500 kB.
>
> En la primera verificación del 2026‑10‑06 pasaron 24/39 porque el navegador estaba conectado a
> procesos Angular antiguos y una API previa. Tras iniciar Angular desde el código actual y usar
> la API que publica `/api/v1/agenda/resumen.csv`, pasaron los **39/39 escenarios**; la guía E2E
> conserva la instrucción de usar la misma API actualizada desde Angular y `URL_API`.
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

## Recursos visuales

La guía de imágenes, iconos SVG, fondos animados y criterios de movimiento
accesible está en [`docs/recursos-visuales.md`](docs/recursos-visuales.md).
El área de trabajo usa `ambiente-clinicai-red-v1.jpg` (96 KB) con desplazamiento
ambiental lento y el nuevo icono SVG `roles` distingue la gestión de accesos en
la navegación. El movimiento se desactiva con `prefers-reduced-motion`.
La cabecera de Historia clínica usa `historia-clinica-integral.jpg`; la biblioteca
de iconos SVG incluye pictogramas para formulario clínico, examen dental e
historial de versiones. El movimiento de los fondos se desactiva cuando el
sistema operativo solicita movimiento reducido.
Automatizaciones usa `automatizaciones-flujo-clinica.svg`, con agenda, documentos y mensajes conectados, y un pictograma SVG propio. Su red de puntos se desplaza suavemente en el encabezado y respeta `prefers-reduced-motion`.
Integraciones incorpora `integraciones-clinicai-banner.png`, una ilustración panorámica del ecosistema conectado de la clínica, y el pictograma vectorial `conexiones`. La imagen se usa en un encabezado oscuro con halo y flotación lentos, detenidos bajo `prefers-reduced-motion`.

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

**Entregable obligatorio de cierre:** crear una pestaña de Ayuda/Documentación con un manual
independiente para cada rol del sistema y cada rol personalizado de clínica. Las guías serán
específicas a las tareas y permisos de cada rol; no se reutilizará el mismo manual entre roles.
Se elaborarán al cerrar los flujos de producto y está registrado como tarea 11.1 en
[`docs/backlog.md`](docs/backlog.md).

### Funcionalidad existente relevante

| Área | Estado actual | Código principal |
|---|---|---|
| Marca e interfaz | Marca ClinicAI, ilustraciones por módulo y acceso a pantalla completa. El panel usa `panel-clinicai-dental-network-v1.jpg` como fondo panorámico oscuro, con movimiento lento, halo y reflejo; el título claro mantiene el contraste y las señales llevan pictogramas SVG. El icono `diente-conectado` del encabezado tiene un pulso tenue; las animaciones respetan `prefers-reduced-motion`. Odontograma, pagos y seguimiento inteligente cuentan con símbolos SVG propios. El acceso suma un flujo explicativo en SVG, resplandor ambiental y pictogramas distintos para cada rol local. La biblioteca de iconos SVG se mantiene en código y se usa también en las tarjetas de integraciones. El Asistente incorpora `asistente-clinico-banner.jpg`, una cabecera panorámica de odontología conectada con agenda, documento y mensajes; el fondo y el halo se mueven con suavidad y respetan `prefers-reduced-motion`. Configuración y Automatizaciones tienen ilustraciones ambientales propias; Integraciones añade `integraciones-clinica-seguras.jpg`, con un escudo dental conectado a calendario, mensajería, IA y correo. Usuarios y roles incorpora `usuarios-roles-acceso.jpg`, un banner panorámico de equipo, permisos y módulos con iconos SVG y movimiento suave. Los banners con halo y desplazamiento respetan `prefers-reduced-motion`. Promociones tiene una portada panorámica propia (`campanas-pacientes.jpg`) y el espacio de trabajo suma luz ambiental animada muy tenue. Conocimiento suma un icono vectorial de documento verificado y un halo animado; el estado vacío del centro de notificaciones usa `notificaciones-vacias.png` con flotación suave. La lista de espera incluye `lista-espera-vacia.svg`, ilustración vectorial con flotación sutil que se detiene con `prefers-reduced-motion`. Todas las animaciones respetan esa preferencia. El simulador solo aparece si la API confirma modo local y el rol tiene `conversacion.responder`. | `frontend/public/images/`, `frontend/src/app/compartido/icono.component.ts`, `frontend/src/app/nucleo/servicios/modo-local.service.ts`, `frontend/src/app/paginas/panel/panel.component.ts`, `frontend/src/app/paginas/acceso/`, `frontend/src/app/paginas/configuracion/configuracion.component.ts`, `frontend/src/app/paginas/automatizaciones/automatizaciones.component.ts`, `frontend/src/app/paginas/promociones/`, `frontend/src/app/paginas/conocimiento/`, `frontend/src/app/paginas/usuarios/usuarios.component.ts` |
| Sesión, roles y permisos | Autorización RBAC en el backend; cada clínica puede gestionar usuarios, asignar roles y permisos y crear roles propios dentro de sus capacidades. La navegación solo oculta opciones: el servidor siempre revalida. | `backend/app/modulos/usuarios/`, `backend/app/nucleo/autorizacion.py`, `frontend/src/app/paginas/usuarios/` |
| Administración global de clínicas y accesos | El superadministrador lista clínicas y personal, crea clínicas con su sede y administrador inicial, agrega sucursales y asigna cuentas nuevas o existentes a una clínica, roles/módulos y todas o algunas de sus sedes. El cambio reemplaza roles, revoca sesiones y queda auditado; las sucursales heredan la zona horaria salvo que se indique otra. | `backend/app/modulos/organizacion/plataforma.py`, `frontend/src/app/paginas/plataforma/`, `backend/app/modulos/usuarios/servicios.py` |
| Administración de clínica | La ruta `/configuracion` reúne el perfil de la clínica y sus integraciones; enlaza a Usuarios y roles para reutilizar la gestión ya existente. El perfil permite editar nombre, identificación fiscal, teléfono, correo, idioma, moneda y zona horaria, sin aceptar un ID de clínica en la ruta. | `backend/app/modulos/organizacion/rutas.py`, `frontend/src/app/paginas/configuracion/` |
| Catálogo clínico | Con `especialidad.gestionar` y `servicio.gestionar` se crean, editan y desactivan especialidades y servicios. Se configuran duración, preparación, precio, moneda, pago previo y tipo de consultorio. La API verifica la clínica, audita cambios y protege la oferta de servicios activos al desactivar una especialidad. Consultorios se administran por sede con `sede.gestionar`. | `backend/app/modulos/organizacion/rutas.py`, `frontend/src/app/paginas/catalogo/`, `frontend/src/app/nucleo/servicios/catalogo.service.ts` |
| Horarios y feriados | En `/configuracion`, el permiso `agenda.configurar` habilita la gestión por sede de franjas semanales, pausas y feriados de sede o de clínica. Se validan rangos, pausas internas, periodos superpuestos y alcance de roles; las escrituras quedan auditadas y la disponibilidad ya consume estos registros. | `backend/app/modulos/organizacion/agenda_rutas.py`, `frontend/src/app/paginas/configuracion/agenda-configuracion.component.ts`, `docs/security.md` |
| Bloqueos operativos de agenda | En `/configuracion`, `bloqueo.gestionar` permite registrar vacaciones, ausencias, capacitaciones y mantenimientos para una sede, profesional o consultorio. El servidor valida alcance, advierte con 409 sobre citas activas coincidentes y exige confirmación explícita; registra auditoría y la disponibilidad descuenta los bloqueos existentes. | `backend/app/modulos/agenda/bloqueos_rutas.py`, `frontend/src/app/paginas/configuracion/bloqueos-agenda.component.ts`, `docs/security.md` |
| Disponibilidad semanal del equipo | En `/configuracion`, `agenda.configurar` o `profesional.gestionar` permite definir franjas particulares por profesional y sede, duración de cita y vigencias. Se validan solapamientos y ámbito; los cambios quedan auditados y el cálculo de disponibilidad ya consume las franjas guardadas en hora local de la sede. Sin horario particular, se conserva el horario general de la sede. | `backend/app/modulos/profesionales/agenda_rutas.py`, `frontend/src/app/paginas/configuracion/agenda-profesionales.component.ts`, `backend/app/modulos/agenda/repositorio.py` |
| Credenciales por clínica | Anthropic, WhatsApp Cloud API, Google Calendar y SMTP se configuran desde la interfaz. Las claves se cifran en el servidor, se guardan por clínica y las respuestas solo revelan si existe una clave; nunca devuelven su valor. Los cambios quedan auditados. | `backend/app/modulos/configuracion/rutas.py`, `backend/app/modulos/organizacion/modelos.py`, `frontend/src/app/paginas/configuracion/` |
| Base de conocimiento | Carga y revisión de texto y PDF; el servidor valida tipo, tamaño, páginas y contenido activo, exige ClamAV en producción, extrae texto y lo indexa en PostgreSQL/pgvector. El binario no se conserva. ACL por rol, usuario, sede o especialidad, con auditoría y denegaciones directas prioritarias. El RAG recupera solo fragmentos de la versión vigente; para corregir un documento aprobado, primero se retira a borrador y la nueva versión debe volver a aprobarse. La fuente y el trabajo sobreviven a fallos; el worker recoge cada minuto hasta 10 ingestas pendientes y el indexado es idempotente. Un proveedor que falla deja el trabajo `FALLIDA` para evitar reintentos continuos; tras corregirlo se puede reenviar el mismo contenido. Sin ClamAV en desarrollo, el PDF queda marcado como no analizado; OCR y embeddings semánticos reales siguen pendientes. | `backend/app/modulos/conocimiento/`, `backend/app/tareas/al_ingestas_conocimiento.py`, `frontend/src/app/paginas/conocimiento/` |
| Agenda y reservas | Día, semana, mes y lista con filtros de sede, especialidad, servicio y profesional. Recepción reserva desde un hueco calculado con la disponibilidad real, busca al paciente, confirma y ve la cita en el calendario; cancelar y reprogramar actualizan los mismos registros auditados. Pruebas E2E verifican persistencia contra PostgreSQL. | `backend/app/modulos/agenda/`, `frontend/src/app/paginas/agenda/`, `pruebas-e2e/escenarios/05-demo-operativa.spec.ts` |
| Agenda y seguimiento | El panel usa citas dentro del ámbito, presenta tareas de hoy y carga por profesional. Permite periodos rápidos, rango personalizado inclusivo de hasta 366 días y filtros por sede, especialidad, profesional, servicio y estado; al elegir sede usa su zona horaria para convertir el rango a UTC. Los catálogos se cargan según el acceso de la sesión y los filtros también alcanzan el resumen local y el análisis opcional. Las métricas incluyen citas por estado, pacientes distintos y atendidos nuevos/recurrentes (según primera atención completada), inasistencia, tiempo medio de espera, pacientes actualmente esperando y los que superan 15 minutos, además de cancelaciones, ofertas aceptadas y tiempo medio para recuperar turnos desde lista de espera. Si se concede `adherencia.leer`, agrega tomas registradas, omitidas, porcentaje administrativo y alertas abiertas sin datos de pacientes ni medicamentos; los importes requieren `pago.leer`. Las tendencias agregadas se agrupan por fecha, hora y día de semana en la zona horaria de cada sede. Las tasas de inasistencia y métricas de cohorte se ocultan con filtro de estado único. El registro agregado RF‑Q06 aparece solo con `adherencia.leer`; faltan visualizaciones adicionales. La ocupación porcentual no se inventa sin horarios disponibles como denominador. | `backend/app/modulos/dashboard/`, `frontend/src/app/paginas/panel/panel.component.ts`, `frontend/src/app/nucleo/utilidades/pendientes.ts` |
| Lista de espera | Recepción registra profesional, fechas, días y franja horaria; el motor compara preferencias en la zona local de la sede. Las ofertas expiran, se reofrecen sin duplicar citas y, al aceptar, reagendan la cita previa de forma atómica; si el turno ya se ocupó, la cita previa se conserva. Una oferta sin consentimiento aparece como llamada pendiente. Verificación vigente: 48 pruebas de integración, suite frontend 442/442 y recorrido E2E 55/55; sin enviar mensajes externos. | `backend/app/modulos/lista_espera/`, `frontend/src/app/paginas/lista-espera/lista-espera.component.ts`, `pruebas-e2e/escenarios/09-lista-espera.spec.ts`, `docs/test-plan.md` |
| Resumen operativo local | Quien tiene `dashboard.leer` puede generar un resumen determinista de citas, inasistencias, espera y pagos pendientes sin clave ni llamada externa. Solo incluye agregados del ámbito autorizado; los importes requieren además `pago.leer`. Describe señales y acciones administrativas, sin inferir causas ni dar recomendaciones clínicas. | `backend/app/modulos/dashboard/analisis_local.py`, `backend/app/modulos/dashboard/rutas.py`, `frontend/src/app/paginas/panel/panel.component.ts` |
| Análisis opcional con IA | Un usuario con `dashboard.leer` y `configuracion.escribir` puede solicitar análisis operativo con Anthropic. Solo se envían métricas agregadas del periodo seleccionado; se excluyen nombres, identificadores y adherencia clínica. Se requiere la integración Anthropic habilitada y una clave configurada. El análisis queda auditado, no ejecuta acciones ni ofrece decisiones clínicas. | `backend/app/modulos/dashboard/rutas.py`, `frontend/src/app/paginas/panel/panel.component.ts` |
| Notificaciones en la aplicación | La campana de la cabecera agrupa tareas reales del día: turnos por vencer, citas sin confirmar y ofertas de lista de espera sin avisar. La cola de llamadas se refresca cada 60 segundos mientras la aplicación está abierta y al abrir la campana; usa el total filtrado por ámbito de la API. Cada aviso enlaza a la pantalla operativa correspondiente. No envía mensajes al paciente. | `frontend/src/app/app.component.html`, `frontend/src/app/nucleo/servicios/pendientes.service.ts` |
| Métricas operativas | `GET /metrics` exporta solicitudes HTTP por patrón de ruta, duración y gauges agregados del outbox; no expone identificadores ni contenido clínico. El perfil local opcional `observabilidad` ejecuta Prometheus con retención de 15 días y cuatro reglas; se verificó que el objetivo Windows/WSL está `UP`. En producción requiere `METRICAS_TOKEN` bearer y red privada. Faltan Alertmanager, destinatarios, señales de auditoría/Redis y una puesta en producción. | `backend/app/nucleo/metricas.py`, `backend/app/api/middleware.py`, `backend/app/main.py`, `infra/prometheus/`, `infra/wsl/observabilidad.sh`, `docs/monitoring.md` |

### Estado de la instancia local

**Verificación local (2026-10-06):** la UI responde en `localhost:4200`; la API actual en `127.0.0.1:8000`
responde `listo` y publica en OpenAPI la exportación de Agenda, las rutas de gestión de consultorios,
especialidades y servicios, y configuración de horarios y feriados. El endpoint de readiness
comprueba la conexión con PostgreSQL. `infra/scripts/demo-local.ps1` verifica la ruta
`/api/v1/agenda/resumen.csv` en OpenAPI para detectar procesos desactualizados. La corrida E2E
completa del 2026‑10‑06 anterior a los nuevos flujos de pagos y anamnesis aprobó 39/39 en esos puertos,
con `LIMITE_LOGIN_POR_MINUTO=200` solo en el proceso de pruebas;
el límite normal de desarrollo sigue en 10. La pantalla de sedes se accede desde Configuración con el permiso
`sede.gestionar`; los cambios quedan auditados y limitados al ámbito asignado.

Cuando se agrega o cambia un permiso del sistema, sincroniza el catálogo y los roles con
`cd backend; uv run python -m app.semillas.cargar --solo-catalogos`. El proceso es idempotente
y no vuelve a cargar los datos clínicos sintéticos.

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
| Equipo y disponibilidad por profesional | En `/equipo`, `profesional.gestionar` habilita crear, editar y desactivar perfiles, asignarlos a varias sedes y definir su sede principal, especialidad, disponibilidad, datos de contacto y preparación; cada cambio se audita y respeta los ámbitos. En `/usuarios`, `rol.asignar` permite vincular una cuenta a un único perfil activo de la misma clínica, listar perfiles libres y cambiar el vínculo liberando la ficha anterior. En `/pacientes`, los permisos separados `paciente.crear` y `paciente.editar` habilitan el CRUD administrativo auditado e idempotente. En `/configuracion` se mantienen las franjas semanales por profesional, su vigencia y duración de cita, que el motor aplica en hora local. Las comisiones siguen pendientes. |
| Recordatorios y respuestas de WhatsApp | Las citas confirmadas crean avisos durables de 24 h y 3 h. Las recetas confirmadas crean avisos genéricos para tomas futuras de pauta fija; los PRN no se programan, y suspender la receta o registrar la toma invalida los avisos pendientes. El worker exige el consentimiento específico de medicación y enlaza al acceso mediante FRONTEND_URL. La entrega real a Meta sigue pendiente y las credenciales por clínica aún necesitan adaptador por clínica. |
| Bandeja de atención de WhatsApp | Los mensajes entrantes derivados a una persona se listan en `/conversaciones`, con permisos `conversacion.leer`, ámbito de clínica/paciente y nivel N2, más auditoría de conteo, listado y detalle. Incluye insignia de pendientes y notificación global. Es de solo lectura; responder requiere el proveedor real y sus controles de ventana/plantillas. |
| Fichas, búsqueda e historial de pacientes entre sedes | CRUD y búsqueda segura de pacientes existen. Hay aislamiento por clínica/ámbito. Compartir una ficha entre clínicas o sedes debe ser una política explícita con permiso y auditoría; no asumir intercambio global. |
| Historia clínica con Formulario 033 MSP, anamnesis configurable y exportación PDF | Notas de evolución versionadas existen. Profesionales con relación asistencial ya pueden registrar alergias y antecedentes desde el resumen clínico; las alergias duplicadas activas se rechazan, su desactivación conserva el motivo y ambas operaciones quedan auditadas. Notas, antecedentes, recetas, imágenes clínicas, versiones del odontograma y planes dentales pueden clasificarse N3; los procedimientos heredan el nivel del plan. El backend exige `historia_clinica.leer_sensible`, filtra los datos en SQL y audita el nivel real. La migración `20261006_024` añade sensibilidad al odontograma y la `20261006_025` a planes y procedimientos asociados; resumen, indicadores y fotos vinculadas respetan el filtro N3. El diseñador propio de anamnesis permite crear, versionar y publicar preguntas configurables por clínica y registrar respuestas inmutables, con vínculo asistencial, auditoría y control N3; no sustituye el Formulario MSP 033. La captura A–P versionada tiene lectura, alta, corrección inmutable e historial con relación asistencial y permiso N3. Su copia clínica imprimible A4 de dos páginas solicita auditoría del servidor antes de abrirse y permite imprimir o guardar desde el navegador. Faltan el cotejo del diseño con el anexo oficial y revisión institucional; no se afirma validez jurídica. Ver [`docs/formulario-033-fuentes.md`](docs/formulario-033-fuentes.md). |
| Odontograma interactivo FDI, hallazgos por pieza/cara e historial | API versionada con auditoría y control de relación asistencial; mapa inicial integrado en historia clínica. Las superficies de la pieza seleccionada son accesibles por teclado con flechas y activación Enter/espacio; el formulario ofrece una alternativa. Pruebas de componente cubren permisos, historial, conflictos, edición y navegación por caras; falta ampliar vocabulario y cubrir E2E. Ver `docs/plan-modulo-dental.md` y E‑35 en `docs/known-limitations.md`. |
| Planes dentales, plantillas, presupuesto y progreso por procedimiento | API e interfaz auditadas para crear/proponer planes, registrar constancia del documento firmado en la clínica, completar/cancelar procedimientos con actualización versionada del odontograma, usar plantillas y registrar controles. Cada plan y sus procedimientos admiten N2/N3; N3 exige permiso sensible, se filtra también del resumen, indicadores y fotos vinculadas, y no activa avisos automáticos por fases. Los planes propuestos o aceptados generan una vista de presupuesto con clínica, paciente, referencia estable, procedimientos, piezas, importes y total, imprimible o guardable a PDF. La clínica se consulta bajo el permiso del plan y sin exponer su identificación fiscal. Desde el plan se agenda cada procedimiento de la siguiente fase; la cita valida clínica, paciente, servicio y estado, y queda vinculada atómicamente. Impide una cita activa duplicada y libera el vínculo al cancelar. API y E2E cubren el ciclo. Firma electrónica sigue pendiente. |
| Diario clínico, evolución y alertas de seguimiento posterior | Notas de evolución versionadas existen. El worker evalúa diariamente a las 09:20 (Ecuador) tomas omitidas de recetas confirmadas (mínimo 4, al menos 25 %); mantiene una sola alerta abierta por receta. La API limita lectura y atención por clínica, ámbito y relación asistencial, registra auditoría, y las notificaciones y pantalla de medicación muestran el seguimiento; las alertas de adherencia permanecen visibles aunque no haya tomas programadas en la ventana actual. El profesional puede programar y cerrar con auditoría un control posterior a procedimientos. Si no tiene relación asistencial, puede declarar una emergencia con motivo y obtener 30 minutos de acceso; el sistema notifica a administración dentro de la plataforma y registra la revisión. Siete frases explícitas sobre problemas con el tratamiento crean avisos persistentes, auditados y revisables desde conversaciones, sin desambiguar números compartidos. Aún faltan cobertura de expresiones libres y reglas de prioridad o escalado; confirmar revisión no clasifica gravedad ni resultado clínico. |
| Radiografías, fotos, documentos y galería clínica por paciente/pieza | La API y galería autenticada permiten cargar imágenes saneadas y cifradas, filtrar por tipo/pieza, volver a verlas con permiso/auditoría y anularlas con motivo; incluye foto de perfil separada. E2E de carga y visualización verificado. En desarrollo, sin ClamAV, quedan marcadas `NO_DISPONIBLE`; producción rechaza cargas hasta habilitar antivirus. Documentos generales requieren verificar sus endpoints y pantallas antes de darlos por cubiertos. |
| Recetas con membrete, PDF, QR y firmas | Crear y confirmar recetas, corrección firmada mediante nueva versión, historial inmutable y reemplazo de tomas futuras existen. Receta imprimible con marca de clínica, QR verificable y firma electrónica con validez jurídica no están implementados como la capacidad comercial descrita. |
| Consentimientos informados digitales por especialidad y firma en pantalla | La base contiene consentimientos generales para controlar comunicaciones. Plantillas de consentimiento clínico, firma del paciente/profesional y PDF trazable siguen pendientes. No confundir ambos tipos de consentimiento. |
| Comprobantes de pago | PDF/JPEG/PNG/WebP validados por contenido, escaneados con ClamAV cuando está habilitado, cifrados en el almacén y descargables solo dentro del ámbito autorizado; carga, listado y descarga auditados. En producción la carga falla cerrada si el antivirus no está disponible. |
| Presupuestos, abonos, saldos, cobros vencidos y reportes | Cada cita puede tener un cargo con total pactado, vencimiento opcional y varios pagos parciales. La interfaz y API muestran pagos confirmados, montos comprometidos y saldos; se pueden filtrar saldos vencidos según la fecha local de la sede y el sistema deja de marcarlos al quedar pagados. La campana de seguimiento incluye el recuento de cargos con saldo vencido para quien tiene `pago.leer` y apunta a Pagos; refresca al abrirse y aplica el ámbito del usuario desde la API. La fecha se fija y audita una sola vez; cargos antiguos no heredan fechas inventadas. Rechazar un pago libera el monto reservado. Se conservan historial inmutable y comprobantes cifrados. El presupuesto odontológico se imprime desde el plan propuesto/aceptado; Pagos ya ofrece CSV diario agregado por estado y método, con fechas locales por sede, doble permiso, filtro opcional de sede y auditoría, sin identidades. Faltan vigencia y condiciones configurables, presupuestos administrativos ajenos al plan, recordatorios enviados al paciente, saldos consolidados por paciente, contabilidad, facturación SRI y reportes financieros detallados/Excel/PDF. |
| Contabilidad de ingresos/gastos, caja y utilidad | El panel expone algunas sumas de pagos autorizadas. Libro de gastos, flujo de caja, conciliación y utilidad neta no existen todavía; no estimarlos a partir de pagos brutos. |
| Facturación electrónica SRI, notas de crédito y modos de prueba/producción | Pendiente. Requiere diseño fiscal, credenciales seguras, firma, homologación con proveedor autorizado y revisión legal/técnica ecuatoriana; no simular facturas autorizadas. |
| Inventario dental, movimientos, lotes, caducidad y proveedores | Pendiente. Hace falta definir catálogo, kardex, unidades, alertas, vencimientos y trazabilidad antes de crear indicadores. |
| Dashboard: producción, cobros, citas, pacientes nuevos, conversión, ocupación y gastos | Hay conteos por estado, pacientes distintos, inasistencia, espera promedio y alertas de pacientes en sala, pagos por estado y carga diaria. Nuevos pacientes, embudo de presupuestos, conversión, horas disponibles, gastos y ganancias requieren datos/modelos que aún no existen. |
| Estadísticas de agenda: horarios pico, tasas y tendencias | Parcial: conteos por estados y comparativa de inasistencia. Distribución por día/hora, retención, cancelaciones comparables y tendencias confiables requieren consultas y definiciones métricas adicionales. |
| Segmentación de pacientes, retención, demografía y tratamientos populares | Pendiente en dashboard. No enviar atributos clínicos a campañas ni usar diagnóstico/tratamiento para publicidad. Definir base legal y consentimiento antes de segmentar. |
| Productividad y exportes Excel/CSV/PDF | La Agenda exporta un resumen CSV por fecha local y estado; Pagos exporta el resumen financiero por fecha local, estado y método. Ambos requieren permiso de lectura del módulo y `reporte.exportar`, aplican el ámbito del servidor, no incluyen pacientes y dejan auditoría. Reportes detallados, Excel/PDF y más cortes siguen pendientes. | `backend/app/modulos/agenda/rutas.py`, `backend/app/modulos/pagos/rutas.py`, `frontend/src/app/paginas/agenda/`, `frontend/src/app/paginas/pagos/` |
| Ajustes de marca, logo y preferencias por clínica/sede | Perfil institucional, integraciones y catálogo de especialidades, servicios y consultorios están disponibles. Subida de logo, aplicación en documentos, preferencias funcionales y configuración heredada por sede están pendientes. |
| Ortodoncia, endodoncia, periodoncia y armonización facial | Pendientes como módulos clínicos especializados. El soporte dental común (odontograma/planes) es base de dominio, no sustituye formularios ni flujos específicos de cada especialidad. |
| Varias clínicas/sucursales, recursos y políticas de pacientes compartidos | El portal aprovisiona clínicas y sedes y puede limitar cada cuenta a sedes concretas dentro de sus roles. Los datos están aislados por clínica. La gestión de consultorios permite crear, editar y activar/desactivar dentro de las sedes autorizadas, con auditoría. Sigue pendiente una política explícita de pacientes compartidos entre sedes. |
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

El inventario de ilustraciones, iconos y animaciones de interfaz está en
[`docs/recursos-visuales.md`](docs/recursos-visuales.md). El panel usa un fondo panorámico
optimizado, halos de movimiento lento que respetan movimiento reducido, y la biblioteca SVG
incluye iconos de agenda, ubicación, pulso, historial, equipo clínico y comunicación segura.
Atención de mensajes muestra una ilustración de bandeja al día, con animación suave accesible.
El estado inicial del seguimiento usa una nueva ilustración SVG liviana de clínica conectada;
el menú móvil y los indicadores de tendencia usan pictogramas vectoriales de ClinicAI. La base de
conocimiento incorpora una portada panorámica de documentos protegidos y un flujo de revisión
con iconos SVG; su halo de fondo respeta `prefers-reduced-motion`. El inventario y los prompts
visuales están documentados en [`docs/recursos-visuales.md`](docs/recursos-visuales.md).

Para reparar una base local ya poblada donde el profesional local no tenga una historia
versionada visible, ejecutar desde `backend`:

```powershell
uv run python -m app.semillas.cargar --solo-historia-clinica
```

Esta carga es sintética, se limita a local/desarrollo y no duplica pacientes ni citas.

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

El 6 de octubre de 2026 se ejecutaron `npm run lint`, `npm run build` y `npm run test:ci`
después de añadir navegación por teclado a las superficies del odontograma, el reporte financiero
en Pagos, el registro de alergias/antecedentes y el control N3 de la anamnesis. Esa suite aprobó 406 pruebas.
Cobertura: 87,56 % de líneas, 71,12 % de ramas, 80,45 % de funciones y 85,77 % de sentencias. La compilación inicial termina
en 451,55 kB. La prueba
focalizada recorre caras con las flechas y registra el hallazgo con Enter; el spec del servicio
de recorrido de agenda ahora comprueba también los métodos HTTP de sus nueve rutas.
La suite backend completa más reciente, ejecutada antes del reporte financiero,
aprobó 1682 pruebas y omitió 3 integraciones que requieren Anthropic; la cobertura total fue
87,65 %. Esa corrida precede a los cambios recientes. Ruff lint, formato y mypy pasan,
`alembic check` no detecta operaciones nuevas y 32 pruebas focalizadas de archivos y pagos pasan
tras las correcciones de tipos. El reporte financiero pasó 9 pruebas API y la gestión de
anamnesis 6 pruebas API focalizadas con sensibilidad N3 y redacción local; Ruff y mypy de Historia pasan.

**Actualización de sensibilidad clínica (2026-10-06):** migraciones `20261006_022` a `20261006_025` cubren notas, recetas, odontogramas y planes dentales; las imágenes clínicas también admiten N3 con permiso para carga, lectura y descarga. Los procedimientos heredan el nivel del plan. Resumen, indicadores, agenda y fotos vinculadas respetan el filtro; redacción local excluye planes N3 incluso con permiso sensible, y los avisos automáticos por fase se omiten. Las suites API de planes, resumen, métricas, imágenes y agenda pasaron **83/83**. Frontend **441/441**, lint y build; Ruff, mypy y `alembic check` pasan. Detalle en `docs/test-plan.md`.

**Actualización de RAG (2026-10-06):** detecté y corregí una exposición donde una versión recién cargada podía responder antes de su aprobación. La migración `20261006_026` añade la marca de versión vigente a los fragmentos; el filtro de recuperación sigue en SQL y en la misma tabla. La interfaz ahora exige retirar documentos aprobados/publicados a borrador antes de cargar cambios. El flujo automatizado verifica la aprobación de la nueva versión y que el RAG no recupere las anteriores. Suites de conocimiento/RAG **83/83**, frontend **442/442**, lint y build pasan. La ingesta durable reanudable continúa pendiente.

En la continuación del 2026-10-06 se añadió el diseñador de anamnesis configurable por clínica.
`/configuracion` ofrece borradores, edición, publicación y creación de versiones; en el resumen
clínico, «Abrir formularios de anamnesis» carga los formularios publicados solo cuando se solicita.
La API está en `backend/app/modulos/historia/anamnesis_rutas.py`: exige rol administrativo para
configurar, profesional y relación asistencial para capturar, permiso de lectura clínica para
consultar; N3 además exige `historia_clinica.leer_sensible`. Las preguntas publicadas y las
respuestas guardadas son inmutables y auditadas. Las migraciones 018 y 019 están aplicadas;
la 019 permite retirar una versión publicada conservando su fecha. Las tres pruebas API
focalizadas pasan y `alembic check` no detecta diferencias de esquema. El diseñador de anamnesis es
propio y no reemplaza el Formulario oficial MSP 033. La captura del formulario tiene interfaz A–P,
historial, correcciones por versión y una copia imprimible A4 de dos páginas cuya exportación se
audita antes de abrirse. La captura permite vincular cita, nota, odontograma y control de placa
solo cuando el rol y el módulo habilitan su lectura; las citas ajenas al profesional, canceladas
y no asistidas no se ofrecen. No copia datos al seleccionar una fuente: el personal puede aplicar
el motivo y el relato subjetivo de una nota únicamente en campos vacíos. Las vinculaciones quedan
en el registro y se muestran en su detalle y en la copia. El odontograma y la placa se enlazan sin
convertir automáticamente sus hallazgos al formulario. Pendientes: cotejar la impresión con el
anexo oficial y obtener revisión institucional antes de afirmar validez jurídica.

La revisión de la frontera del agente ejecutó **137 pruebas locales**: 82 unitarias sobre el
catálogo y el límite clínico, 35 del webhook y 20 de integración del despachador contra PostgreSQL.

---

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `backend/` | API FastAPI, dominio, capa de IA, tareas, migraciones Alembic y pruebas |
| `frontend/` | Aplicación Angular 19 PWA |
| `infra/` | Dockerfiles, ficheros compose, aprovisionamiento de WSL2 y scripts; `infra/wsl/observabilidad.sh` inicia Prometheus local y descubre la puerta de enlace WSL |
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
| [`docs/agente.md`](docs/agente.md) | Las ocho herramientas, la frontera clínica y lo que aún falta |
| [`docs/backup-and-restore.md`](docs/backup-and-restore.md) | Respaldo cifrado y la restauración **ya verificada** |
| [`docs/monitoring.md`](docs/monitoring.md) | Qué vigilar y por qué; qué emite ya el sistema |
| [`docs/incident-response.md`](docs/incident-response.md) | Clasificación por daño al paciente y guías por tipo |
| [`docs/whatsapp-integration.md`](docs/whatsapp-integration.md) | Webhooks, plantillas y entrega |
| [`docs/calendar-integration.md`](docs/calendar-integration.md) | OAuth, sincronización y reconciliación |
| [`docs/deployment.md`](docs/deployment.md) | Despliegue local, staging, producción y rollback |
| `docs/backup-and-restore.md` | Respaldo y restauración verificada — **pendiente** |
| `docs/monitoring.md` | Exportación API y recolector/reglas locales verificados; Alertmanager, destinatario, guardia y monitoreo de producción — **pendientes** |
| `docs/incident-response.md` | Respuesta a incidentes — **pendiente** |
| [`docs/production-readiness.md`](docs/production-readiness.md) | Estado real frente a los criterios de producción |
| [`docs/test-plan.md`](docs/test-plan.md) | Qué se prueba, con qué, por qué de esa forma, y la evidencia de la última ejecución |
| [`docs/known-limitations.md`](docs/known-limitations.md) | Limitaciones y riesgos residuales |
| [`docs/backlog.md`](docs/backlog.md) | Backlog por fases con criterios de aceptación |
| [`docs/recursos-visuales.md`](docs/recursos-visuales.md) | Inventario de ilustraciones, iconos SVG y animaciones; incluye el estado visual del seguimiento inteligente |
| [`docs/decisiones/`](docs/decisiones/) | Registros de decisiones de arquitectura (ADR) |
| [`docs/informe-avance.md`](docs/informe-avance.md) | **Estado real del proyecto**, con los 18 puntos exigidos y sus evidencias |

---

## Licencia y titularidad

Proyecto privado. Sin licencia de distribución definida.
