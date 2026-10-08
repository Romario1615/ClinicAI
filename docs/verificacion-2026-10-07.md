# Verificación de ClinicAI tras actualizar desde GitHub

Rama de trabajo: `claude/friendly-gates-o240sb`. Base de esta revisión:
`727c9f5`. Se conserva el diseño de pantallas de trabajo, pestañas y ventanas
incorporado desde GitHub. Todos los datos de esta ejecución son sintéticos.

## Cambios realizados

- La barra de fecha de Agenda reparte sus controles en varias líneas en móvil.
  El navegador detectó 332 px de contenido en una pantalla de 320 px; después
  de la corrección mide 320 px y conserva todos los controles.
- Los selectores del Formulario 033 identifican la región examinada o la pieza
  dental. Hallazgo y grado también tienen un nombre contextual. Una prueba de
  componente verifica los 67 selectores de las tablas y sus nombres distintos.
- Catálogo y Automatizaciones permiten enfocar y desplazar su contenido con
  teclado también con permisos de solo lectura.
- Las pruebas E2E siguen el buscador como formulario, los nombres actuales de
  las pestañas clínicas, las ventanas de citas y sedes y el nuevo diálogo de
  carga de imágenes. Conservan las comprobaciones de persistencia por API.
- Dos escenarios nuevos verifican las cuatro vistas de Agenda y Pacientes a
  1280×720, 821×600, 390×844 y 320×844, las acciones fijas y el desplazamiento
  interno en escritorio, y las pestañas clínicas con flechas, Inicio y Fin.
- La carga de imágenes verifica accesibilidad y ancho móvil dentro de la
  ventana que se abre sobre la ficha del paciente.
- El backend genera OpenAPI cuando se solicita, con la caché de FastAPI.
  Las métricas obtienen las rutas efectivas de los routers, con sus prefijos,
  sin generar todo el contrato durante el arranque. Se comparó el documento
  completo con el del servidor anterior y resultó idéntico.
- Las métricas dan prioridad a rutas fijas como `/citas/series` frente a
  `/citas/{cita_id}`. Las etiquetas siguen usando plantillas y omiten IDs.
- La prueba del historial de reprogramación identifica el evento
  `RESCHEDULED` antes de comprobar horarios y motivo. El reloj fijo asigna
  el mismo instante a creación y reprogramación; ordenar solo por fecha no
  garantiza cuál fila queda al final. Se conservan todas las comprobaciones
  del historial y pasan las 46 pruebas del servicio de Agenda.
- La primera prueba del formulario extenso dispone de 10 segundos para su
  compilación bajo cobertura; se detectó un timeout de 5 segundos al ejecutar
  simultáneamente las tres suites. No se añadieron reintentos.

## Evidencia disponible

Las cifras frontend y Chromium de esta tabla corresponden a la revisión general.
La corrección posterior del perfil se registra al final con su nueva ejecución.

| Comprobación | Resultado |
|---|---|
| Frontend completo, Vitest | 605/605, 83 archivos |
| Cobertura frontend | Sentencias 86,12 %; ramas 72,88 %; funciones 81,60 %; líneas 88,31 % |
| Lint y build de producción frontend | Aprobados; paquete inicial 462,85 kB, presupuesto 500 kB |
| Contrato y métricas backend con cobertura focalizada | 8/8, 1 min 52,84 s |
| Ruff lint y formato backend | Aprobados, 408 archivos formateados |
| mypy | Aprobado, 223 archivos de aplicación |
| Bandit, umbral CI `-ll` | Sin hallazgos medios o altos; 12 de severidad baja |
| Servicio de Agenda tras corregir la prueba del historial | 46/46, 11,69 s |
| Selección de pruebas en CI | 1858 casos; todos pertenecen a una puerta principal. Marcadores: 893 unitarias, 960 integración/API, 15 concurrencia y 698 seguridad; los grupos se solapan |
| Migraciones en base temporal vacía | `upgrade head`, `downgrade -1`, `upgrade head` y `alembic check` aprobados |
| Regresión completa backend con cobertura | 1855 aprobadas, 3 omitidas (Anthropic real), sin fallos; 19 min 39,63 s |
| Cobertura backend global | 87,89 % frente al mínimo 80 %; líneas 91,46 %, ramas 71,30 % |
| Chromium completo | 62/62, 15 archivos, 6,9 minutos; sin reintentos |
| axe WCAG 2.2 A/AA | Diez recorridos, seis roles y 22 rutas visibles del menú |
| Acceso en los servicios de desarrollo 4200/8000 | 6/6 roles: botones sin contraseña, manual propio en Ayuda y cierre de sesión |

