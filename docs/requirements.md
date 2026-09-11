# Requisitos

Catálogo de requisitos con identificador estable. El backlog por fases y los criterios de
aceptación están en [`backlog.md`](backlog.md); el estado de verificación, en
[`production-readiness.md`](production-readiness.md).

Prioridad: **B** bloqueante para operar · **A** alta · **M** media.

---

## RF‑A · Autenticación y usuarios

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑A01 | Inicio de sesión con correo y contraseña | B |
| RF‑A02 | Cierre de sesión con revocación efectiva del token de refresco | B |
| RF‑A03 | Recuperación de contraseña por token de un solo uso, sin revelar si la cuenta existe | B |
| RF‑A04 | Cambio de contraseña con verificación de la actual y revocación de otras sesiones | B |
| RF‑A05 | Verificación de correo electrónico | A |
| RF‑A06 | Expiración de sesión por inactividad y por vida máxima absoluta | B |
| RF‑A07 | Revocación de tokens, individual y por usuario | B |
| RF‑A08 | Segundo factor TOTP, obligatorio en los roles configurados | B |
| RF‑A09 | Bloqueo temporal por intentos fallidos, por cuenta y por IP | B |
| RF‑A10 | Historial de accesos consultable por el propio usuario y por el auditor | A |
| RF‑A11 | Activación y desactivación de usuarios, con revocación inmediata de sesiones | B |

## RF‑B · Roles y permisos

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑B01 | RBAC con permisos granulares `recurso.accion` | B |
| RF‑B02 | Roles base: superadministrador, administrador de clínica, recepción, profesional, asistente, auditor | B |
| RF‑B03 | Ámbito por clínica, sede, especialidad, profesional, paciente y tipo de información | B |
| RF‑B04 | Validación de permiso **y** de ámbito en cada endpoint del backend | B |
| RF‑B05 | Un permiso sin ámbito asignado equivale a alcance nulo | B |
| RF‑B06 | Acceso clínico condicionado a relación asistencial con el paciente | B |
| RF‑B07 | Acceso de emergencia con motivo, plazo, auditoría y notificación | A |
| RF‑B08 | Guards de frontend como mejora de experiencia, nunca como control | B |

## RF‑C · Configuración de la clínica

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑C01 | Gestión de clínicas, sedes y consultorios | B |
| RF‑C02 | Gestión de especialidades y servicios, con duración y precio | B |
| RF‑C03 | Tiempo de preparación entre citas, por servicio y por profesional | B |
| RF‑C04 | Horarios de atención y descansos | B |
| RF‑C05 | Feriados, con opción de recurrencia anual | B |
| RF‑C06 | Vacaciones y bloqueos de agenda | B |
| RF‑C07 | Política de cancelación configurable | A |
| RF‑C08 | Configuración de recordatorios y de sus horarios | B |
| RF‑C09 | Configuración de pagos | A |
| RF‑C10 | Catálogo de mensajes y plantillas aprobadas | B |
| RF‑C11 | Zona horaria configurable, con `America/Guayaquil` por defecto | B |

## RF‑D · Profesionales

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑D01 | Datos del profesional: nombre, especialidad, correo, WhatsApp, sede, registro profesional | B |
| RF‑D02 | Servicios que atiende, con duración y precio propios opcionales | B |
| RF‑D03 | Horario propio y granularidad de turnos | B |
| RF‑D04 | Calendario conectado por OAuth, sin almacenar contraseñas | A |
| RF‑D05 | Tokens de terceros cifrados en reposo | B |
| RF‑D06 | Estado de disponibilidad y aceptación de pacientes nuevos | A |
| RF‑D07 | Configuración propia de recordatorios | M |
| RF‑D08 | Pacientes asignados | A |

