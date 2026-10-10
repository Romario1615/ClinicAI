# Verificación de OCR local — 2026-10-10

## 1. Implementación

Reconocimiento de PDF escaneados desde Conocimiento, sin claves externas.
Vista previa editable, confirmación humana, identificación de páginas vacías
y guardado posterior mediante la ingesta existente. No publica contenido ni
crea documentos durante la extracción. Se corrigió además el desplazamiento
automático del marco de ventanas al enfocar campos, que ocultaba la cabecera.
Implementación: `6e86fe8`; cierre de lecturas y recorridos: `6627b4a`, ambos
en `main` local.

## 2. Archivos

Backend: `modulos/conocimiento/ocr.py`, `ocr_proceso.py`, `rutas.py`,
`esquemas.py`, configuración, auditoría y manuales de Ayuda. Dependencias:
`backend/pyproject.toml`, `uv.lock`, Dockerfile backend y CI. Frontend:
`cargar-documento.component.ts`, su suite, `api.service.ts` y el marco común
`ventana-flotante.component.ts`. Pruebas: fixture PDF imagen sintético,
`test_conocimiento_ocr.py`, `test_conocimiento_api.py` y escenarios Chromium
05, 17 y 31.
Guía, ADR-0028, arquitectura, seguridad, límites, preparación y README actualizados.

## 3. Decisiones

OCR explícito antes de la ingesta, español/inglés, PDFium y Tesseract locales.
Un proceso por solicitud: PDFium no comparte hilos. Pipes, sin shell, sin
archivos persistidos por la conversión y sin credenciales de la aplicación en
el entorno del proceso. No añade Pillow/NumPy. No hay migración ni nuevos permisos.
[ADR-0028](decisiones/0028-ocr-local-con-revision.md).

## 4. Recorrido de usuario

Conocimiento → Cargar documento → PDF → Reconocer texto del escaneo → corregir
Contenido → confirmar comparación con el original → guardar borrador. Editar
otra vez desmarca la revisión. Fallar conserva el PDF; durante la conversión
se bloquean cierre, sustitución de archivo y doble envío. Se conserva el
nombre del escaneo al ingerir el texto revisado. El antivirus del original se
informa en la vista previa y su ausencia se mantiene visible tras guardar.

## 5. Permisos, ámbitos y auditoría

El nuevo POST exige `conocimiento.cargar`. Las pruebas verifican 401, 403,
archivos inválidos, rol autorizado y aislamiento. No recibe un ID ni lee
documentos: añadir un ID/clínica ajenos no modifica la extracción ni la clínica
de auditoría. Acceder después al documento ajeno sigue devolviendo 404.
`documento.extraido` registra actor/clínica de sesión, método y cantidades;
no incluye contenido ni nombre del archivo. No crea filas de conocimiento.
El SQL RAG conserva aprobación, vigencia, sensibilidad y ACL.

## 6. Entorno

Windows, Python 3.12.15, API sintética exclusiva en 8020, PostgreSQL real
`clinicai_qa_ocr_4f27f0d5` desde cero hasta `20261009_038`, Redis 13, WhatsApp y
calendario sandbox, LLM/embeddings mock. Aplicación Angular real en 4200.
Tesseract 5.3.4 en WSL `clinica`, idiomas `spa` y `eng`. PDFium instalado desde
`pypdfium2==5.14.0`. Solo datos y documentos sintéticos.

## 7. Backend y regresión

**1.181 aprobadas**, 291,36 s: todas las unitarias y suites API/integración de
conocimiento, agente de conocimiento, fugas RAG, evaluación RAG y auditoría
append-only. La suite OCR incluye 46 casos de límites, estructura, render,
errores, concurrencia, cancelación, cierre del árbol y variables permitidas.
Las llamadas al motor y al cierre se controlan en unitarias; la API incluye
una conversión real de PDF imagen y verifica ausencia de alta y auditoría.
Manuales tras actualizar sus pasos: **26/26**, 3,91 s.

Desde `backend`, con `COVERAGE_FILE` distinto para esta ejecución:

```powershell
uv run python ../tmp/qa-20261010-ocr/entorno.py -m pytest pruebas/unitarias pruebas/api/test_conocimiento_api.py pruebas/api/test_agente_conocimiento_api.py pruebas/integracion/test_conocimiento.py pruebas/integracion/test_rag_fugas.py pruebas/integracion/test_evaluacion_rag.py pruebas/integracion/test_auditoria_append_only.py --cov=app.modulos.conocimiento --cov-report=xml:../tmp/qa-20261010-ocr/cobertura-final.xml --junitxml=../tmp/qa-20261010-ocr/backend-regresion-final.xml -q --tb=short
uv run pytest pruebas/unitarias/test_ayuda_manuales.py -q
```

El auxiliar ignorado dirige todos los accesos a la base exclusiva. No es una
corrida completa de todas las API clínicas ni una evaluación de embeddings reales.

## 8. Frontend

