# Verificación: Google Calendar y calendario propio

Fecha: 2026-10-10. Rama: `main`, trabajo local sobre `076ddff`.
Implementación confirmada en `2431be8`; documentación en el bloque siguiente.

## 1. Objetivo y alcance

Completar el adaptador Google Calendar v3, consumir las claves configuradas por
clínica, renovar credenciales y ofrecer al profesional una ventana propia en
Agenda. La agenda interna sigue siendo la fuente de verdad.

## 2. Implementación

- Crear, consultar, modificar y retirar eventos mediante HTTPX.
- ID determinista, reconocimiento de envíos repetidos y recreación acotada.
- Actualización y retirada con revisión remota y `If-Match`.
- Renovación anticipada y una repetición tras 401; refresco rotado o conservado.
- Configuración cifrada por clínica; desactivar no usa claves globales.
- OAuth firma el calendario elegido; consentimiento en otra pestaña conserva
  la sesión original. Callback HTML para navegador y JSON para clientes API.
- Ventana con consulta, autorización, resumen de sincronización y desconexión
  con motivo. Reintento manual de errores, sin sobrescribir conflictos.
- Manual exclusivo del profesional actualizado en Ayuda.

## 3. Archivos

Backend: `app/modulos/calendario/{google,configuracion,adaptadores,seleccion,
oauth,servicios,rutas,esquemas}.py`, `app/tareas/calendario.py`,
`app/nucleo/auditoria.py`, `app/modulos/ayuda/manuales.py` y sus pruebas.
Frontend: `paginas/agenda/calendario-profesional.{component,service}.ts`,
su spec y la cabecera de Agenda. Navegador: escenario 30.
Documentación: README, guía Calendar, ADR-0027, seguridad, limitaciones,
preparación y este informe.

## 4. Decisiones

[ADR-0027](decisiones/0027-calendario-google-y-renovacion.md). HTTPS a hosts
fijos, sin redirecciones del cliente HTTP. IDs válidos para Google derivados
de la cita; un 409 se verifica antes de aceptar el evento. Un borrado confirmado
avanza a otra generación determinista, con máximo de cinco.

La autorización se abre mediante un enlace explícito en otra pestaña; la sesión
de ClinicAI se mantiene en memoria en la original. La interfaz admite únicamente
el destino OAuth HTTPS de Google y usa `noopener noreferrer`.

## 5. Permisos y ámbito

Se conserva `profesional.conectar_calendario`: únicamente conexiones del
profesional autenticado. ID ajeno produce 404. No se añaden permisos, rutas
ni escrituras clínicas. El callback verifica firma, vigencia, uso único y
profesional activo. Su auditoría identifica el retorno como SISTEMA y conserva
el profesional verificado en los metadatos; no inventa una sesión de usuario.

La sincronización manual procesa solo la conexión propia solicitada. Conexión,
desconexión y sincronización manual quedan auditadas.

## 6. Pruebas backend

**1.293/1.293 aprobadas**, 270,26 s, sin pruebas omitidas en esta selección.

Incluye todas las unitarias del backend y regresión de calendario, tareas,
Agenda, configuración, Ayuda, anti doble reserva y reserva concurrente.
PostgreSQL y Redis reales; solo las respuestas de Google se sustituyen por
`httpx.MockTransport`. No se declara una ejecución completa del backend.

Comando sobre la base sintética exclusiva, usando el lanzador local ignorado:

```powershell
$env:COVERAGE_FILE='../tmp/qa-20261010-calendario/.coverage-final'
uv run python ../tmp/qa-20261010-calendario/entorno.py -m pytest pruebas/unitarias pruebas/integracion/test_calendario.py pruebas/integracion/test_tareas_calendario.py pruebas/api/test_calendario_api.py pruebas/integracion/test_servicio_agenda.py pruebas/integracion/test_tareas_agenda.py pruebas/integracion/test_anti_doble_reserva.py pruebas/api/test_agenda_api.py pruebas/api/test_configuracion_api.py pruebas/api/test_ayuda_api.py pruebas/concurrencia/test_reserva_concurrente.py -q --tb=short --cov=app.modulos.calendario --cov=app.tareas.calendario --cov-report=term-missing --cov-report=xml:../tmp/qa-20261010-calendario/calendario-final.xml --junitxml=../tmp/qa-20261010-calendario/backend-final.xml
```

## 7. Pruebas frontend

`npm run test:ci -- --coverage`: **878/878**, 109 archivos, 71,40 s.
Incluye 13 casos de la ventana nueva: permisos, envíos duplicados, borradores,
errores, sincronización, desconexión, cargas anteriores y destinos OAuth inválidos.

## 8. Navegador y diseño

Chromium: **8/8**, sin reintentos, ejecución conjunta de los escenarios 15 y 30.

Escenarios 15 y 30: escritorio 1366×768, tableta 1024×768 y móvil 390×844;
ventana dentro del viewport, errores legibles, validación, consulta por rol,
Escape, recuperación de foco y reglas WCAG con axe. Se conservan las listas
con desplazamiento propio y los pies de ventana fijos.

```powershell
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
npx playwright test escenarios/15-pantallas-trabajo.spec.ts escenarios/30-calendario-profesional.spec.ts --project=chromium --workers=1 --retries=0
```

## 9. Cobertura e inventario

Frontend: declaraciones **85,86 %**, ramas **73,21 %**, funciones **82,03 %**,
líneas **88,35 %**. Calendario y su tarea: **89,95 %** combinando líneas y ramas;
umbral del 80 % conservado. Configuración, esquemas, eventos y selección: 100 %;
adaptador Google: 85 %; servicio: 88 %; OAuth: 92 %; rutas: 94 %; tarea: 93 %.

