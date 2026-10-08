# ADR-0023 — Periodontograma, aprendizaje local y fotografías privadas

Estado: aceptada. Fecha: 2026-10-08.

## Decisión

- El periodontograma pertenece a Odontología/Periodoncia y se abre desde la
  ficha. Registra 32 piezas FDI con seis sitios por pieza. PS y MG son valores
  opcionales; NIC se calcula como PS + MG solo si ambos existen. No se
  sustituyen mediciones ausentes por cero. MG positivo indica posición apical
  y negativo coronal; referencia: [manual de la Universidad de Berna](https://www.periodontalchart-online.com/manual/).
- Cada examen y corrección conserva autor, fecha, sede, cita y versión
  anterior. Corregir o anular exige motivo y crea otra versión; los disparadores
  de PostgreSQL impiden modificar o eliminar las versiones existentes.
- La analítica usa registros autorizados, días completos en la zona de la
  clínica y modelos locales por indicador: media semanal, tendencia lineal y
  suavizado exponencial. Selección y evaluación usan bloques temporales
  diferentes. Se muestra error frente a la referencia, tamaño de muestra y
  limitaciones; sin datos suficientes no hay predicción.
- Los indicadores de estado se capturan al consultar la analítica. La clave
  incluye clínica, actor, permisos y todas las dimensiones del ámbito. No se
  reconstruye un estado histórico que nunca fue observado.
- Las recomendaciones son administrativas y requieren revisión humana.
  Los gráficos no diagnostican ni proponen tratamientos.
- Las fotos opcionales se añaden al formulario y al detalle del registro,
  incluidos registros administrativos. Se valida el contenido real, se
  eliminan metadatos y se cifra el archivo; no existen enlaces públicos.
  Listado, descarga y retirada validan el permiso y ámbito del registro padre.
- Las fotos clínicas siguen los permisos de imágenes e historia, incluidos
  relación asistencial, especialidad y autorización adicional para N3. El
  nivel del ámbito RAG y las ACL siguen controlando las fotos de documentos
  de conocimiento. Superadministración puede gestionar fotos de clínicas,
  sedes y personal entre clínicas; esto no habilita pacientes ajenos.
- Si falla una foto después de crear el registro, el reintento reutiliza su
  identificador y completa la carga. No crea otro registro ni otra versión.

## Consecuencias

Migraciones `032`, `033` y `034`. La cámara nativa depende del dispositivo;
en equipos sin soporte se elige un archivo. Las imágenes adjuntas a Conocimiento
son respaldos privados y no se procesan con OCR ni se incorporan al índice RAG.
Los respaldos de campañas tampoco sustituyen la imagen aprobada que enviará
WhatsApp. El aprendizaje de estados necesita observaciones futuras reales.
