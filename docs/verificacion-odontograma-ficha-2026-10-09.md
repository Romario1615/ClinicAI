# Odontograma y funciones de ficha — 2026-10-09

## 1. Solicitud

Hacer legible el odontograma en Historia, revisar herramientas y accesos de la
ficha, corregir fallos y evaluar una conexión de WhatsApp mediante MCP.

## 2. Problema reproducido

En 1366×768, la pieza medía 25,59 px. La distribución calculaba su tamaño a
partir del alto sobrante entre cabeceras, paleta y captura de fotos. El lienzo
con contención de tamaño podía quedar contraído. La prueba nueva falló con
esa medida antes de cambiar estilos.

## 3. Diseño implementado

Selector compacto de especialidad en Historia y ficha, conservando opciones
y permisos. El mapa calcula piezas por ancho con mínimo de 44 px en
escritorio; un contenedor estrecho distribuye las hemiarcadas en filas. La
tarjeta permite desplazamiento interno. Guardado, motivo y fotos pasan a una
ventana flotante y la barra de guardado permanece accesible dentro de la tarjeta.

## 4. Correcciones funcionales

Un rechazo del primer guardado se confundía con fallo de carga, retirando el
mapa y la ventana. Se separan ambos estados: un rechazo mantiene borrador,
ventana y error para reintentar. Se bloquean cierre y segundo envío durante
el guardado. Cerrar la revisión conserva piezas/motivo; fotos pendientes
requieren confirmación de descarte. Si una versión ya se creó y fallaron
fotos, el reintento no crea otra; al cerrar se recarga la versión existente.

## 5. Accesos corregidos

«Pagos del paciente» enviaba `paciente` en la URL, pero Pagos solo filtraba
por `cita`. Se añade filtro opcional `paciente_id` a pagos y cargos, aplicado
antes de contar/paginar dentro de la consulta autorizada. El alta de un abono
conserva el paciente de la ficha y consulta sus citas; si hay cita de origen,
la mantiene. Gestionar citas conserva el paciente sugerido de Agenda.

## 6. Archivos y decisiones

Frontend: selector común, Ficha, Historia, Odontograma y Pagos, con sus suites.
Backend: rutas/repositorio de Pagos, API de listado y manual profesional de
Ayuda. Escenario de navegador 26. README, arquitectura, seguridad, limitaciones,
preparación, evaluación MCP y coordinación AGENTS. Sin migración ni nuevos
secretos. La presentación no modifica vocabulario clínico ni datos existentes.

## 7. Permisos e integridad

Profesional registra con permiso, especialidad propia y relación asistencial;
Recepción y Asistencia consultan sin editar. Las versiones antiguas son
inmutables. El filtro financiero no amplía clínica, sede ni profesional.
N3/Formulario 033 conserva su permiso adicional. Las pruebas usan pacientes
sintéticos y PostgreSQL exclusivo.

## 8. Pruebas backend

```powershell
.venv/Scripts/python.exe -m pytest pruebas/api/test_odontologia_api.py pruebas/api/test_periodontograma_api.py pruebas/api/test_historia_api.py pruebas/api/test_consulta_historia_roles_api.py pruebas/api/test_especialidades_historia_api.py pruebas/api/test_planes_tratamiento_api.py pruebas/api/test_imagenes_api.py -q --no-cov
.venv/Scripts/python.exe -m pytest pruebas/api/test_pagos_listado_api.py -q --no-cov
.venv/Scripts/python.exe -m pytest pruebas/unitarias/test_ayuda_manuales.py -q --no-cov
```

Resultados: **89/89** clínicos (158,41 s), **11/11** Pagos (13,03 s), **26/26**
manuales (3,56 s); **126 casos distintos**. Dos casos nuevos verifican filas,
total, otro paciente, sede excluida y UUID inválido de ambos listados. No se
repitió toda la batería backend previa ni se midió una nueva cobertura backend.

## 9. Pruebas de interfaz

