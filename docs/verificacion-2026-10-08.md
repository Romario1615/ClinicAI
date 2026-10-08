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
externos ni validez institucional de los PDFs. En esa revisión Periodoncia
incluía el índice de placa; el periodontograma completo se implementó después
y su evidencia se registra en la ampliación al final de este informe.
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
<a id="agente-periodontograma-analitica-y-fotografias"></a>

# Agente, periodontograma, analítica y fotografías

## 1. Alcance implementado

Ficha con **Agente del paciente** junto al historial, herramientas operativas
existentes y confirmación humana. Periodontograma versionado de 32 piezas,
seis sitios, fotos y PDF. Analítica descriptiva/predictiva/prescriptiva con
aprendizaje local y datos reales del ámbito. Captura y galerías privadas de
registros clínicos y administrativos. Manuales propios de cada rol.

## 2. Archivos y organización

`modulos/asistente/paciente_*`, `ia/conversacion.py`, migración `035` y
`compartido/agente-paciente.*`; periodontograma en `modulos/odontologia` y
`paginas/historia-clinica`; observaciones en `modulos/dashboard`, fotografías
en `modulos/imagenes`, formularios y galería compartida. Se extrajeron el
repositorio de capturas y la huella de ámbito; el encabezado del Panel tiene
su propio componente para conservar los presupuestos de estilos.

## 3. Decisiones

[ADR-0023](decisiones/0023-periodontograma-analitica-y-fotos.md) y
[ADR-0024](decisiones/0024-agente-en-la-ficha.md): conservar versiones, datos
ausentes y filtros; modelos locales verificables; fotos privadas; paciente
fijo, permisos del operador y confirmación antes de una escritura operativa.

## 4. Pruebas backend ejecutadas

La corrida completa previa al agente aprobó **2.082 pruebas** y omitió tres
llamadas optativas a un proveedor externo, en **16 min 2 s**, con PostgreSQL
temporal y `pytest --no-cov -q -n 2 --dist=loadfile`. La base exclusiva se eliminó.
Después, la revisión focalizada del agente y los módulos afectados aprobó
**168 pruebas**, en **2 min 49 s**, con `--no-cov -q -n 1 --dist=loadfile`, incluyendo
regresiones del agente de WhatsApp y sus servicios. No se presentan como una
sola ejecución global actualizada. Los manuales ampliados aprobaron **26 casos**.

## 5. Pruebas frontend ejecutadas

`npm.cmd run test:ci -- --runner-config='../tmp/qa-20261007/vitest-ia.mjs'`:
**743 pruebas aprobadas en 102 archivos**, en **8 min 18 s**, con un trabajador
por la memoria disponible. Una primera corrida detectó cuatro selectores de
pruebas que pulsaban Fotos en lugar de Editar; se corrigió la selección del
botón explícito y se repitió la batería.

## 6. Recorridos de navegador

Chromium con API 8020 y PostgreSQL exclusivo: **4/4**, en **49,3 s**, archivo
`18-periodontograma-analitica-agente.spec.ts`. Ficha profesional con historial,
resumen local, citas y cierre; recepción sin lectura clínica; periodontograma
con PS/MG/sangrado, foto privada, persistencia, PDF y móvil; tres análisis.
Axe WCAG A/AA sin incidencias en los estados revisados.

## 7. Cobertura

En la corrida frontend de 743 casos: sentencias **85,11 %**, ramas **71,92 %**,
funciones **80,65 %**, líneas **87,42 %**. No se rebajaron mínimos. Las corridas
backend citadas usaron `--no-cov`; no se atribuye una medición nueva de cobertura.

## 8. Calidad estática

Ruff, formato y Mypy aprobados: **397 archivos formateados**, **253 fuentes
tipadas**. Bandit con umbral de severidad media/alta sin hallazgos. Lint y build
frontend aprobados sin advertencias de presupuesto. El encabezado y selector
del Panel se extrajeron en componentes; se conservó el límite de 14 kB.

## 9. Fallos corregidos

La auditoría del agente utiliza el origen WEB admitido por la base; los apartados
desde el personal se identifican como PANEL y WhatsApp conserva su origen.
Las lecturas de fotos clínicas aplican los permisos clínicos de sensibilidad,
conservando el control independiente del ámbito RAG y ACL de Conocimiento.
Un recorrido detectó una foto correctamente guardada que no se mostraba: se
añadió regresión de listado y descarga. Se corrigió un selector de caché de
prueba que mezclaba operaciones incompletas con la respuesta terminada.
La selección de cita se explica antes de preparar cambios y se retira al
cancelarla. La sesión de un operador no puede reutilizarla otro usuario de
la misma clínica. Se añadieron pruebas específicas de ambos comportamientos.

## 10. Riesgos pendientes

Carga, DAST, restauración real, accesibilidad manual y comportamiento del LLM
externo siguen pendientes. Modelos con historia insuficiente no pronostican;
sus recomendaciones administrativas requieren revisión humana.

## 11. Credenciales faltantes

No se añadieron claves externas. Las funciones locales operan con PostgreSQL;
LLM libre, WhatsApp real, calendarios y otros servicios se verifican después
de configurar credenciales del cliente. Sandbox no acredita entrega externa.

## 12. Entorno de revisión

Frontend local 4200 y API local 8000; pruebas de navegador dirigidas a 8020.
Los datos de pruebas son sintéticos y se alojan en bases exclusivas. El acceso
por botones sigue restringido al entorno de desarrollo.

## 13. Producción

Configurar dominios, autenticación definitiva, roles y ámbitos del cliente,
proveedores y almacén cifrado; verificar integraciones con sus credenciales.
Esta revisión local no cierra la fase de producción.

## 14. Migraciones y despliegue

`032`–`035`: tablas aditivas de periodontograma, fotografías, observaciones y
sesiones. Se comprobó upgrade/downgrade de las cuatro y `alembic check` en
base temporal. La base local conserva los datos existentes y está en `035`.
Actualizar API y worker con el mismo código y conservar archivos cifrados.

## 15. Reversión

Revertir código preservando las tablas y archivos incorporados. El downgrade
elimina las tablas de esta ampliación y se utiliza aquí solo en una base
descartable; no es una operación de reversión de historia clínica en producción.

## 16. Respaldo y restauración

Conservar base, objetos cifrados y claves administradas por el cliente. El
script de respaldo exige una clave externa; no se inventó una ni se declara
una nueva restauración operativa en esta revisión.

## 17. Evidencia y siguientes verificaciones

Registros en `tmp/qa-20261007`: `backend-periodontograma-total.log`,
`backend-agente-final-168.log`, `backend-agente-manuales.log`,
`frontend-agente-total-verificado.log`, `e2e-agente-4.log`,
`e2e-agente-confirmacion-corregido.log`, `frontend-agente-build-verificado.log`,
`frontend-agente-lint-verificado.log` y salidas finales de Ruff/Mypy/Bandit.
Las imágenes `agente-en-ficha.png`, `periodontograma-fotos.png`,
`periodontograma-movil.png` y `analitica-predictiva.png` usan datos sintéticos.
La revisión final de cambios posteriores se añade debajo.

## 18. Preparación

Funcionalidad local verificada en los recorridos indicados. Continúan abiertas
las integraciones externas y las verificaciones de preparación operativa;
no se declara el producto listo para producción.
