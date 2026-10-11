# Verificación de documentos privados y PDF — 2026-10-10

## 1. Implementación

Identidad obligatoria en enlaces nuevos y antiguos, comprobación privada de recetas
suspendidas, auditoría con IP/intentos y PDF con fuente local, símbolos, párrafos y
fechas de sede/clínica. Presupuesto desde plan con validación recuperable y errores
Blob explicados al personal. No se modifica la pauta de una receta confirmada.
La redacción compartida oculta enlaces privados y consultas de URL en logs.

## 2. Archivos

`documentos/{fuente_pdf,pdf,servicios,rutas}.py`, `nucleo/registro.py`, fuente/métricas/licencia,
`infra/scripts/preparar-fuente-pdf.py`, cliente HTTP de frontend, manuales de Ayuda,
pruebas unitarias/API y Chromium 32. El escenario 18 actualiza el supuesto de
recepción a ADR-0026. `main.py` comparte únicamente plantillas públicas de métricas.
README, arquitectura, seguridad, límites, preparación y ADR-0029 documentan el bloque.

## 3. Decisiones

Nacimiento registrado prioritario; documento alfanumérico de cuatro caracteres
solo si falta esa fecha. No se comparan cadenas vacías. Los PDFs no interpretan
HTML, JS ni operadores aportados. Fuente fija con SHA-256 y licencia, UTF-16BE,
CIDToGIDMap y ToUnicode. NFC; caracteres no representables e instrucciones de
composición no soportada fallan de forma explícita, sin sustituir unidades.
Se rechazan categorías Unicode M, Zl y Zp aunque la fuente las contenga; los
saltos ordinarios LF se conservan. Logs de librerías y aplicación comparten
redacción de ruta/consulta, sin afirmar protección de registros históricos externos.
La zona se conserva en nuevas instantáneas; en registros previos se usa la zona
vigente de sede/clínica. No se infiere duración ni se cambia medicación.

## 4. Entorno

Windows, PostgreSQL real y Redis local. Cinco bases propias: cuatro particiones
backend y una para navegador, con prefijos exclusivos `clinicai_qa_documentos_`,
`clinicai_qa_documentos_p[1-3]_` y `clinicai_qa_documentos_e2e_`. Datos sintéticos
y transacciones reversibles para API. La API temporal 8020 usa la última base;
el navegador dirige ahí sus solicitudes. Se conservan app 4200 y API 8000.
Mocks de LLM/embeddings y WhatsApp/Calendar sandbox; sin mensajes externos.

## 5. Comandos backend

Los auxiliares ignorados fijan base exclusiva, almacén y archivo de cobertura.
Un manifiesto distribuye todas las pruebas sin duplicar archivos; solo la
partición cero usa Redis real para integración. No ejecutar dos procesos de
pytest sobre la misma base, aunque sus sesiones usen transacciones reversibles.
Inventario final: **146 archivos**, ninguno omitido o duplicado. Los nombres de
base son temporales: para repetir el recorrido hay que preparar bases nuevas.

```powershell
$env:PYTHONUNBUFFERED='1'
uv run python ../tmp/qa-20261010-documentos/ejecutar-particion.py 0
uv run python ../tmp/qa-20261010-documentos/ejecutar-particion.py 1
uv run python ../tmp/qa-20261010-documentos/ejecutar-particion.py 2
uv run python ../tmp/qa-20261010-documentos/ejecutar-particion.py 3
# Cada ejecución: coverage run -m pytest --no-cov -q <selección>.
# --no-cov evita una segunda instrumentación del plugin; coverage run mide app.
# Al combinar se conserva fail_under=80, source=app y branch=true del proyecto.
uv run python ../tmp/qa-20261010-documentos/combinar-cobertura.py final
uv run ruff check app pruebas ../infra/scripts/preparar-fuente-pdf.py
uv run ruff format --check app pruebas ../infra/scripts/preparar-fuente-pdf.py
uv run mypy app
uv run bandit -q app/modulos/documentos/pdf.py app/modulos/documentos/fuente_pdf.py `
  app/modulos/documentos/rutas.py app/modulos/documentos/servicios.py `
  app/main.py app/nucleo/registro.py ../infra/scripts/preparar-fuente-pdf.py
```

