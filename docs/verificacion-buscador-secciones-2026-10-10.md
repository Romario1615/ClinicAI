# Verificación del buscador de secciones — 2026-10-10

## 1. Implementación

Botón «Buscar sección» en el menú, con ventana flotante y resultados agrupados.
Busca por nombre y categoría sin depender de tildes, mayúsculas ni orden de
palabras. Exige todas las palabras; muestra cantidad, vacío y error de navegación.

## 2. Archivos

`frontend/src/app/app.component.{ts,html,scss,spec.ts}`, componente compartido
`buscador-secciones.component.{ts,html,scss,spec.ts}` y escenario Chromium 34.
README, arquitectura, límites, preparación, AGENTS y este informe. El buscador
utiliza la ventana existente; no modifica backend, permisos ni esquema.

## 3. Organización

Se mantienen Resumen, Atención clínica, Comunicación e IA, Finanzas y
Administración. Ayuda aparece también en la búsqueda. Los resultados proceden
de la misma lista autorizada del menú; no hay una segunda matriz de acceso.
Los nombres y destinos de las 23 secciones existentes se conservan.

## 4. Decisiones

Consulta local sobre metadatos de navegación, sin búsqueda remota ni datos de
pacientes. No se guarda la consulta en el navegador; cerrar o cambiar de
identidad la descarta. Los enlaces permiten copiar la dirección o abrir otra
pestaña. La elección normal usa el router y bloquea una segunda elección pendiente.

## 5. Permisos

Filtrar antes de buscar por permiso, rol y modo local. Clínicas permanece
exclusiva de plataforma y el simulador exige que la API confirme entorno local.
Un destino fuera de la lista autorizada no inicia navegación desde el selector.
La autorización y los ámbitos siguen siendo responsabilidad del backend.

## 6. Entorno

Windows, app 4200 y API sintética 8020. PostgreSQL real con base propia
`clinicai_qa_buscador_` más sufijo aleatorio validado, esquema hasta 038,
catálogos y semillas sintéticas; después se habilitó plataforma local.
Redis 13, LLM/embeddings mock y canales WhatsApp/Calendar sandbox.
Auxiliares e informes generados en `tmp/qa-20261010-buscador/`, ignorada por Git.

## 7. Pruebas de frontend

La selección final del armazón y buscador pasa **36/36** en dos suites.
El armazón incluye once pruebas nuevas: paridad de
enlaces autorizados, exclusión de rutas, normalización/categorías/vacío, foco,
cierre de capas, elección repetida de sección actual, errores, duplicados,
cambio de identidad, parámetros, gestos de otra pestaña y enlace móvil a la ruta actual.
El componente suma cuatro pruebas sobre grupos vacíos, actualización de entradas,
eventos originales, error dentro de la ventana y bloqueo de cierre durante navegación.

La corrida completa con cobertura pasa **921/921**, **111/111 suites**, 465,81 s,
antes del último ajuste de foco y la aplicación del estilo común al campo de
búsqueda. La regresión posterior **36/36** incluye esas dos correcciones y la
prueba nueva del enlace repetido. Son corridas distintas. El runner temporal
configura solo `maxWorkers: 2`, manteniendo los umbrales y aislamientos del proyecto.

```powershell
cd frontend
npx ng test --watch=false --no-coverage --include=src/app/app.component.spec.ts `
  --include=src/app/compartido/buscador-secciones.component.spec.ts
npx ng test --watch=false --coverage `
  --runner-config=../tmp/qa-20261010-buscador/vitest.config.mjs
npm run lint
npx tsc --noEmit -p tsconfig.spec.json
npm run build
```

## 8. Cobertura

Medición de la corrida completa anterior al último ajuste: **86,04 % sentencias,
73,51 % ramas, 82,31 % funciones y 88,52 % líneas**. Se conservan los mínimos
80/70/80/80; la regresión posterior no sustituye esa medición global.
No se mide ni atribuye cobertura backend a este cambio exclusivo del frontend.

## 9. Chromium

La primera corrida pasa **36/36**, 6,0 min, antes de separar el componente.
La selección posterior, con un caso adicional, obtiene **36 aprobadas y una
fallida**, 6,3 min: detectó el foco del enlace repetido. Después de corregirlo,
categorías y buscador pasan **18/18**, 2,0 min, sin reintentos. Incluyen los
nueve casos del buscador y paridad para los seis roles.

El cierre posterior al estilo común del campo pasa **9/9**, 1,4 min, sin reintentos.
La regresión incluye ingreso, autorización y distribución de todas las páginas.
Son **37 casos distintos entre corridas**, no una corrida única 37/37 ni la
batería completa de Chromium del proyecto. Una sola instancia y un worker.

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
npx playwright test escenarios/34-buscador-secciones.spec.ts `
  escenarios/33-menu-categorias.spec.ts escenarios/01-acceso.spec.ts `
  escenarios/02-autorizacion.spec.ts escenarios/15-pantallas-trabajo.spec.ts
npx playwright test escenarios/34-buscador-secciones.spec.ts `
  escenarios/33-menu-categorias.spec.ts
npx playwright test escenarios/34-buscador-secciones.spec.ts
```

## 10. Accesibilidad y diseño

