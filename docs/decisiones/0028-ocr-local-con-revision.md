# ADR-0028 — OCR local con vista previa revisada

Fecha: 2026-10-10. Estado: implementado y verificado localmente.

## Contexto

La carga PDF existente requiere una capa de texto. Un documento escaneado se
rechaza y obliga a transcribirlo fuera de ClinicAI. Se necesita incorporar
protocolos e instructivos desde la misma interfaz sin nuevas APIs pagadas,
sin publicar resultados inciertos y conservando el control del RAG.

## Decisión

Ofrecer reconocimiento explícito antes del alta o ingesta. PDFium convierte
las páginas visibles y Tesseract reconoce `spa+eng` en la infraestructura
local. Un proceso nuevo por solicitud evita compartir PDFium entre hilos y
permite imponer un plazo total. No se incorpora Pillow: su vulnerabilidad
opcional conocida E-12 sigue fuera del árbol base y del nuevo camino de OCR.

La respuesta es una vista previa editable. El usuario compara y confirma el
texto; modificarlo obliga a confirmarlo nuevamente. Después usa la ingesta de
texto existente, en borrador y con análisis de inyección. La aprobación,
vigencia, sensibilidad y ACL exigidos en SQL permanecen como barreras del RAG.
El endpoint no concede privilegios ni indexa historias de pacientes.

No se añade persistencia ni migración para una vista previa efímera. El
permiso es `conocimiento.cargar`; no existe un documento destino que consultar.
Se audita el actor y clínica efectivos, método y cantidades, sin contenido.
La versión conserva el nombre del archivo y el hash del texto revisado.

## Controles

20 MB, 20 páginas, 8 millones de píxeles/página, 500.000 caracteres y dos
procesos concurrentes por API. Antivirus obligatorio en producción; validación
estructural anterior al motor nativo. Plazos por página y documento, cierre
de recursos y del árbol de procesos, variables del motor permitidas sin
credenciales de la aplicación. Linux añade límites de memoria/CPU y desactiva
core dumps. Windows tiene límites de entrada, píxeles y tiempo; WSL usa
`timeout` dentro de Linux. No hay shell ni ruta de archivo suministrada por el usuario.

## Consecuencias y alternativas

Permite trabajar sin claves externas. Exige instalar y actualizar el motor,
idiomas y PDFium. No garantiza lectura de manuscritos ni conserva maquetación.
El original no se archiva, la vista previa no se reanuda tras cerrar y el
límite de concurrencia es por proceso, no por clínica o clúster.

OCR automático durante la ingesta se descartó porque ocultaría errores antes
de crear el índice. Un proveedor externo exigiría transferencia de documentos,
credenciales y aceptación adicional. La cola duradera queda para documentos
largos y trabajos masivos; este flujo es interactivo y acotado.

## Fuentes primarias

La [documentación de PDFium](https://pypdfium2.readthedocs.io/en/stable/python_api.html)
exige evitar su uso simultáneo entre hilos. La
[documentación de Tesseract](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
describe los idiomas y el motor CLI. El
[manual del ejecutable](https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc)
documenta la entrada/salida por stdin/stdout.

[Operación y límites](../conocimiento-ocr.md).
[Informe](../verificacion-ocr-2026-10-10.md).