## 6. Resultados backend

Regresión completa por particiones:

| Partición | Aprobadas | Omitidas | Tiempo |
|---|---:|---:|---:|
| 0, repetición aislada | 1884 | 3 llamadas reales a Anthropic sin configurar | 1150,16 s |
| 1 | 159 | 0 | 516,80 s |
| 2 | 204 | 0 | 594,92 s |
| 3 | 161 | 0 | 462,06 s |

Son **2408 aprobadas y tres externas omitidas** en cuatro ejecuciones. El cierre
de módulos actualizados pasó **162/162**, incluidos identidad, PDF, API y redacción;
incluye tres variantes API añadidas después de la partición 2. La colección
actual contiene 2414 casos: **2411 distintos aprobados entre las corridas y tres
externos omitidos**, no una corrida única 2411/2411. El aislamiento del registro
global se repitió **10/10** tras añadir restauración de handlers y structlog.

Cobertura final combinada: **89,04 %**; documentos **90,93 %**, fuente PDF
**97,87 %** y generador PDF **100 %**. Se conserva el umbral **80**. Se combinaron
copias de las cuatro mediciones y del cierre de módulos, manteniendo los originales.
La medición anterior de logging/fuente en las particiones 1–3 se sustituyó por la
actual para no atribuir aciertos a líneas desplazadas; ambos módulos siguen en
el informe y denominador. El archivo combinado final se creó nuevo, sin arrastrar
una combinación previa.

La regresión intermedia de documentos/manuales obtuvo
96 aprobadas y un error de fixture descrito en el punto 11. Cobertura parcial de
documentos: 90,45 %; no sustituye el resultado completo. El catálogo de métricas
y su API pasaron 3/3 en 11,10 s; limitar cobertura a `app.main` obtuvo 72,48 % y
no alcanzó el umbral 80, que se conserva en la corrida completa.
Los artefactos locales están en `tmp/qa-20261010-documentos/`: manifiesto,
colección, resultados de cada partición, repetición cero, cierre de módulos y
`cobertura-backend-final.json`.

## 7. Autorización y lógica

La batería protege 401, permisos 403, clínica/sede/especialidad ajenas 404, N3,
autor, receta confirmada, revocación, consentimiento, idempotencia, versionado y
restricciones append-only. Las pruebas nuevas rechazan identidad vacía aun en
enlaces preexistentes, documento insuficiente y falta de referencia al compartir.
La receta suspendida no revela estado antes de verificar identidad. El nacimiento
registrado sigue teniendo prioridad. Los intentos/IP no guardan verificadores.
Valores de planes fuera de límites producen 422 y ninguna versión parcial.

## 8. Frontend

Corrida definitiva: **899/899**, 110 suites, 113,37 s. Cobertura: 85,95 %
sentencias, 73,46 % ramas, 82,09 % funciones y 88,44 % líneas. Lint/build aprobados.
El cliente solo interpreta errores Blob pequeños como JSON; cuerpos vacíos o
grandes tienen respuesta inmediata genérica. No incorpora contenido PDF a un
mensaje de error. La suite de descargas añade nueve regresiones.

```powershell
npx ng test --watch=false --coverage
npm run lint
npm run build
```

## 9. Navegador y diseño

Chromium definitivo sobre el commit de implementación: **11/11**, 3,5 min,
sin reintentos ni omisiones. Las corridas previas completas fueron 11/11
en 2,1 y 2,4 min; la última se ejecutó durante la regresión con cobertura.
Presupuesto/cotización/receta/faciograma/periodontograma reales, versión, anulación,
entrega sandbox, agente, analítica, consulta de recepción y escritura rechazada.
El nuevo escenario 32 comprueba error 422 real de PDF desde la ficha y libera el
botón; la página pública a 390×844 rechaza identidad incorrecta, descarga tras
verificación y exige cero infracciones Axe WCAG 2A/AA, 2.1AA y 2.2AA y sin desborde.
La primera corrida tuvo 10 aprobadas y un supuesto obsoleto; se corrigió y repitió
la selección completa. No se computa como aprobada esa primera corrida.
Una repetición arrancó antes de que la API reiniciada estuviera lista: 9 aprobadas
y dos conexiones rechazadas. Se esperó `/salud/listo` 200 y se repitió la selección
completa, con 11/11; no se oculta ni se computa esa corrida parcial como aprobada.

