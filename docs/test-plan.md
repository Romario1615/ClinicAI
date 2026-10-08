# Plan de pruebas

## Faciograma visible y documentos desde la ficha (2026-10-07)

Frontend **635/635**, lint y build aprobados; cobertura 86,19 % sentencias,
73,62 % ramas, 81,46 % funciones y 88,65 % líneas. Chromium **67/67 en 7,7 minutos**:
pestañas directas, cita conservada, faciograma versionado/anulado y visible a
1440/768/390 px, axe en su ficha y en las 22 rutas, presupuesto/cotización/receta
con PDF real y entrega sandbox. La prueba de equipo también edita identidad,
quita/restaura acceso y comprueba que no se pierde el perfil profesional.

La API de desarrollo 8000/4200 se verificó mediante navegador sin escrituras
clínicas. El administrador habilitó el módulo facial para su especialidad
odontológica mediante la API versionada. Las escrituras del navegador se
hacen en la base E2E exclusiva. Los cuatro recorridos de documentos se repitieron
con la API reiniciada y la corrección de N3: **4/4 en 46,3 s**.

Backend: **73/73** de las rutas locales/RAG, semillas y manuales con el entorno
de CI; **2/2** unitarias del conteo de recetas de semillas; **2/2** API para
copias sensibles de recetas. Las regresiones nuevas se reprodujeron fallando
antes del arreglo. La corrida global posterior aprobó **1921 pruebas y omitió
tres de Anthropic real en 10 min 36 s**, con ENTORNO=desarrollo, otra BD temporal
y proveedores mock/sandbox. Se ejecutó sin cobertura; no se atribuye una medida
nueva de cobertura backend a esta corrida. Las dos bases desechables se retiraron.
[Informe y estado de CI](verificacion-2026-10-07.md#faciograma-visible-y-documentos-desde-la-ficha).

## CRUD, faciograma y documentos (2026-10-07)

La ampliación añade regresiones de clínica/cuenta, versionado y anulación de
registros, mapa facial, generación de PDFs, recetas confirmadas, presupuesto
desde plan, enlaces privados, identidad/caducidad/intentos y consentimiento.
Se prueba SQL directo contra PostgreSQL para impedir actualización de contenido
y borrado. El worker se ejecuta únicamente sobre el mensaje sintético del caso,
con adaptador sandbox; no se vacía ni procesa la cola de desarrollo completa.

Tres recorridos Chromium prueban CRUD administrativo, documento desde la ficha
con cita y mapa facial con teclado, PDF y límites a 1440/768/390 px. Los manuales
se comprueban por rol, permisos, rutas y ausencia de secciones repetidas.
El ciclo `031` se verificó en una BD vacía: upgrade, downgrade a `030`, upgrade
y `alembic check`; los datos del navegador viven en una BD temporal separada.
Regresión final: backend 1917 aprobadas/3 omitidas y frontend 632/632;
Chromium **66/66 en 7,8 minutos**, con seis roles y axe en las 22 rutas;
lint, formato, mypy, Bandit `-ll` y build pasan. El 87,37 % de cobertura backend
corresponde a la primera corrida, que encontró dos expectativas antiguas luego
corregidas; la repetición completa se hizo sin cobertura. Resultados del navegador
y comandos en [el informe](verificacion-2026-10-07.md#crud-faciograma-y-documentos).

> **Corrección posterior de «Perfil de pacientes» (2026-10-07):** frontend completo **609/609 en 84 archivos**, cobertura 86,13 % sentencias, 72,88 % ramas, 81,60 % funciones y 88,32 % líneas; lint y build aprobados. Chromium focalizado **2/2**: axe del panel y comprobación geométrica de la tarjeta en siete anchos de 320 a 1440 px, con etiquetas largas, valores grandes y «Protegido». El escenario visual usa un desglose agregado sintético sobre la respuesta del dashboard para reproducir esos extremos; la sesión y el resto de la API son reales. [Cambio y comandos](verificacion-2026-10-07.md#corrección-posterior-del-perfil-de-pacientes). La corrida completa E2E anterior de 62/62 se conserva como evidencia separada.

> **Verificación actual tras actualizar desde GitHub (2026-10-07):** rama `claude/friendly-gates-o240sb`, base `727c9f5`. Frontend **605/605**, 83 archivos; cobertura: sentencias 86,12 %, ramas 72,88 %, funciones 81,60 %, líneas 88,31 %. Lint y build pasan, paquete inicial 462,85 kB. Chromium **62/62 en 6,9 minutos**, sin reintentos, contra API y BD temporal aisladas; axe cubre diez recorridos, seis roles y 22 rutas. Incluye formularios, ventanas, persistencia clínica/administrativa, 320/390 px y acciones fijas en escritorio. Backend completo: **1855 aprobadas y 3 omitidas** (Anthropic real), **87,89 % de cobertura**, 19 min 39 s. Contrato/métricas 8/8; Ruff, formato, mypy y Bandit `-ll` pasan. Los seis roles entran, abren su manual propio y salen también en los servicios de desarrollo. Las migraciones `029` y `030` están encadenadas y se verificaron también sobre una base vacía con `upgrade`, reversión y `alembic check`. [Cambios, entorno y comandos](verificacion-2026-10-07.md). Las cifras de ejecuciones previas se conservan como registro histórico.

> **Cierre de puertas locales anterior (2026-10-07):** Frontend: `npm ci`, `npm run test:ci` (538/538; sentencias 86,04 %, ramas 72,82 %, funciones 81,17 %, líneas 88,30 %), lint y TypeScript pasan. El build de producción compila, con un aviso no bloqueante de presupuesto inicial: 502,66 kB frente a 500 kB. `app.routes.ts` es composición declarativa y queda excluido del denominador de cobertura; los guardias se prueban por ruta en `app.routes.spec.ts`. La repetición global más reciente del backend con `pytest -q` aprobó 1806 pruebas y omitió 3 de Anthropic por requerir credenciales; una corrida anterior con cobertura midió 87,45 % (mínimo 80 %). La suite API de autenticación actual pasa 40/40. La primera corrida global había encontrado una aserción basada en un sufijo aleatorio de clínica; se corrigió y la repetición completa pasó. Las suites focalizadas previas registran 835 unitarias, 908 API/integración, 15 de concurrencia y 679 de seguridad. `pip-audit`, Ruff (lint y formato), mypy y Bandit (`-ll`) pasan. Los dos Dockerfiles construyen; Trivy con el mismo umbral CI (`HIGH,CRITICAL`, `ignore-unfixed`) no encuentra hallazgos corregibles tras retirar setuptools global no usado del runtime. Gitleaks sobre todo el historial no encuentra secretos después de revisar y registrar coincidencias sintéticas de pruebas. La corrida CI completa aún queda por ejecutar en una sola pasada. Las 3 pruebas de LLM real no se llamaron.

> **Rotación de sesiones (2026-10-06):** la suite de autenticación API e integración aprobó 70 pruebas. Comprueba encadenamiento, invalidación del refresco anterior, detección de reutilización, revocación de toda la familia, rechazo del par sucesor y evento de auditoría de alerta. No requiere servicios externos.

> **Segundo factor y control de intentos (2026-10-06):** la suite de autenticación completa pasó 71/71. Una prueba API confirma que un rol que exige TOTP no recibe sesión sin configurarlo; integración cubre código válido/inválido y auditoría. El bloqueo de cuenta y el limitador por IP comprueban 429/`Retry-After`, el bloqueo aunque se envíe la contraseña correcta y la recuperación al expirar.
>
> **Contraseñas (2026-10-06):** 63 pruebas unitarias/API comprueban hash Argon2id, verificación, sal, parámetros antiguos con rehash, límites, política de creación y que una clave rechazada no se almacena ni se devuelve.
>
> **Configuración (2026-10-06):** `test_configuracion.py` pasó 53/53; producción rechaza secretos ausentes o débiles, valores de ejemplo, proveedores simulados, CORS inseguro y variables desconocidas antes de construir la aplicación.

> **IDOR en Pagos (2026-10-06):** `test_comprobante_se_valida_cifra_audita_y_se_descarga_dentro_del_ambito` verifica control positivo dentro de la sede y respuestas 404 al salir de ámbito para el contenido, listado de comprobantes e historial. Módulo de pagos API: 9/9 pruebas.

> **Aislamiento entre clínicas en Automatizaciones (2026-10-06):** `test_el_estado_de_automatizaciones_no_se_cruza_entre_clinicas` autentica usuarios de dos clínicas y verifica que apagar un flujo en una no modifica el valor que consulta la otra. `test_automatizaciones_api.py`: 4/4, Ruff y formato aprobados. No requiere proveedores de mensajería.

> **Auditoría append-only (2026-10-06):** tres pruebas de integración envían `UPDATE`, `DELETE` y `TRUNCATE` directamente a PostgreSQL y verifican que los disparadores rechazan cada operación con SQLSTATE `42501`. La migración `20261006_028` quedó aplicada; `alembic check` no detecta cambios de esquema faltantes. La separación del rol runtime respecto al propietario del esquema sigue pendiente para producción.

> **Migración de frontend (2026-10-07):** desde una instalación limpia de Angular 22.2.1, `npm ci` y `npm audit --audit-level=high` terminan con cero vulnerabilidades; `npx tsc --noEmit`, `npm run lint` y `npm run build` pasan. Tras los cambios de interfaz, `npm run test:ci` aprobó 452/452 pruebas Vitest con cobertura de 86,51 % sentencias, 74,37 % ramas, 81,02 % funciones y 88,36 % líneas, superando los mínimos (80/70/80/80). El build aún imprime un aviso no bloqueante por superar en 1,16 kB el presupuesto inicial de 500 kB. CI ejecuta el mismo comando, sin Chromium. La suite corre aislada por archivo para mantener limpio TestBed; tres pruebas que usaban `fakeAsync` se adaptaron a temporizadores Vitest. No se conectaron APIs externas.

> **Interfaz liquid glass y formularios (2026-10-07):** superficies de interacción con transparencia y blur, controles y tablas densas con opacidad suficiente; menú móvil flotante con fondo de cierre, Escape y tratamiento de anchos pequeños. E2E comprueba sin desbordamiento horizontal a 320 y 390 px, cierre por teclado/fondo y auditoría axe WCAG 2.2 A/AA en ese menú. El panel concentra sus siete filtros en una ventana flotante Liquid Glass, presenta el total de filtros activos y conserva el filtro de fechas en la zona horaria seleccionada; E2E verifica cierre por Escape, ausencia de desbordamiento a 320/390 px y axe sobre el diálogo después de completar su animación de entrada. En Equipo, alta y edición del profesional se abren como diálogo modal y liberan el ancho para el listado; Vitest cubre apertura, datos precargados, cancelación y cierre con Escape, y axe analiza el formulario real. El formulario de reprogramación comparte la misma pieza modal y conserva su contenido al pulsar fuera.

> **Formularios de configuración Liquid Glass (2026-10-07):** el perfil de clínica, Anthropic, WhatsApp, Google Calendar, SMTP, JEV y proveedor de respuestas muestran tarjetas de estado y abren ventanas de edición accesibles. La cancelación revierte parámetros y limpia claves no enviadas; las claves existentes nunca precargan su valor. Las pruebas de Configuración e Integraciones IA pasan 11/11; la suite frontend completa, 516/516. El E2E de administración pasó 1/1 con axe WCAG 2.2 AA, cierre por Escape, perfil restaurado al cancelar, clave vacía tras reabrir y viewport sin desbordamiento a 390/320 px. Ese recorrido encontró y llevó a corregir un desbordamiento de 19 px en el encabezado móvil de Configuración. `npm run lint`, `npx tsc --noEmit` y `npm run build` pasan; sigue el aviso conocido de 1,16 kB sobre el presupuesto inicial.

> **Carga sintética completa y formularios Liquid Glass (2026-10-07):** la integración contra PostgreSQL invoca los valores predeterminados del generador y verifica 2 sedes, 4 especialidades, 8 profesionales, 60 pacientes y 200 citas; en el mismo escenario carga documentos sintéticos con embeddings locales y recetas por el servicio clínico. `test_semillas.py`: 31/31. La alta de campaña y el borrador del plan dental usan ventanas Liquid Glass centradas, con botones asociados al formulario para conservar el envío y validación nativa. El escenario E2E clínico completó el ciclo del plan (1/1), pasó axe WCAG 2.2 AA en el diálogo y confirmó que la página no se desborda a 390/320 px; ese chequeo llevó a corregir el encabezado de paciente en móviles y el ancho mínimo de títulos largos. Vitest frontend: 516/516 (86,52 % sentencias, 73,99 % ramas, 81,08 % funciones, 88,38 % líneas). `npm run test:a11y`: 10/10, con axe, Escape y pruebas móviles también para la campaña. Lint, TypeScript y build pasan; el presupuesto inicial sigue superado por 1,16 kB. No se conectaron proveedores externos.

> **Acceso local por rol (2026-10-07):** la API lista los seis roles solo cuando hay cuentas sintéticas activas del rol base; el inicio resuelve la cuenta en el servidor, audita `login.rol_local` y rechaza accesos locales en preproducción/producción. Las pruebas confirman además que cuentas normales, inactivas y roles de clínica no aparecen, y que el segundo factor queda satisfecho solo dentro de la sesión local sintética. `test_autenticacion_api.py`: 40/40; incluye el acceso de los seis roles. La E2E `14-accesibilidad.spec.ts` inicia sesión con los seis y revisa las 20 rutas visibles.

> **Guardias de navegación (2026-10-07):** `app.routes.spec.ts` recorre las 18 rutas de trabajo: comprueba autenticación, segundo factor, acceso positivo para cada permiso alternativo declarado y redirección al faltar permiso. También confirma que la consola de clínicas rechaza al administrador de clínica y deja pasar al superadministrador. Son pruebas de navegación, no controles de datos: la API conserva autorización y filtro de ámbito por clínica/sede. `npm run test:ci`: 59 pruebas nuevas; suite completa 516/516. `npm run test:a11y` aprobó 10/10 recorridos en navegador real; los seis roles visitan las 20 rutas de menú sin infracciones axe. La configuración excluye `src/app/app.routes.ts` del umbral porque la tabla es declarativa y Angular instrumenta cada cargador diferido como función sin ejecutarlo en esas pruebas; las funciones de guardia sí quedan cubiertas por las pruebas de contrato.

> **Formularios administrativos Liquid Glass (2026-10-07):** altas y ediciones de consultorios, especialidades, servicios, horarios de sede, feriados, disponibilidad profesional, bloqueos y registro de abonos se abren en ventanas flotantes accesibles; las listas mantienen el ancho completo. El borrado de horarios y franjas tiene confirmación propia. Los bloqueos que coinciden con citas activas muestran un diálogo de confirmación con solo el total, sin datos de pacientes. Vitest frontend: 452/452; lint, TypeScript y build pasan. `npm run test:a11y` aprobó sus 10/10 pruebas: axe comprueba los diálogos de catálogo, configuración y abonos; Escape los cierra; el menú recorre las secciones visibles por rol. El viewport móvil de 320/390 px se verifica en el menú, filtros del dashboard y formulario de abonos.

> **Lectura segura de DOCX (2026-10-07):** el XML contenido en archivos aportados por usuarios se analiza con `defusedxml`; una regresión con declaración DTD y entidad externa confirma el rechazo controlado. Suite DOCX: 7/7; pruebas de archivos relacionadas: 17/17; Ruff, mypy y Bandit completo (`-ll`) pasan, con cero hallazgos medianos/altos.

> **Actualización de dependencias Python (2026-10-07):** `pip-audit` detectó 24 avisos en PyJWT 2.13.0, pypdf 6.18.0, urllib3 2.7.0 y Werkzeug 3.1.8. El lock se actualizó dentro de las restricciones del proyecto a PyJWT 2.15.1, pypdf 6.19.0, urllib3 2.8.0 y Werkzeug 3.1.9; la auditoría del lock resultó limpia. En entorno aislado pasan 835 unitarias, 908 API/integración, 15 de concurrencia y 679 de seguridad; la repetición global más reciente con `pytest -q` terminó con 1806 pruebas aprobadas y 3 omitidas. Una corrida anterior con cobertura registró 87,45 %. Las pruebas omitidas requieren credenciales de Anthropic; no se llamó a proveedores externos. Ruff, formato, mypy y Bandit pasan. Una aserción de texto con falso positivo por sufijo aleatorio quedó corregida y la repetición global completa pasa. Las imágenes Docker de backend y worker pasan Trivy sin hallazgos HIGH/CRITICAL corregibles.

> **Vidrio líquido, Motion, Ayuda y Gastos (2026-10-07):** frontend `npm run test:ci` **491/491** (80 archivos; sentencias 86,80 %, ramas 74,70 %, funciones 81,71 %, líneas 88,50 %), `ng lint` sin hallazgos y build con chunk inicial de 450,56 kB. Nuevas pruebas de componente para la coreografía de movimiento, el motor (con `Element.animate` simulado), el servicio con y sin `prefers-reduced-motion`, el contador, el gráfico en movimiento, la salida animada de ventanas, Ayuda y Gastos. Backend: **861 unitarias** (26 nuevas sobre los manuales: unicidad de títulos y pasos, rutas existentes, ninguna sección clínica para roles administrativos, filtro por permisos efectivos), Ruff, formato, mypy y Bandit en verde; integración/API/concurrencia **925 aprobadas, 3 omitidas** (Anthropic real) y 8 del simulador que solo existen con `ENTORNO=local` (30/30 en esa corrida). `test_gastos_api.py` (12) cubre 401/403 auditados, idempotencia (repetición y conflicto 409), entrada inválida, IDOR por sede y clínica (404), anulación única, el disparador de PostgreSQL que rechaza `UPDATE`/`DELETE` directos y el cálculo del flujo; `test_ayuda_api.py` (7) cubre la ausencia de sesión, la persona sin roles vigentes, un manual distinto para recepción y profesional, el manual compuesto de un rol propio, que un rol de otra clínica no aporta manual y que los parámetros de la petición no cambian el resultado. Migración `20261007_029`: `upgrade`, `downgrade -1`, `upgrade` y `alembic check`. E2E **55/55** con axe en 22 rutas. Sin APIs externas: esas pruebas quedan pendientes.

> **RBAC y matriz de roles (2026-10-06):** la suite lee la tabla de `docs/security.md`, valida que cubra una sola vez todos los códigos de permiso del catálogo y compara la concesión con el backend, parametrizando los seis roles base. Esta comparación encontró omisiones y permisos clínicos/financieros descritos de forma más amplia que la implementación. Se corrigió la matriz sin modificar las concesiones. La suite `test_autorizacion.py` pasa 35/35; 15 casos verifican cobertura y decisiones de la matriz.

> **Cabeceras HTTP y CORS (2026-10-06):** 3 pruebas API recorren respuesta de salud, error 404 y preflight. Verifican las seis cabeceras de seguridad, correlación, credenciales, método y cabeceras permitidas, y que un origen ajeno no recibe `Access-Control-Allow-Origin`. Los 13 casos parametrizados de producción rechazan configuraciones inseguras, incluido `ORIGENES_CORS=*`.

> **Revocación de consentimiento (2026-10-06):** 26 pruebas de integración del outbox y 3 pruebas API de consentimiento pasan contra PostgreSQL. Una nueva regresión encola un aviso, revoca el consentimiento antes del procesamiento y verifica que el mensaje termina `DESCARTADO`, el adaptador no recibe ningún envío y el worker reporta el descarte. Ruff y formato pasan en los módulos afectados; el adaptador usado es sandbox.

> **Accesibilidad (2026‑10‑06):** axe-core WCAG 2.2 A/AA analiza cinco pantallas principales y todas las secciones del menú visibles para seis roles; una aserción exige la cobertura de las 20 rutas. Diez escenarios pasan sin infracciones. Se corrigieron contraste insuficiente en Conocimiento y Catálogo, y navegación por teclado de la tabla horizontal en Pagos. También se verifican salto al contenido, landmark único, grupo de roles nombrado y `aria-current="page"`. Frontend completo: **442/442**, lint y build pasan. Siguen pendientes estados interactivos adicionales y revisión manual con lector de pantalla y zoom.

> **E2E (2026‑10‑07):** la corrida completa aprobó **57/57 pruebas en 3,4 minutos** con frontend actual, API aislada en el puerto 8002 y PostgreSQL/Redis efímeros. Agenda prueba reservas simples y series semanales desde ventanas Liquid Glass; Historia clínica crea un plan y agenda su fase desde el mismo diálogo. Incluye el menú móvil a 320/390 px, sin desbordamiento horizontal; axe WCAG 2.2 A/AA recorrió las 20 rutas visibles de los seis roles sin infracciones. Ver `pruebas-e2e/README.md`.
>
> **E2E del diseñador de anamnesis (2026‑10‑07):** añadí al escenario de administración una comprobación de axe y desbordamiento móvil a 390/320 px para la nueva ventana Liquid Glass. `npx playwright test escenarios/14-accesibilidad.spec.ts --list` reconoce los 10 recorridos, pero no ejecuté el escenario contra navegador real: el daemon de Docker no respondió a `docker compose up` ni `docker ps`. Verifiqué que los puertos aislados 5433/6380 quedaron cerrados; no se usó la base ni la API de desarrollo. Ese bloqueo de infraestructura quedó superado en esta revisión: los diez recorridos de accesibilidad pasaron usando la API y una base temporal en PostgreSQL local.

> **Notas SOAP y recetas en ventanas Liquid Glass (2026‑10‑07):** crear y corregir notas, y redactar recetas, abre una ventana de alto completo sobre la historia clínica. El contenido clínico se desplaza dentro del vidrio; Guardar, Firmar y Cancelar quedan en el pie. Escape y Cancelar cierran sin enviar, y guardar cierra y actualiza la historia. Las pruebas de componentes de ambos editores pasan 8/8. Añadí E2E de axe WCAG 2.2 AA y viewport 390/320 px, pero no los he ejecutado contra navegador real porque Docker sigue sin responder; Playwright compila y reconoce 59 escenarios.

> **Delegaciones de firma Liquid Glass (2026‑10‑07):** el formulario que ocupaba la página se trasladó a una ventana centrada con lista de delegaciones visible, pie de acciones, Escape/cancelación y borrado del borrador al cerrar. Se valida que sean dos profesionales distintos, que ambas fechas existan y que el término no anteceda al inicio. La prueba del componente pasa 4/4; en esa verificación la suite completa frontend pasó 522/522. El E2E añade auditoría axe y comprobación a 390/320 px en el recorrido por roles; `--list` reconoce los 59 escenarios, esa ampliación se ejecutó después y pasó en la suite vigente de 62 escenarios contra una base temporal local.

> **Diseñador de anamnesis Liquid Glass (2026‑10‑07):** la administración de plantillas ahora abre en una ventana modal amplia; las preguntas se desplazan dentro del cuerpo y Guardar/Publicar/Cancelar permanecen en el pie. Se agrupan los campos de plantilla y la eliminación de una pregunta queda identificada para teclado/lectores de pantalla. Prueba de componente: 4/4.
>
> **Formularios clínicos en ventanas Liquid Glass (2026‑10‑07):** el alta de alergias, el registro de antecedentes y la desactivación con motivo se abren en ventanas modales. El pie conserva Guardar/Confirmar y cancelar o cambiar de paciente elimina el borrador sensible; las respuestas demoradas de otro paciente no sustituyen el resumen abierto. El componente `resumen-clinico.component.spec.ts` pasa 6/6, incluida la regresión de cancelación y cambio de paciente. En esa medición frontend pasó 522/522 (86,14 % sentencias, 73,44 % ramas, 80,99 % funciones, 88,12 % líneas); lint, TypeScript y build pasaron. El paquete inicial medía 501,22 kB (1,22 kB sobre el presupuesto). La auditoría axe E2E cubre las rutas y diálogos enumerados en la sección E2E; estas nuevas ventanas tienen verificación de componente.
> **Agenda y ocupación (2026‑10‑07):** PostgreSQL pasó 111 pruebas de servicio, API, gestión profesional y concurrencia; 62 pruebas unitarias cubrieron disponibilidad, Hypothesis y calendario local/DST; 3 pruebas validaron la ocupación del dashboard. Con la integración actual, el índice de series recurrentes usa `20261007_030` después de `20261007_029` (Gastos); la migración se valida de nuevo en la verificación registrada arriba. En la verificación de agenda, el frontend pasó 516/516, lint y TypeScript; el build de producción generó el paquete, con un aviso de 1,22 kB sobre el límite inicial de 500 kB. No se llamaron APIs externas.

> **Continuación de verificación y sedes Liquid Glass (2026‑10‑07):** la suite unitaria actual del backend aprobó **858/858**; la prueba focalizada de series y ocupación aprobó **6/6**. Editar sede ahora abre una ventana Liquid Glass con pie fijo, cancelación explícita y mensajes de error dentro del diálogo; sus pruebas cubren apertura, guardado, cancelación y fallo de API. En esa medición la suite frontend aprobó **528/528**, con 85,95 % de sentencias, 72,75 % de ramas, 80,98 % de funciones y 88,14 % de líneas; lint y build pasaron (el bundle inicial medía 501,28 kB, 1,28 kB sobre el límite). Docker Desktop informa `stopped`; `docker desktop start` indica que ya se está ejecutando, pero el servicio `com.docker.service` no se puede iniciar desde esta cuenta por permisos. Por eso no se corrieron los 59 escenarios E2E actuales ni se tocaron la API o base de desarrollo. Al recuperar el motor Docker, ejecutar de nuevo E2E.

> **Portal global Liquid Glass (2026‑10‑07):** el registro de clínica, alta de sucursal, creación de cuenta y asignación de roles/sedes del superadministrador se abren en ventanas flotantes con pie fijo; cancelar elimina el borrador y los errores se presentan dentro del diálogo. El E2E de aprovisionamiento se actualizó para usar esas ventanas; `npx playwright test --list` reconoce 59 pruebas en 14 archivos. Cinco pruebas de componente verifican cancelación, limpieza, alta de clínica, alta de sede y asignación. El navegador E2E espera que Docker vuelva a iniciar.

> **Formulario MSP 033 en Liquid Glass (2026-10-07):** la captura versionada se abre en un diálogo centrado de alto completo y hasta 1440 px, con scroll interno, acciones persistentes, sin cerrar al pulsar fuera y con Escape bloqueado durante el guardado; los errores del servidor se muestran dentro para permitir corregirlos y Cancelar limpia el borrador y los avisos. Vitest focalizado aprobó 13/13 comprobaciones funcionales y la suite completa `npm run test:ci` aprobó 534/534 con sus umbrales globales. Playwright enumera el nuevo recorrido de axe, Escape y viewports 390/320 px dentro de 60 escenarios en 14 archivos. Las pruebas de backend para el esquema MSP 033, ocupación y series aprobaron 14/14; no se pudo ejecutar el navegador porque `com.docker.service` está detenido y la cuenta no puede iniciarlo.

> **Ventanas Liquid Glass y accesibilidad (2026‑10‑07):** el componente modal devuelve el foco al control que lo abrió, atrapa Tab/Mayús+Tab entre controles visibles, omite controles ocultos, cierra con Escape cuando está permitido y desactiva animaciones si el sistema solicita movimiento reducido. Las pruebas de `ventana-flotante.component.spec.ts` cubren el ciclo del foco, el cierre y la navegación por teclado, incluidos elementos ocultos. Suite frontend: **538/538**, cobertura 86,04 % sentencias, 72,82 % ramas, 81,17 % funciones y 88,30 % líneas; lint pasa y build compila con aviso de 2,66 kB sobre el presupuesto inicial.
> **Capturas clínicas en ventanas Liquid Glass (2026‑10‑07):** la captura de anamnesis, la carga de imágenes y la redacción/anulación de indicaciones se abren sobre la ficha con pie de acciones fijo. Cancelar limpia el borrador clínico sin enviar la solicitud y conserva visible el historial; los fallos de carga permanecen dentro del diálogo para permitir corregirlos. Las pruebas focalizadas aprobaron 14/14 entre los tres componentes. La suite global de frontend se repitió después de estos cambios.

> **Suite completa de componentes (2026‑10‑06):** `npm run test:ci` ejecutó **442/442 pruebas** con Chromium Headless CI. Cobertura global: sentencias 85,71 %, ramas 72,94 %, funciones 80,95 % y líneas 87,61 %, por encima de los mínimos 80/70/80/80 que aplica Karma. La ejecución focalizada de un solo componente no sirve para medir el umbral global; la suite completa sí lo satisface.

> **Lista de espera (2026‑10‑06):** las suites `test_lista_espera.py`, `test_tareas_lista_espera.py` y `test_aviso_oferta.py` aprobaron **48/48 pruebas de integración** contra PostgreSQL. Cubren prioridad y preferencias de pacientes, control de ámbito, expiración al límite exacto, reoferta sin duplicar citas, aceptación/rechazo, preservación de la cita previa si el turno se ocupa, consentimiento y cola de avisos no comunicados. La suite frontend completa aprobó **442/442** en esa revisión, incluidas las 8 pruebas del componente. El escenario `09-lista-espera.spec.ts` está incluido en la suite E2E actual 57/57 y verifica alta, oferta y reagendamiento en navegador; no envía WhatsApp real. La comunicación depende del proveedor configurado y requiere consentimiento.

> **Privacidad de logs (2026‑10‑06):** `test_registro.py` aprueba **55/55**. La prueba nueva emite una excepción por las rutas reales de logging con cédula, correo y teléfono en su mensaje, además de un campo `nombre`; verifica la salida JSON completa, la presencia del tipo de excepción y la ausencia de esos datos, conservando el UUID del paciente para depuración. Las pruebas también cubren eventos de structlog y registros de SQLAlchemy.

> **Dashboard (2026‑10‑06):** la suite frontend completa aprobó **435/435**, además de lint y compilación de producción. `PanelComponent` verifica rangos/filtros y presenta métricas; las tendencias conservan etiquetas y valores en listas accesibles, con carga, error sin cifras obsoletas y estados vacíos. Las pruebas focalizadas backend aprobaron **17 casos**, más Ruff y mypy. RF‑Q03 cubre cancelación, oferta aceptada y tiempo de recuperación. RF‑Q06 verifica permiso clínico independiente y agregación; los datos se muestran en resumen local y quedan excluidos del proveedor IA. Visualizaciones avanzadas adicionales continúan pendientes.

> **Ocupación del dashboard (2026‑10‑07):** API contra PostgreSQL verifica la capacidad configurada, el descuento de una pausa de 30 minutos y los 15 minutos de preparación de una reserva: 210 minutos disponibles, 45 ocupados y 21,4 %. Dos pruebas unitarias comprueban unión de horarios solapados, recorte de reservas y porcentaje nulo sin capacidad. La suite completa frontend aprobó 453/453, incluida la prueba de porcentaje, etiquetas de tiempo y nombre accesible de la barra; lint, TypeScript y build pasan. E2E del flujo de llegada y atención pasó 1/1 y confirma el valor compartido por API y pantalla. Ruff y mypy pasan en el módulo de cálculo. Se oculta el cálculo con filtro por estado o ámbito parcial de pacientes; no se envían datos nuevos al proveedor IA.

> **Anamnesis configurable (2026‑10‑06):** migraciones 018/019 aplicadas; 3 pruebas API verifican creación, publicación y retiro de versiones, captura tipada, inmutabilidad, relación asistencial y autorización N3. El frontend aprobó 415/415 pruebas (87,25 % líneas, 71,42 % ramas, 80,23 % funciones, 85,42 % sentencias), `npm run lint` y `npm run build`. `alembic check`, Ruff y mypy no detectaron diferencias/errores en los módulos modificados. El formulario se monta al abrirlo para no consultar endpoints clínicos si el usuario no lo solicita.

> **Formulario MSP 033 (2026‑10‑06):** la interfaz añade lectura, captura A–P, corrección inmutable, historial y copia imprimible A4 de dos páginas. El permiso N3 exige permiso clínico y sensible; la API registra la versión solicitada antes de permitir imprimir y no guarda contenido clínico en auditoría. Dieciséis pruebas API/esquema pasaron contra PostgreSQL aislado en revisión 020: permisos, alta, consulta, corrección, conflicto de versión, exportación, asociación de fuentes del paciente, rechazo de fuente de otro paciente, auditoría e inmutabilidad en base. La suite frontend pasó 427/427 (87,57 % líneas, 71,93 % ramas, 80,74 % funciones y 85,69 % sentencias), además de lint y build. Se probaron las referencias opcionales, el filtro por permiso/profesional, el no acceso sin permisos, reintento de fuentes y el prellenado explícito solo en campos vacíos. La verificación de entonces usó una base aislada; desde esa revisión, la base compartida avanzó con las migraciones hasta `20261006_023`. La copia aún requiere cotejo institucional con el anexo oficial; el navegador gestiona la impresión dúplex.

> **Actualización de medicamentos (2026‑10‑06):** el servicio clínico aprobó **41 pruebas de integración contra PostgreSQL** para el calendario. La suite de respuestas por WhatsApp verifica cinco rutas: `TOMADA`, `RECORDARME DESPUÉS`, `NO PUDE TOMARLA`, `AYUDA` y mensaje que indica explícitamente un problema con el tratamiento. La plantilla sugiere las cuatro primeras; la quinta solo se reconoce cuando el paciente la escribe. Comprueba paciente y toma inequívocos, ventana temporal, registro de toma/omisión, recordatorio diferido sin alterar la hora prescrita, handoff y auditoría. La suite combinada de intenciones, plantillas, integración y webhook aprobó **136 pruebas** tras corregir una opción de plantilla que infringía la regla de privacidad. La entrega en Meta sigue sin verificarse porque no hay credenciales ni plantilla aprobada configuradas.

> **Sensibilidad clínica (2026‑10‑06):** migraciones `20261006_022` y `20261006_023` añaden N2/N3 por nota y receta; las imágenes clínicas también aceptan N3. Las 72 pruebas backend previas cubren notas, resumen y servicio clínico; las 12 pruebas API de recetas cubren permiso, auditoría, filtro SQL y conservación N3 al versionar; las 8 de imágenes cubren denegación, alta N3, listado y descarga filtrados, y auditoría reforzada. Frontend aprobó **439/439**, lint y build; cobertura 87,40 % líneas, 72,78 % ramas, 80,72 % funciones y 85,52 % sentencias. Ruff y mypy pasan.

> **Sensibilidad del odontograma (2026‑10‑06):** migración `20261006_024` agrega N2/N3 por versión con restricción en PostgreSQL; los registros previos quedan N2. Crear N3 exige `historia_clinica.leer_sensible`; las lecturas filtran versiones N3 en SQL y registran N3 en auditoría incluso cuando el resultado visible es vacío; las ediciones sin permiso se rechazan y ninguna versión puede bajar de N3. Los hallazgos del plan dental heredan el nivel del odontograma y auditan el nivel efectivo. Las pruebas API de odontología y planes de tratamiento pasan **29/29**. Frontend **440/440**, lint y build; Ruff y mypy odontológico pasan. Cobertura frontend: 87,40 % líneas, 72,74 % ramas, 80,72 % funciones y 85,53 % sentencias.

> **Sensibilidad de planes dentales (2026‑10‑06):** migración `20261006_025` agrega N2/N3 por plan; los procedimientos heredan la clasificación del plan. Crear y leer N3 exige `historia_clinica.leer_sensible`; la consulta filtra planes en SQL y registra lecturas N3 aunque queden ocultas. Resumen clínico, indicadores del dashboard y fotos vinculadas aplican el permiso; recepción no puede agendar fases N3. La redacción local omite planes N3 incluso con permiso sensible. No se encolan avisos automáticos por fase para planes sensibles. El frontend permite clasificar el borrador y evita guardarlo como plantilla general. Las suites API de planes, resumen, métricas, imágenes y agenda aprobaron **83/83**. Frontend **441/441**, lint y build; Ruff y mypy pasan. `alembic check` no detecta operaciones nuevas. Cobertura frontend: 87,40 % líneas, 72,74 % ramas, 80,68 % funciones y 85,52 % sentencias.

> **Versión vigente del RAG (2026‑10‑06):** migración `20261006_026` marca qué versión de cada documento puede recuperarse. Una versión nueva no se acepta mientras el documento está aprobado/publicado; hay que retirarlo a borrador, cargar la versión y repetir revisión y aprobación. La regresión verifica que la búsqueda devuelve únicamente la versión recién aprobada y que las versiones históricas no reaparecen. Las suites de conocimiento/RAG aprobaron **83/83** y las pruebas de semillas **29/29**. La suite frontend completa pasa **442/442**, lint y build; cobertura frontend: 87,60 % líneas, 72,93 % ramas, 80,95 % funciones y 85,70 % sentencias. Ruff, mypy y `alembic check` no detectan errores ni diferencias nuevas.

> **Reanudación automática de ingesta (2026‑10‑06):** ARQ construye el proveedor de embeddings local configurado y recoge cada minuto hasta diez trabajos pendientes, bloqueándolos con `SKIP LOCKED`; fallos controlados quedan `FALLIDA` para evitar reintentos continuos. Las pruebas de integración con PostgreSQL verifican que una versión pendiente se indexa, elimina su fuente temporal y no reaparece en el siguiente barrido; también comprueban que un proveedor caído no se reintenta en bucle y conserva la fuente. El conjunto combinado de conocimiento, API de conocimiento, fugas RAG, arquitectura y worker aprobó **95/95**. Ruff y mypy pasaron. El comportamiento ante una caída de proceso se simula dejando el trabajo durable en `PENDIENTE`; no se mata un proceso real en esta prueba.

> **Revisión durable de ingesta (2026‑10‑06):** la regresión ampliada y la prueba de registro de trabajo aprobaron **2/2**. Las suites combinadas de conocimiento, API de conocimiento, fugas del RAG y arquitectura aprobaron **85/85**; las pruebas no hicieron llamadas externas. Ruff y mypy pasaron en los módulos tocados. `alembic check` no detectó operaciones pendientes; conserva las advertencias preexistentes por ciclos de claves foráneas y defaults calculados.

> **Validación focalizada previa (2026‑10‑06):** alergias y antecedentes pasaron 5 pruebas API antes de añadir el control N3: rechazo sin relación asistencial, alta, duplicado activo, reflejo en el resumen, desactivación con motivo conservado y auditoría sin texto clínico. El resumen solo ofrece edición a la identidad profesional y el servidor revalida permiso y relación. El reporte financiero CSV previo aprobó 9 pruebas API con fecha local, alcance, privacidad y auditoría. La suite backend completa de 1682 pruebas citada a continuación es anterior a estos cambios; se han repetido las suites API focalizadas.
>
> En la revisión anterior, vencimientos y pagos aprobaron 34 pruebas API focalizadas.
> La suite backend completa instrumentada aprobó 1682 pruebas y omitió 3 integraciones que llaman a Anthropic en 40 min 47 s; la cobertura total es 87,65 % (umbral: 80 %). Ruff lint, formato y mypy pasan; `alembic check` no detectó operaciones nuevas, aunque advierte el ciclo existente de claves foráneas entre imágenes y planes y columnas calculadas que no puede comparar como defaults. Las corridas agrupadas aprobaron 814 unitarias, 854 de integración/API, 15 de concurrencia, 635 de seguridad y 93 de RAG; los marcadores se solapan y esos totales no se suman. Después de corregir el tipo del catálogo PDF y las sumas de pagos históricos, 32 pruebas focalizadas de archivos y pagos pasan.
> Corrida frontend anterior: 402 pruebas tras habilitar recorrido por teclado en las caras del odontograma y aserciones de método HTTP en el servicio de recorrido; cobertura de esa ejecución: 87,75 % de líneas, 71,09 % de ramas, 80,57 % de funciones y 85,91 % de sentencias. La verificación vigente de frontend está arriba. La prueba del odontograma mueve el foco con flechas y registra la superficie con Enter. La API de catálogo aprobó 29 pruebas al habilitar acceso del lector de planes a los datos públicos de su clínica. La frontera del agente aprobó 82 pruebas unitarias, 35 pruebas API del webhook y 20 pruebas de integración de `TestDespachador` (137 en total); cada una de las ocho herramientas rechaza argumentos incompletos y deriva, y las siete de datos rechazan al principal sin permisos.
> Los 39 escenarios E2E pasaron en una sola corrida con una API actualizada y
> `LIMITE_LOGIN_POR_MINUTO=200`, según `pruebas-e2e/README.md`. La migración `20261006_012`
> añadió acceso temporal de emergencia y revisión administrativa; el recorrido API pasa.
> La última corrida volvió a pasar 39/39 después de corregir la paginación de datos clínicos,
> completar la semilla sintética visible al profesional y añadir el mantenimiento de sedes.
> En una verificación posterior del 2026‑10‑06, la suite E2E ejecutó 39 escenarios contra
> el API activo del puerto 8000: 24 pasaron y 15 fallaron. Esa instancia no publica la ruta nueva
> `/api/v1/agenda/resumen.csv` y `.env` conserva el límite normal de 10/min, por lo que esta
> corrida no valida el código actual completo. El escenario de listado de pacientes pasó al
> repetirse solo tras renovarse la ventana. Se corrigió `pruebas-e2e/README.md` para exigir que
> Angular y `URL_API` usen una API del código actual iniciada con `LIMITE_LOGIN_POR_MINUTO=200`.
> Esta corrida no se cuenta como suite E2E aprobada.
> Frontend lint y build pasan en esta fase previa; el chunk inicial medido entonces (441,91 kB) quedó bajo el presupuesto de 500 kB.
> El 2026‑10‑06 se ampliaron las pruebas de cuenta/perfil profesional: 5 pruebas API y el E2E de
> equipo pasan contra la API actualizada; 17 pruebas API de pacientes también pasan. El rol
> Profesional predefinido se puede asignar con una ficha activa de la clínica y conserva los
> límites de delegación de los demás roles. La verificación de imágenes, iconos y animación
> del 2026‑10‑06 aprobó `npm run lint`, `npm run build` y las 382 pruebas frontend.
> La suite focalizada de pagos y operación aprobó 34 pruebas, incluyendo pagos parciales,
> límites del total pactado, conciliación histórica, vencimientos y permisos por sede.
> El aviso interno de cartera vencida quedó cubierto con pruebas de permiso, recuento y navegación a Pagos.
> Corrida E2E anterior del 2026‑10‑06: **39/39 escenarios aprobados en 4,7 minutos** contra la API actualizada del puerto 8000. La verificación vigente de 62/62 pruebas y el comando reproducible constan al inicio de este documento.

Este documento dice **qué se prueba, con qué, y por qué de esa forma**. No es un
inventario de pruebas: el inventario está en el código. Lo que aquí importa son las
decisiones que hacen que una suite verde signifique algo.

---

## 1. Principio: probar el sistema, no el código

Tres reglas que se aplican sin excepción:

**Las garantías del motor se prueban contra el motor.** El anti doble‑reserva no es lógica
de Python: es una restricción de exclusión GiST (ADR‑0009). Una suite que sustituya
PostgreSQL por SQLite prueba el código y no el sistema, y daría verde sobre un esquema
que permite dos pacientes a la misma hora. Las pruebas de integración usan PostgreSQL 16
con pgvector y Redis reales, en contenedores.

**La concurrencia se prueba con concurrencia real.** No con dobles, no con mocks de
transacción: con varias conexiones distintas y una `asyncio.Barrier` que las suelta a la
vez. Es la única forma de observar el interbloqueo que aparece con 50 participantes y que
no aparece con dos.

**Probar las piezas no prueba el cableado.** Esta regla se añadió después de un fallo
real: `configurar_registro` combinaba un factory de structlog con un procesador
incompatible, y **toda** línea de registro lanzaba `AttributeError`. La suite estaba verde
porque cada prueba invocaba el procesador de redacción de forma aislada y ninguna llamaba
a la configuración y después emitía una línea. En la API eso habría sido un 500 en la
primera petición. Desde entonces hay pruebas de arranque para la configuración de logs y
para el worker.

**Una suite verde no sustituye a ejercer el sistema.** Regla añadida tras encontrar tres
fallos del filtro de ámbito —uno de ellos dejaba a la recepción sin poder agendar nada, y
otro exponía las citas de todos los profesionales a quien tuviera el ámbito de profesional
vacío— **arrancando la API y recorriendo el flujo real**, con 557 pruebas en verde.

Vivían en el espacio entre lo que las fixtures suponían y lo que los datos reales tienen:
las fixtures construían el `Principal` a mano, con un ámbito que ningún rol real produce.
Por eso ahora existe una comprobación de extremo a extremo contra la base con datos
sintéticos —login, catálogo, disponibilidad, reserva idempotente, colisión de turno,
cancelación e IDOR— que se ejecuta antes de dar una fase por cerrada, y por eso las
pruebas de ámbito verifican **dimensión por dimensión** con una prueba de control que
confirma que el caso permitido sí devuelve datos. Sin esa prueba de control, las demás
pasarían por el motivo equivocado.

**La regla se volvió a cumplir en la Fase 4, y con un fallo peor.** Con 891 pruebas en
verde, ejercer el sistema arrancado contra las semillas reales destapó que **un paciente que
respondía `BAJA` por WhatsApp no quedaba dado de baja**: la columna guarda el número como lo
escribió el personal («+593 99 900 0333») y el webhook entrega solo dígitos
(«593999000333»), así que la revocación de consentimiento no encontraba a quien revocar y el
sistema le seguía escribiendo.

Las fixtures guardaban el número **ya normalizado**, que es justo lo que el panel no hace.
Las 26 pruebas del webhook pasaban por el motivo equivocado. Es el mismo sitio donde vivían
los tres fallos de ámbito: el espacio entre lo que la fixture supone y lo que los datos
reales tienen.

De ahí dos consecuencias para las pruebas de este repositorio:

* **Una fixture debe guardar el dato en la forma más incómoda que admita el sistema**, no en
  la más cómoda para la aserción. El teléfono se guarda ahora con «+» y espacios.
* **Los identificadores de las pruebas se generan por prueba, no son constantes del módulo.**
  El `phone_number_id` estaba fijo, y bastó que un ejercicio manual insertara una fila de
  configuración con ese mismo valor para que 20 pruebas fallaran por datos ajenos. Igual con
  contar filas: `SELECT count(*)` sobre una tabla entera supone una base vacía, y la de
  desarrollo no lo está.

**Una prueba que comprueba una ausencia necesita su prueba de control.** Las 21 pruebas de
fuga del RAG afirman que un documento archivado, vencido o de otra sede **no** se recupera.
Todas pasarían aunque la búsqueda estuviera rota y no devolviera nunca nada —que es la forma
más fácil de tener una suite verde que no prueba nada—. Por eso cada bloque tiene una prueba
que comprueba que el caso **permitido sí** devuelve datos.

**Y hay cosas que solo aparecen al medir, no al ejecutar la suite.** En la Fase 6, el arnés de
evaluación destapó que una pregunta sin documentación devolvía el corpus entero: el umbral de
similitud no se aplicaba, y la consulta textual unía los términos con `AND` así que casi nunca
coincidía. Cada fallo tapaba al otro, y **ninguna prueba de comportamiento los habría
encontrado** —todas usaban preguntas que sí tenían respuesta—. De ahí que el arnés mida
también lo que pasa cuando **no** hay respuesta, y que registre las cifras obtenidas para que
una regresión se vea como un número que baja.

**Un porcentaje de cobertura es una medición, y una medición puede estar mal.** Regla
añadida en la Fase 4, al ver que `conversaciones/servicios.py` aparecía al 65 % con 26
pruebas de API que lo recorren entero. La causa no era el código ni las pruebas: SQLAlchemy
async ejecuta el código que rodea a cada consulta dentro de un greenlet (`greenlet_spawn`),
y `coverage` no traza esas líneas sin `concurrency = ["thread", "greenlet"]`.

El síntoma empuja en la dirección contraria a la útil: invita a escribir pruebas para
líneas que ya estaban probadas, y **oculta las que de verdad no lo están**. Corregirlo
subió la cobertura total de 89,18 % a 91,63 % sin añadir una sola prueba —y dejó a la vista
dos huecos reales (`destinatarios.py` al 41 %, la cancelación de recordatorios sin cubrir)
que el ruido tapaba.

Antes de creerse un número bajo, conviene comprobar que la línea se ejecuta de verdad: un
`print` o un fallo provocado a propósito lo resuelven en un minuto.

---

## 2. Marcadores y qué cubre cada uno

Los marcadores no son etiquetas decorativas: determinan qué se ejecuta en cada paso del
pipeline y qué infraestructura necesita.

| Marcador | Necesita | Qué cubre | Estado |
|---|---|---|:--:|
| `unitaria` | nada | lógica pura: motor de disponibilidad, redacción de logs, autorización, traducción de errores, criptografía | **308** |
| `integracion` | PostgreSQL, Redis | restricciones, disparadores, índices parciales, aislamiento transaccional, servicios completos, semillas, worker | **157** |
| `api` | PostgreSQL, Redis | contorno HTTP: códigos de estado, forma del cuerpo, cabeceras, **quién puede llamar a qué** | **71** |
| `concurrencia` | PostgreSQL | carreras reales por el mismo turno, con conexiones separadas | **10** |
| `seguridad` | según el caso | un control de seguridad concreto por prueba | **162** |
| `rag` | PostgreSQL + pgvector | recuperación, filtros de permiso, resistencia a inyección de prompt | **80** |
| `lento` | — | tarda más de cinco segundos | — |

Los marcadores se solapan a propósito: una prueba de IDOR es `api` **y** `seguridad`.

**Corte histórico del inventario de marcadores:** 564 pruebas backend y 67 frontend. No es el conteo vigente de la suite; la validación general anterior al vencimiento reportó 1658 pruebas backend aprobadas y 3 integraciones opcionales omitidas. Después del cambio, pagos/operación aprobaron 34 pruebas API. Frontend aprobó 382 pruebas, con 87,96 % de líneas, 71,38 % de ramas, 80,65 % de funciones y 86,37 % de sentencias. El reporte backend general se imprimió, pero pytest no terminó limpiamente porque un proceso quedó activo después del resumen.

---

## 3. Lo que se prueba porque puede hacer daño

Esta sección lista, por dominio, las propiedades que la suite verifica. Están escritas
como afirmaciones comprobables, no como áreas.

### Agenda y concurrencia

* Dos reservas simultáneas del mismo turno producen **una sola cita**. Verificado con 50
  participantes reales.
* El invariante se comprueba **en SQL** — cero pares de citas activas solapadas — y no
  contando ganadores. Una prueba anterior contaba ganadores y estaba mal: con rangos
  semiabiertos `[inicio, fin)`, `[13:45,14:15)` y `[14:15,14:45)` no se solapan.
* Parte de los rechazos bajo carga llegan como **interbloqueo** (SQLSTATE 40P01), no como
  violación de exclusión (23P01). Tratar solo el segundo dejaría una fracción de las
  reservas devolviendo 500 bajo competencia real.
* Un bloqueo temporal vencido **no se puede confirmar**: ese turno pudo ofrecerse ya a
  otra persona.
* El barrido libera solo lo vencido, con el límite exacto al segundo, y el turno queda
  **realmente** libre — comprobado reservándolo otra vez, no leyendo el estado de la fila.

### Autenticación

* Correo inexistente, contraseña incorrecta y cuenta desactivada devuelven **el mismo
  código, el mismo mensaje y el mismo estado HTTP**. Distinguirlos permitiría enumerar al
  personal de la clínica.
* El bloqueo por intentos **no cede ante la contraseña correcta**. Si cediera, no serviría.
* El contador de intentos **sobrevive a la excepción**. Es el fallo más fácil de introducir
  en la capa HTTP: si el manejador de errores deshiciera la transacción, el contador
  volvería a cero en cada intento y el bloqueo no se activaría nunca, con la suite del
  servicio en verde. Tiene una prueba de API dedicada.
* Reutilizar un token de refresco revoca **la familia completa** de sesiones.
* Retirar un permiso surte efecto **con el mismo token**, sin esperar a que caduque.

### Autorización y aislamiento

* La dependencia `exige_permiso` se prueba contra **endpoints de sonda** montados en la
  propia suite, con la dependencia real. Aísla el fallo y no caduca cuando cambie el
  endpoint que se hubiera usado de excusa.
* Un recurso fuera de ámbito devuelve **404, no 403**, y la respuesta es **indistinguible**
  de la de un recurso inexistente. Si se distinguieran, el 404 dejaría de proteger nada.
* Notas y resumen clínico comparan una ficha sin relación, una ficha de otra clínica y un
  identificador inexistente. Un rol administrativo (sin permiso clínico) y otro con permiso de
  lectura (sin relación asistencial) reciben el mismo cuerpo 404; otros módulos y roles siguen
  en la matriz pendiente de la tarea 2.9.
* `GET /historia/pacientes/{id}/notas` y `GET /resumen-clinico` devuelven la misma respuesta
  404 para una ficha inexistente, fuera de ámbito, sin permiso clínico o sin relación vigente.
  La falta de permiso queda auditada; la pantalla puede solicitar acceso temporal por emergencia con motivo sin distinguir los demás casos 404.
* El IDOR se prueba **transición por transición** (confirmar, cancelar, reprogramar,
  completar, inasistencia). Basta con que una sola olvide el filtro de ámbito para que la
  agenda de otra sede sea modificable desde fuera, y una prueba genérica sobre el detalle
  no lo detectaría.
* Una exclusión de ámbito gana a un comodín, y el ámbito vacío no da acceso a nada.
* La administración de horarios prueba las franjas solapadas, descansos fuera de horario,
  auditoría de alta/edición/eliminación y la lista real de la sede. Para feriados se prueban
  cierres parciales solapados, recurrencia anual y el límite que impide a un rol de sede
  modificar un cierre de toda la clínica.
* Los bloqueos prueban alta/listado/edición/eliminación y auditoría, destino dentro de clínica
  y sede, timestamps con zona, ámbito limitado y la advertencia 409 de citas activas. La
  respuesta de conflicto no contiene nombres ni datos de pacientes y el bloqueo solo se crea
  tras la confirmación explícita.
* La disponibilidad semanal del equipo prueba CRUD y auditoría, autorización por profesional
  y sede, vigencias, rechazo de solapamientos y que una franja guardada aparece en el cálculo
  de turnos en la zona horaria local correspondiente.

### Datos sensibles

* Los campos sensibles se redactan por nombre **y** por patrón de contenido, de forma
  recursiva.
* Los registros de **otras librerías** pasan por la misma cadena de redacción. Importa:
  SQLAlchemy escribe las sentencias con sus parámetros enlazados, y esos parámetros son
  nombres, documentos y teléfonos de pacientes. Hay una prueba que emite desde
  `sqlalchemy.engine`.
* Los esquemas de salida son explícitos. Hay pruebas que comprueban que `hash_contrasena`,
  `secreto_2fa_cifrado` e `intentos_fallidos` **no aparecen** en ninguna respuesta.
* Un error de validación no refleja el valor rechazado: ese valor puede ser una contraseña
  o el documento de un paciente.

### Dashboard y filtros agregados

* Verificación focalizada 2026‑10‑07: las pruebas de operación API, cohortes de pacientes,
  perfil demográfico, retorno a 30 días, ocupación y resumen local aprobaron **50/50** entre
  API contra PostgreSQL y lógica agregada unitaria. Ruff pasa en los archivos de prueba y mypy
  en dashboard y el repositorio de pacientes.
* `test_dashboard_aplica_filtros_de_especialidad_servicio_y_estado` valida en PostgreSQL que
  sede, profesional, especialidad, servicio y estado se combinan en el agregado. Contrasta dos
  profesionales de la misma sede y una segunda sede fuera del ámbito, y comprueba estado vacío,
  estado inválido (422) y el análisis local filtrado.
* `test_dashboard_analisis_ia_aplica_filtros_y_ambito` intercepta Anthropic con un cliente en
  memoria: el agregado pasa de 1 a 2 citas al quitar el filtro de profesional, y la sede fuera
  del ámbito produce 0. Comprueba que el agregado enviado no lleva demografía ni fecha de
  nacimiento; no se conecta a un proveedor real ni transmite datos externos.
* `test_dashboard_profesional_usa_su_ambito_sin_filtro_explicito` inicia sesión con un perfil
  profesional, verifica que recibe su cita sin enviar `profesional_id` y obtiene cero al pedir
  las métricas de otro profesional.
* `test_dashboard_cohortes_altas_sin_cita_y_filtro_estado` contrasta altas con y sin citas en
  el ámbito seleccionado, descarta pacientes de otra clínica y fuera de fecha, no devuelve
  identidades y deja las cohortes nulas al filtrar por estado. `PanelComponent` muestra altas
  y una tabla accesible por mes; una prueba del componente cubre valores y estado filtrado.
* `test_dashboard_demografia_agregada_y_supresion_de_grupos_pequenos` usa PostgreSQL para
  comprobar edades al cierre local del rango, sexo registrado y citas autorizadas. Verifica
  que grupos menores de cinco y la celda complementaria no exponen cantidades, que el filtro
  sin citas devuelve `null`, y que ni identidades ni fechas de nacimiento salen en la respuesta.
  El componente presenta ambos repartos separados; las barras decorativas se omiten en celdas
  protegidas y la tarjeta comunica el umbral de privacidad.
* `test_dashboard_retorno_30_dias_solo_usa_cohortes_maduras_y_completadas` verifica con
  PostgreSQL cohortes observadas por 720 horas, una devolución exactamente en el día 30,
  citas confirmadas que no cuentan, supresión cuando un grupo tiene menos de cinco personas y
  estado de cita incompatible. `test_dashboard_retorno_30_dias.py` agrega seis casos de
  denominador y supresión primaria/complementaria. El seguimiento puede ocurrir después del
  rango que selecciona la cohorte y nunca cuenta citas no completadas.
* `PanelComponent` verifica que los cinco filtros seleccionados se envían al endpoint de
  resumen agregado. También comprueba fechas inclusivas convertidas con la zona de Guayaquil
  y `Pacific/Kiritimati`, que el resumen local conserva el rango y que una fecha invertida no
  dispara consultas. La suite completa de Angular aprobó **538/538** (86,04 % sentencias,
  72,82 % ramas, 81,17 % funciones y 88,30 % líneas), incluida la presentación demográfica y
  de retorno. Lint, TypeScript y build de producción pasan; el presupuesto del bundle inicial
  queda excedido por 2,66 kB (502,66 frente a 500 kB). E2E visual todavía requiere Docker.

### Datos sintéticos

Tras cargar las semillas se verifican cuatro invariantes, todas a cero: ninguna cita activa
solapada, ningún documento fuera del prefijo `99`, ningún correo fuera de
`example.invalid`, ningún paciente sin la marca `[SINTETICO]`.

---

## 4. Puertas del pipeline

Definidas en [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). El pipeline
**bloquea la fusión** ante cualquiera de estas condiciones:

| Puerta | Herramienta | Por qué bloquea |
|---|---|---|
| Lint y formato | `ruff` | `TID251` prohíbe `datetime.now()` fuera de `reloj.py` (ADR‑0010); se comprobó que una llamada de prueba hace fallar el lint. Las semillas pueden fijar la fecha con `RelojFijo`. |
| Tipos | `mypy --strict` | Un `Optional` no comprobado en la resolución de ámbito se traduce en acceso indebido, no en un error visible |
| Seguridad estática | `bandit -ll` | Solo severidad media o superior: un informe con cien avisos irrelevantes se deja de leer |
| Pruebas | `pytest` por marcador y después completa | Los marcadores se ejecutan por separado para que el fallo diga **qué** falló |
| Cobertura | `pytest-cov`, `fail_under = 80` | RNF‑06 |
| Secretos | `gitleaks`, historial completo | Un secreto comprometido en un commit anterior sigue comprometido aunque el archivo ya no exista |
| Dependencias | `pip-audit --strict` sobre el bloqueo exportado | Se audita lo que se despliega, no lo que el ejecutor resolvió |
| Migraciones | `alembic upgrade head` → `check` → `downgrade -1` → `upgrade head` → `downgrade base` → `upgrade head` → `check` | CI comprueba una reversión puntual y que el esquema completo se puede reconstruir desde cero en PostgreSQL efímero (RNF‑11) |
| Coherencia de modelos | `alembic check` | Detecta el modelo cambiado sin migración generada |
| Extensiones | consulta a `pg_extension` | Sin `btree_gist` no existe la garantía anti doble‑reserva; sin `vector` no hay conocimiento |
| Imágenes | `docker build` + `trivy` (HIGH, CRITICAL) | `ignore-unfixed`: una vulnerabilidad sin parche no se arregla bloqueando la fusión, se registra como riesgo |
| Frontend | `eslint`, `tsc --noEmit`, Vitest (`npm run test:ci`), `ng build`, `npm audit` | Las comprobaciones frontend se ejecutan localmente; la suite actual aprobó 538/538 con los umbrales de cobertura configurados. La corrida completa del pipeline CI aún no se lanzó en GitHub |

**Hallazgo de la primera ejecución de estas puertas:** `pip-audit` encontró 44
vulnerabilidades conocidas en tres paquetes, incluidas 7 en `cryptography` —la biblioteca
que cifra los secretos de segundo factor y los tokens OAuth en reposo—. Se corrigieron
subiendo `cryptography` a 50.0.1 y `pytest` a 9.x, y **eliminando Pillow del árbol**: sus
35 vulnerabilidades no se podían corregir porque `fastembed` limita `pillow<12.0`, y el
único uso de QR (el código de provisionamiento TOTP) no necesita Pillow si se genera SVG.

---

## 5. Lo que este plan todavía no cubre

Declarado de forma explícita, no por omisión.

| Área | Estado | Fase |
|---|---|:--:|
| E2E con Playwright (57 pruebas) | **parcial** | Las 57 pasan contra la API actual y PostgreSQL; quedan pendientes aceptación clínica integral y reserva por WhatsApp simulado descritas en `pruebas-e2e/README.md` |
| Pruebas de contrato de API (`schemathesis`) | **aprobado**: valida el OpenAPI completo y genera/contrasta una solicitud anónima por cada operación publicada (100+), por ASGI; sin proveedores externos | 2 |
| Suite de WhatsApp (firma inválida, duplicado, reintento, estado de entrega) | **no empezado** | 4 |
| Suite de calendario (token vencido, evento borrado en el proveedor, conflicto) | **no empezado** | 4 |
| Evaluación de RAG (Hit@K, precisión, fugas entre pacientes y especialidades = 0) | **no empezado** | 6 |
| Suite completa de medicamentos (respuestas, recordatorios, PRN y cambios de pauta) | **parcial:** el servicio tiene 41 pruebas; calendario, registro de tomas, PRN y cancelación de avisos están cubiertos. Falta documentar el recorrido completo de respuestas de paciente y entrega de recordatorios. | 7 |
| DAST sobre la API en ejecución | **no empezado** | 10 |
| Carga con k6 | **no empezado** | 10 |
| Recuperación ante caídas (Redis, PostgreSQL, proveedor externo) | **no empezado** | 10 |
| Restauración real desde copia de seguridad | **no empezado** | 10 |

**Una copia de seguridad no se declara válida hasta que se restaura y se verifica.** Esa
verificación es parte de la Fase 10 y hoy no existe.

---

## 6. Cómo ejecutarlo en local

```powershell
.\infra\scripts\infra-arriba.ps1          # PostgreSQL + Redis
cd backend
uv run alembic upgrade head
uv run python -m app.semillas.cargar --solo-catalogos

uv run pytest -m unitaria -q
uv run pytest -m "integracion or api" -q
uv run pytest -m concurrencia -q
uv run pytest -m seguridad -q
uv run pytest --cov=app --cov-report=term-missing

uv run ruff check . ; uv run ruff format --check .
uv run mypy app
uv run bandit -r app -ll
uv run alembic check
```

Auditoría de dependencias (se audita el bloqueo, no el entorno):

```powershell
uv export --frozen --no-emit-project --no-hashes --extra dev --extra llm -o requisitos.txt
uv run pip-audit --strict --desc -r requisitos.txt
```

---

## 7. Reglas sobre las propias pruebas

* **No se sube cobertura borrando pruebas ni relajando aserciones.** Si una prueba falla,
  se corrige la causa.
* **Si se descubre que una prueba estaba mal escrita, se corrige y se explica en el
  commit.** Ha pasado seis veces en este proyecto, y cada caso está documentado en el
  mensaje del commit correspondiente: tres asumían comportamientos de disponibilidad que
  el motor no tiene, una ordenaba por un UUID aleatorio creyendo que era un orden estable,
  una esperaba 423 donde el diseño usa 401 a propósito, y una medía la caducidad del token
  creyendo que medía la del bloqueo.
* **Las pruebas de seguridad no se desactivan.** Las que verifican que la IA no puede
  escribir en la base ni tomar decisiones clínicas, menos que ninguna.
* Ninguna prueba usa datos reales de pacientes. Nunca.
# Verificación de agente contextual y ampliación clínica (2026-10-08)

Los recorridos usan exclusivamente datos sintéticos. PostgreSQL se comprueba
en una base exclusiva; no se ejecutan escrituras de pruebas en la clínica local.

- Backend: periodontograma y sus seis sitios, nulos, sensibilidad, autoría,
  versiones, anulación y PDF; modelos locales y observaciones separadas por
  permisos; fotos privadas, contenido falso, ACL, clínica ajena, autor y
  versiones históricas; sesiones del agente por operador/paciente, claves,
  cambio de accesos, vencimiento, confirmación, cancelación, reserva y
  reprogramación, intentos de argumentos ajenos, límites clínicos y caché sin
  resumen clínico. Regresión del flujo WhatsApp y herramientas existentes.
- Frontend: panel contextual y botones por permiso, clave conservada al
  reintentar, confirmación/descartado, cambio de persona y persistencia del
  contexto al actualizar citas, fechas e importes legibles, captura y galerías.
- Chromium: `18-periodontograma-analitica-agente.spec.ts` ejecuta la ficha real
  del profesional y recepción, captura de seis sitios/foto/PDF, los tres
  análisis, axe y ancho móvil. El resumen sigue al lado del historial.
- Migraciones: `upgrade`, `downgrade -4`, `upgrade` y `alembic check` en la
  base temporal de los recorridos; limpieza exclusiva al terminar.

```powershell
# Dentro de backend, con PostgreSQL de pruebas configurado
.venv/Scripts/python.exe -m pytest --no-cov -q pruebas/api/test_agente_paciente_api.py pruebas/api/test_fotos_registro_api.py
.venv/Scripts/python.exe -m ruff check app pruebas
.venv/Scripts/python.exe -m mypy app
# Frontend: conservar los mínimos de cobertura
cd ../frontend
npm.cmd run test:ci
npm.cmd run lint
npm.cmd run build
# API real aislada preparada y frontend arriba
cd ../pruebas-e2e
npx.cmd playwright test escenarios/18-periodontograma-analitica-agente.spec.ts
```

Las cifras y los comandos de la ejecución concreta están en el informe de
verificación. La corrida completa anterior del backend y las focalizadas
actuales se registran por separado; no se suman como si fueran una sola corrida.