## RF‑E · Pacientes

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑E01 | Registro de paciente con documento de identidad | B |
| RF‑E02 | Identificación por WhatsApp para funciones administrativas | A |
| RF‑E03 | **El WhatsApp no es identificación suficiente para datos clínicos**; verificación adicional obligatoria | B |
| RF‑E04 | Contactos, incluido contacto de emergencia | A |
| RF‑E05 | Registro de consentimientos con versión del texto, canal y evidencia | B |
| RF‑E06 | Revocación de consentimiento con efecto inmediato | B |
| RF‑E07 | Historial de citas y profesionales tratantes | A |
| RF‑E08 | Documentos del paciente con validación y análisis de archivo | A |
| RF‑E09 | Alergias y antecedentes, registrados solo por un profesional | B |
| RF‑E10 | Preferencias de horario para la lista de espera | A |

## RF‑F · Historia clínica

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑F01 | Notas de evolución estructuradas | B |
| RF‑F02 | Versionado inmutable con autor, fechas, versión anterior y motivo de modificación | B |
| RF‑F03 | Prohibición de sobrescritura y de borrado | B |
| RF‑F04 | Diagnósticos registrados exclusivamente por el profesional | B |
| RF‑F05 | Indicaciones, exámenes, archivos y seguimientos | A |
| RF‑F06 | Recepción sin acceso automático a información clínica | B |
| RF‑F07 | Nivel de sensibilidad por registro, con control reforzado | A |

## RF‑G · Reservas y agenda

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑G01 | Cálculo de disponibilidad por profesional, servicio y sede | B |
| RF‑G02 | Disponibilidad que respeta duración, preparación, descansos, feriados, vacaciones y bloqueos | B |
| RF‑G03 | Gestión de salas y recursos | A |
| RF‑G04 | Estados `PENDING` `HELD` `CONFIRMED` `RESCHEDULED` `CANCELLED` `COMPLETED` `NO_SHOW` | B |
| RF‑G05 | Bloqueo temporal de turno con expiración automática | B |
| RF‑G06 | **Prevención de doble reserva garantizada por la base de datos** | B |
| RF‑G07 | Idempotencia en creación y modificación | B |
| RF‑G08 | Historial de cambios de cada cita | B |
| RF‑G09 | Citas recurrentes | M |
| RF‑G10 | Zona horaria configurable y almacenamiento en UTC | B |
| RF‑G11 | La agenda interna es la fuente de verdad | B |

## RF‑H · Reservas por WhatsApp

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑H01 | Comprensión de intenciones: reservar, consultar, cancelar, reprogramar, confirmar, precio, ubicación | A |
| RF‑H02 | Herramientas `find_availability`, `hold_slot`, `confirm_appointment`, `cancel_appointment`, `reschedule_appointment`, `get_patient_appointments`, `handoff_to_human` | A |
| RF‑H03 | Solo WhatsApp Business Cloud API; prohibida la automatización de WhatsApp Web | B |
| RF‑H04 | Verificación del webhook y validación de firma | B |
| RF‑H05 | Protección contra mensajes duplicados y fuera de orden | B |
| RF‑H06 | Reintentos y seguimiento de estados de entrega | B |
| RF‑H07 | Registro de conversaciones con minimización de datos | A |
| RF‑H08 | Transferencia a un humano | B |
| RF‑H09 | Opt‑in y opt‑out con efecto inmediato | B |
| RF‑H10 | Plantillas aprobadas para mensajes proactivos | B |

## RF‑I · Sincronización de calendarios

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑I01 | Conexión y desconexión por OAuth | A |
| RF‑I02 | Renovación de tokens y manejo de token vencido | A |
| RF‑I03 | Consulta de disponibilidad externa | A |
| RF‑I04 | Creación, actualización y cancelación de eventos | A |
| RF‑I05 | Relación `appointment_id` · `professional_id` · `calendar_id` · `external_event_id` | B |
| RF‑I06 | Identificación de conflictos y reconciliación de cambios externos | A |
| RF‑I07 | Estado de sincronización y registro de errores | A |
| RF‑I08 | **La indisponibilidad del calendario externo no pierde la cita interna** | B |
| RF‑I09 | Los eventos externos no contienen datos clínicos | B |