```powershell
$env:URL_API='http://127.0.0.1:8020/api/v1'
npx playwright test escenarios/17-registros-y-documentos.spec.ts `
  escenarios/18-periodontograma-analitica-agente.spec.ts `
  escenarios/32-documentos-integridad.spec.ts --project=chromium
```

## 10. PDF y medición

PDFium renderizó ejemplos sintéticos y se inspeccionaron sus imágenes: símbolos,
saltos de párrafo, palabras largas dentro del ancho y referencias de 23 zonas.
La extracción pypdf y ContentStream comprueban texto y operadores permitidos;
no hay OpenAction, AA ni anotaciones. Una fuente incorporada con ToUnicode evita
depender de fuentes del lector. Generación de 20 PDFs sintéticos de 40 filas:
mediana **79,28 ms**, máximo **161,27 ms**, 491 599 bytes. Es una medición local
durante otras tareas, no una prueba de carga ni un SLA.

[Captura en gris del PDF sintético](imagenes/pdf-unicode-sintetico-2026-10-10.png):
prueba unidades, párrafos, fecha local y una cadena ancha. No contiene una pauta
para un paciente real ni representa una receta válida.

## 11. Fallos encontrados y corregidos

- La reproducción previa confirmó que nacimiento arbitrario podía superar una
  identidad vacía. Ahora se rechaza y se cuenta el intento. No se crean nuevos
  enlaces sin datos verificables.
- cp1252 sustituía «μ» y perdía saltos. La fuente Unicode conserva glifos admitidos
  y rechaza los demás, incluidos controles invisibles o bidireccionales.
- El primer frontend completo obtuvo 897 aprobadas y un fallo: decodificar un
  Blob vacío retrasaba la finalización del control de descarga. El camino sin
  cuerpo vuelve a ser inmediato; la repetición 899/899 incluye una regresión.
- Una fixture intentaba persistir 301 caracteres en `VARCHAR(300)` antes de
  invocar el presupuesto. Se sustituyó por una descripción vacía que la BD
  admite y el presupuesto rechaza; la validación >300 permanece en dominio.
  No se cambia el esquema ni se relajan las aserciones de límites.
- El escenario 18 suponía que recepción no consultaba resúmenes, anterior a la
  decisión del propietario y ADR-0026. Ahora exige resumen de ese paciente,
  lectura visible y rechazo 403 al intentar registrar contenido clínico.
- Las primeras corridas con cobertura se interrumpieron para corregir trabajo
  repetido en creación de aplicaciones: un perfil sin variables locales señaló
  el catálogo de rutas de métricas. Se conservan en caché solo plantillas públicas
  de la topología fija; cada aplicación mantiene contadores, permisos y sesiones.
  La ruta configurable de métricas se añade por instancia. Las rutas no conocidas
  se agregan como `no_encontrada`, sin publicar identificadores.
- La revisión del servidor encontró 13 referencias de enlaces privados en sus
  registros de prueba. La cadena compartida ahora oculta ruta y consulta. La
  repetición final produjo ocho accesos privados, todos ocultos y sin respuestas
  500; se sanearon dos referencias en un log previo de reproducción propio.
  No se revisaron ni modificaron registros históricos de otras instalaciones.
- Se detectaron separadores y marcas Unicode con ancho cero presentes en la
  fuente. Se rechazan explícitamente, con casos U+2028, U+2029, U+034F y U+FE0F,
  además de la validación API que conserva el carácter dentro de un texto.
