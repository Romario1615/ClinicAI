# Plan — Módulo dental e imágenes clínicas

Estado: **fases A–H implementadas con las limitaciones declaradas** · Actualizado: 2026-10-05

Decisiones tomadas con la persona responsable:

* Las imágenes de pacientes se guardan en **MinIO (compatible S3)**, en el Docker existente.
  En producción se cambia a S3/R2 por configuración, sin tocar código.
* Primera entrega dental: **odontograma, galería de imágenes, plan de tratamiento y selección
  de consultorio**.
* Además (pedido posterior): **promociones por WhatsApp con imágenes generadas por IA**,
  **seguimiento de tratamientos por chat** y **Jev (TypeSafe AI)** como modelo de decisión
  del agente.

### Actualización del alcance del producto (2026-10-05)

La presentación de referencia de Odontozen amplía el objetivo del producto: ortodoncia,
endodoncia, periodoncia y armonización facial ya no se consideran fuera de alcance. Se
implementarán después de estabilizar los flujos compartidos de odontograma, imágenes,
tratamientos, consentimiento y permisos. Esta ampliación es una hoja de ruta, no evidencia de
que esos módulos estén implementados.

La presentación es solo una referencia funcional y visual. No copiar su marca, textos, precios,
estadísticas, testimonios ni ejemplos de pacientes; los detalles y estados de cobertura están
en la sección «Cobertura funcional tomada de la presentación de referencia» de `README.md`.

### Decisión de almacenamiento (ajuste sobre la propuesta inicial)

Las imágenes se **cifran en la aplicación** (AES‑GCM, la misma primitiva de
`CifradorDatos`) antes de llegar a MinIO, y se **descargan siempre a través del API**, no con
URLs firmadas. Motivo: con URL firmada la descarga no pasa por el backend y no queda en
auditoría quién la vio; con el proxy cada visualización deja su entrada. MinIO ve solo bytes
cifrados.

---

## Reglas que aplican (CLAUDE.md)

* Imágenes, odontograma y plan son **N2 · Clínico**. Recepción no los ve.
* Toda lectura y escritura queda en auditoría. Cada descarga de imagen también.
* El odontograma y el plan son **append-only con versiones**: no se borra historia clínica.
* **La IA no lee ni modifica** odontograma, plan ni imágenes. No hay herramienta del agente
  para nada de esto.
* Solo datos sintéticos en semillas y pruebas. Las imágenes de prueba se generan por código
  (no fotos reales).

---

## Fase A — Selección de consultorio · Implementada

1. Se reutiliza `GET /catalogo/consultorios`; la ocupación se calcula en la agenda con las
   citas de **toda la sede**, no solo las del profesional filtrado.
2. Agenda: tablero de consultorios (franja 07:00–21:00, libre/ocupado ahora, próxima cita) y
   selector de sala al reservar; las salas ocupadas a esa hora se ven pero no se eligen.
3. Backend: el consultorio debe ser de la sede de la cita (antes no se validaba: una sala de
   otra sede o clínica quedaba grabada). Pruebas: sala de la sede → 201, de otra sede o
   inexistente → 404, inactiva → 422. El choque lo sigue resolviendo la restricción `gist`.
4. **Implementado:** al reprogramar, la interfaz ofrece salas libres en el nuevo horario,
   advierte si la sala actual ya está ocupada y permite cambiarla. La API valida que la sala
   pertenezca a la sede; pruebas de componente y API cubren el cambio.

## Fase B — Almacén de archivos clínicos · Parcial

1. `app/nucleo/almacen.py` provee adaptador de objetos local/S3; `infra/compose` debe
   completar MinIO persistente y el bucket privado antes del despliegue.
2. Las imágenes se cifran en la aplicación con AES-GCM antes del almacenamiento y se
   descargan por el API; no se entregan URLs firmadas. El navegador nunca recibe la clave.
3. Validación del archivo **por contenido** (firma mágica), no por extensión: JPEG, PNG,
   WebP, DICOM. Tamaño máximo configurable. Se eliminan metadatos EXIF (ubicación).
4. Antivirus (clamd) como adaptador: en desarrollo se registra «no disponible» y se declara.
5. Tabla `imagen_paciente`: paciente, tipo (`PERFIL`, `RADIOGRAFIA_PERIAPICAL`,
   `RADIOGRAFIA_PANORAMICA`, `FOTO_INTRAORAL`, `FOTO_EXTRAORAL`, `OTRA`), piezas asociadas,
   fecha de toma, autor, hash SHA‑256, clave del objeto. Anulación lógica, nunca borrado.

El saneamiento de imágenes, el cifrado contextual y el adaptador de almacén existen en
backend. El API ofrece carga, galería por paciente/tipo/pieza, descarga autorizada y auditada,
anulación lógica y foto de perfil; el ciclo tiene pruebas HTTP. En desarrollo sin ClamAV la
carga registra `NO_DISPONIBLE`; en producción se rechaza si el antivirus no está habilitado.
La ficha ya integra foto de perfil y galería autenticada; el E2E verifica carga, cifrado y
visualización con un PNG válido. En producción aún se debe configurar ClamAV y el almacén
MinIO/S3 del entorno.