## RF‑J · Lista de espera inteligente

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑J01 | Registro en lista de espera con preferencias | A |
| RF‑J02 | Evento de turno liberado al cancelar, en la misma transacción | A |
| RF‑J03 | Selección de candidatos por servicio, profesional, sede, duración y preferencias | A |
| RF‑J04 | **Oferta a un paciente a la vez**, con control de concurrencia | B |
| RF‑J05 | Oferta con fecha, hora, servicio, profesional, sede, tiempo límite y opciones de aceptar o rechazar | A |
| RF‑J06 | Expiración de oferta y paso al siguiente candidato | A |
| RF‑J07 | Reagendamiento al aceptar, con liberación del turno anterior | A |
| RF‑J08 | Cadena de espacios liberados | A |
| RF‑J09 | **Ante aceptación simultánea, un solo ganador y respuesta adecuada al otro** | B |
| RF‑J10 | Actualización de calendarios y aviso a paciente y profesional | A |

## RF‑K · Recordatorios

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑K01 | Confirmación inmediata de la reserva | B |
| RF‑K02 | Recordatorio un día antes y horas antes, con horarios configurables | B |
| RF‑K03 | Avisos de cancelación y de reprogramación | B |
| RF‑K04 | Resumen diario para el profesional | A |
| RF‑K05 | Aviso de cambio de agenda | A |
| RF‑K06 | **Recordatorios persistentes y reintentables** | B |
| RF‑K07 | **Sin diagnósticos ni datos clínicos en las notificaciones** | B |

## RF‑L · Recetas y medicamentos

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑L01 | Creación de receta por el profesional, con medicamento, dosis, unidad, vía, frecuencia, horarios, inicio, fin e instrucciones | B |
| RF‑L02 | **Solo una receta confirmada genera calendario de tomas** | B |
| RF‑L03 | Programación de recordatorios de toma | B |
| RF‑L04 | Respuestas del paciente: tomé, recordarme después, no pude, tengo un problema, hablar con la clínica | B |
| RF‑L05 | Registro de adherencia | B |
| RF‑L06 | Alertas al personal autorizado por toma omitida o problema reportado | B |
| RF‑L07 | **La IA no crea ni modifica recetas, dosis ni tratamientos, no suspende medicación, no sugiere duplicar tomas, no interpreta reacciones y no diagnostica** | B |
| RF‑L08 | **Los medicamentos «cuando sea necesario» no se convierten en horarios fijos sin confirmación profesional** | B |
| RF‑L09 | Al cambiar una receta, se cancelan o ajustan los recordatorios futuros y se conserva el historial | B |
| RF‑L10 | Derivación a personal ante un problema reportado | B |

## RF‑M · Base de conocimiento

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑M01 | Carga de PDF, documentos y texto manual | A |
| RF‑M02 | Versionado, etiquetas, especialidad, sede, servicio y vigencia | A |
| RF‑M03 | Estados `DRAFT` `PENDING_REVIEW` `APPROVED` `PUBLISHED` `ARCHIVED` | A |
| RF‑M04 | Responsable del documento y registro de la aprobación | A |
| RF‑M05 | **Solo documentos aprobados y vigentes son utilizables por el agente** | B |
| RF‑M06 | Contenido limitado a materia administrativa y protocolos aprobados | B |
| RF‑M07 | **La historia clínica individual no se indexa en una base vectorial global** | B |

## RF‑N · PostgreSQL y pgvector

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑N01 | Tablas `knowledge_documents`, `knowledge_chunks`, `knowledge_embeddings`, `knowledge_permissions`, `knowledge_versions`, `knowledge_ingestion_jobs` | A |
| RF‑N02 | Metadatos de fragmento: `clinic_id`, `branch_id`, `specialty_id`, `service_id`, `professional_id`, `document_id`, `version`, `status`, `effective_from`, `effective_until`, `sensitivity_level` | A |
| RF‑N03 | Búsqueda híbrida semántica y textual | A |
| RF‑N04 | Filtros por permisos, especialidad, sede y vigencia | B |

