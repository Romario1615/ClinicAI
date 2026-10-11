# Verificación de espacios del frontend — 2026-10-11

## 1. Implementación

El propietario precisó que el solapamiento se veía en la pantalla de inicio.
Se separan los bloques del titular de acceso, se aumenta su interlínea y se
asigna al gráfico el alto disponible de su fila. La revisión general detectó
también el título de Conocimiento debajo de las acciones a 821×600: se agrupan
los botones y se permite su salto de fila. Fotografías WebP, logo y colores
turquesa continúan integrados en la portada.

## 2. Archivos

Ocho archivos frontend: plantilla, estilo y spec de acceso; plantilla, estilo
y spec de Conocimiento; componente y spec de `GraficoRedComponent`.
Tres archivos E2E: `apoyo/espacio.ts`, escenarios 37 y 38.
README, arquitectura, límites, preparación, AGENTS, este informe y seis capturas
documentan el bloque. No se añade dependencia de ejecución.

## 3. Titular y marca

El mensaje principal y «IA para coordinar» tienen elementos propios y separación
de `0.25em`. La interlínea pasa de 1,12 a 1,3; el espaciado de letras se suaviza.
En móvil se conserva el mensaje principal seguido del bloque de IA. Logo, nombre
grande, imagen original del equipo y fotos alternativas se siguen sirviendo.

[Antes en tableta](imagenes/portada-espacio-tableta-antes-2026-10-11.png).
[Después en tableta](imagenes/portada-espacio-tableta-2026-10-11.png).
[Escritorio](imagenes/portada-espacio-escritorio-2026-10-11.png).
[Móvil](imagenes/portada-espacio-movil-2026-10-11.png).

## 4. Ilustración y cabecera de Conocimiento

`GraficoRedComponent.ajustada` es opcional. En portada, el SVG ocupa el alto que
le asigna su fila y el `viewBox` conserva la proporción del dibujo. Los demás
usos mantienen su comportamiento natural. Es una medida de contención de la
ilustración; la medición inicial de catorce tamaños no encontró un cruce de
su rectángulo con las tarjetas.

Conocimiento reserva una base de 18rem al texto; la agrupación de acciones tiene
ancho máximo y sus etiquetas pueden partirse. La cabecera permite otra fila
en escritorio. Los botones tienen un alto mínimo de 44px.

[Conocimiento antes](imagenes/conocimiento-espacio-antes-2026-10-11.png).
[Conocimiento después](imagenes/conocimiento-espacio-2026-10-11.png).

## 5. Roles y datos

Se usan los roles de administración y plataforma para recorrer sus secciones,
y la auditoría de accesibilidad por los seis roles base. Los contratos de
autenticación, permisos, especialidades y consulta/escritura clínica siguen
controlados por la política existente. La maquetación no concede acceso a datos.
Todas las capturas y recorridos del bloque usan pacientes, personal y documentos
sintéticos de una base QA exclusiva.

## 6. Entorno de integración

Windows, frontend `http://localhost:4200`, API QA 8020, PostgreSQL y Redis reales.
Base de prefijo validado `clinicai_qa_solapes_`, migrada a head 038; catálogos,
semilla sintética y plataforma local. LLM/embeddings mock y canales sandbox.
La preparación y los informes están en `tmp/qa-20261011-solapes/`, ignorada por
Git. La API y base de desarrollo se conservan.

## 7. Pruebas de componentes

Frontend completo **949/949**, **112/112 suites**, **164,95 s**. Añade cinco
pruebas: agrupación y permisos de acciones de Conocimiento; bloques del titular,
ilustración ajustada en acceso y ajuste opcional del gráfico conservando `viewBox`.
Regresión dirigida final **31/31**, tres suites, **4,20 s**.

