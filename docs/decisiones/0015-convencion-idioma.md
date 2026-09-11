# ADR‑0015 — Convención de idioma del código y la documentación

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

El usuario eligió explícitamente **«todo en español»**, incluyendo identificadores,
tablas y endpoints, no solo la documentación.

Existe un conflicto real con su propia especificación, que fija en inglés un conjunto
concreto de nombres de forma normativa: los estados de cita, de documento y de pago; las
seis tablas `knowledge_*` con sus columnas de metadatos; y los nombres de las
herramientas del agente.

## Decisión

**Regla general — español.** Documentación, textos de interfaz, mensajes al usuario,
comentarios, mensajes de commit, y también identificadores de código, nombres de tablas,
columnas y rutas de la API.

**Identificadores sin diacríticos.** `contrasena`, `ano`, `cancelacion`, `medico`,
`numero`. Aunque Python 3 y PostgreSQL admiten Unicode en identificadores, las tildes y
la `ñ` provocan fricción en terminales, volcados de base de datos, comparaciones de
cadenas y herramientas de terceros. Las tildes sí se usan en documentación y en textos de
interfaz, donde son correctas y visibles para el usuario.

**Excepciones que se mantienen en inglés** porque la especificación las fija y cambiarlas
rompería el contrato acordado:

* Estados: `PENDING`, `HELD`, `CONFIRMED`, `RESCHEDULED`, `CANCELLED`, `COMPLETED`,
  `NO_SHOW`, `DRAFT`, `PENDING_REVIEW`, `APPROVED`, `PUBLISHED`, `ARCHIVED`,
  `PROOF_RECEIVED`, `UNDER_REVIEW`, `REJECTED`, `REFUND_PENDING`.
* Tablas de conocimiento: `knowledge_documents`, `knowledge_chunks`,
  `knowledge_embeddings`, `knowledge_permissions`, `knowledge_versions`,
  `knowledge_ingestion_jobs`, con sus metadatos `clinic_id`, `branch_id`,
  `specialty_id`, `service_id`, `professional_id`, `document_id`, `version`, `status`,
  `effective_from`, `effective_until`, `sensitivity_level`.
* Herramientas del agente: `find_availability`, `hold_slot`, `confirm_appointment`,
  `cancel_appointment`, `reschedule_appointment`, `get_patient_appointments`,
  `handoff_to_human`.
* Lo impuesto por terceros: nombres de Alembic, parámetros de OAuth, campos de los
  payloads de WhatsApp Cloud API, cabeceras HTTP estándar, y la API de Angular y FastAPI.

## Consecuencias

* El modelo de datos queda mixto: la mayoría de tablas en español y seis en inglés. Es
  una inconsistencia visible, asumida a conciencia por respetar la especificación; queda
  documentada aquí para que no se «corrija» por error en el futuro.
* Las opciones de enumeración van en inglés donde la especificación lo fija, mientras que
  el nombre del tipo va en español (`EstadoCita.CONFIRMED`). Cada enumeración incluye una
  función de etiqueta en español para la interfaz.
* Los mensajes de error de la API llevan un código estable en inglés para los clientes
  programáticos y un mensaje en español para las personas.
