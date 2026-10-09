# Verificación del logo de ClinicAI — 2026-10-09

## 1. Pedido

Crear una marca propia visible y entregable para ClinicAI, con celeste y
turquesa, conservando el fondo original del inicio de sesión.

## 2. Implementación

C abierta, cruz de cuidado y tres nodos conectados. `app-marca` comparte la
identidad en acceso, menú y cabecera; los presupuestos que ya cargan el símbolo
reciben el nuevo vector. Se renuevan favicon, Apple Touch y manifiesto.

## 3. Archivos

- `frontend/public/images/clinicai-simbolo.svg` y tres logos completos SVG.
- Tres PNG transparentes, iconos 192/512, recortable 512 y Apple Touch 180.
- `frontend/public/favicon.ico`, `manifest.webmanifest`, `src/index.html`.
- `frontend/src/app/compartido/marca.component.ts` y su spec.
- `infra/scripts/generar-logos.py`, `exportar-logos.mjs`.
- `pruebas-e2e/escenarios/27-identidad-clinicai.spec.ts`.
- Lámina, README, recursos visuales, arquitectura, límites y preparación.

## 4. Decisiones visuales

Vector nativo para mantener nitidez y peso ligero. Letras de Plus Jakarta Sans
750 convertidas en trazos para los logos exportables. Variantes para fondo claro,
oscuro y una tinta; no se añaden fuentes remotas ni una dependencia de aplicación.

## 5. Integración

Los consumidores existentes conservan `/images/clinicai-simbolo.svg`. La portada
usa el modo destacado, el menú el normal y la cabecera el compacto. El descriptor
identifica «Gestión clínica con IA». No se altera `acceso-equipo.png`.

## 6. Accesibilidad y espacio

La marca tiene un nombre accesible único; su imagen interna es decorativa y
el texto duplicado queda oculto al lector. Dimensiones intrínsecas reservan el
espacio. El primer recorrido encontró solapamiento de la marca con notificaciones
a 320 px: el host ya no se comprime y el símbolo/hueco se ajustan hasta 360 px.
La regresión posterior confirma límites completos y separación de controles.

## 7. Exportaciones

SVG completos de 359 × 128 unidades; PNG correspondientes de **1436 × 512**
con alfa real. Iconos generales con transparencia; máscara y Apple Touch con
fondo opaco. ICO con PNG de **16/32/48/64** px. Lámina de 1280 × 800.

## 8. Regeneración

```powershell
uv run --no-project --with fonttools==4.61.0 --with brotli==1.2.0 --with defusedxml==0.7.1 python infra/scripts/generar-logos.py
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
node infra/scripts/exportar-logos.mjs
```

Ambos ejecutados. La fuente procede del paquete local ya existente, licencia
SIL OFL 1.1; los resultados no necesitan fuentes instaladas para abrirse.

## 9. Pruebas de frontend

Desde `frontend`:

```powershell
npx.cmd ng test --no-watch --coverage --runner-config=../tmp/qa-20261009-ficha-agenda/vitest.config.mjs
npx.cmd ng test --no-watch --no-coverage --include='**/marca.component.spec.ts' --include='**/acceso.component.spec.ts' --include='**/app.component.spec.ts' --runner-config=../tmp/qa-20261009-ficha-agenda/vitest.config.mjs
```

La configuración temporal limita Vitest a dos workers. Suite completa:
**840/840**, 108 archivos, 208,89 s. Regresión final tras el ajuste compacto:
**21/21**, tres archivos, 10,41 s. El nuevo spec aporta cuatro pruebas de
identidad accesible, descriptor y modos destacados/compactos.

## 10. Cobertura

Sentencias **85,70 %**, ramas **73,13 %**, funciones **81,63 %** y líneas
**88,10 %**, calculadas por la batería completa. La regresión final se ejecutó
sin cobertura para conservar ese informe completo.

## 11. Navegador

Desde `pruebas-e2e`, con el navegador local configurado:

```powershell
npx.cmd playwright test escenarios/27-identidad-clinicai.spec.ts escenarios/22-ficha-compartida-marca.spec.ts -g 'ClinicAI|identidad|marca se ve|logo destacado' --project=chromium
```

Resultado final: **4/4**, sin reintentos, 11,7 s. El primero había obtenido
3/4 antes de corregir el solapamiento. Se comprueban:

- Portada a 1440×900, 1280×600, 1024×768, 768×1024, 390×844 y 320×568:
  nombre grande, símbolo cargado, fondo conservado y seis roles dentro del alto.
- Marca de la aplicación a 1440×900, 1024×768, 900×768, 821×768,
  768×1024, 390×844 y 320×568: límites, espacio y descriptor según ubicación.
- Cuatro SVG servidos sin fuentes externas ni elementos ejecutables;
  siete PNG con dimensiones y alfa esperados; cuatro entradas ICO.
- Manifiesto y referencias HTML coherentes. Axe WCAG 2 A/AA, 2.1 AA y
  2.2 AA del acceso: cero infracciones en el escenario existente.

Solo lecturas de recursos y acceso local de recepción con datos sintéticos;
no se crean ni modifican pacientes, citas o registros clínicos.

## 12. Lint, tipos y compilación

`npm.cmd run lint` y `npm.cmd run build` aprobados; Angular comprueba tipos
y plantillas al compilar. Paquete inicial **469,22 kB**, sin avisos de presupuesto.
`node --check infra/scripts/exportar-logos.mjs`, Ruff y formato del generador
Python aprobados.

## 13. Seguridad y dependencias

`npm.cmd audit --json`: **cero vulnerabilidades**, incluidas dependencias de
desarrollo. El primer análisis del generador señaló lectura XML con ElementTree;
se sustituyó por `defusedxml` con rechazo explícito de DTD/entidades. Bandit
final del generador: cero hallazgos. No se incorporan paquetes a la aplicación.
Gitleaks del índice antes del commit: **cero secretos detectados**.

## 14. Configuración y credenciales

No necesita claves, APIs ni datos clínicos. Los generadores usan el símbolo,
fuente y Chromium locales; sus dependencias Python están fijadas y aisladas.
Backend, autorizaciones y agente permanecen en su configuración existente.

## 15. Staging y producción

Los recursos se copian desde `frontend/public` durante el build. El manifiesto
declara tamaños y finalidad, pero no se comprobó una instalación en dispositivo
real ni se realizó un despliegue. El service worker usa su inventario existente
para actualizar recursos; un navegador puede necesitar recargar su caché de favicon.

## 16. Despliegue y rollback

Entregar el build del frontend con sus recursos públicos. Revertir el commit
del bloque y reconstruir recupera la identidad anterior. No hay migraciones ni
datos que transformar; restauración de BD no aplica a este cambio visual.

## 17. Documentación y pendientes

README incluye la lámina y los entregables. Recursos visuales documenta paleta,
variantes y regeneración. Límites y preparación declaran el alcance de Chromium;
pendientes: instalación física iOS/Android e impresión profesional, si se requieren.

## 18. Evaluación

Logo creado, colocado y exportado con comprobación de marca, acceso, armazón
y recursos. Este cierre corresponde a identidad visual; no constituye una
nueva aceptación clínica ni modifica el estado de integraciones externas.
