# ADR-0024 — Agente limitado al paciente de la ficha

Estado: aceptada. Fecha: 2026-10-08.

## Decisión

La ficha incorpora **Agente del paciente** junto al historial. Reutiliza el
flujo de WhatsApp y sus ocho herramientas, con la identidad del operador y
sus permisos efectivos. El servidor fija el paciente de la ruta y conserva
los demás filtros: clínica, sede, especialidad, profesional y sensibilidad.
Ni el mensaje ni una respuesta del modelo pueden ampliar ese contexto.

Las sesiones duran dos horas, pertenecen a un operador y un paciente y guardan
una huella de autorización. Un cambio de accesos obliga a abrir otra sesión.
Las herramientas leen mediante repositorios y escriben mediante los servicios
existentes. Reservar, confirmar, cancelar o reprogramar prepara primero una
propuesta de cinco minutos. **Confirmar acción** vuelve a validar datos,
permisos y disponibilidad antes de ejecutarla. **Descartar** no modifica la
cita. Solo se aceptan los horarios ofrecidos por el servidor y la cita
seleccionada dentro de esa ficha.

Una ficha abierta desde Pacientes no selecciona una cita por su cuenta.
**Mis citas → Usar esta cita** establece el contexto; sin selección, el agente
explica ese paso y no prepara una escritura ni deriva automáticamente.
Después de cancelar, deja de mostrar esa cita como seleccionada.

El resumen clínico se calcula localmente mediante el asistente autorizado,
con relación asistencial, filtros de autor/especialidad y auditoría. No se
envía al LLM ni se guarda su contenido en la caché de idempotencia. Los
protocolos consultan documentos aprobados y vigentes según sus ACL. El agente
no prescribe, diagnostica ni altera notas, medicamentos o tratamientos.

Abrir, enviar mensajes y confirmar usan `Idempotency-Key`. Las salidas son
esquemas explícitos; no se presenta JSON ni identificadores técnicos al usuario.
La interfaz permite reintentar una petición fallida conservando su clave.

## Consecuencias

Migración `035`: `sesion_agente_paciente`. No duplica conversaciones de WhatsApp,
ni comparte el historial privado con el índice de conocimiento. Sin API
conversacional configurada, **Funciones locales** ofrece consultas y operaciones
reales con botones/reglas. El lenguaje libre depende del proveedor configurado
por la clínica. Los envíos externos siguen usando el canal y consentimientos
existentes; el modo sandbox no confirma entrega real.

Cada uno de los seis manuales de Ayuda tiene instrucciones propias para este
panel. Los roles personalizados reciben la sección según sus permisos.