Regresión focal de Odontograma/selector: **19/19**; Pagos: **15/15**. Casos
nuevos cubren revisión sin POST, conservación de borrador/motivo, envío único,
error dentro de ventana, recuperación de fotos y bloqueo de consulta.

La batería completa usa el comando siguiente y configuración temporal
`maxWorkers: 2`, conservando umbrales y aserciones. **836/836**, 107 archivos,
168,15 s. Cobertura: instrucciones **85,70 %**, ramas **73,13 %**, funciones
**81,63 %**, líneas **88,10 %**. Se repitió completa tras el ajuste final de
la ficha; las corridas anteriores no se suman a ese total.

```powershell
npx.cmd ng test --no-watch --coverage --runner-config=../tmp/qa-20261009-ficha-agenda/vitest.config.mjs
```

## 10. Navegador

Escenario 26: **4/4**, 52,1 s, sin reintentos. Comprueba Historia, ficha,
dos versiones persistidas y sus colores, nota por pieza, consulta por
Recepción, extremos 18/28/38/48, 1366×768, 1024×768 y 390×844, acceso a
Pagos con filtros reales y Agenda con el paciente sugerido.

La batería completa obtuvo **99/100**, 15,9 minutos. Todas las funciones de
ficha/herramientas aprobadas; el único fallo fue contraste durante la entrada
animada del detalle de Analítica. Se corrigió la sincronización de la prueba,
manteniendo el mismo control WCAG, y se añadió una serie financiera vacía
determinista. Regresión completa del escenario 21: **6/6**, 32,7 s.
Total: **101 casos distintos aprobados entre ambas corridas**, sin reintentos
automáticos. No se presenta la primera corrida como 100/100 ni se repitieron
los otros 95 casos tras cambiar únicamente ese spec.

Los artefactos de la primera corrida se conservaron en
`tmp/qa-20261009-odontograma-ficha/artefactos-completos` antes de ejecutar la
segunda. Logs separados: `navegador-completo.log` y `navegador-analitica.log`.
Se ejecuta una sola CLI a la vez para conservar sus artefactos.

```powershell
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx.cmd playwright test --project=chromium --workers=1
npx.cmd playwright test escenarios/21-analitica-diseno.spec.ts --project=chromium --workers=1
```

## 11. Matriz funcional

| Función de la ficha | Evidencia complementaria |
| --- | --- |
| Resumen, datos, búsqueda y foto de perfil | Escenarios 03/12/20/22; suites de Ficha y Pacientes |
| Historial de citas y atención desde Agenda | 12/17/25; contexto, nota vinculada y regreso a cita |
| Diez herramientas del selector y foco visible | 24; profesional, recepción, Historia y reapertura móvil |
| Evolución, antecedentes y versiones | 04/22/25; API Historia y consultas por rol/especialidad |
| Recetas y seguimiento de tomas | 04/17; documentos privados y calendario de recuento |
| Indicaciones | 20; ventana y enlace público, suites públicas y de Historia |
| Presupuestos/cotizaciones/PDF/solicitud WhatsApp | 17; generación y entrega sandbox, no entrega Meta |
| Odontograma | 26; editar pieza/cara/nota, motivo, dos versiones y consulta |
| Periodontograma/índice de placa | 18/24; API periodontal y odontológica |
| Formulario 033 | 04/24; formulario sensible y rechazo sin permiso |
| Planes/procedimientos/controles | 04/17; API Planes y contexto de citas |
| Faciograma | 17; zonas, versiones, cita y PDF en escritorio/móvil |
| Imágenes clínicas y adjuntos | 07/18; API Imágenes y reintentos de fotos |
| Agente del paciente | 18/19; resumen autorizado y confirmación de acciones administrativas |
| Accesos Pagos/Agenda | 25/26; paciente y cita conservados; ámbito financiero API |

La matriz identifica recorridos ejecutables; no afirma cobertura exhaustiva
de todas las combinaciones clínicas ni aceptación por especialistas.