La regresión inicial del backend se interrumpió después de identificar el
coste repetido de generar OpenAPI durante cada arranque. Una segunda ejecución
aprobó 876 casos y omitió las tres llamadas optativas a Anthropic, antes de
detenerse por el orden indeterminado de la prueba del historial. La repetición
final incluye la corrección y aprobó los 1855 casos ejecutables sin fallos.
La cobertura se midió en esa misma ejecución, no mediante la suma de resultados
focalizados. JUnit registra 1858 casos, cero fallos, cero errores y tres omitidos.

## Entorno de ejecución

El frontend de desarrollo sigue en `http://localhost:4200`. Chromium usa una
API separada en `127.0.0.1:8020` y una base temporal creada en PostgreSQL local
con todas las extensiones y migraciones del proyecto. La base de desarrollo
permanece disponible para el usuario. Los fixtures de API e integración
revierten sus transacciones; los casos de concurrencia usan conexiones propias
y limpian explícitamente sus datos.

Al finalizar Chromium se detuvo la API del puerto 8020 y se eliminó únicamente
su base temporal. Se conservaron PostgreSQL, Redis y los servicios de desarrollo.
La API de desarrollo se reinició con el código corregido: `/salud/listo`
responde `listo` y el frontend devuelve HTTP 200. La comprobación adicional de
los seis roles usa estos servicios, sin redirigir el navegador a la API E2E.

Proveedores de IA y embeddings: `mock`. WhatsApp y calendario: `sandbox`.
No se configuraron ni llamaron proveedores externos. Redis de la API E2E usa
el índice 14 y el límite local de acceso es 200 por minuto. No se cambió `.env`.

## CRUD, faciograma y documentos

Ampliación posterior a la corrección del Panel, sobre `claude/friendly-gates-o240sb`.
Se añadieron edición y baja reversible de clínicas/cuentas, ficha de atención
según cita/sede/especialidad, faciograma de 23 zonas, registros versionados,
PDFs y entrega mediante enlace privado por WhatsApp. La plantilla conserva la
privacidad; los envíos se prueban con sandbox, sin credenciales externas.
La receta PDF conserva su origen confirmado y no permite editar la pauta.

La revisión en navegador detectó una carrera en el editor de clínicas: se podía
escribir antes de terminar la carga y el GET reemplazaba lo escrito. Se corrigió
deshabilitando campos durante carga/guardado. Elegir una cita de especialidad
ajena bloquea correctamente la atención clínica. Se corrigieron selectores de
pruebas y se actualizaron dos expectativas antiguas al incorporar el cuarto
consentimiento y el módulo facial por omisión en dermatología.

El PDF facial añade una página con mapa vectorial y leyenda. Los presupuestos
excluyen procedimientos cancelados; el editor selecciona sede cuando el ámbito
incluye varias sedes limitadas. El listado filtra módulos antes de paginar.
Las instrucciones de Ayuda son propias de cada rol y no amplían sus permisos.

Pruebas añadidas: `test_crud_administrativo_api.py`,
`test_registros_paciente_api.py`, `test_pdf_documentos.py`, cinco componentes
frontend y `17-registros-y-documentos.spec.ts`. El ciclo de migración `031`
pasó en la BD temporal con reversión a `030` y `alembic check`; también está
aplicado en la BD local. Los logs de esta revisión quedan en
`tmp/qa-20261007/*registros*.log` (excluidos de Git).

