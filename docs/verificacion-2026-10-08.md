# Verificación del 8 de octubre de 2026

## Cambios reunidos en main

Se resolvió la fusión con `claude/friendly-gates-o240sb`, conservando los cambios
de agenda, ocupación y protección de formularios de GitHub, y los filtros de
autor/especialidad, delegación de firma y herramientas de la ficha. El acceso
local incorpora selección de perfiles sintéticos por especialidad.

## Diseño de gestión con agente IA

Portada completa, marca azul/cian, núcleo IA con seis conexiones, partículas SVG
decorativas y panel de seguimiento con la misma identidad. La base de estilos
aplica la paleta a módulos, controles, tarjetas y ventanas. El área de trabajo
utiliza todo el ancho disponible. Los fondos no interceptan clics ni teclado,
no leen datos clínicos y no realizan peticiones externas.

Las animaciones respetan `prefers-reduced-motion` y el servicio de movimiento.
Las preferencias de contraste/transparencia ocultan el ambiente decorativo.
El agente se presenta como apoyo para agenda, mensajes y conocimiento aprobado;
no se anuncia conexión con proveedores reales ni capacidad de decidir tratamientos.

## Recorrido funcional del faciograma

Chromium, frontend en 4200 y API en 8020 con PostgreSQL exclusivo y datos
sintéticos. Los proveedores de IA son mock; mensajería y calendario usan sandbox.

- Odontología muestra odontograma y Periodoncia y rechaza las zonas faciales con 403.
- Dermatología muestra Faciograma y oculta odontograma y Periodoncia.
- El selector de registros ofrece únicamente las herramientas de cada especialidad.
- Un clic en Mentón abre el editor; se guarda observación, estado, sede y motivo.
- Enter vuelve a abrir la observación guardada; la corrección incrementa la versión.
- El registro corregido se muestra en la ficha y descarga un PDF con cabecera válida.
- Axe WCAG 2/2.1 A/AA y ausencia de desbordamiento horizontal aprobados a 1440 y 390 px.

Artefactos locales: `tmp/qa-20261007/faciograma-browser-final.log`,
`faciograma-1440.png`, `faciograma-390.png` y `faciograma-verificado.pdf`.

## Alcance

Estas pruebas usan datos sintéticos. No prueban entrega real a WhatsApp, modelos
externos ni validez institucional de los PDFs. Periodoncia incluye el índice de
placa existente; el periodontograma clínico completo mantiene su trabajo pendiente.
El PDF facial conserva el esquema vectorial y las observaciones; la nueva
ilustración anatómica se usa en la pantalla.

## Navegación y accesibilidad del rediseño

Chromium aprobó acceso y panel en escritorio/móvil para los seis roles y el
manual de Ayuda de cada uno. La portada pasó a 1920, 1440, 768 y 390 px, sin
desbordamiento horizontal. Axe WCAG 2/2.1 A/AA pasó en 22 vistas: cuatro tamaños
de portada y tres por rol (panel escritorio/móvil y Ayuda). Se verificó que
activar movimiento reducido elimina la animación de las partículas.

Se corrigió el relleno heredado del armazón que dejaba márgenes en la portada.
El primer análisis de insignias del panel coincidió con su entrada animada;
la comprobación final espera que terminen la carga y las transiciones finitas
para medir el contraste estable, sin excluir controles de la auditoría.

Evidencia local: `tmp/qa-20261007/portada-ia-browser.log` y capturas `ia-*.png`.

## Pruebas focalizadas de API

**129 aprobadas** en 4 min 16 s sobre PostgreSQL exclusivo, con un trabajador:
autenticación, selección local de especialidad, módulos de historia, registros
del paciente y aislamiento entre especialistas. Se corrigió el nombre del campo
de ámbito del fixture (`valor_id`); se mantuvieron las aserciones y los requisitos
de autorización. La base temporal se eliminó al terminar.

## Regresión completa del backend

**2 030 aprobadas, 3 omitidas** en 11 min 3 s, con dos trabajadores sobre
PostgreSQL y Redis y una base exclusiva. Las tres omitidas requieren activar
llamadas reales a Anthropic (`PRUEBAS_LLM_REAL=1`); no se configuraron esas APIs.
La base temporal se eliminó al terminar y la base de desarrollo se conservó.

La ejecución completa anterior quedó interrumpida y no se cuenta como resultado
final. La primera corrida focalizada contenía un fixture con un campo de ámbito
incorrecto y errores de autenticación durante competencia de memoria; el fixture
se corrigió y las siguientes 129 focalizadas y 2 030 globales pasaron sin relajar
las aserciones, las reglas clínicas ni los parámetros de contraseñas.

Evidencia: `tmp/qa-20261007/backend-ia-main-completo.log` y
`aislamiento-total-entorno.json` con `limpiado: true`.

## Frontend, calidad y servidor local

**689 pruebas aprobadas en 94 archivos**, en 6 min 51 s. Cobertura: sentencias
84,64 %, ramas 71,51 %, funciones 80,35 % y líneas 86,93 %. La primera ejecución
aprobó 678 casos pero no alcanzó el mínimo de funciones; se añadieron once
pruebas de contratos de API para clínicas, sedes, usuarios, especialidades,
avisos, agenda, anulación y errores. Se conservaron los mínimos de cobertura.
Los tres casos nuevos del ambiente decorativo comprueban accesibilidad, tono
y cambio de preferencia de movimiento.

- Lint frontend aprobado. Build de producción aprobado, **466,80 kB** iniciales,
  sin avisos de presupuesto; los paquetes de pantalla continúan diferidos.
- Ruff y formato: aprobados, 369 archivos. Mypy: 232 fuentes sin incidencias.
  Bandit: sin incidencias de severidad media/alta.
- Gitleaks: sin secretos en cambios preparados ni en los commits de integración.
- PostgreSQL: readiness de la API local responde `listo`.
- API 8000 reiniciada con estos cambios; frontend 4200 disponible. El catálogo
  local ofrece seis roles y perfiles de Odontología, Medicina general, Pediatría
  y Dermatología. Chromium verificó de nuevo sesión, ámbito y manual propio con
  axe para los seis roles sobre los servicios locales 4200/8000.
- API de pruebas 8020 detenida; su base exclusiva quedó eliminada y su
  metadato de limpieza confirmado. La base de desarrollo se conserva.

Evidencia local: `frontend-ia-cobertura.log`, `build-ia-final.log`,
`lint-ia-final.log` e `ia-local-browser.log`, dentro de `tmp/qa-20261007/`.