Corrida definitiva tras el ajuste del marco y las lecturas: **890/890**,
109 suites, 104,85 s. Cobertura: 85,93 % sentencias, 73,38 % ramas,
82,07 % funciones y 88,43 %
líneas. Lint y build aprobados. No se reducen umbrales por la ejecución parcial.

```powershell
npm run lint
npm run build
npx ng test --watch=false --coverage
```

Las regresiones nuevas protegen revisión obligatoria, correcciones, reintento,
nombre original, no duplicar extracción/alta, archivo Word y cancelación al
destruir la ventana. El foco pasa al editor; su etiqueta y descripción son explícitas.
La suite del formulario incluye **25/25**, cuatro regresiones de lecturas
obsoletas y fallos de lectura reproducidos antes de la corrección.

## 9. Navegador y diseño

El escenario 31 reconoce el PDF imagen real a 1366×768, 1024×768 y 390×844,
edita el texto, exige revisión, guarda un borrador y comprueba auditoría sin
carga. Axe exige cero infracciones WCAG 2A/AA y 2.1AA en la ventana.
Se comprueban marco, cabecera, pie y ausencia de desplazamiento del contenedor
exterior. El escenario 15 recorre todas las secciones de administración y
plataforma; el 06 comprueba fuente aprobada y respuesta sin respaldo.
No se ejecutan dos instancias Playwright sobre las mismas carpetas de artefactos.

La corrida completa obtuvo **116 aprobadas, dos fallos de escenario y una
omitida**, 22,0 min, sin reintentos. Los fallos corresponden a los supuestos
del escenario 05 (horarios en sábado) y 17 (lectura no concede escritura),
descritos en el punto 11. La omitida de bandeja requería dos hilos de QA:
se prepararon en la misma base exclusiva, sin habilitar integraciones reales.
El cierre de las siete suites afectadas obtuvo **33/33**, 6,8 min, sin
reintentos ni omisiones, con los hilos vigentes/vencidos definidos. Son
**119 casos distintos aprobados entre las dos corridas**; no una corrida
única de 119/119. La repetición incluye ambos fallos corregidos, la bandeja,
OCR y la regresión de ventanas y diseño. Las capturas de escritorio/móvil
se inspeccionaron: cabecera y pie permanecen dentro del marco.

```powershell
$env:URL_API='http://127.0.0.1:8020/api/v1'
npx playwright test --project=chromium
# Tras conservar los artefactos anteriores y preparar los dos hilos sintéticos:
$env:QA_BANDEJA_VIGENTE='<id del hilo sintético vigente>'
$env:QA_BANDEJA_VENCIDA='<id del hilo sintético vencido>'
npx playwright test escenarios/05-demo-operativa.spec.ts escenarios/06-conocimiento.spec.ts escenarios/15-pantallas-trabajo.spec.ts escenarios/17-registros-y-documentos.spec.ts escenarios/20-acceso-formularios.spec.ts escenarios/28-revision-modulos.spec.ts escenarios/31-conocimiento-ocr.spec.ts --project=chromium
```

## 10. Cobertura

Conocimiento: **92,24 %**, sentencias y ramas combinadas en la ejecución
definitiva del backend. Módulo `ocr.py`: **98 %**; proceso `ocr_proceso.py`:
**93 %**. La cobertura se mide desde Windows: las cuatro líneas Linux de
límites de recursos no se contabilizan ejecutadas allí.

El proceso real se ejecutó también en Linux con su virtualenv exclusivo y
Tesseract local: PDF sin capa de texto, dos páginas, reconocimiento de
`HORARIO SINTETICO` y aviso de página 2 vacía. Su memoria virtual/CPU/core dumps
se limitan antes de leer el archivo. Esa comprobación no se suma a la cobertura Windows.

## 11. Incidencias corregidas

PDFium exige cierre explícito de páginas y bitmaps; las pruebas detectaron que
no admiten el mismo context manager que el documento. La auditoría exige una
secuencia y prohíbe la palabra texto en sus claves: se usa `paginas_vacias`
para la cantidad, conservando la protección. El editor tenía el contador
incluido en su nombre accesible: ahora tiene etiqueta/descripción separadas.

La inspección visual reveló scroll interno del marco móvil de hasta 77 px y
cabecera fuera del viewport. Se cambia el marco a `overflow: clip`; el cuerpo
continúa desplazable. El test mide el marco real, no solo la capa de diálogo.
No se relajan las aserciones. Una compilación intermedia detectó delimitadores
de plantilla en un comentario CSS; se corrigieron antes de repetir la verificación.
Una ejecución simultánea de frontend/navegador obtuvo un timeout de preparación
de ListaEspera (10 s) y un 503 del OCR por su límite de motor. Se repite la
verificación secuencial, sin aumentar plazos ni habilitar reintentos. El frontend
definitivo pasó completo; las primeras ejecuciones no se reportan como aprobadas.

La corrida completa de Chromium detectó una aserción que exigía capacidad de
agenda positiva incluso en sábado, cuando la clínica sintética no abre. El
cálculo correcto es capacidad cero y porcentaje no calculable. El escenario 05
comprueba ese estado y conserva las aserciones positivas sobre capacidad,
porcentaje y gráfica accesible en un periodo de siete días. No se inventan
horarios ni se altera la fórmula del producto para satisfacer la prueba.