```powershell
cd backend
.venv/Scripts/python.exe -m pytest pruebas/api/test_crud_administrativo_api.py pruebas/api/test_registros_paciente_api.py pruebas/unitarias/test_pdf_documentos.py -q --no-cov
.venv/Scripts/python.exe -m pytest -q --cov=app --cov-report=term
cd ../frontend
npm run test:ci
npm run lint
npm run build
cd ../pruebas-e2e
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
$env:URL_API='http://127.0.0.1:8020/api/v1'
npx playwright test
```

Playwright requiere API/BD temporales preparadas y solo datos sintéticos.
| Comprobación de la ampliación | Resultado |
|---|---|
| Backend completo, segunda corrida sin cobertura | 1917 aprobadas, 3 omitidas (Anthropic real), 11 min 16 s |
| Backend focalizado, incluyendo expectativas actualizadas | 66/66, 77,62 s |
| Cobertura backend, primera corrida | 87,37 %; aquella corrida tuvo dos expectativas antiguas fallidas, posteriormente corregidas y repetidas |
| Frontend completo | 632/632, 89 archivos, 71,26 s |
| Cobertura frontend | 86,18 % sentencias; 73,51 % ramas; 81,48 % funciones; 88,63 % líneas |
| Frontend lint/build | Aprobados; 463,02 kB iniciales, sin avisos de presupuesto |
| Chromium completo, repetición final | 66/66 en 7,8 minutos; seis roles, axe en las 22 rutas y CRUD/documentos/faciograma |
| Backend estático | Ruff, formato y mypy (229 fuentes) pasan; Bandit `-ll` sin hallazgos medios/altos |
| Secretos | Gitleaks sobre los 89 commits de la revisión, sin hallazgos; valores redactados en el log |
| Base de desarrollo | Migración `031` actual, `alembic check` sin operaciones faltantes |
| Servicios reiniciados | API lista, frontend 200 y worker sandbox activo; seis roles acceden, abren su manual y cierran sesión |

La primera corrida Chromium completa aprobó 63/66. Al editar la interfaz durante
esa ejecución, la recarga del servidor cerró la sesión de auditoría. La aserción
global de rutas produjo otro fallo derivado del reinicio del trabajador de
Playwright. La prueba de demografía interceptaba `route.fetch` contra la API de
desarrollo, aunque el resto usaba la API temporal: se corrigió para respetar
`URL_API`. La repetición completa con archivos estables aprobó **66/66** sin
reintentos. Se detuvo la API temporal y se eliminó exclusivamente su BD sintética
`clinicai_e2e_20261007_25eecff3`. Se conservan BD, Redis, frontend, API y worker de
desarrollo. Las capturas del faciograma a 1440/768/390 px quedan en
`tmp/qa-20261007/faciograma-*.png`.

### Consolidación en main

El usuario eligió `main` como única rama principal. La `main` anterior y
`modulo-dental-y-mensajeria` son ancestros de la rama de trabajo; no tenían commits
exclusivos que requirieran resolver una fusión. Se conservan sus commits mediante
avance de `main` al resultado revisado. El stash antiguo queda como copia local
de respaldo, ya integrado en revisiones anteriores; no se reaplica encima del
trabajo actual.

## Faciograma visible y documentos desde la ficha

### Hallazgo en la instalación local

El profesional del acceso local usa Odontología. Sus módulos de historia eran
odontograma, periodoncia, planes e imágenes; el faciograma no estaba habilitado.
El gráfico existía dentro de Atención y documentos y no tenía pestaña directa.
Administración lo habilitó mediante la configuración versionada existente,
conservando los cuatro módulos y los permisos del rol. Esa configuración vive
en la BD local: otras clínicas deben habilitarlo para su propia especialidad.

