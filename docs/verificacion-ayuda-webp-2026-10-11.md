# Verificación de Ayuda e imágenes interiores — 2026-10-11

## 1. Implementación

Ayuda incorpora Expandir/Contraer todas, Limpiar búsqueda con retorno de foco,
contador de resultados e icono del rol. Buscar abre las tareas coincidentes.
Quince ilustraciones públicas se convierten a WebP y se integran en las pantallas
interiores y estados vacíos. Se mantiene un manual independiente por rol.

## 2. Archivos

`paginas/ayuda/ayuda.component.{ts,spec.ts}`, helper/spec `nucleo/utilidades/icono-rol`,
uso compartido del helper en acceso, quince archivos públicos WebP y
`infra/scripts/exportar-interfaz-webp.mjs`. Dieciséis plantillas/estilos cambian
la referencia del recurso. Nuevo escenario 36; README, arquitectura, recursos,
límites, preparación, AGENTS, este informe y capturas documentales.

## 3. Recursos visuales

Originales: **8.531.109 bytes**. Derivados: **499.754 bytes**, **94,1 % menos**.
Se limita el ancho a 320/480/640/1200/1400 px según su uso y se codifica a calidad
0,88; no se amplía la fuente. La proporción y la transparencia se conservan.
Se verifica MIME, RIFF/WEBP, decodificación y disponibilidad de los originales.
La medida compara bytes, sin prometer reducción del tiempo de carga.

## 4. Decisiones de interfaz

Se conserva el patrón pantalla de trabajo: cabecera fija y columnas desplazables
en escritorio. Controles de al menos 44 px, flecha de apertura, encabezado
diferenciado y ajuste de textos/insignias largos. En móvil se permite desplazamiento
vertical, sin desborde horizontal. El filtro local busca palabras en título,
propósito, pasos y límites, normalizadas sin tildes ni mayúsculas.

## 5. Roles y autorización

La API sigue determinando los manuales y tareas permitidos. No se mezclan roles,
se añaden procedimientos clínicos ni se cambia escritura de historias. El helper
solo elige un recurso público de una lista cerrada. `administrador_clinica` usa
el pictograma de administración; códigos personalizados usan el de seguridad.
Cambiar de manual descarta filtro/aperturas y abre su primera tarea.

## 6. Entorno

Windows, frontend 4200 y API QA 8020 sobre PostgreSQL real con base exclusiva
`clinicai_qa_interfaz_` más sufijo aleatorio validado, migrada hasta head 038.
Catálogos y datos sintéticos, plataforma local habilitada, Redis 13,
LLM/embeddings mock y canales sandbox. Auxiliares e informes en
`tmp/qa-20261011-interfaz/`, ignorada por Git. Sin escritura en la BD de desarrollo.

## 7. Pruebas de componentes

Corrida completa **944/944**, **112/112 suites**, **268,13 s**. Añade seis pruebas
de Ayuda y nueve del helper respecto al bloque anterior. Se comprueban controles
masivos, apertura individual, búsqueda/limpieza/foco, cambios de manual y eventos
obsoletos. Las pruebas anteriores de acceso continúan dentro de la batería.
Regresión dirigida final **30/30**, tres suites, **7,33 s**: Ayuda, helper y acceso.

```powershell
cd frontend
npx ng test --watch=false --coverage --runner-config=../tmp/qa-20261011-interfaz/vitest.config.mjs
npx ng test --watch=false --no-coverage --include=src/app/paginas/ayuda/ayuda.component.spec.ts `
  --include=src/app/nucleo/utilidades/icono-rol.spec.ts `
  --include=src/app/paginas/acceso/acceso.component.spec.ts
```

## 8. Cobertura

**86,23 % sentencias, 73,82 % ramas, 82,63 % funciones y 88,74 % líneas**.
Runner temporal con `maxWorkers: 2`, manteniendo aislamiento y umbrales
80/70/80/80. No se atribuye nueva cobertura backend a un bloque de presentación.

## 9. Pruebas en Chromium

La selección de regresión obtiene **28/28**, cuatro suites, **3,9 min**, sin
reintentos. Recorre portada, categorías, pantallas de trabajo y Ayuda.
Los seis roles consultan sus manuales desde la API QA real. El caso de
varios manuales usa una respuesta sintética exclusivamente de presentación;
no concede roles ni permisos a la cuenta real. Es una selección de la batería,
sin atribuir pruebas de todos los botones o reglas del backend a este recorrido.

Auditoría adicional de todas las secciones por rol: **6/6**, **4,2 min**, en una
corrida separada y sin reintentos. La unión de rutas auditadas coincide con las
**23 rutas** del menú. Incluye ventanas de alta de equipo, catálogo, delegaciones
y abonos cuando están autorizadas. No se presenta como una corrida única 34/34.