## Fase C — Ficha del paciente con imágenes · En curso

1. Implementado: foto de perfil en la ficha, cargada con autorización desde la API.
2. Implementado: galería por paciente, filtros por tipo y pieza, carga y vista previa autenticada.
3. Implementado: E2E que confirma carga, lectura cifrada y metadatos de pieza/tipo.
4. Implementado: botones visibles «Subir foto» y «Tomar foto» (cámara en tableta o teléfono)
   en la ficha y en la cabecera de la historia clínica.
5. Implementado: fotos por procedimiento del plan («Fotos del tratamiento»): la imagen se liga
   con `procedimiento_id` (migración `20261006_002`); el servidor exige que el procedimiento
   pertenezca a un plan del mismo paciente y clínica, si no responde 404.
6. Pendiente: carga por arrastre, ClamAV operativo y almacén MinIO/S3 configurado para
   despliegue.

## Fase D — Odontograma · API e interfaz inicial implementadas

1. API con notación **FDI**, validación de dentición permanente, temporal y mixta, y versiones
   completas auditadas, inmutables y con motivo para cada corrección.
2. Odontograma interactivo: cada pieza se dibuja con sus cinco caras clicables (vestibular
   arriba en la arcada superior y abajo en la inferior; mesial siempre hacia la línea media)
   y una paleta tipo pincel con los hallazgos de cara y de pieza. Pintar solo cambia un
   borrador; se guarda todo junto como versión nueva con motivo.
3. Panel por pieza: registro (estado, hallazgos por cara, nota) e **historial de la pieza**:
   versiones en que cambió con fecha, motivo y nota, procedimientos del plan que la afectan y
   sus fotos, con carga directa etiquetada con la pieza.
4. Pendiente: ampliar el vocabulario dental (movilidad, recesión, supernumerarios), navegación
   de caras por teclado (hoy el teclado usa el número de la pieza y el formulario) y E2E del
   pintado. La fase dental todavía no está completa.

## Fase E — Plan de tratamiento · Ciclo completo implementado

1. API e interfaz permiten crear borradores con procedimientos por pieza/cara, fases e importe
   estimado; FDI, moneda y orden se validan. Lecturas y cambios quedan auditados.
2. El profesional responsable puede proponer el borrador. El estado visible aclara que falta
   registrar la aceptación del paciente; todavía no se permite completar procedimientos.
3. La autenticación actual identifica personal clínico, no al paciente. Antes de registrar su
   aceptación se necesita una identidad de paciente verificada y una constancia trazable; una
   acción del profesional no debe presentarse como firma o aceptación digital del paciente.
4. **Implementado:** registrar la aceptación como constancia de un documento firmado en la
   clínica (medio + referencia + escaneo opcional), exigida por `CHECK`; no se presenta como
   firma digital. Completar procedimientos (solo plan aceptado) con resultado opcional que
   crea una versión nueva del odontograma ligada al procedimiento; cancelar procedimientos y
   planes con motivo; cierre automático del plan. El profesional puede proponer una fecha de
   control posterior al completar un procedimiento y registrarlo como atendido con nota y
   auditoría. La fecha la elige el profesional; el sistema no prescribe intervalos ni envía
   mensajes al paciente. API, restricción PostgreSQL y recorrido E2E verificados.
5. **Implementado:** plantillas editables por clínica. Para cada procedimiento de la siguiente
   fase pendiente, el plan ofrece agendarlo por separado. La cita conserva el paciente
   preseleccionado y el API valida que el plan esté aceptado, el procedimiento pendiente,
   paciente y clínica coincidan y, si se definió, también el servicio. El vínculo se guarda
   junto con la reserva bajo bloqueo transaccional; una fase no admite dos citas activas.
   Cancelar esa cita libera el vínculo en la misma transacción para permitir reagendar. El
   flujo tiene pruebas de API y E2E.

---

## Fase F — Promociones por WhatsApp · Implementada (sandbox)

1. Campañas: nombre, imagen, texto, plantilla de WhatsApp aprobada, segmento, fecha de envío.
2. Imagen: subida manual **o** generada por un modelo de imágenes vía API (adaptador con
   proveedor configurable; sin credencial se usa el adaptador sandbox y se declara).
   La persona elige y aprueba la imagen antes de enviar: la IA propone, no publica.
3. Solo a pacientes con **consentimiento de marketing** vigente; baja con «BAJA» por chat.
4. Segmentos solo con datos administrativos (sede, última visita, servicio administrativo).
   **Nunca** segmentación por diagnóstico o tratamiento: sería tratar datos clínicos con fines
   comerciales sin consentimiento específico.
5. Envío por plantilla de marketing aprobada por Meta con cabecera de imagen; ritmo limitado.