## 12. Incidentes de verificación

Las primeras pruebas nuevas usaban nombres supuestos «Pieza 16», «Cerrar» y
«Agenda», mientras la aplicación muestra «Pieza FDI 16», «Listo» y la fecha
del día. Se corrigieron los localizadores para probar controles reales.
La selección de versión recibió una etiqueta accesible explícita. La vuelta
a Pacientes espera URL y cabecera de la nueva página antes de buscar, evitando
escribir en el formulario anterior durante la navegación. Una primera
corrida coincidió con recarga del frontend al editar; no se contabiliza como
aprobada. El fixture de cargos necesitaba `origen="PACTADO"`, exigido por la
base: se corrigió el fixture sin relajar la restricción.

En la corrida completa, Axe observó texto de serie vacía con ratios 3,62 y
3,54 mientras la ventana pasaba de opacidad cero a uno. La prueba espera las
animaciones reales de la ventana y verifica opacidad acumulada uno antes de
medir. La serie vacía estable aprueba WCAG con el estilo original; no se
excluyó la regla ni se apagaron las animaciones de la aplicación.

## 13. Calidad y seguridad

Ruff, formato y mypy (255 archivos) aprobados. Bandit de los archivos backend
modificados sin hallazgos. Lint y build aprobados; paquete inicial 468,69 kB.
`npm audit --omit=dev` y `npm audit` completo: **0 vulnerabilidades**.
Gitleaks del índice de implementación: **0 secretos**. Se repite la inspección
al confirmar la documentación final: **0 secretos**. El commit de
implementación también se inspeccionó sin hallazgos.

## 14. WhatsApp MCP y credenciales

La búsqueda de plugins devolvió cero MCPs de WhatsApp y no hay servidor
configurado. Se localizaron proyectos de autores que usan Cloud API; la
[evaluación](whatsapp-mcp.md) registra enlaces, alcance y encaje propuesto.
Faltan servidor/transporte y cuenta Meta de prueba. No se instalaron paquetes
MCP ni se enviaron mensajes reales. Las credenciales se introducirán en
Configuración/almacén correspondiente, fuera de Git y del chat.

## 15. Entornos y despliegue

Frontend 4200 y API de desarrollo 8000 permanecen disponibles. Navegador y API
usan temporalmente 8020, BD/almacén exclusivos y proveedores sandbox/mock.
Staging/producción requiere autenticación definitiva, configuración cifrada
por clínica, Cloud API con webhooks firmados, consentimiento, plantillas,
worker y comprobación de entrega. No se desplegó ni publicó este bloque.

## 16. Rollback y restauración

El cambio no migra datos: revertir su commit restaura interfaz y parámetros
anteriores. Las versiones creadas permanecen en PostgreSQL y no se eliminan
al revertir código. Respaldo/restauración de datos clínicos sigue el runbook
existente. La base temporal `clinicai_qa_ficha_219824a2` se eliminó; se detuvo
la API 8020 y se retiraron sus dos archivos sintéticos por rutas literales
comprobadas. Quedan los logs/artefactos y directorios vacíos ignorados por Git.
Aplicación 4200 y API 8000 verificadas con **HTTP 200** al terminar. La base
de desarrollo y sus archivos permanecen intactos.

## 17. Pendientes

Identificar el MCP deseado y comprobar conexión con cuenta de prueba. Aceptación
clínica por odontología/estética, entrega externa real y controles de producción
siguen pendientes. Navegador complementa API y componentes; no evalúa todos
los posibles datos de cada formulario ni sustituye revisión clínica.

## 18. Evaluación

Los ajustes locales de presentación, persistencia y accesos cuentan con
regresión completa de interfaz, API afectada y los 101 recorridos distintos
descritos arriba. Se conserva consulta por roles y edición por especialidad.
La sincronización de contraste de Analítica se corrigió como incidencia de
la verificación. No se declara conexión MCP ni preparación integral de
producción. La retirada del entorno temporal se registra en la sección 16.
