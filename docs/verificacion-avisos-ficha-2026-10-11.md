# Avisos, estados del acceso y ficha — 2026-10-11

## 1. Implementación

La continuación de la revisión visual detectó el panel de notificaciones fuera
del viewport móvil y por debajo del límite inferior en horizontal. Se corrige
su contención y se revisan estados del inicio, ficha, agente y herramientas.

## 2. Archivos

Plantilla, estilo, componente y spec de `AppComponent`; auxiliar E2E
`apoyo/espacio.ts`; contrato visual del escenario 22; nuevos escenarios 39–41.
README, arquitectura, límites, preparación, AGENTS y este informe documentan
el bloque. El código clínico y los contratos de API no se modifican.

## 3. Decisiones de diseño

Cabecera, lista y enlace final ocupan tres filas. La lista admite desplazamiento
y su fila usa `minmax(0, 1fr)`. El alto máximo sigue el viewport dinámico. En móvil
el panel se fija al borde derecho de la pantalla con áreas seguras; en escritorio
se mantiene junto a la campana. El estilo de vidrio y la imagen WebP del vacío
continúan integrados.

[Móvil antes](imagenes/avisos-movil-antes-2026-10-11.png).
[Móvil después](imagenes/avisos-movil-2026-10-11.png).
[Lista desplazable en horizontal](imagenes/avisos-horizontal-2026-10-11.png).

## 4. Cierre, foco y totales

Se añade **Cerrar notificaciones**, con área táctil de 44 px. Este cierre y
Escape devuelven el foco a la campana. Pulsar fuera o elegir un destino conservan
su comportamiento habitual. La insignia visible abrevia totales superiores a
99; la descripción accesible y la cabecera mantienen el total completo.

## 5. Acceso y ficha

La portada se mide durante carga de accesos, envío local pendiente y error
503 con mensaje/referencia largos. Los dobles HTTP no aceptan credenciales.
La ficha se revisa con el agente y el selector de herramientas abiertos para
profesional y recepción, usando historias sintéticas de la API QA real.
Las comprobaciones de consulta/escritura por rol continúan en los escenarios
clínicos existentes; recepción no obtiene acciones de registro clínico.

[Contacto de la ficha móvil con agente abierto](imagenes/ficha-agente-movil-2026-10-11.png).

## 6. Datos y entorno

Windows, frontend `http://localhost:4200`, API exclusiva 8020, PostgreSQL y
Redis reales. Base con prefijo validado `clinicai_qa_estados_`, migrada a head
038 y cargada con catálogos, semilla sintética y plataforma local. Canales
sandbox, LLM/embeddings mock. Evidencia temporal en `tmp/qa-20261011-estados/`.
La aplicación/API de desarrollo 4200/8000 se conservan.

## 7. Pruebas de componentes

Frontend completo **953/953**, **112 suites**, **156,89 s**. Regresión dirigida
del armazón **36/36**. Cuatro pruebas nuevas cubren cierre/foco, separación de
cabecera/lista/pie, carga/vacío y total accesible de la insignia compacta.

```powershell
cd frontend
npx ng test --watch=false --coverage --runner-config=../tmp/qa-20261011-estados/vitest.config.mjs
npx ng test --no-watch --no-coverage --include=src/app/app.component.spec.ts `
  --runner-config=../tmp/qa-20261011-estados/vitest.config.mjs
```

## 8. Cobertura

**86,25 % sentencias, 73,86 % ramas, 82,63 % funciones, 88,76 % líneas**.
Runner temporal de dos workers, con aislamiento y umbrales existentes. Es
cobertura frontend; no se atribuyen resultados nuevos del backend a este bloque.

## 9. Chromium y regresión

La selección principal final obtiene **42/42**, doce suites, **12,0 min**,
sin omisiones ni reintentos. Incluye auditoría por seis roles de las 23 rutas,
ficha desde Agenda, herramientas, odontograma, consultas sin edición, WebP,
portada y geometría general. El informe con adjuntos se conserva en
`tmp/qa-20261011-estados/informe-42/` antes de la corrida adicional.

La revisión adicional obtiene **32/32**, cinco suites, **4,3 min**, sin
omisiones ni reintentos: distribución de secciones, formularios de pie fijo,
categorías, buscador por seis roles y avisos con movimiento normal/reducido.
Las tres pruebas originales de avisos se repiten; no se presentan ambas
corridas como una ejecución única de 74 casos distintos.

Para repetir la selección principal con el escenario 39 actual, se excluye
su variante normal, añadida después de arrancar esa corrida. La segunda
selección comprueba las cuatro pruebas del escenario 39.

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx playwright test escenarios/14-accesibilidad.spec.ts `
  escenarios/19-ficha-agente-diseno.spec.ts escenarios/22-ficha-compartida-marca.spec.ts `
  escenarios/24-menu-herramientas.spec.ts escenarios/25-ficha-desde-agenda.spec.ts `
  escenarios/26-ficha-odontograma.spec.ts escenarios/35-acceso-webp.spec.ts `
  escenarios/37-espacio-interfaz.spec.ts escenarios/38-portada-espacio.spec.ts `
  escenarios/39-notificaciones-espacio.spec.ts escenarios/40-acceso-estados.spec.ts `
  escenarios/41-ficha-espacio.spec.ts --project=chromium --grep-invert='con movimiento normal'
npx playwright test escenarios/15-pantallas-trabajo.spec.ts escenarios/20-acceso-formularios.spec.ts `
  escenarios/33-menu-categorias.spec.ts escenarios/34-buscador-secciones.spec.ts `
  escenarios/39-notificaciones-espacio.spec.ts --project=chromium
```

