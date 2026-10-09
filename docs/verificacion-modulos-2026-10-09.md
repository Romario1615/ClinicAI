# Revisión por módulos, formularios, botones y gráficas — 2026-10-09

## 1. Pedido

Revisar módulo por módulo los formularios, las consultas y las funciones de
los botones, y comprobar que las gráficas representan correctamente sus datos.
Corregir las incidencias encontradas y repetir la regresión anterior.

## 2. Inventario y alcance

El inventario reproducible analiza los metadatos de los componentes y sus
plantillas mediante TypeScript y el compilador de Angular:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
node infra/scripts/inventariar-interfaz.mjs > tmp/inventario-interfaz.json
```

Resultado: **99 plantillas**, **66 formularios en 45 plantillas** y **502
declaraciones de botones**. Cero errores de análisis y cero botones sin una
acción declarada, navegación o comportamiento nativo de formulario. Los
controles repetidos por un bucle cuentan una vez. Los controles compartidos
se contabilizan en su componente, no de nuevo en cada página que los contiene.

Un evento declarado no demuestra que una acción termine correctamente. Por
eso se combina este inventario con pruebas de componentes, API/integración
y recorridos de navegador que consultan los cambios guardados. No se afirma
haber ejecutado las 502 declaraciones en todas sus combinaciones de entradas,
roles, estados y tamaños de pantalla.

## 3. Matriz por módulo

«Componente/API» identifica pruebas de contratos y lógica; «navegador» añade
un recorrido real entre interfaz, API y PostgreSQL. Todos los componentes
forman parte de la batería completa. Los números son declaraciones estáticas.

| Módulo | Formularios | Botones | Comprobaciones y evidencia |
|---|---:|---:|---|
| Compartido y núcleo | 7 | 91 | Ventanas, foco, cierre, chats, fotos, editor clínico y buscador; componente/API y navegador 03/07/18/20/24. |
| Acceso | 1 | 2 | Roles, redirección, sesión y teclado; navegador 01/02/14/20/27. |
| Agenda | 2 | 41 | Reserva, recurrencia, reprogramación, cancelación, llegada, atención y ficha; navegador 05/12/25, API y concurrencia. |
| Simulador del agente | 1 | 7 | Disponibilidad, reserva y confirmación; navegador 05, componentes y herramientas backend. |
| Analítica IA | 2 | 11 | Tres vistas, filtros, búsqueda, metodología, gráficos, vacíos y reintento; navegador 18/21 y cálculos API/dominio. |
| Cambio de contraseña | 1 | 1 | Validación y contrato de autenticación; componente/API. |
| Catálogo | 4 | 19 | Alta, edición, activación y desactivación de especialidades, servicios y salas; navegador 28 y componente/API. |
| Configuración | 10 | 66 | Sedes, integraciones, horarios, pausas, cierres, disponibilidad profesional y bloqueos; navegador 11/12/28 y componente/API. |
| Conocimiento | 3 | 19 | Formularios, consulta de fuentes aprobadas y ausencia de fuente; navegador 06/20 y RAG/API. |
| Delegaciones | 1 | 4 | Alta, validación, cancelación y revocación; componente/API. |
| Equipo | 1 | 4 | Crear, editar y desactivar perfiles; navegador 10 y componente/API. |
| Gastos | 3 | 10 | Validación, importe exacto, consulta filtrada y anulación; navegador 20/23 y componente/API. |
| Historia clínica | 13 | 99 | Notas y versiones, recetas, MSP 033, odontograma, faciograma, periodontograma, documentos y permisos; navegador 04/17/18/22/24/25/26, componente/API. |
| Medicamentos | 1 | 6 | Calendario de tomas, PRN, futuro y revisión humana de alertas; navegador 04 y componente/API. |
| Pacientes | 2 | 12 | Buscar, consultar, alta, ficha, historial y accesos directos; navegador 03/20/22/24/25/26 y componente/API. |
| Pagos | 6 | 24 | Cargos, abonos, comprobantes, revisión, exportación y filtro por paciente; navegador 05/26 y componente/API. |
| Plataforma | 3 | 20 | Clínica, administrador inicial, cuentas, acceso y estados; navegador 01/17/20 y componente/API. |
| Promociones | 1 | 10 | Borrador, imagen propia/propuesta, aprobación, cola y cancelación con motivo; componente/API y diseño/accesibilidad 14/15. |
| Páginas públicas | 2 | 5 | Tokens, carga, bloqueo, caducidad, documento e indicaciones; componente/API. |
| Usuarios | 2 | 16 | Roles, alta y edición, asignaciones, desactivación/reactivación; navegador 20/28 y componente/API. |
| Asistente | 0 | 1 | Chat compartido, enviar y permisos; navegador 12 y componentes/herramientas. |
| Automatizaciones | 0 | 3 | Fases, interruptor con motivo y consulta de auditoría; componente/API y diseño/accesibilidad 14/15. |
| Ayuda | 0 | 1 | Manual propio por rol, navegación y descarga; componentes y navegador 14/15. |
| Conversaciones | 0 | 11 | Filtros, mensajes, ventana de 24 h, tomar, responder, devolver y cerrar; navegador 08/28 y componente/API. |
| Lista de espera | 0 | 12 | Anotar, ofrecer y resolver turno; navegador 09 y componente/API. |
| Panel | 0 | 6 | Cifras, cohortes, demografía, series, ocupación, contexto de consultas y navegación; navegador 14/16/29 y componente/API/dominio. |
| Seguridad | 0 | 1 | Consulta de controles y acceso autorizado; componente/API y diseño/accesibilidad 14/15. |

## 4. Incidencias corregidas

- **Editar horario era rechazado por la API.** El formulario copiaba `id`
  desde la respuesta y lo enviaba en la modificación. Ahora construye el
  esquema de entrada con los siete campos admitidos; las vigencias vacías
  se convierten en `null`. Se comprueba editar la franja y retirar sus pausas.
- **Datos de una selección anterior.** Una respuesta lenta podía reemplazar
  consultorios, horarios, cierres, bloqueos, profesionales o franjas después
  de cambiar sede/profesional. Cada consulta lleva una secuencia y descarta
  éxitos y errores que ya no corresponden al contexto visible.
- **Envíos y cierres durante el guardado.** Se impide repetir cambios de
  estado del catálogo y guardados de bloqueos; ventanas y selectores de
  horarios y disponibilidad quedan protegidos hasta terminar la petición.
  Al guardar correctamente se libera el estado antes de limpiar el formulario.
- **Errores de horario ocultos por la ventana.** El mensaje de rechazo se
  presenta dentro de la ventana con `role="alert"`; se conserva lo escrito
  para corregir y reintentar. Abrir un alta limpia el error anterior.
- **«Devolver al agente» aparecía en el estado incorrecto.** La acción se
  ofrece en `EN_HANDOFF`, cuando una persona tiene la conversación. «Tomar»
  vuelve a cargar la lista aunque el filtro conserve el mismo estado.
- **Detalle anterior en la bandeja.** Se descartan respuestas obsoletas de
  lista, paginación, detalle y apertura desde un aviso. Responder realiza una
  sola recarga del hilo a través de la lista.
- **Acciones de mensajería ofrecidas a consulta.** La interfaz deshabilita
  respuestas y gestión del hilo según `conversacion.responder` y
  `conversacion.tomar`. Los handlers comprueban lo mismo; el backend conserva
  la autorización existente y no se conceden permisos adicionales.
- **Cifras y análisis del Panel asociados al filtro anterior.** Seis
  regresiones reproducen respuestas y errores tardíos de actual/comparación,
  un rango invalidado, catálogos de otra especialidad, análisis pendientes
  y consultas duplicadas. El contexto de consulta invalida los resultados
  anteriores y limpia comparación y análisis al cambiar filtros.

## 5. Archivos

- `frontend/src/app/paginas/catalogo/catalogo.component.ts` y su spec.
- Configuración: `agenda-configuracion`, `agenda-profesionales` y
  `bloqueos-agenda`, cada componente y su spec.
- `conversaciones/conversaciones.component.ts` y su spec;
  `nucleo/servicios/configuracion.ts` añade el nombre de un permiso existente.
- `analitica/analitica.component.spec.ts` y
  `backend/pruebas/api/test_analitica_api.py`.
- `panel/panel.component.ts` y su spec; el escenario 29 comprueba errores
  anteriores retrasados mientras conserva cifras de la API real.
- `infra/scripts/inventariar-interfaz.mjs`.
- `pruebas-e2e/escenarios/28-revision-modulos.spec.ts` y
  `pruebas-e2e/apoyo/sembrar-bandeja.py`.
- README, matriz de formularios, límites, preparación y coordinación.

## 6. Decisiones

Se conservan los contratos de la API, los registros clínicos por versiones,
los permisos por rol/especialidad y el patrón de ventanas flotantes. No hay
dependencias nuevas, endpoints nuevos ni modificaciones de esquema.

Las secuencias de consulta impiden que una respuesta tardía cambie el destino
visible. Los selectores y cierres se bloquean durante la escritura. Las
pruebas de rechazo verifican el mensaje y el borrador, no solo el código HTTP.

## 7. Gráficas y cálculos

La nueva prueba API prepara dos días con cargas distintas: una atención con
60 minutos de espera y cinco con 10. Comprueba el promedio ponderado
`110/6 ≈ 18,33`, no el promedio de dos promedios. También comprueba:

- Diez citas, seis atenciones y 120 minutos programados para ellas.
- Una misma persona contada una vez por día: dos pacientes-día.
- Asistencia 75 %, inasistencia 25 % y cancelación 20 %, con sus denominadores.
- Espera no medida como `null` y cero muestras, frente a conteo cero observado.
- Ausencia de pronóstico cuando solo existen dos días de mediciones.

El spec de Analítica verifica coordenadas SVG exactas de valores 0/5/10,
continuidad de histórico/pronóstico y límites de la banda de predicción.
Los recorridos de navegador comprueban tres vistas, valores grandes, series
vacías, ventanas, errores, reintento, lectura con teclado y adaptación móvil.

La regresión backend incluye aprendizaje de estacionalidad/tendencia,
separación temporal de entrenamiento/evaluación, límites de porcentajes,
rechazo de duplicados y valores no finitos, historial insuficiente y ocupación
con pausas/cierres/bloqueos. No se modifica el algoritmo ni se atribuye una
precisión real a una muestra sintética.

## 8. Entorno y aislamiento

Se preparan **seis bases sintéticas exclusivas**: una para API, cuatro clones
para workers de pytest y una para navegador. PostgreSQL/pgvector y Redis son
reales; LLM y embeddings usan `mock`, WhatsApp y calendario usan `sandbox`.
La API temporal utiliza 8020; se conserva el frontend 4200 y la API de
desarrollo 8000. Los archivos cifrados de QA se guardan dentro de
`tmp/qa-20261009-modulos/almacen`, fuera de los archivos de desarrollo.

La semilla de bandeja exige un nombre de base de QA y el puerto local 8020.
No imprime tokens. Prepara un hilo vigente y uno vencido; el escenario devuelve
la integración del agente a su valor anterior en `finally`. Franjas, cierres
y disponibilidad profesional creados por el escenario se retiran por su ID.

## 9. Interfaz y compilación

```powershell
# Desde frontend; configuración temporal con maxWorkers: 2
npx.cmd ng test --no-watch --coverage --runner-config=../tmp/qa-20261009-modulos/vitest.config.mjs
npm.cmd run lint
npm.cmd run build
```

Primera regresión posterior a los cambios administrativos: **859/859**,
108 archivos, 355,98 s. Lint y build aprobados; paquete inicial 469,26 kB.
Después se añadió y reprodujo la corrección del contexto del Panel.

Corrida completa final tras la corrección del Panel: **865/865**, **108
archivos**, **155,47 s**. Sus seis regresiones habían fallado antes de
corregir; el archivo del Panel aprueba después **25/25**, **3,97 s**.
Lint y build finales aprobados; Angular comprueba tipos y plantillas.
Paquete inicial **469,26 kB**, sin avisos de presupuesto; build **15,556 s**.

Las regresiones nuevas se reprodujeron antes de corregir: respuestas
obsoletas, envíos/cierres pendientes, estado de devolución y payload de
edición. Las pruebas no se eliminaron ni se relajaron sus aserciones.

## 10. Backend

```powershell
# Desde backend; POSTGRES_BD/QA_BD_BASE apuntan a la base exclusiva.
# PYTHONPATH incluye tmp/qa-20261009-modulos para el plugin qa_worker.
# qa_worker asigna a cada gw0..gw3 su clon y Redis 10..13.
.venv/Scripts/python.exe -m pytest -n 4 -p qa_worker --cov=app --cov-report=xml:../tmp/qa-20261009-modulos/backend-cobertura.xml --junitxml=../tmp/qa-20261009-modulos/backend-resultados.xml -q
.venv/Scripts/python.exe -m pytest pruebas/api/test_analitica_api.py -q
```

Corrida completa: **2228 aprobadas y tres omitidas**, **1280,71 s**.
Las tres omitidas son `test_agente_modelo_real.py`: requieren la API real de
Anthropic y `PRUEBAS_LLM_REAL=1`. La nueva regresión numérica se añadió después
de esa colección y su archivo aprueba **3/3** en **6,61 s**. No se presenta
la suma de ambas ejecuciones como una sola corrida de 2229 casos.

Después de verificar la reversión de la migración se repite Analítica y los
ocho archivos de indicadores, ocupación, aprendizaje, cohortes y capturas:
**57/57**, **63,47 s**, sin cobertura para conservar el informe completo.
Incluye la nueva prueba; es una regresión separada, no 57 casos adicionales.

```powershell
.venv/Scripts/python.exe -m pytest pruebas/api/test_analitica_api.py pruebas/api/test_dashboard_ocupacion_api.py pruebas/api/test_indicadores_api.py pruebas/unitarias/test_aprendizaje_dashboard.py pruebas/unitarias/test_dashboard_ocupacion.py pruebas/unitarias/test_dashboard_ocupacion_agenda.py pruebas/unitarias/test_dashboard_analisis_local.py pruebas/unitarias/test_dashboard_retorno_30_dias.py pruebas/unitarias/test_capturas_dashboard.py -q
```

## 11. Navegador

```powershell
# Desde backend, sobre la BD sintética que atiende 8020:
.venv/Scripts/python.exe ../pruebas-e2e/apoyo/sembrar-bandeja.py --bd <base-QA>
# Los últimos datos JSON establecen QA_BANDEJA_VIGENTE y QA_BANDEJA_VENCIDA.
# Desde pruebas-e2e, URL_BASE=http://localhost:4200;
# URL_API=http://127.0.0.1:8020/api/v1 y Chromium local configurado:
npx.cmd playwright test --project=chromium
```

Corrida completa del bloque administrativo: **110/110**, **23,3 minutos**,
sin reintentos ni omisiones. Incluye los seis casos nuevos del escenario 28.
Después de terminar esa corrida se aplica la corrección del contexto del
Panel. Su escenario 29 aprueba primero **1/1** en **8,8 s** y conserva cifras
obtenidas sin cambios de la API real; solo retrasa y rechaza dos solicitudes
anteriores para comprobar el descarte de resultados obsoletos.

```powershell
npx.cmd playwright test escenarios/14-accesibilidad.spec.ts escenarios/16-panel-demografia.spec.ts escenarios/21-analitica-diseno.spec.ts escenarios/29-panel-contexto.spec.ts --project=chromium --grep='panel de seguimiento|perfil de pacientes|analítica:|Panel conserva'
```

Regresión final después del ajuste del Panel: **9/9**, **57,5 s**, sin
reintentos. Comprueba accesibilidad del Panel/filtros y Agenda, perfil de
pacientes en siete anchos, las seis pruebas de Analítica y el contexto real
del Panel ante errores HTTP anteriores.

Las corridas se ejecutan una tras otra; el informe HTML de la completa se
copia bajo `tmp/qa-20261009-modulos/informe-completo` antes de que Playwright
regenere su directorio de resultados. No se suman las corridas como si
hubieran sido una sola ejecución de 119 casos.

El escenario 28 aporta seis recorridos de catálogo, cuentas/roles,
horarios/cierres, bloqueos, conversaciones y disponibilidad profesional.
Comprueba validación, cancelación, lectura posterior y eliminación o cambio
de estado según la entidad. El caso de mensajería comprueba la ventana de
24 h, toma/asignación, respuesta con `Idempotency-Key`, devolución y cierre.
La respuesta queda en cola sandbox: no demuestra entrega con Meta.

Se corrigieron selectores del spec que incluían texto de las opciones,
filas de otra pestaña y un atributo `name` que NgModel no refleja en el DOM.
Se espera la retirada efectiva de la pausa antes de seleccionar «Hasta».
No se amplían las esperas para ocultar el fallo real del payload.

## 12. Cobertura

Backend: **88,91 %** combinada, **92,23 %** de líneas y **73,95 %** de ramas,
calculadas por la batería completa con workers aislados.

La primera regresión de 859 pruebas obtuvo sentencias 85,68 %, ramas
73,08 %, funciones 81,81 % y líneas 88,13 %.

La corrida final de 865 pruebas obtiene sentencias **85,80 %**
(9399/10954), ramas **73,07 %** (3460/4735), funciones **81,95 %**
(2362/2882) y líneas **88,29 %** (7982/9040).

## 13. Calidad, secretos y dependencias

Ruff de backend y semilla de bandeja: aprobado. Formato: **470 archivos**.
Mypy: **255 archivos**, sin incidencias. Bandit de la semilla nueva: cero
hallazgos. El código de aplicación backend no cambia en este bloque.
`node --check infra/scripts/inventariar-interfaz.mjs` aprobado.

Los escenarios 28/29 y sus auxiliares también aprueban TypeScript estricto con
`--noEmit`, mediante una configuración temporal. Los tipos Node fijados
`22.10.2` se instalaron únicamente bajo `tmp` para esa comprobación: no se
modificaron los manifiestos ni los locks de la aplicación.

Auditorías de dependencias frontend y E2E, incluidos paquetes de desarrollo:
cero vulnerabilidades. `pip-audit` del exportado fijado por `uv.lock`, con
base, desarrollo y LLM: sin vulnerabilidades conocidas. El extra opcional
`embeddings` mantiene la exclusión documentada E-12; no se instala aquí.

Gitleaks del índice del bloque funcional: **cero secretos**. Análisis de
`origin/main..HEAD` después de `0aca147`: **18 commits**, cero secretos;
se redactan los informes y no se muestran valores sensibles.
Índice del bloque del Panel y del cierre documental: cero secretos.

## 14. Migraciones

No se añade ninguna migración. Se aplicó `upgrade head` y `alembic check` al
preparar las bases. En la base API exclusiva se comprobó después el recorrido
**038 → 037 → 038**, verificando la revisión exacta entre operaciones y
repitiendo `alembic check`. No se revierte la base de desarrollo ni WhatsApp.

Alembic conserva sus avisos existentes sobre el valor calculado
`knowledge_chunks.contenido_tsv` y la comparación del índice trigram con
cláusula de operador. El resultado final es «No new upgrade operations
detected»; la revisión registrada vuelve exactamente a `20261009_038`.

## 15. Configuración y credenciales

La verificación no requiere claves de clientes. Los adaptadores externos
siguen simulados y el límite de acceso local de la API de QA es 200/minuto.
El agente de WhatsApp solo se habilita temporalmente en la base sintética
para probar la devolución; se restaura al concluir ese escenario.

Staging y producción necesitan las variables y servicios de
[despliegue](deployment.md): PostgreSQL/Redis, cifrado y almacenamiento,
autenticación de producción, worker y credenciales de proveedores elegidos.
Faltan cuenta/servidor de prueba MCP, Meta y las APIs contratadas del cliente
para una aceptación externa; no se crean credenciales ni se envían mensajes.

## 16. Despliegue, rollback y restauración

Trabajo local en `main`, sin push ni despliegue. Entregar el build del
frontend para aplicar las correcciones; los contratos API no cambian.
Revertir el commit del bloque y reconstruir recupera la interfaz anterior;
no exige un downgrade de base de datos. La restauración de datos operativos
usa el [procedimiento de respaldo](deployment.md), ajeno a este cambio.

Se detuvo únicamente la API temporal 8020 y se verificó el puerto libre;
se retiraron las seis bases por su nombre exclusivo, comprobando su ausencia.
Se eliminaron individualmente los cuatro archivos cifrados sintéticos de
este bloque, tras verificar sus rutas; quedan directorios vacíos y los
informes ignorados bajo `tmp`. La aplicación **4200** y la API **8000**
responden **200** después de la limpieza. La carpeta ajena `.impeccable`
permanece intacta y no se incluye en los commits.

## 17. Riesgos y límites

Esta ejecución comprueba Chromium y los tamaños declarados por los
escenarios; no incluye Firefox/Safari ni cámaras físicas. Las fotografías y
documentos usan muestras sintéticas. No se ejecuta una carga nueva, DAST,
pipeline remoto, Meta real, calendario externo real ni un LLM contratado.
Los tres casos del modelo externo permanecen omitidos deliberadamente.

Los pronósticos y sugerencias operativas requieren historial suficiente;
su cálculo correcto en una muestra no acredita precisión de producción.
Esta revisión automatizada no sustituye aceptación de los profesionales,
configuración de infraestructura ni los requisitos legales pendientes.

## 18. Cierre y documentación

README resume las correcciones; la matriz de formularios enlaza el inventario
reproducible. Límites y preparación declaran el alcance de la batería y las
integraciones pendientes. AGENTS registra el bloque para Claude. Los manuales
por rol siguen en Ayuda; se conservan las acciones y permisos descritos.

Correcciones funcionales confirmadas en `main`: `0aca147` (formularios,
bandeja, inventario y pruebas) y `d80f2ed` (contexto del Panel y su regresión).
La documentación se confirma en un bloque de cierre separado, sin push.
La matriz distingue módulos comprobados en navegador de contratos de
componente/API y deja explícitos los límites de la ejecución sintética.

Regresión anterior y pruebas de las correcciones aprobadas. Las integraciones
externas y aceptación clínica siguen fuera de esta revisión local; no se
declara una preparación integral de producción ni una prueba exhaustiva
de cada combinación de los 502 controles.
