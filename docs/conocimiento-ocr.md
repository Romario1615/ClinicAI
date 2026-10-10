# PDF escaneados en la base de conocimiento

## Desde la interfaz

Requiere `conocimiento.cargar`. En **Conocimiento → Cargar documento**:

1. Seleccione el PDF. Para un PDF con texto o un Word (.docx) puede usar la carga directa.
2. Si es un escaneo, pulse **Reconocer texto del escaneo**.
3. Revise **Contenido** contra el original. Corrija cifras, palabras y el orden
   de las tablas. El aviso identifica las páginas en las que no se reconoció texto.
4. Marque **He comparado y corregido el texto con el documento original**.
   Otra edición desmarca esa confirmación.
5. Guarde. La vista previa no creó un documento: el alta y la ingesta ocurren ahora.
6. Envíe el borrador al circuito habitual de revisión y aprobación.

El OCR no publica documentos ni concede permisos. Solo documentos aprobados o
publicados, vigentes y dentro del ámbito/ACL del solicitante pueden responder
consultas. La base de conocimiento admite documentación de la clínica; las
historias individuales de pacientes no pertenecen a este índice.

La ventana conserva su pie de acciones al desplazar el formulario y admite
escritorio, tableta y móvil. Un fallo del motor conserva el PDF para reintentar.
La ingesta conserva sus reintentos y el tratamiento de fotos pendientes.

## Motor y límites

PDFium renderiza todas las páginas a 180 dpi y Tesseract reconoce español e
inglés. No utiliza LLM, credenciales externas, Pillow ni NumPy. El PDF se
transmite al backend de ClinicAI; no se envía a un servicio externo de OCR.

| Límite | Valor |
|---|---|
| Tamaño | 20 MB, o menos si `MAX_TAMANO_ARCHIVO_MB` es menor |
| Páginas | 1–20; configurable hacia abajo |
| Renderizado | Máximo 8 millones de píxeles por página |
| Texto | 500.000 caracteres |
| Motor por página | 15 segundos; margen de cierre del cliente de 2 segundos |
| Proceso completo | 90 segundos por defecto; configurable entre 15 y 120 |
| Concurrencia | 2 conversiones por proceso de API; el exceso recibe 503 para reintentar |
| Linux | 1 GiB de memoria virtual, 120 segundos de CPU; sin core dumps |

PDFium no es seguro para uso simultáneo desde hilos. Cada solicitud utiliza un
proceso nuevo. Se cierran explícitamente documento, páginas y bitmaps. El
proceso recibe variables del sistema permitidas, sin credenciales de BD,
OAuth, JWT o proveedores. Usa pipes y argumentos estructurados, sin shell.
Tiempos agotados y cancelaciones terminan el árbol propio del proceso.

En Windows no se aplica `RLIMIT_AS`; siguen los límites de bytes, páginas,
píxeles y tiempo. En modo WSL, el `timeout` Linux limita el OCR por página
incluso si su lanzador Windows se cierra; puede tardar hasta 15 segundos en terminar.
Este aislamiento de procesos no constituye un sandbox de seguridad del sistema operativo.

Antes del renderizado se analiza el archivo con el antivirus configurado y se
rechazan PDF cifrados, estructuras dañadas, acciones activas y adjuntos. En
producción el antivirus es obligatorio; desarrollo sin ClamAV devuelve
`NO_DISPONIBLE`, que no acredita un análisis limpio.

El original y las imágenes renderizadas no se guardan por la aplicación. La
ingesta guarda el texto revisado, el nombre del archivo y la versión habitual;
su hash corresponde al texto ingerido. El circuito previo a completar una
ingesta conserva temporalmente ese texto según su mecanismo de recuperación.
La auditoría de extracción registra método, cantidades y estado antivirus,
sin texto, nombre del archivo ni datos clínicos.

## Configuración y despliegue

La imagen `infra/docker/Dockerfile.backend` instala Tesseract y sus idiomas.
Después de cambiar dependencias, reconstruya la imagen y compruebe su salud.

```dotenv
OCR_HABILITADO=true
OCR_EJECUCION=local
OCR_MAX_PAGINAS=20
OCR_TIEMPO_MAXIMO_SEGUNDOS=90
```

En Linux fuera del contenedor, instale `tesseract-ocr`, `tesseract-ocr-spa` y
`tesseract-ocr-eng` con el gestor de paquetes de su distribución. Compruebe
`tesseract --list-langs`: debe mostrar `spa` y `eng`.

En el entorno Windows de este proyecto:

```powershell
wsl -d clinica -u root --exec apt-get update
wsl -d clinica -u root --exec apt-get install -y tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng
wsl -d clinica --exec tesseract --list-langs
```

```dotenv
OCR_EJECUCION=wsl
OCR_DISTRIBUCION_WSL=clinica
```

Instale las dependencias Python con `uv sync --frozen` y reinicie la API tras
cambiar configuración. El equipo local quedó configurado para WSL; ningún
secreto se añade a `.env.example`. Una instalación sin el motor o los idiomas
muestra un error recuperable, conservando el archivo. Puede deshabilitar el
OCR con `OCR_HABILITADO=false`; las cargas de texto, PDF con texto y DOCX siguen funcionando.

## Contrato HTTP

`POST /api/v1/conocimiento/extraer-escaneo`, multipart `archivo`, exige
`conocimiento.cargar`. Responde con `contenido`, `metodo=OCR_LOCAL`, `paginas`,
`paginas_sin_texto`, `requiere_revision_humana=true` y `escaneo_antivirus`.
No consulta documentos por ID ni acepta una clínica destino. El actor y la
clínica de la auditoría se derivan de la sesión. No crea documentos, versiones
ni embeddings. Por ello no necesita una clave de idempotencia de escritura.

Errores: 401 sin sesión, 403 sin permiso, 413 por tamaño, 415 por archivo no
admitido y 503 por motor desactivado, ocupado, ausente o plazo agotado. La
confirmación humana de la vista previa es un control de interfaz; la barrera
de uso por el agente sigue siendo la aprobación y el ACL en el backend.

## Límites funcionales

No hay garantía de precisión: manuscritos, escaneos borrosos, columnas y tablas
complejas necesitan corrección. No se reconstruye el diseño ni se calcula
confianza clínica. No se procesan fotos adjuntas mediante OCR, ni imágenes
independientes o escaneos DOCX. No hay cola duradera para conversión, caché de
vista previa, original archivado o comprobación automática del texto oculto
en la carga directa. No equivale a validación clínica ni a una certificación.

[Decisión técnica](decisiones/0028-ocr-local-con-revision.md).
[Evidencia](verificacion-ocr-2026-10-10.md).