Estado: módulo `promociones` (borrador → aprobada → enviada/cancelada), consentimiento
`PROMOCIONES` separado, `BAJA PROMOCIONES` por chat, envío por el outbox con deduplicación,
generador de imágenes con sandbox y adaptador compatible con OpenAI, pantalla «Promociones»
con vista previa tipo chat. Sin verificar contra Meta ni contra el proveedor de imágenes
(E‑28, E‑30).

## Historia clínica integrada · Implementada

La historia clínica muestra la foto del paciente y se organiza en pestañas según permisos:
Evolución (notas SOAP con alta y corrección versionada desde la interfaz), Odontograma,
Periodoncia (índice de placa de O'Leary con serie histórica), Imágenes y radiografías
(galería con visor y comparación), Planes de tratamiento y Recetas. En Configuración, los
administradores pueden diseñar y publicar plantillas versionadas de anamnesis por clínica;
el profesional abre esos formularios a demanda desde el resumen previo a consulta.

El resumen previo a la consulta también permite al profesional vinculado registrar alergias
(sustancia, reacción observada y severidad) y antecedentes por categoría. El servidor valida
permiso, clínica, ámbito y relación asistencial; rechaza duplicados activos de alergia. Desactivar
una alergia exige motivo y conserva el registro. Las altas y desactivaciones se auditan sin copiar
sustancias ni descripciones a los metadatos. Las respuestas de anamnesis se guardan inmutables
contra la versión de preguntas utilizada; N3 exige permiso sensible y se filtra según acceso.
Estos formularios propios no sustituyen el Formulario oficial MSP 033, cuya versión vigente debe
confirmarse antes de implementar su PDF trazable.

Corrección de seguridad asociada: el autor de una nota es el profesional de la sesión; el
cliente ya no puede firmar a nombre de otro.

Firma de recetas (decidido 2026-10-05): **delegación registrada**. Un profesional firma por
otro solo con una delegación vigente creada por administración (pantalla «Delegaciones de
firma»), con vigencia y motivo; se audita como firma delegada. Recetas: alta en borrador y
confirmación desde la pestaña Recetas de la historia clínica.

## Fase G — Seguimiento de tratamientos por chat · Implementada (ajustada)

1. El paciente consulta por WhatsApp sus próximas citas y la fase siguiente de su plan
   («tiene pendiente la fase 2; ¿agendamos?»), sin nombrar diagnóstico ni procedimiento
   clínico en el mensaje (regla 10).
2. Recordatorio para agendar la siguiente fase cuando la anterior se completa.
3. Cualquier pregunta clínica deriva a `handoff_to_human`.

Ajuste de seguridad: la IA **no** lee el plan (N2; reglas 4 y 5). El punto 1 queda como
etiqueta en la derivación («pregunta por la siguiente fase»), y el punto 2 lo hace código
determinista: al cerrar una fase con otras pendientes se encola un recordatorio genérico
(`SEGUIMIENTO_TRATAMIENTO`) que no nombra tratamiento ni pieza (E‑34).

## Fase H — Jev como modelo de decisión del agente · Implementada (sin clave real)

Jev (TypeSafe AI) devuelve decisiones tipadas con probabilidad (`choice`, `score`, `noul`), no
texto. Uso:

1. **Enrutar el mensaje entrante** antes del LLM: intención (reservar, consultar cita,
   cancelar, reprogramar, pregunta informativa, seguimiento, baja de promociones, otro).
2. **Detectar pregunta clínica o urgencia** (`noul`) → derivación obligatoria a humano, como
   segunda barrera además de las reglas actuales.
3. Con confianza alta, las intenciones simples se resuelven con código determinista (consultar
   citas, baja de promociones) sin llamar al LLM. Con confianza baja, decide el LLM.
4. Jev **no ejecuta** nada en la base de datos: decide; el código de servicios ejecuta con
   permisos, validación y auditoría (regla 4).
5. Sin `TYPESAFE_API_KEY` se usa un clasificador sandbox por reglas y se declara.

## Permisos nuevos (se añaden a `docs/security.md`)

| Permiso | Uso |
|---|---|
| `imagen_clinica.leer` | Ver galería y descargar imágenes |
| `imagen_clinica.cargar` | Subir imágenes |
| `paciente.foto_gestionar` | Cambiar la foto de perfil |
| `odontograma.leer` / `odontograma.escribir` | Odontograma |
| `plan_tratamiento.leer` / `plan_tratamiento.escribir` | Plan de tratamiento |

## Credenciales y dependencias pendientes

* MinIO: credenciales solo por variable de entorno (`ALMACEN_*`). `.env.example` sin valores.
* clamd: ausente en desarrollo; obligatorio antes de producción y para analizar cargas de archivo.
* La base de conocimiento ya extrae PDF con texto seleccionable en el servidor (backlog 6.2).
  OCR para escaneos y extracción DOCX siguen pendientes; producción exige ClamAV.