- La primera partición cero obtuvo 1869 aprobadas, un bloqueo de catálogo y
  tres omisiones externas. La regresión de módulos se había lanzado sobre su
  misma base; ambos procesos cargaron permisos al mismo tiempo. Fue un fallo
  de coordinación de pruebas. Se repitió la partición sola: 1884 aprobadas y
  tres externas omitidas. No se modifica el cargador ni se relajan sus aserciones
  para ocultarlo.

## 12. Secretos y dependencias

`npm audit` frontend/E2E: cero vulnerabilidades. `pip-audit` de requisitos
bloqueados base y dev/LLM: ninguna conocida. El inventario del virtualenv con
extras conserva 35 avisos de Pillow 11.3.0 (E-12/ADR-0007); esta exportación no
instala ni invoca Pillow. fontTools 4.66.1 solo regenera métricas en desarrollo.
Ruff/formato: 417 archivos; mypy: 260 fuentes; Bandit de archivos afectados,
incluidos logging y fábrica de aplicación, aprobados.
Gitleaks del índice de implementación/documentación y rango de commits desde
`eee526d`: sin hallazgos, con salida redactada.
No se ejecutó nueva auditoría Docker ni DAST.

## 13. Base y migraciones

No cambia el esquema. Las cinco bases exclusivas se migraron desde cero hasta
`20261009_038`. No hay una migración nueva que revertir. La actualización de
zona solo añade un dato a nuevas instantáneas JSON, sin modificar versiones previas.
API 8020 y las cinco bases exclusivas retiradas; ausencia comprobada en
`pg_database`. App `http://localhost:4200` y API 8000 `/salud/listo` responden 200.
La revisión automática bloqueó la eliminación de cinco adjuntos
sintéticos en `tmp/qa-20261010-documentos-e2e/almacen/`; el motivo devuelto fue
«blocked by policy». Permanecen ignorados por Git, sin una API/base que los sirva.
No se borraron datos ni archivos ajenos.

## 14. Configuración y credenciales

La fuente, licencia y JSON de métricas deben distribuirse juntos; se verifica
el hash al cargar. No requiere claves para generar PDFs. WhatsApp real sigue
necesitando credenciales propias, consentimiento y destinatario confirmado.
Staging/producción conservan autenticación completa, ámbito y separación de
especialidades; los accesos por rol siguen limitados al entorno local.

## 15. Despliegue

Reconstruir backend/frontend desde el commit aprobado. Docker copia la carpeta
de fuentes con `backend/`; no instala fontTools en la API. En staging, verificar
salud, exportación autorizada, unidad Unicode, fechas por sede, controles de
caducidad e identidad y error visible del cliente. Los documentos clínicos de
staging deben estar autorizados y revisados por su profesional.
Revisar redacción de rutas/consultas en API y proxy, así como la conservación de
logs anteriores: la protección nueva no cambia registros históricos.

## 16. Rollback y restauración

Preferir corrección hacia delante: volver al código anterior reintroduciría la
verificación vacía. Ante problemas de representación, detener nuevas entregas
externas y corregir el recurso/lector con pruebas sintéticas. No modificar ni
borrar historia para solventar un problema de exportación. La fuente se restaura
desde el archivo fijado y se regeneran métricas con el script; conservar licencia.
Los respaldos de PostgreSQL y claves siguen el procedimiento existente; el bloque
no ensaya una restauración completa ni altera los respaldos.

## 17. Pendientes

Resolver el enlace del outbox desde referencia cifrada al enviar; la carga útil
actual contiene el enlace en claro aunque `entrega_documento` tenga hash/cifrado.
Firma certificada y aceptación del envío real. Composición bidireccional, emojis
fuera de la fuente y escrituras complejas no están soportadas. Los PDFs previos usan zona vigente
porque no conservaban su configuración histórica. E-12 sigue pendiente.

## 18. Preparación

Implementación **`e3f930d`**, local en `main`, sin push. Lectura/escritura y datos
clínicos conservan la política del propietario. La exportación y entrega se verifican con datos
sintéticos, sin contacto con clientes ni proveedor real. Backend, frontend,
navegador y controles estáticos aprobados. La limpieza de bases/API está completa;
cinco adjuntos sintéticos permanecen por el bloqueo documentado. No se declara
producción global.
