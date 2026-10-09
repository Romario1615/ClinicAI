# Verificación de interfaz — Analítica IA (2026-10-09)

## Alcance

Revisión sobre `main`, a partir de `326f047`. Se revisaron los cambios recientes
de portada (`99eac72`), especialidades (`721e4e2`) y bandeja de WhatsApp
(`0e5b05a`, `846fb34`). Este bloque modifica Analítica IA y sus instrucciones
en Ayuda; conserva el trabajo de esas entregas.

### Cambios

- Cabecera de IA compacta, con contadores de la respuesta autorizada:
  indicadores, modelos `validado_localmente` y recomendaciones.
- Tarjetas con nombre antes del valor, márgenes, leyendas, separación interna,
  definición y detalle. Tres columnas en pantallas amplias, dos en tamaños
  intermedios y una en móvil o escritorio estrecho.
- Buscador tolerante a tildes y filtro por cinco áreas. No crea indicadores,
  importes, pronósticos ni permisos. Claves futuras se agrupan en Operación.
- Tres vistas con selección visible y nombre accesible. Propuestas con prioridad,
  revisión humana y vínculo al módulo autorizado por el servidor.
- Metodología en ventana compartida con foco, Escape y retorno al botón de
  origen: serie diaria completa, datos del modelo y pronóstico. Alcance y límites
  en otra ventana. Tablas desplazables y encabezados asociados.
- Filtros en ventana hasta 1100 px, con acciones fijas. El resumen sigue
  mostrando la consulta aplicada durante la edición.
- Fechas del gráfico y periodo en español; hora de generación en la zona de la
  clínica. Línea observada y pronóstico diferenciados por trazo y leyenda.
- Mediciones cero visibles, series vacías explicadas, puntos aislados dibujados
  y huecos conservados. El recorte visual a 60 días se declara cuando corresponde;
  la tabla mantiene todas las fechas devueltas por la API.
- Manuales de recepción, profesional, administración, auditoría,
  superadministración y roles personalizados actualizados con pasos propios.

## Pruebas

Frontend 4200 y API local 8000 con datos sintéticos. No se crean pacientes ni
se modifica historia clínica; el endpoint existente de analítica conserva su
captura diaria al consultarlo. Los extremos visuales y el error transitorio
sustituyen solo la respuesta agregada, según el patrón del escenario visual 16.

- Componentes: búsqueda combinada, áreas autorizadas, filtros, respuestas fuera
  de orden, error/reintento, diálogos, series desconocidas/cero, puntos aislados
  y hora de la clínica.
- Chromium: recorrido anterior de analítica más cinco escenarios nuevos;
  ocho tamaños y tres vistas (**24 combinaciones**): 1920×1080, 1440×900,
  1366×768, 1024×768, 821×600, 768×1024, 390×844 y 320×740.
- Medición de separación, solapamientos, desbordes y desplazamiento limitado
  a la lista en escritorio. En 821×600 la lista conserva más de 90 px.
- Búsqueda, filtro Finanzas, detalle por Enter, Escape y foco devuelto;
  límites, cifras de trece dígitos, nombres largos, series vacías, filtros
  en ventana y recuperación de un 503 sintético.
- Axe WCAG 2 A/AA y 2.1 A/AA en detalle, vista predictiva y extremos móviles.

### Comandos

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
npm.cmd run test:ci -- --runner-config='../tmp/qa-20261007/vitest-ia.mjs'
# Comprobación focalizada:
npm.cmd run test:ci -- --coverage=false --include='src/app/paginas/analitica/analitica.component.spec.ts' --runner-config='../tmp/qa-20261007/vitest-ia.mjs'

cd ../pruebas-e2e
npx.cmd playwright test escenarios/21-analitica-diseno.spec.ts escenarios/18-periodontograma-analitica-agente.spec.ts --grep 'analítica'

cd ../backend
.venv/Scripts/python.exe -m pytest pruebas/unitarias/test_ayuda_manuales.py -q
```

El archivo local de Vitest limita los trabajadores a uno; no cambia aserciones
ni mínimos de cobertura. Registros y capturas bajo `tmp/qa-20261007/` (ignorado
por Git).

### Resultados

- **Frontend completo: 770/770**, 103 archivos, 282,33 segundos. Incluye
  las **13 pruebas** de Analítica (ocho nuevas). Cobertura: 85,14 % sentencias,
  72,05 % ramas, 80,91 % funciones y 87,62 % líneas; mínimos cumplidos.
  Registro: `analitica-frontend-completo.log`.
- **Manuales: 26/26**, 3,61 segundos después del formato final.
  Registro: `analitica-manuales-final.log`. Ruff y formato aprobados.
- **Lint y compilación de producción: aprobados**, sin avisos de presupuesto.
  Paquete inicial: 468,10 kB. Analítica se carga de forma diferida (48,51 kB).
  Registros: `analitica-lint-final.log`, `analitica-build-final.log`.
- **Secretos:** Gitleaks del índice aprobado; informe y registro en
  `analitica-gitleaks-indice.json` y `analitica-gitleaks-indice.log`, con
  resultados redactados y sin secretos detectados.
- **Chromium focalizado: 6/6**, 39,8 segundos, sin reintentos. Se repite en el
  bloque final junto con la auditoría de desbordes de todas las secciones del
  menú para administración y plataforma.
- **Chromium final: 8/8**, 2,5 minutos, sin reintentos. Incluye los cinco
  escenarios nuevos, el recorrido anterior de analítica y los dos recorridos
  de todas las secciones del menú (administración y plataforma) en escritorio
  y móvil. Registro: `analitica-e2e-menu-final.log`. Se ejecuta con el código
  final, incluidos el contador de modelos validados y el aviso de 60 días.
- El primer ajuste compacto pasó seis escenarios; la inspección de capturas
  detectó un buscador demasiado estrecho. Al darle otra fila, dos pruebas
  señalaron que el área útil era de 89 px en 821×600. Se trasladaron los filtros
  a la ventana para conservar espacio y se repitió el bloque; **se conservó la
  aserción de más de 90 px**, sin relajar el criterio.

Capturas: `analitica-compacta-20261009.png`, `analitica-movil-20261009.png`,
`analitica-finanzas-predictiva-20261009.png` y
`analitica-extremos-movil-20261009.png`.

La aplicación 4200 y API 8000 permanecen activas. Se comprobó el servidor de
desarrollo y se actualizó la referencia `origin/main`: no había commits remotos
nuevos que integrar; los siete commits anteriores pendientes de publicación
se conservaron. Este bloque se guarda sobre ellos en `main` local.

## Decisiones y límites

No cambian esquemas, cálculos, autorización, rutas ni claves. No requiere
migraciones ni configuración nueva. La analítica permanece local y
administrativa: la interfaz no convierte modelos experimentales en validados
ni ejecuta recomendaciones. El contador sigue el estado emitido por el backend.

Esta entrega no repite la suite global del backend ni confirma proveedores
externos. Se revisan Chrome/Chromium y datos sintéticos; no se acreditan equipos
físicos ni otros navegadores. Los requisitos de producción siguen pendientes.
Reversión: revertir este bloque y reconstruir el frontend; no hay cambios de
datos que restaurar ni nuevos secretos.