Consulta etiquetada, resultados como enlaces nativos y grupos con encabezados.
Cantidad anunciada con `role="status"`; foco inicial en el campo. Escape cierra
solo la ventana y devuelve el foco al botón, manteniendo el cajón móvil.
Elegir una sección cierra las capas y enfoca el contenido tras renderizar.

Abrir el menú móvil lleva el foco al buscador; cerrar desde su fondo devuelve
el foco al botón del menú. Navegar desde un enlace del cajón lo lleva al contenido,
incluida navegación omitida a la misma dirección. Una cancelación no deja una
solicitud de foco pendiente para la navegación siguiente.

El escenario nuevo mide ventana y ausencia de desborde a 1366×768, 1024×768,
821×600, 390×844 y 320×568, y exige cero infracciones Axe WCAG 2A/AA, 2.1AA
y 2.2AA en el diálogo. La lista larga desplaza dentro de la ventana existente.

[Captura final revisada](imagenes/buscador-secciones-2026-10-10.png), tomada
con la API sintética: campo táctil de 44 px, categorías y lista dentro del diálogo.

## 11. Incidencias

La primera selección obtuvo 29/30: la prueba de foco tras navegación usaba un
fixture con render manual, que destruía la ventana después de medir el foco.
Se cambió esa prueba a render automático, como la aplicación, y se repitió la
selección completa **31/31** tras añadir el caso de gestos/destino no autorizado.
No se relajan expectativas, tiempos ni umbrales.

La compilación inicial avisó que el estilo del armazón excedía en 735 bytes
su presupuesto de 14 kB. Se extrajo la ventana a un componente propio con sus
estilos y pruebas, conservando el presupuesto. La primera corrida completa del
frontend se interrumpió para repetirla sobre esa separación definitiva;
no se declara aprobada esa ejecución parcial. La selección tras extraer pasa **35/35**.

El caso móvil nuevo detectó que `RouterLink` puede emitir `NavigationSkipped`
antes del manejador de la plantilla. La elección repetida ya compara el destino
con la ruta actual y solicita el foco tras cerrar; no depende de esperar otro
evento del router. Regresión de componentes **36/36** y navegador **18/18**.

La captura revisada mostró el campo con apariencia nativa; se aplicó el estilo
común `campo__control`, con tamaño táctil de 44 px. El primer cierre de dos casos
obtuvo uno aprobado y uno fallido al iniciar antes de estar lista la API
reiniciada: aún no aparecía el botón local de plataforma. Se comprobó salud 200
y seis accesos antes de repetir la suite del buscador. No se amplían timeouts.

Ayuda conserva el aviso NG0956 existente sobre seguimiento por identidad;
sus cinco pruebas pasan. Esa página no se modifica en este bloque.

## 12. Calidad

Lint y tipos de frontend/specs aprobados. Compilación de producción aprobada
sin avisos de presupuesto tras separar la ventana; `git diff --check` aprobado.
Paquete inicial definitivo: **485,71 kB**, transferencia estimada **132,65 kB**.
No se agregan librerías de búsqueda ni dependencias de ejecución.

## 13. Seguridad y dependencias

`npm audit --audit-level=high` en frontend y E2E: **cero vulnerabilidades**.
Gitleaks del índice sin hallazgos, con redacción; se verifica también el rango
de commits propio al cerrar el bloque.
La consulta no se persiste ni se envía al servidor. No amplía capacidades clínicas.

## 14. Credenciales y configuración

No necesita APIs ni credenciales nuevas. Los accesos por rol usados en QA son
sintéticos y exclusivos del entorno local. La autenticación de producción sigue
su configuración vigente. Abrir otra pestaña exige su propia sesión en memoria.

## 15. Staging y producción

Aceptar permisos reales, teclado, búsquedas sin resultado, menú móvil y elección
de módulo actual. Las pruebas de este bloque usan Chromium; quedan otros motores
y lectores de pantalla físicos para aceptación. No acredita los canales externos.

## 16. Despliegue y rollback

Desplegar el paquete frontend completo. Compatible con backend vigente, sin
migraciones ni cambios de configuración. Rollback: restaurar el paquete frontend
anterior; no revertir esquema ni datos.

## 17. Restauración y documentación

La base de desarrollo no se usa para formularios de QA. Se retiró exclusivamente
la API propia 8020, verificando su árbol y propietario del puerto. La comprobación
inmediata del primer cierre precedió a la terminación del proceso; se confirmó
su ausencia después. Se reinició para la última revisión visual y se retiró de
nuevo, esperando y verificando que el puerto quedara libre.

La base exclusiva se eliminó tras validar nombre, diferencia respecto a desarrollo
y cero conexiones; se confirmó su ausencia en PostgreSQL. **4200 y 8000 responden
200**, puerto 8020 libre y estado de base propia `eliminada: true`.
Se conservan los informes ignorados y archivos ajenos, incluida `.impeccable/`.
README, arquitectura, límites y preparación actualizados.
Los manuales específicos de Ayuda conservan sus contenidos por rol.

## 18. Evaluación

Implementación comprobada en `main`, commit **4e0ba71**, con documentación local.
Sin push ni despliegue. Las corridas identificadas verifican búsqueda, permisos
visibles, navegación, foco, adaptación y contraste del selector y categorías.
Se retiró el entorno temporal y se conserva la aplicación de desarrollo.
No se declara regresión completa del backend ni de todos los escenarios E2E.
