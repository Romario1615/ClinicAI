# Verificación del menú por categorías — 2026-10-10

## 1. Implementación

Cinco categorías desplegables: Resumen, Atención clínica, Comunicación e IA,
Finanzas y Administración. Solo una abierta a la vez; Ayuda permanece al pie.
Se conservan las 23 rutas existentes, condicionadas a permisos, rol y modo local.

## 2. Archivos

`frontend/src/app/app.component.{ts,html,scss,spec.ts}`, auxiliar E2E de sesión,
escenarios 01, 02, 10, 11, 14 y nuevo 33. README, arquitectura, limitaciones,
preparación, este informe y captura propia del menú. No se modifica el backend.

## 3. Organización

La [tabla del README](../README.md#secciones-agrupadas-por-categorías-2026-10-10)
identifica la categoría de cada módulo. Seguridad clínica pertenece a
Administración; Agente demo conserva su restricción al entorno local.
Los nombres y destinos de los módulos no cambian.

## 4. Decisiones

Filtrar antes de agrupar y omitir categorías vacías. La apertura vive en memoria;
no se guarda una preferencia entre usuarios. Al finalizar la navegación se abre
la categoría del destino, incluidas rutas anidadas y parámetros. Las listas
cerradas conservan únicamente enlaces autorizados en el DOM, con `hidden`.

## 5. Permisos

No se amplían permisos ni ámbitos. Las pruebas verifican ausencia de enlaces
sin permiso, Clínicas solo para superadministración y simulador solo local.
Recepción y asistencia conservan consulta clínica, sin conceder escritura.
El contador de categoría suma exclusivamente enlaces que la persona puede usar.

## 6. Entorno

Windows, frontend 4200, API de pruebas 8020 y PostgreSQL real con base exclusiva
`clinicai_qa_navegacion_` más sufijo aleatorio validado. Se aplicó el esquema hasta
038 y después catálogos, datos sintéticos y cuenta local de plataforma. Redis 13,
LLM/embeddings mock y WhatsApp/Calendar sandbox. No se envían mensajes externos ni
se usa la base de desarrollo para formularios E2E. Los auxiliares están ignorados
en `tmp/qa-20261010-navegacion/`; repetir exige preparar una base nueva.

## 7. Pruebas de frontend

Corrida definitiva: **907/907**, **110/110 suites**, 433,14 s. Incluye ocho
regresiones nuevas del armazón; su suite pasa 21/21. Para limitar la carga local,
el archivo temporal del runner contiene solo `test: { maxWorkers: 2 }`.
Conserva los umbrales del proyecto y no cambia aislamientos ni aserciones.

```powershell
cd frontend
npx ng test --watch=false --coverage `
  --runner-config=../tmp/qa-20261010-navegacion/vitest.config.mjs
npm run lint
npx tsc --noEmit -p tsconfig.spec.json
npm run build
```

## 8. Cobertura

85,99 % sentencias, 73,48 % ramas, 82,19 % funciones y 88,47 % líneas.
Se conservan los mínimos 80/70/80/80. El informe generado queda ignorado.
No se atribuye cobertura backend a un cambio exclusivo del frontend.

## 9. Chromium

La selección de navegación y regresión pasó **30/30**, 5,8 min, sin reintentos.
Acceso, autorización, altas de clínica/equipo/usuarios, edición de sede,
distribución de todas las secciones y nueve casos nuevos del menú por categorías.
Los seis roles conservan todas sus rutas sin duplicados ni categorías vacías.
Se comprobaron teclado, Atrás, destino de ingreso con parámetros y cajón móvil.

La auditoría posterior de todas las secciones para cada rol pasó **6/6**, 4,9 min,
sin reintentos. Su cierre exige cubrir exactamente las 23 rutas del menú, incluidas
las categorías inicialmente cerradas. Son **36 casos distintos aprobados en dos
corridas**, no una sola corrida 36/36 ni la batería Chromium completa del proyecto.

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
npx playwright test escenarios/33-menu-categorias.spec.ts `
  escenarios/01-acceso.spec.ts escenarios/02-autorizacion.spec.ts `
  escenarios/10-equipo.spec.ts escenarios/11-sedes.spec.ts `
  escenarios/15-pantallas-trabajo.spec.ts --project=chromium
npx playwright test escenarios/14-accesibilidad.spec.ts `
  --grep='todas las secciones' --project=chromium
```

## 10. Accesibilidad y diseño

Encabezados nativos con `aria-expanded`, `aria-controls` y listas identificadas;
los grupos cerrados salen del recorrido del teclado. Los enlaces activos usan
`aria-current`. Atrás lleva el foco al encabezado visible cuando cierra la lista
que lo conservaba. Escape devuelve el foco al botón del menú móvil.

El caso nuevo exige cero infracciones Axe WCAG 2A/AA, 2.1AA y 2.2AA en el menú
a 1366×768, 1024×768, 821×600, 390×844 y 320×568. Ninguna categoría produce
desborde horizontal; las listas extensas desplazan dentro del menú. Marca y Ayuda
quedan fuera de esa lista. La regresión 15 mide además todas las páginas de
administración y plataforma a 1366, 1024 y 390 px.

[Captura revisada del menú](imagenes/menu-categorias-2026-10-10.png), tomada
con la API sintética: muestra Resumen abierto, cuatro categorías cerradas y Ayuda.

## 11. Incidencias de la ejecución

- La selección inicial del armazón pasó 21/21, pero su cobertura parcial no
  alcanzó el umbral global; no se declara aprobada esa salida. La corrida
  completa posterior alcanza los umbrales sin modificarlos.
- Se interrumpió la primera corrida completa tras tiempos de espera de fixtures
  durante ejecución con muchos workers y otros procesos activos. La repetición
  con dos workers pasa completa, incluidos esos archivos, sin ampliar timeouts.
- La primera selección de navegador se interrumpió tras comprobar que faltaban
  las semillas de la base exclusiva. Se cargaron antes de repetir los 30 casos.
  Habilitar plataforma antes de crear la clínica sintética falla explícitamente;
  el orden definitivo es catálogos/datos y luego la cuenta de plataforma.
- Los auxiliares anteriores asumían enlaces siempre desplegados. Ahora abren
  su categoría y recorren también enlaces inicialmente cerrados. No se elimina
  ninguna sección de la matriz de accesibilidad.
- Lint detectó el sufijo de una clase de prueba; se corrigió y se repitió.
- La comprobación separada de tipos E2E requiere definiciones Node que esas
  dependencias no incluyen. No se instala ni se declara aprobada esa comprobación;
  Angular y sus specs sí pasan tipos. Playwright transpila y ejecuta los escenarios.
- La suite de Ayuda emite el aviso NG0956 existente sobre seguimiento de filas;
  sus cinco pruebas pasan y no se modifica esa página en este bloque.

## 12. Calidad

Lint aprobado, tipos de frontend/specs aprobados, build de producción aprobado
sin avisos de presupuesto y `git diff --check` aprobado. El paquete inicial
mide 476,26 kB, transferencia estimada 130,87 kB. No se instala una librería
de acordeones ni se añade una dependencia de ejecución.

## 13. Seguridad y dependencias

`npm audit --audit-level=high` en frontend y E2E: cero vulnerabilidades.
Gitleaks del índice con redacción: cero hallazgos. La apertura de categorías
no se persiste en almacenamiento del navegador.
La imagen documentada contiene solo el menú, sin ficha ni datos de paciente.

## 14. Credenciales y configuración

No requiere claves ni servicios externos adicionales. Las pruebas usan los
accesos de roles sintéticos del modo local. Producción conserva su autenticación
vigente; el simulador sigue condicionado a la confirmación del backend.

## 15. Staging y producción

Comprobar categorías por permisos reales, teclado, navegador Atrás, acceso
directo, contadores y cajón móvil. La prueba automática de este bloque usa
Chromium; otros navegadores siguen requiriendo aceptación en staging.
Las restricciones del producto y sus canales externos permanecen documentadas
en `known-limitations.md` y `production-readiness.md`.

## 16. Despliegue y rollback

Desplegar el paquete frontend completo de este bloque. Backend compatible,
sin cambios de rutas HTTP, migraciones ni configuración. Para revertir la
presentación, restaurar el paquete frontend anterior; no revertir la base.

## 17. Restauración y documentación

No se altera información clínica ni administrativa de desarrollo; no necesita
restauración de datos. Se conservan app 4200 y API 8000: ambas responden **200**
al cierre. La API temporal 8020 se detuvo comprobando su árbol de procesos propio;
la base exclusiva se eliminó tras verificar ausencia de conexiones y su nombre
validado, distinto de desarrollo. Se confirmó su ausencia en PostgreSQL.
README, arquitectura,
límites, preparación y AGENTS documentan la organización y los resultados.
Los manuales propios de Ayuda conservan sus rutas y acciones de cada rol.

## 18. Evaluación

La organización del menú está implementada y verificada en el alcance descrito.
Implementación guardada en `main`, commit `fbf77c4`, sin publicar los commits locales.
No se declara producción global ni una regresión completa del backend o de todos
los escenarios Chromium del proyecto. Los resultados corresponden a las corridas
identificadas, con sus incidencias y límites explícitos.