Inventario estático: 100 plantillas, 68 formularios, 510 declaraciones de
botones; cero errores y cero botones sin acción declarada. Ese inventario no
equivale a probar funcionalmente cada botón en esta ejecución.

## 10. Calidad estática y compilación

Ruff y formato aprobados (472 archivos); mypy sin incidencias en 257 archivos.
Bandit sobre calendario, tarea y auditoría sin hallazgos. Las excepciones B105
son constantes de estados, nombres públicos de acciones y URL pública de OAuth,
con motivo junto al código; no se omite esa regla globalmente.
Frontend lint y build aprobados, sin avisos de compilación.

## 11. Fallos encontrados y corregidos

- La interfaz no traducía el error HTTP: ahora muestra el mensaje del servidor
  y conserva el calendario escrito.
- El regreso a la misma pestaña perdería la sesión en memoria: se usa otra
  pestaña y actualización explícita de estado.
- Un fallo transitorio durante el refresco después de un 401 podía interpretarse
  como revocación. Se conserva la clasificación del fallo, incluido el segundo
  intento de retirada. Ocho nuevas regresiones cubren estos casos.
- Al obtener el bloqueo se vuelve a leer la fila, para no utilizar credenciales
  anteriores conservadas por la sesión ORM. Una regresión usa PostgreSQL real.
- Una fixture de cancelación omitía el motivo obligatorio: se corrige la prueba,
  manteniendo la restricción de PostgreSQL.
- La etiqueta de campo requerida incluye un asterisco añadido por la interfaz;
  el selector del navegador reconoce ese nombre accesible completo.

Durante el montaje de pruebas se corrigió la URL de la API aislada para incluir
`/api/v1`. Se separó el archivo de cobertura: dos procesos de pytest sobre el
mismo archivo alteraban la medición. La evidencia final procede de ejecuciones
terminadas, sin bajar el umbral del 80 % ni relajar las reglas WCAG.

## 12. Secretos y dependencias

Gitleaks del índice y de los commits de este bloque, con salida redactada:
ningún secreto detectado. Los informes se conservan en el directorio QA ignorado.

`npm audit` de frontend y E2E: cero vulnerabilidades. `pip-audit` del conjunto
bloqueado base/dev/LLM: ninguna vulnerabilidad conocida. El extra opcional
`embeddings` no se auditó en este bloque; conserva el seguimiento E-12.
No se incorporan paquetes ni se cambia ningún archivo de dependencias.

## 13. Base de datos y migraciones

No se crean migraciones ni se modifica el esquema. La base de pruebas se creó
desde cero y se llevó a `20261009_038`. `alembic check`:
**No new upgrade operations detected**.

Persisten avisos del comparador de Alembic sobre ciclos entre imágenes/planes,
columnas calculadas y el índice trigram existente; no se presentan como validación
completa de esas expresiones. No se revierte una migración ajena para este bloque.

## 14. Aislamiento y limpieza

Solo pacientes sintéticos. API temporal 8020 y base exclusiva con prefijo
`clinicai_qa_calendario_`; la app 4200 y la API de desarrollo 8000 se conservan.
Las pruebas de BD revierten sus transacciones. Los logs, XML y capturas se
guardan en `tmp/qa-20261010-calendario`, ignorado por Git.

API temporal detenida y puerto 8020 libre. Base `clinicai_qa_calendario_ada79fb1`
retirada tras verificar el nombre exacto y ausencia de conexiones. No se borran
archivos ajenos ni la carpeta `.impeccable/`, que ya estaba presente. Aplicación
4200 y API de desarrollo 8000 responden 200 después de la limpieza.

## 15. Credenciales y configuración

El entorno local permanece en `MODO_CALENDARIO=sandbox`; LLM y WhatsApp de QA
son simulados. No se usan credenciales reales, no se publica ningún evento en
Google y no se envía ningún mensaje.

Para staging: cuenta autorizada de prueba, proyecto OAuth, URI exacta al callback
de la API, integración habilitada y secreto configurado por clínica. El servidor
debe habilitar `MODO_CALENDARIO=google`. Configurar secretos de firma y cifrado
por los mecanismos existentes; nunca copiarlos al repositorio.

## 16. Despliegue

Trabajo local en `main`, sin push ni despliegue. Antes de activar para un cliente,
ejercer consentimiento, crear/mover/cancelar, borrar/mover fuera de ClinicAI,
revocar permiso y observar reintentos con su cuenta de prueba. Verificar cuotas,
trabajos periódicos y alertas; resolver los bloqueos externos de preparación.

## 17. Rollback y restauración

Desactivar la integración de la clínica detiene nuevas operaciones reales sin
recurrir a otra cuenta. Desconectar revoca las credenciales locales; no elimina
eventos ya publicados. No usar sandbox como rollback en producción.

Revertir los commits de este bloque y reconstruir frontend/API/worker no requiere
reversión de esquema. La restauración debe recuperar BD y clave de cifrado
coherentes; si la clave se pierde, volver a autorizar. No se realizó una nueva
restauración de backups en esta verificación.

## 18. Pendientes y preparación

Implementación local verificada en el alcance descrito. La aceptación real de
Google sigue pendiente: no se cierran E-1 ni E-2 ni se declara producción lista.
Faltan sincronización incremental con `syncToken`, resolución visual de conflictos
y evaluación de cuotas a volumen. Un borrado repetido más de cinco generaciones
requiere revisión. No se ejecutaron carga, DAST, navegadores adicionales ni
evaluaciones de modelos clínicos en este bloque.

Fuentes primarias: [Google Calendar: insertar eventos](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert),
[errores](https://developers.google.com/workspace/calendar/api/guides/errors),
[OAuth offline](https://developers.google.com/identity/protocols/oauth2/web-server#offline).