```powershell
cd frontend
npx ng test --watch=false --coverage --runner-config=../tmp/qa-20261011-solapes/vitest.config.mjs
npx ng test --watch=false --no-coverage `
  --include=src/app/paginas/conocimiento/conocimiento.component.spec.ts `
  --include=src/app/paginas/acceso/acceso.component.spec.ts `
  --include=src/app/compartido/grafico-red.component.spec.ts
```

## 8. Cobertura

**86,24 % sentencias, 73,82 % ramas, 82,63 % funciones, 88,74 % líneas**.
Runner temporal con dos workers; mantiene aislamiento y umbrales 80/70/80/80.
La cobertura corresponde al frontend. El bloque no añade código backend ni
atribuye nueva cobertura de API a una corrección visual.

## 9. Chromium: revisión y regresión

Selección final **28/28**, seis suites, **5,3 min**, sin reintentos. Incluye
pantallas de trabajo, formularios flotantes, ficha/agente/periodontograma,
Analítica IA, WebP/acceso y los escenarios nuevos de geometría.
Se revisan las rutas disponibles de administración/plataforma a **1366×768,
1024×768, 821×600, 390×844 y 320×568**, con sus consultas cargadas.
La repetición final mide 22 rutas de administración y 23 de plataforma:
**225 mediciones** sin cruces visibles.

Siete módulos recorren todas sus pestañas en cuatro tamaños: Panel, Configuración,
Catálogo, Usuarios y roles, Gastos y caja, Atención de mensajes y Medicamentos.
La repetición registra **56 mediciones** de sus pestañas.
Once formularios se miden a 1024×768, 821×600, 390×844 y 320×568, al inicio,
mitad y final de su cuerpo desplazable: **132 mediciones**. Sus ventanas se
abren mediante el botón real y se cierran con Escape.

La portada usa **14 tamaños**, de 320×568 a 1920×1080, con movimiento normal
y reducido: **28 combinaciones**. Además se repiten los ocho tamaños del acceso,
sus seis roles alcanzables, teclado, errores de presentación y contraste.

Corrida adicional final **11/11**, dos suites, **6,7 min**, sin omisiones ni
reintentos. Incluye seis auditorías Axe por rol cuya unión coincide con las
**23 rutas** del menú y repite los cinco casos de geometría después de su
revisión de formato. Sus metadatos registran **413 mediciones** de rutas,
pestañas y formularios, todas sin cruces visibles. Se registra como corrida
separada de la 28/28; ambas comparten cinco casos.

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx playwright test escenarios/15-pantallas-trabajo.spec.ts `
  escenarios/20-acceso-formularios.spec.ts escenarios/21-analitica-diseno.spec.ts `
  escenarios/35-acceso-webp.spec.ts escenarios/37-espacio-interfaz.spec.ts `
  escenarios/38-portada-espacio.spec.ts
npx playwright test escenarios/14-accesibilidad.spec.ts escenarios/37-espacio-interfaz.spec.ts `
  --grep 'todas las secciones visibles|medición|textos y controles|pestañas del panel|once formularios' `
  --reporter=list,json