La ficha ahora ofrece Faciograma y Documentos y PDF con atajos desde el resumen.
La selección de cita se conserva entre las tres vistas de atención y propaga
su sede/especialidad. La pestaña inicial solo se selecciona si está autorizada.
En móvil, las pestañas se desplazan horizontalmente. Se revisaron las pantallas
de los tres roles operativos en el navegador contra los servicios 4200/8000;
no se escribieron registros clínicos en desarrollo.

### Pruebas ejecutadas

| Comprobación | Resultado |
|---|---|
| Frontend | 635/635 en 89 archivos, 54,16 s |
| Cobertura frontend | Sentencias 86,19 %; ramas 73,62 %; funciones 81,46 %; líneas 88,65 % |
| Lint y build | Aprobados; 463,02 kB iniciales y sin avisos de presupuesto |
| Chromium completo | 67/67 en 7,7 minutos; seis roles y axe en las 22 rutas |
| Faciograma en la ficha | Alta, corrección v2, anulación v3, historial, cita conservada, PDF y escritorio/móvil; axe sin incidencias |
| Documentos con la API final | 4/4 en 46,3 s; presupuestos, cotizaciones y recetas, PDF y solicitudes sandbox |
| PDF abiertos con pypdf | Faciograma: dos páginas; presupuesto, cotización y receta: una página cada uno; texto extraíble |
| Backend focalizado | 73/73 en 55,19 s con ENTORNO=desarrollo del ejecutor de CI |
| Resumen de semillas | 2/2 unitarias: incluye receta, confirmación, suspensión y tomas adicionales |
| Copia de receta N3 | 2/2 API en 3,41 s: conserva sensibilidad solicitada, rechaza edición y deniega WhatsApp |
| Backend global nuevo | En ejecución, en otra BD exclusiva, sin llamadas a proveedores |
| Ruff, formato y mypy | Aprobados; 419 archivos formateados y 229 fuentes tipadas |

La primera corrida Chromium dio 66 aprobadas y una aserción fallida: la prueba
buscaba «Recetas» con nombre exacto cuando existía un borrador y el nombre era
«Recetas 1». El recorrido con teclado funcionaba. Se hizo estable el selector,
se comprobó junto al faciograma (2/2) y se repitió toda la suite sin reintentos.

Se descubrió que emitir como N3 una receta originalmente N2 reducía la copia a
N2. Dos casos reprodujeron ese fallo; ahora se conserva el nivel más restrictivo.
La copia no permite edición directa (422); la corrección parte de la receta
original. Las corridas globales anteriores se detuvieron para incorporar la
corrección y su contrato correcto; no se cuentan como aprobadas ni como cobertura.

### Diferencias encontradas en CI