```powershell
cd pruebas-e2e
$env:URL_API='http://127.0.0.1:8020/api/v1'
$env:URL_BASE='http://localhost:4200'
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx playwright test escenarios/36-ayuda-imagenes.spec.ts escenarios/35-acceso-webp.spec.ts `
  escenarios/15-pantallas-trabajo.spec.ts escenarios/33-menu-categorias.spec.ts
npx playwright test escenarios/14-accesibilidad.spec.ts --grep 'todas las secciones visibles'
```

## 10. Accesibilidad y espacio

Ayuda se mide a **1366×768, 1024×768, 821×600, 844×390, 390×844 y 320×568**,
incluyendo Axe WCAG 2A/AA, 2.1AA y 2.2AA. Se conserva navegación de pestañas
con flechas/Inicio, nombres accesibles y estados de carga, error y vacío.
El contador tiene `role=status`; las imágenes de rol son decorativas.
Sin infracciones en las seis auditorías de tamaños de Ayuda. El escenario 15
mide también todas las rutas visibles de administración y plataforma a 1366×768,
1024×768 y 390×844; no detecta desplazamiento de página en escritorio ni desborde
horizontal en móvil. La portada conserva las comprobaciones de ocho tamaños.

[Escritorio](imagenes/ayuda-webp-escritorio-2026-10-11.png).
[Móvil](imagenes/ayuda-webp-movil-2026-10-11.png).

## 11. Incidencias y correcciones

Resuelto NG0956 al cambiar manuales: las listas de texto sin estado usan posición
como clave. La prueba conserva el nodo del límite, verifica su nuevo contenido y
exige ausencia del aviso. Se mantienen claves propias en tareas y permisos.

Primera corrida del escenario 36: **8 aprobadas/2 fallidas**. Una contaba tarjetas
antes de la respuesta; ahora espera la primera tarea. Otra llenaba el buscador
global de pacientes mientras cargaba Ayuda; ahora selecciona el nombre accesible
Buscar en el manual. No se relajan autorización, umbrales ni aserciones.

## 12. Calidad y compilación

Lint, tipos Angular/specs, sintaxis del exportador, diferencias sin errores de
espacio y build aprobados. Paquete inicial **485,81 kB**, transferencia estimada
**132,65 kB**, sin avisos ni aumento de presupuestos. Los recursos públicos se
descargan aparte. No se incorpora un formateador nuevo al proyecto.

```powershell
cd frontend
npm run lint
npx tsc --noEmit -p tsconfig.spec.json
npm run build
cd ..
node --check infra/scripts/exportar-interfaz-webp.mjs
git diff --check
```

## 13. Vulnerabilidades y secretos

Auditorías npm de frontend y E2E: **cero vulnerabilidades**. Gitleaks del índice
de implementación y del commit `a0e1b8c` aprobado, sin secretos y con salida
redactada. Comprobación de documentación y rango final aprobadas al cerrar.
No cambian dependencias Python,
autenticación ni manejo de claves; los riesgos anteriores del producto permanecen.

## 14. Credenciales y configuración

El exportador utiliza Chromium local instalado y los originales del repositorio.
No requiere API ni claves nuevas. El modo de acceso, especialidades, MFA y
autorización dependen de su configuración existente. No se modifican contratos
de API ni el esquema de datos.

## 15. Staging y producción

Publicar frontend y quince recursos juntos. Validar calidad visual, tareas de
roles reales, enlaces, vacío, foco, teclado, zoom y preferencias en navegadores
objetivo. La evidencia automatizada usa Chromium y datos sintéticos; otros
motores, lectores físicos y dispositivos requieren aceptación propia.

## 16. Despliegue, rollback y restauración

Implementación `a0e1b8c`, local en `main`, sin push.
Restaurar el paquete frontend previo revierte recursos/controles. Los originales
permanecen; no requiere restaurar datos ni revertir una migración. Se aplican
migraciones existentes solo en QA para integración, sin repetir downgrade ajeno.

## 17. Limpieza y pendientes

API **8020** detenida tras verificar PID propio, descendientes y propietario
del puerto. Base sintética exclusiva retirada con prefijo validado, cero sesiones
y ausencia posterior comprobada. El estado de QA queda marcado como eliminado.
Frontend **4200** y API **8000** conservados, ambos con respuesta **200**;
base de desarrollo y `.impeccable/` ajena conservadas. Evidencias sintéticas
ignoradas de QA quedan disponibles; no se eliminan archivos ajenos.

## 18. Evaluación

Mejora de recursos y lectura de manuales implementada, con batería completa de
componentes y selección de navegador aprobadas. No se declara terminado el
producto ni preparación global para producción.
