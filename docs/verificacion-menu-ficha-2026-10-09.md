# Menú de herramientas de la ficha — 2026-10-09

## 1. Solicitud

Corregir «Elegir qué registrar»: el menú se abría, pero elegir una herramienta
parecía no producir ninguna acción.

## 2. Causa reproducida

El módulo sí cambiaba dentro de Atención, pero su contenido comenzaba fuera
del área visible. A 1366 × 768 px, sus títulos estaban entre 1049 y 1091 px.
Al cerrar el menú, el foco volvía a «Elegir qué registrar». Las dos regresiones
nuevas fallaron antes del arreglo por mantener el panel inactivo.

## 3. Implementación

La ficha transmite una solicitud por cada elección, incluso si se repite el
mismo módulo. Historia espera su carga, selecciona la pestaña autorizada y,
después de renderizarla, desplaza su panel a la vista y le entrega el foco.
El selector de Historia clínica usa el mismo comportamiento.

## 4. Archivos

`ficha-paciente.component.ts`, `atencion-paciente.component.ts`,
`historia-clinica.component.ts/.html`, sus tres suites de componente y
`pruebas-e2e/escenarios/24-menu-herramientas.spec.ts`.
README, limitaciones, preparación para producción y este informe.

## 5. Decisiones

Se conserva la ventana de la ficha y su contexto de paciente, cita y sede.
Elegir una herramienta abre su sección; crear un registro continúa siendo
una acción explícita del profesional. No se crean registros al navegar.

## 6. Permisos

El foco solo se dirige a pestañas disponibles. Recepción y asistencia siguen
consultando; la escritura depende del rol, especialidad y autorización del
servidor. Formulario 033 conserva el requisito de permiso sensible.

## 7. Reapertura y recarga

Volver a elegir la misma herramienta funciona después de usar otra pestaña.
Una recarga de datos no vuelve a imponer la elección anterior ni roba el foco.
Reabrir el mismo módulo no recrea la historia ni solicita otra lista de citas.

## 8. Pruebas de componente

Ocho regresiones nuevas: contador de elecciones, transferencia con/sin cita,
carga pendiente, reapertura, conservación de navegación/foco, permiso sensible
y selector de Historia. La ejecución focalizada inicial aprobó 47 pruebas;
la suite de Atención final aprobó 7/7.

## 9. Regresión completa de interfaz

`npm.cmd run test:ci`: **825/825**, 107 archivos, 87,62 s.
Cobertura: instrucciones **85,49 %**, ramas **72,88 %**, funciones **81,46 %**,
líneas **87,87 %**. La primera ejecución focalizada usó cobertura global y
salió con código 1 por sus umbrales, aunque sus 41 pruebas aprobaron; después
se ejecutó sin cobertura y se comprobó la cobertura en la batería completa.

## 10. Navegador

El escenario 24 recorre las diez herramientas con un profesional y recepción,
la reapertura en escritorio/móvil, el selector de Historia y la cita conservada.
Se ejecuta junto a las regresiones 15, 17, 18, 19 y 22 sobre API/BD sintéticas.
**Resultado final: 21/21, 5,2 minutos, sin reintentos**, en un único proceso.
Incluye seis roles, teclado, escritorio/móvil, formularios clínicos, versiones,
PDF, solicitudes WhatsApp sandbox y el agente junto a la historia.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
$env:URL_API='http://127.0.0.1:8020/api/v1'
npx.cmd playwright test escenarios/15-pantallas-trabajo.spec.ts escenarios/17-registros-y-documentos.spec.ts escenarios/18-periodontograma-analitica-agente.spec.ts escenarios/19-ficha-agente-diseno.spec.ts escenarios/22-ficha-compartida-marca.spec.ts escenarios/24-menu-herramientas.spec.ts --project=chromium
```

## 11. Incidencias de la ejecución

La aserción inicial de Formulario 033 esperaba un título diferente; se corrigió
a «Formulario odontológico», manteniendo la comprobación de visibilidad.
Un proceso de Playwright adicional compartió `test-results` y borró artefactos
del otro: dos recorridos terminaron con ENOENT al cerrar sus contextos. La
regresión final se ejecuta en un solo proceso. El nuevo recorrido de Historia
también se corrigió para navegar por la interfaz: una recarga completa cierra
la sesión por ADR-0016 y no sirve para abrir una ruta autenticada.

## 12. Calidad y tamaño

`npm.cmd run lint` aprobado después de corregir el sufijo del componente doble
de pruebas. `npm.cmd run build` aprobado sin avisos; paquete inicial 468,69 kB.
`git diff --check` aprobado.

## 13. Seguridad y dependencias

`npm.cmd audit --audit-level=high`: cero vulnerabilidades conocidas tanto en
frontend como en pruebas E2E. Gitleaks del índice aprobado, sin hallazgos:
`git diff --cached | gitleaks stdin --redact --report-format json --report-path ...`.
No hay cambios de backend, paquetes, permisos ni migraciones en este arreglo.

## 14. Entorno y configuración

Frontend 4200, API temporal 8020, PostgreSQL exclusivo y Redis 14.
LLM/embeddings mock, WhatsApp/calendario sandbox y almacén de archivos
exclusivo de la tarea. No se usan datos de pacientes reales ni API pagadas.

## 15. Staging, producción y despliegue

Cambio local en `main`. No se despliega ni se publica en GitHub en este bloque.
Staging y producción conservan la configuración y los requisitos existentes.
La revisión acredita navegación local; no acredita integración externa real.

## 16. Rollback

Revertir el commit de este arreglo devuelve la navegación anterior. No exige
revertir base de datos ni restaurar permisos o registros clínicos.

## 17. Limpieza y restauración

API 8020 detenida y su base sintética eliminada después de terminar las pruebas.
Dos archivos privados de periodontograma retirados por sus rutas explícitas;
el almacén exclusivo queda sin archivos. Las evidencias de pruebas se conservan
en `tmp/qa-20261009-herramientas`. Aplicación 4200 y API 8000 responden 200;
la base y los archivos de desarrollo se conservan.

## 18. Preparación y pendientes

Arreglo verificado en interfaz completa y regresión de navegador afectada,
documentado y reunido en `main` local. No se repite el backend completo ni se
atribuye a estos 21 escenarios una corrida completa de toda la batería E2E.
Las condiciones generales de producción e integraciones reales siguen en sus
documentos; este arreglo no amplía permisos ni habilita servicios externos.