## 10. Geometría y accesibilidad

Avisos: ocho tamaños entre 1440×900 y 320×568, incluido 844×390. Se exige panel
dentro de la pantalla, enlaces alcanzables, lista desplazable en horizontal,
cabecera/pie estables y Axe WCAG AA sobre el panel abierto. El total extremo
49380 procede de cuatro respuestas agregadas sintéticas, sin cambiar entidades.

Portada: tres estados, ocho tamaños y tres posiciones de desplazamiento,
**72 mediciones**. Ficha: dos roles, tres estados, siete tamaños y tres
posiciones, **126 mediciones**. El detector compara texto/controles visibles
y ahora admite una raíz ARIA explícita e incluye los enlaces con destino.
La revisión general del escenario 37 repite su contrato de sensibilidad.

Sus adjuntos registran **110 mediciones/22 rutas** de administración y
**115/23 rutas** de plataforma, **56 mediciones** de pestañas y **132** de once
formularios: **413** en total, con cero incidencias. Los adjuntos de ficha
registran **63 mediciones por rol**, con cero incidencias. La portada y avisos
también obtienen cero incidencias dentro de los tamaños y estados medidos.

## 11. Diagnóstico y correcciones de pruebas

La medición inicial del panel encontró bordes izquierdos de **−114,20 px**
a 390×844 y **−79,03 px** a 320×568. A 844×390 su borde inferior quedaba
a **500,95 px** desde arriba, superando el viewport por **110,95 px**. Son fallos
de distribución corregidos en el producto.

El escenario 22 aún esperaba el PNG como fondo CSS y seis tarjetas visibles
simultáneamente. Se actualiza al contrato WebP existente: foto original visible
y seis roles alcanzables por desplazamiento, con texto/icono contenidos y
área táctil mínima, manteniendo marca, color, contraste y permisos.

La primera prueba de carga apuntó a `/citas/` en vez de `/agenda/citas` y no
retenía su consulta. Ahora exige capturar la petición real antes de medir el
estado pendiente y devuelve el esquema `elementos` de la API. El nuevo recorrido
de ficha usó inicialmente «Datos y contacto»; se corrige a «Contacto y
consentimientos», sin renombrar el producto ni relajar la geometría.

## 12. Calidad y compilación

Lint, tipos Angular y specs, revisión de formato y `git diff --check` aprobados.
Build aprobado sin avisos: **487,26 kB** iniciales y **132,86 kB** de transferencia
estimada; se conservan los presupuestos y dependencias existentes.

```powershell
cd frontend
npm run lint
npx tsc --noEmit -p tsconfig.app.json
npx tsc --noEmit -p tsconfig.spec.json
npm run build
cd ..
git diff --check
```

## 13. Vulnerabilidades y secretos

`npm audit --audit-level=low` en frontend y E2E: **cero vulnerabilidades**.
Gitleaks del índice de implementación y del rango `b7d005f..9da9a8c` aprobado,
con salida redactada. Se comprueba también el índice de documentación al
confirmar el cierre.
No cambia el manejo de secretos ni se introducen dependencias Python.

```powershell
git diff --cached | gitleaks stdin --redact --no-banner
gitleaks git --redact --no-banner --log-opts='b7d005f..HEAD'
```

## 14. Credenciales y configuración

No requiere credenciales adicionales. El servidor mantiene el control del
modo local y de las opciones de acceso. Los avisos usan sus consultas y filtros
de ámbito existentes. Las integraciones externas conservan su preparación
y aceptación pendientes documentadas en los límites del producto.

## 15. Staging y producción

Comprobar avisos con el volumen real autorizado, cierre/foco, navegación,
teclado, zoom, horizontal y áreas seguras de teléfonos. Revisar portada durante
carga/error y ficha/agente/herramientas con los roles y especialidades efectivos.
Chromium y respuestas sintéticas de presentación no acreditan otros motores,
teléfonos físicos, autenticación real de proveedores ni cálculos de alertas.

## 16. Despliegue, rollback y restauración

Desplegar el paquete frontend completo. No hay migración ni cambio de contratos
de API. Restaurar el paquete frontend anterior revierte esta presentación;
no requiere restaurar datos. Revertir el commit específico conserva las otras
fases de desarrollo; no reiniciar el historial compartido.

## 17. Limpieza y pendientes

API propia 8020 detenida tras comprobar PID, comando y propietario del puerto;
base QA `85a562d6` retirada tras comprobar prefijo, diferencia frente a desarrollo
y ausencia de conexiones. Puerto 8020 libre y estado QA `eliminada=true`.
`/acceso` en 4200 y `/salud/listo` en 8000 responden **200**. Capturas, informes
y logs sintéticos del bloque se conservan en la carpeta temporal ignorada.
No hay archivos de almacenamiento generados por estos recorridos.

Implementación `9da9a8c`; trabajo en `main` local, sin push.
`.impeccable/` ajena se conserva.
Quedan aceptación de otros motores/dispositivos y los pendientes de canales
externos descritos en `known-limitations.md` y `production-readiness.md`.

## 18. Evaluación

Bloque visual implementado y comprobado con **953 pruebas frontend**, regresión
dirigida **36/36**, Chromium **42/42** y **32/32**, controles de calidad y limpieza
del entorno exclusivo. La evidencia es una revisión visual y funcional acotada,
sin declarar terminado todo el producto ni certificar cada combinación de
contenido y permisos.