La [corrida 37716853153](https://github.com/Romario1615/ClinicAI/actions/runs/37716853153)
del commit `6702084` terminó con fallos. Frontend, calidad estática, dependencias
y detección de secretos pasaron. Se corrigieron estas causas:

- Imágenes: el ejecutor no pudo resolver `trivy-action@0.28.0`. Se fija la
  [publicación oficial v0.36.0](https://github.com/aquasecurity/trivy-action/releases/tag/v0.36.0)
  al commit `ed142fd0673e97e23eac54620cfb913e5ce36c25`, comprobando su etiqueta firmada.
- Pruebas locales del agente: CI configura ENTORNO=desarrollo; la aplicación
  aislada de API ahora declara local y proveedores simulados explícitos. Las
  restricciones de entorno de la aplicación real se conservan.
- Semillas: la receta extra del acceso local no entraba en el resumen; se
  contabilizan receta, confirmación, suspensión y tomas sin cambiar los datos clínicos.

La nueva corrida remota aún no se declara aprobada. Los logs, PDF y capturas
están en `tmp/qa-20261007/` (excluido de Git): `frontend-ficha-final.log`,
`e2e-completo-ficha-repeticion.log`, `e2e-documentos-api-final.log`,
`backend-ci-focalizado.log`, `receta-sensible-final.log`,
`backend-ficha-regresion-definitiva.log`, `local-faciograma.png`,
`local-documentos.png`, `local-usuarios.png`, `local-clinicas.png` y
`faciograma-{1440,768,390}.png`.

## Comandos de la revisión anterior

```powershell
cd frontend
npm run test:ci
npm run lint
npm run build

cd ../backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run bandit -r app -ll --format screen
New-Item -ItemType Directory -Force ../tmp/qa-20261007 | Out-Null
$env:COVERAGE_FILE='../tmp/qa-20261007/cobertura-backend-final'
uv run pytest --cov=app --cov-report=term --cov-report=xml:../tmp/qa-20261007/cobertura-backend-final.xml -q --durations=8 --junitxml=../tmp/qa-20261007/backend-regresion-completa.xml
Remove-Item Env:COVERAGE_FILE

cd ../pruebas-e2e
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
$env:URL_API='http://127.0.0.1:8020/api/v1'
npx playwright test
```

Playwright requiere la API de pruebas y sus datos sintéticos ya preparados.
Los logs locales de esta revisión están en `tmp/qa-20261007/`, excluidos de Git.
El reporte HTML de Playwright queda en `pruebas-e2e/informe/`.

## Corrección posterior del perfil de pacientes

Se reprodujo el recorte de «Protegido» y la invasión de la columna vecina en la
tarjeta del Panel. La regla general `.tendencia__lista li`, más específica que
`.demografia__fila`, imponía tres columnas y reservaba solo `2ch` para el valor.
En la vista de 1280 px, la tarjeta medía 954 px y su contenido 975 px; en móvil
de 320 px medía 286 px con 307 px de contenido.

La tarjeta vive ahora en `perfil-pacientes.component.ts`, con estilos propios.
Cada fila muestra categoría y valor arriba, con la barra debajo; las etiquetas
se ajustan y el valor reserva su ancho completo. Edades y sexo comparten formato
de encabezado. Los filtros, las cifras recibidas y la supresión de grupos siguen
mostrándose desde la respuesta autorizada del dashboard.

| Comprobación posterior | Resultado |
|---|---|
| Frontend completo | 609/609, 84 archivos, 91,19 s |
| Cobertura frontend | Sentencias 86,13 %; ramas 72,88 %; funciones 81,60 %; líneas 88,32 % |
| Lint y build | Aprobados, sin avisos de presupuesto; 462,85 kB iniciales |
| Chromium focalizado | 2/2, 24,8 s: axe del panel y perfil agregado |
| Geometría de la tarjeta | Sin recortes ni solapamientos a 1440, 1280, 1024, 821, 768, 390 y 320 px |

Las cuatro pruebas nuevas del componente cubren ausencia de desglose publicable,
proporción de barras, celdas protegidas, ceros y actualización al cambiar filtros.
El escenario `16-panel-demografia.spec.ts` usa una demografía agregada sintética
para asegurar etiquetas largas, valores de seis dígitos y «Protegido». Solo
sustituye esa parte de la respuesta; no modifica datos en PostgreSQL. Comprueba
también que las celdas protegidas carecen de barra rellena. Este escenario valida
presentación; los cálculos demográficos se prueban en el backend.

```powershell
cd frontend
npm run test:ci
npm run lint
npm run build

cd ../pruebas-e2e
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx playwright test escenarios/16-panel-demografia.spec.ts escenarios/14-accesibilidad.spec.ts --grep 'perfil de pacientes|panel de seguimiento' --reporter=list
```

Los logs de esta corrección quedan en `tmp/qa-20261007/`: `frontend-perfil-pacientes.log`,
`build-perfil-pacientes.log` y `panel-demografia-final.log`. La última corrida E2E
completa de 62/62 precede al escenario nuevo; no se declara una corrida completa
de los 63 escenarios actuales.