El escenario 17 encontraba un paciente con tomas mediante lectura compartida
y suponía que eso concedía escritura. La API rechazó correctamente el alta
sin relación asistencial. El recorrido ahora inicia explícitamente la atención
desde la ficha y exige su respuesta 204 antes de emitir cotización/receta.
La guardia clínica, los ámbitos y la separación de especialidades se conservan.

Cuatro regresiones nuevas reprodujeron lecturas de texto que terminaban tarde:
podían sustituir el PDF reconocido o el texto pegado, modificar una ventana
destruida y dejar un rechazo sin mensaje. El formulario identifica cada lectura,
invalida las anteriores al cambiar la fuente y descarta resultados tras el
cierre. Los fallos de lectura conservan un mensaje recuperable, sin detalles
del sistema. La reproducción previa obtuvo 21 aprobadas y cuatro fallos;
la corrida definitiva incluye las cuatro regresiones sin cambiar sus aserciones.

## 12. Secretos y vulnerabilidades

`npm audit`: cero vulnerabilidades en frontend y E2E. `pip-audit` del árbol
bloqueado base y del conjunto dev/LLM: ninguna vulnerabilidad conocida.
El inventario completo del virtualenv del equipo detecta **35 avisos en
Pillow 11.3.0**, del extra opcional `embeddings`: es la excepción E-12 y
ADR-0007 existente, con actualización de fastembed/proveedor alternativo
pendiente. No se instala ni invoca Pillow en el nuevo OCR o la imagen base.
No se declara limpio el conjunto opcional instalado.

Bandit de archivos backend afectados sin hallazgos. Las excepciones B404/B603
se acotan al módulo y llamada subprocess con argv fijo, sin shell y datos en
stdin; no se ocultan hallazgos del resto de la aplicación. Gitleaks del índice
de implementación, correcciones y documentación: ningún secreto detectado,
con salida redactada. Los dos commits de código (`9b26556..6627b4a`) también
pasaron la comprobación antes del commit de documentación.
No se ejecutó una nueva auditoría de la imagen Docker o DAST en este bloque.

## 13. Base de datos y migraciones

No cambia el esquema. La base de QA se migró desde cero hasta 038.
`alembic check`: **No new upgrade operations detected**. El aviso existente
de autogeneración no puede comparar por sí solo la expresión del índice trigram;
no equivale a una verificación completa de ese índice. No se crea un downgrade nuevo.

## 14. Staging y credenciales

OCR no necesita claves de proveedor. Staging debe instalar motor e idiomas,
activar ClamAV, configurar límites y validar calidad con documentos autorizados.
Los proveedores externos y embeddings reales siguen sus pendientes previos.
El equipo local usa `OCR_EJECUCION=wsl`; `.env.example` contiene solo ejemplos.

## 15. Producción y despliegue

Reconstruir backend con el lockfile nuevo y los paquetes Tesseract declarados;
comprobar salud, idiomas, antivirus y un escaneo sintético antes de habilitar
uso. Dimensionar memoria/CPU, límite multipart/proxy y concurrencia por proceso.
Esta ejecución prueba el motor Linux, pero no construyó/desplegó una imagen
nueva ni certifica precisión, carga masiva o aislamiento del sistema operativo.

## 16. Rollback y restauración

Deshabilitar OCR con `OCR_HABILITADO=false` conserva la ingesta convencional.
Revertir el commit de implementación y reconstruir con el lockfile anterior
no requiere revertir el esquema ni eliminar versiones ya guardadas. Los
originales no están archivados en este flujo; conserve su archivo fuente.
Restauración de la base según el procedimiento general de despliegue, sin
operaciones destructivas nuevas para esta función.

## 17. Limpieza y documentación

Se conserva la evidencia ignorada en `tmp/qa-20261010-ocr/` (XML, cobertura,
logs, auditorías, capturas y artefactos de ambas corridas de navegador).
API 8020 detenida, base exclusiva retirada tras comprobar cero conexiones y
estado `eliminada=true`; dos archivos sintéticos del almacén retirados
individualmente con rutas literales verificadas. El revisor automático rechazó
la limpieza recursiva: no se borraron directorios y se usó la eliminación
individual de los dos archivos propios. Aplicación 4200 y API 8000 lista
responden **200**; puerto 8020 libre. El motor local queda instalado para uso.
Manuales de profesional y administración tienen pasos propios, filtrados por
permiso; recepción/asistencia no reciben escritura adicional.

## 18. Pendientes y evaluación

OCR acotado para PDF escaneado, con corrección y aprobación humanas. Pendientes:
calidad de manuscritos/tablas, original archivado, OCR de fotos, conversión
duradera/masiva, cuota por clínica, detección automática de texto oculto,
antivirus operativo de staging y producción, E-12 y aceptación externa.
Se completa este flujo local; no se declara terminado ni listo para producción
el conjunto de ClinicAI. Trabajo local en `main`, sin push.
