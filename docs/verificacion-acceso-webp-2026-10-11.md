# Verificación del acceso y recursos WebP — 2026-10-11

## 1. Implementación

Inicio de sesión con fotografía, identidad ClinicAI destacada, celeste/turquesa,
tarjeta de vidrio claro y accesos por rol. La red y las partículas acompañan el
mensaje sobre coordinación de citas, mensajes y conocimiento aprobado.

## 2. Archivos

`paginas/acceso/acceso.component.{ts,html,scss,spec.ts}`, marca compartida y su
spec, 19 WebP públicos, `infra/scripts/exportar-acceso-webp.mjs`, escenario 35
y expectativa actualizada del fondo en el escenario 20. README, recursos visuales,
límites, preparación, AGENTS, este informe y dos capturas documentales.

## 3. Recursos e identidad

Ocho exportaciones de las cuatro fotos existentes, símbolo transparente de
192 × 192 px y diez pictogramas transparentes de 96 × 96 px. Total: **517.302
bytes**. Las fotos grandes pasan de **2.276.873 a 347.910 bytes**, **84,7 % menos**.
Los originales PNG/JPG y vectores se conservan. No se cambia la identidad del
logo ni se generan personas o información clínica adicionales.

## 4. Decisiones de diseño

Dos paneles en escritorio; marca encima del acceso hasta 820 px. Tarjetas con
icono sobre el texto en anchos intermedios y móvil, evitando partir el nombre
por falta de espacio. A 320 px usan una columna. En alturas reducidas se simplifica
el contenido informativo y desplaza únicamente el panel de acceso. Sus botones
siguen disponibles. Las dimensiones de `srcset` coinciden con los archivos.

## 5. Autenticación y permisos

El servidor continúa determinando si habilita los accesos temporales. Se conserva
la selección de especialidad del profesional, ingreso predeterminado, destino,
contraseña, segundo factor cuando se exige y mensajes normalizados. No se modifican
servicios de autenticación, guardias, permisos, ámbito ni edición clínica.

## 6. Entorno de verificación

Windows, aplicación 4200 y API QA 8020 con PostgreSQL real, base exclusiva
`clinicai_qa_acceso_` y sufijo aleatorio validado. Migraciones vigentes hasta 038;
catálogos, semillas sintéticas y habilitación local de plataforma. Redis 13,
LLM/embeddings mock y WhatsApp/Calendar sandbox. Archivos auxiliares e informes
en `tmp/qa-20261011-acceso/`, ignorada por Git.

## 7. Pruebas de componentes

Regresión final **15/15** en dos suites. Comprueba especialidad, rol predeterminado,
símbolo/fotos/iconos WebP, fallback del pictograma, preparación, formulario normal,
error de consulta, bloqueo de doble envío, recuperación de error y segundo factor.
La contraseña se limpia tras un rechazo. Corrida completa final **929/929**,
**111/111 suites**, **239,16 s**, después de corregir los dos fixtures nuevos.

```powershell
cd frontend
npx ng test --watch=false --no-coverage --include=src/app/paginas/acceso/acceso.component.spec.ts `
  --include=src/app/compartido/marca.component.spec.ts
npx ng test --watch=false --coverage --runner-config=../tmp/qa-20261011-acceso/vitest.config.mjs
```

## 8. Cobertura

Medición global final: **86,20 % sentencias, 73,79 % ramas, 82,55 % funciones
y 88,70 % líneas**. El runner temporal modifica solo `maxWorkers: 2` y mantiene
aislamiento y mínimos 80/70/80/80. No se atribuye cobertura backend a este bloque
exclusivo de presentación y recursos.

## 9. Chromium

Corrida final **29/29**, cinco suites, **3,4 min**, sin reintentos: acceso local,
autorización, formularios flotantes, identidad y portada WebP. Incluye los seis
roles, creación sintética de clínica/acceso, formularios de pacientes, gastos,
conocimiento, usuarios y periodontograma. Es una selección, no toda la batería.

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx playwright test escenarios/35-acceso-webp.spec.ts escenarios/01-acceso.spec.ts `
  escenarios/02-autorizacion.spec.ts escenarios/20-acceso-formularios.spec.ts `
  escenarios/27-identidad-clinicai.spec.ts
```

## 10. Accesibilidad y distribución

Se miden **1440×900, 1366×768, 1024×768, 821×600, 900×500, 844×390,
390×844 y 320×568**: portada de alto/ancho completos, sin desplazamiento
del documento ni desborde horizontal, tarjeta dentro de la ventana y roles
alcanzables con texto/icono separados. El teclado recorre los seis a 320 px.
Se mantienen foco visible, nombres accesibles y controles de al menos 44 px.