```

## 10. Medición y accesibilidad

El detector compara rectángulos de textos y controles visibles y respeta el
diálogo activo. Espera las consultas, fuentes y animaciones finitas de la ruta.
Una prueba de contrato coloca un botón encima de un título: debe detectar el
cruce. Al quitarlo y mantener un texto con elipsis, exige ausencia de incidencias.
La portada añade comparación específica del SVG con mensaje, agente y tarjetas.

La regresión del acceso usa Axe WCAG 2A/AA, 2.1AA y 2.2AA, contraste normal y
mayor, además de teclado en móvil. Analítica comprueba también sus tres vistas,
series vacías, cifras extensas y ventanas. No se aumenta el umbral ni se elimina
una comprobación para conseguir que pasen las pruebas.

## 11. Diagnóstico y correcciones de pruebas

La primera medición general identificó el título de Conocimiento bajo las acciones.
El titular de acceso cruzaba rectángulos de texto entre líneas consecutivas con
interlínea 1,12. Se corrigen la distribución y el espaciado en el producto.

El detector inicial también incluyó texto oculto por su propia elipsis en Pacientes
y contenido móvil que pasaba bajo la cabecera fija. Se aplican esos recortes a
la medición del área visible. Son correcciones del auxiliar, no cambios en la
política de datos ni pruebas de todos los glifos de una tipografía.

`networkidle` podía corresponder a la ruta anterior y medir «Cargando». Ahora se
esperan las peticiones actuales. Una primera corrida ampliada obtuvo 2 aprobadas
y 2 fallidas: la cabecera móvil generaba el falso positivo descrito y el test de
consultorios buscaba «Sedes» exacto. Se usa «Sedes y consultorios» con su contador
y se selecciona sede antes de abrir el formulario. La repetición obtiene 4/4;
la selección final incorpora además el contrato del detector.

## 12. Calidad y compilación

Lint, tipos Angular/specs, revisión de formato y `git diff --check` aprobados.
Build aprobado sin avisos: inicial **485,81 kB**, transferencia estimada
**132,72 kB**. No se modifica el presupuesto de compilación ni se incorpora
un formateador al proyecto.

```powershell
cd frontend
npm run lint
npx tsc --noEmit -p tsconfig.spec.json
npm run build
cd ..
git diff --check
```

## 13. Vulnerabilidades y secretos

`npm audit --json` en frontend y E2E: **cero vulnerabilidades**, incluidos niveles
alto y crítico. Gitleaks de los índices de implementación/documentación y del
commit `5b701a8` aprobado con salida redactada; rango final comprobado al cerrar.
No se modifican dependencias Python ni manejo de credenciales.

```powershell
git diff --cached | gitleaks stdin --redact --no-banner
gitleaks git --redact --no-banner --log-opts='2a8047b..HEAD'
```

## 14. Credenciales y configuración

El bloque usa fuentes, WebP, SVG y paquetes existentes. No requiere claves nuevas.
La respuesta del servidor sigue determinando el acceso local o por credenciales.
El formulario normal y segundo factor se prueban con respuestas sintéticas de
presentación; no constituyen aceptación real de proveedores o identidades.

## 15. Staging y producción

Publicar el paquete frontend completo y sus recursos existentes. Validar los
tamaños, zoom, rol, especialidad, nombres y contenido reales autorizados de la
clínica. Revisar teclado, lectura, movimiento, errores y desplazamiento interno.
Esta evidencia usa Chromium; otros motores y dispositivos físicos requieren
aceptación específica. Los bloqueos generales de producción siguen documentados
en `production-readiness.md`.

## 16. Despliegue, rollback y restauración

Implementación `5b701a8`, local en `main`, sin push.

Restaurar el paquete frontend anterior revierte los ajustes de presentación.
No requiere restauración de datos ni migración nueva. Las migraciones existentes
se aplicaron en la base QA exclusiva para integración, sin revertir el esquema
de desarrollo ajeno a este bloque.

## 17. Limpieza y pendientes

API **8020** detenida tras validar PID, descendientes y propietario del puerto.
Base sintética propia retirada con prefijo validado, cero sesiones y ausencia
posterior comprobada; el estado queda marcado como eliminado. Frontend
**4200/acceso** y API **8000/salud/listo** responden **200**. Base de desarrollo
y carpeta `.impeccable/` ajena conservadas.

Los informes, trazas y archivos sintéticos propios permanecen en la carpeta
ignorada de QA. La revisión geométrica no cubre cada combinación de filtros,
documentos, idiomas, zoom ni acciones clínicas. Mantener aceptación visual
periódica con los dispositivos y contenido autorizados de la clínica.

## 18. Evaluación

Corregidos el espaciado del inicio y el cruce de título/acciones de Conocimiento.
La batería completa de componentes y la selección de regresión de navegador
están aprobadas. Este bloque mejora la presentación y su comprobación repetible;
no declara terminado el producto ni preparación global para producción.