## RF‑O · RAG

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑O01 | Clasificación de intención y enrutado a la fuente adecuada | A |
| RF‑O02 | Aplicación de permisos antes de recuperar | B |
| RF‑O03 | Verificación de vigencia | B |
| RF‑O04 | Respuesta fundamentada con registro de las fuentes usadas | A |
| RF‑O05 | Derivación a humano ante información insuficiente | B |
| RF‑O06 | **«No tengo información aprobada» cuando no hay fuente confiable** | B |
| RF‑O07 | **Contenido de documentos tratado como dato, no como instrucción** | B |
| RF‑O08 | Evaluación con Hit@K, precisión, fundamentación, respuestas sin fuente, resistencia a documentos maliciosos, fugas entre pacientes y entre especialidades, uso de documentos archivados y vencidos | B |
| RF‑O09 | Memoria de paciente aislada y protegida | B |

## RF‑P · Pagos

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑P01 | Pago asistido con precio, método, estado, enlace, comprobante, fecha y comentarios | A |
| RF‑P02 | Estados `PENDING` `PROOF_RECEIVED` `UNDER_REVIEW` `CONFIRMED` `REJECTED` `REFUND_PENDING` | A |
| RF‑P03 | Validación manual con registro del validador | A |
| RF‑P04 | **Sin almacenar tarjetas, claves, OTP ni credenciales financieras** | B |
| RF‑P05 | Auditoría de cambios de estado | A |

## RF‑Q · Dashboard

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑Q01 | Filtros por fecha, sede, especialidad, profesional, servicio y estado | A |
| RF‑Q02 | Métricas de citas: totales, confirmadas, canceladas, reprogramadas, inasistencias, ocupación | A |
| RF‑Q03 | Métricas de lista de espera: turnos liberados, recuperados, tiempo para llenar una cancelación | A |
| RF‑Q04 | Métricas de pacientes: nuevos y recurrentes | A |
| RF‑Q05 | Métricas económicas: pagos pendientes e ingresos | A |
| RF‑Q06 | Métricas de adherencia: tomas confirmadas, omitidas, adherencia y seguimientos pendientes | A |

## RF‑R · Predicciones

| ID | Requisito | Pri |
|---|---|:-:|
| RF‑R01 | Predicción de demanda | M |
| RF‑R02 | Probabilidad de cancelación e inasistencia | M |
| RF‑R03 | Probabilidad de llenar un turno liberado | M |
| RF‑R04 | Predicción de baja adherencia | M |
| RF‑R05 | Recomendación de apertura de horarios | M |
| RF‑R06 | Registro de modelo, versión, fecha, variables, resultado, confianza, explicación y quién consultó | A |
| RF‑R07 | **Las predicciones no cambian tratamientos, no niegan atención y no clasifican negativamente a pacientes** | B |

---

## Requisitos no funcionales

| ID | Requisito | Objetivo |
|---|---|---|
| RNF‑01 | Latencia de consulta de disponibilidad | P95 < 500 ms |
| RNF‑02 | Latencia de creación de cita | P95 < 800 ms |
| RNF‑03 | Latencia de búsqueda RAG | P95 < 2 s |
| RNF‑04 | Latencia del dashboard | P95 < 1,5 s |
| RNF‑05 | Reservas concurrentes sin duplicados | 0 duplicados bajo la carga probada |
| RNF‑06 | Cobertura de pruebas | backend ≥ 80 %, frontend ≥ 70 % |
| RNF‑07 | Accesibilidad | WCAG 2.2 AA |
| RNF‑08 | TypeScript estricto y `mypy` estricto | sin errores |
| RNF‑09 | Sin vulnerabilidad crítica o alta sin justificación y plan | 0 pendientes |
| RNF‑10 | Sin secretos en el repositorio | `gitleaks` limpio |
| RNF‑11 | Migraciones reversibles | `upgrade` y `downgrade` verificados |
| RNF‑12 | Respaldos restaurables | restauración verificada, no solo generada |
| RNF‑13 | PWA instalable y usable con conectividad intermitente | lectura en caché |
| RNF‑14 | Logs sin datos personales ni clínicos | prueba dedicada |
| RNF‑15 | Recuperación ante caída de Redis, PostgreSQL, WhatsApp, calendario o LLM sin pérdida de datos | pruebas de recuperación |