Axe no detecta infracciones WCAG 2A/AA, 2.1AA y 2.2AA en el acceso local,
escritorio y móvil, con contraste normal/aumentado y movimiento reducido.
El fondo inicial permanece estático cuando el usuario reduce movimiento.
La evaluación visual del formulario normal y MFA usa respuestas HTTP simuladas;
no certifica autenticación real por contraseña o un código válido de producción.

[Escritorio](imagenes/acceso-webp-escritorio-2026-10-11.png).
[Móvil](imagenes/acceso-webp-movil-2026-10-11.png).

## 11. Incidencias y correcciones

La primera prueba de tamaños midió `dvh` antes del fotograma posterior al cambio
de ventana. Ahora espera el alto esperado antes de medir, con el límite existente.
Una segunda corrida se interrumpió por recarga de desarrollo al editar la plantilla
durante Axe. La corrida final se ejecutó con la interfaz estable, **29/29**.

Dos pruebas nuevas suponían una sola consulta local. El servicio vigente consulta
el estado global y actualiza opciones al abrir acceso; los fixtures ahora exigen
y responden ambas. La selección original obtuvo 13 aprobadas/2 fallidas; después
del arreglo pasa **15/15**. La primera corrida completa obtuvo **927 aprobadas y
dos fallidas**, ambas de esos fixtures; la repetición completa tras corregirlos
obtiene **929/929**.
Se corrigió el recorte informativo en paisaje y el espacio
entre icono/nombre en tarjetas estrechas. No se relajan umbrales ni autorización.

La suite de Ayuda sigue emitiendo el aviso previo NG0956 al recrear una colección;
sus cinco pruebas pasan. Este bloque no modifica Ayuda ni atribuye ese aviso al acceso.

## 12. Calidad y compilación

Lint, tipos Angular/specs, sintaxis del exportador y build final aprobados:

```powershell
cd frontend
npm run lint
npx tsc --noEmit -p tsconfig.spec.json
npm run build
cd ..
node --check infra/scripts/exportar-acceso-webp.mjs
git diff --check
```

Build sin avisos, paquete inicial **485,81 kB**, transferencia estimada **132,66
kB**; las imágenes públicas se descargan aparte. No se incrementan presupuestos.

## 13. Vulnerabilidades y secretos

Auditorías npm de frontend y pruebas E2E: **cero vulnerabilidades**. Gitleaks
del índice de implementación aprobado con salida redactada; comprobación final
de documentación y del commit de implementación aprobadas, sin hallazgos y con
salida redactada. No cambian árboles de Python,
dependencias de ejecución ni secretos. Se conservan riesgos previos del producto.

## 14. Credenciales y configuración

No se necesitan APIs externas para estos recursos. El exportador usa Chromium
local ya instalado y deriva los archivos desde imágenes/trazados existentes.
La configuración de entorno, cuentas, roles y segundo factor permanece vigente.
No se desactiva la contraseña en producción por un cambio de presentación.

## 15. Staging y producción

Publicar el frontend completo junto con los 19 recursos. Aceptar ambos modos de
acceso en los navegadores objetivo, especialidades asignadas, MFA, teclado, zoom,
preferencias y dispositivos físicos. Este bloque tiene evidencia de Chromium;
Firefox/WebKit y autenticación de producción requieren su propia aceptación.

## 16. Despliegue, rollback y restauración

Implementación: `a008394`, local en `main`, sin push. No hay migraciones
nuevas ni cambios backend. Restaurar el paquete frontend anterior revierte la
presentación; los originales siguen disponibles. No requiere restaurar datos.
La base sintética se crea hasta head para verificar integración, no para cambiar
la BD de desarrollo; no se repite downgrade de migraciones ajenas a este bloque.

## 17. Limpieza y pendientes

API temporal 8020 detenida tras comprobar PID, descendientes y propietario del
puerto. Base exclusiva eliminada con prefijo validado, cero sesiones y comprobación
posterior de ausencia. La aplicación **4200** y API **8000** se conservan y responden
**200**; no se modifica ni elimina la base de desarrollo.
Permanecen documentación y evidencias sintéticas ignoradas
de QA; la carpeta `.impeccable/` ajena se conserva. Los pendientes de canales,
datos y producción anteriores mantienen sus requisitos. Los manuales propios
de cada rol siguen en Ayuda; el cambio no añade procedimientos clínicos nuevos.

## 18. Evaluación

Mejora visual implementada y recorridos de acceso comprobados con datos sintéticos.
La reducción medida es de bytes de fotografías, sin prometer tiempo de carga ni
precisión de IA. No se declara terminado el producto completo ni acreditada su
preparación global para producción.
