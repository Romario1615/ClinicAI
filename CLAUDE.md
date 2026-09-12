# CLAUDE.md — Guía de trabajo en este repositorio

Instrucciones para cualquier agente o persona que modifique este proyecto.
Se asume leído el [`README.md`](README.md) y [`docs/architecture.md`](docs/architecture.md).

---

## 1. Reglas no negociables

Estas reglas protegen datos clínicos. No se relajan por conveniencia, rapidez ni por
petición de "solo para probar".

1. **Nunca** datos reales de pacientes en desarrollo, pruebas, semillas, fixtures,
   ejemplos de documentación ni capturas. Solo datos sintéticos.
2. **Nunca** secretos en el código, en las pruebas, en la documentación ni en el
   historial de Git. Todo secreto entra por variable de entorno.
   `.env.example` no contiene un solo valor real.
3. **Nunca** inventar credenciales, números de WhatsApp, identificadores de calendario,
   nombres de medicamentos aplicados a un paciente concreto ni datos clínicos.
   Si falta una credencial externa, se usa el adaptador sandbox y se declara.
4. **La IA no escribe en la base de datos.** El agente solo invoca las herramientas de
   `backend/app/ia/herramientas/`, que pasan por la capa de servicios con el principal y
   el ámbito del solicitante, validan la entrada y registran auditoría.
5. **La IA no toma decisiones clínicas.** No crea ni modifica recetas, dosis, vías,
   frecuencias ni tratamientos; no suspende medicamentos; no sugiere duplicar una toma;
   no interpreta reacciones adversas; no diagnostica. Todo eso deriva a
   `handoff_to_human`. Hay pruebas que lo verifican; no se desactivan.
6. **No borrar historia clínica.** Las notas son append‑only: se versiona y se conserva
   autor, fecha de creación, fecha de modificación, versión anterior y motivo del cambio.
7. **Autorización en el backend, siempre.** Un guard del frontend no es un control de
   seguridad. Cada endpoint declara su permiso y cada consulta aplica el filtro de ámbito.
8. **No declarar terminado lo que no está probado.** Ni "seguro", ni "100 %", ni "sin
   riesgos". Se reporta la evidencia de la ejecución real de las pruebas.
9. **No automatizar WhatsApp Web** ni ninguna técnica contraria a las políticas de
   WhatsApp. Solo WhatsApp Business Cloud API con firma validada y plantillas aprobadas.
10. **Notificaciones sin datos clínicos.** Ningún recordatorio, plantilla o notificación
    push incluye diagnóstico, medicamento ni motivo de consulta.
11. Ante una ambigüedad que **afecte la seguridad clínica**: detener esa parte y
    preguntar. Ante una ambigüedad que no bloquea: decidir de forma segura, documentar el
    supuesto en el ADR correspondiente y continuar.
12. No se ejecutan comandos destructivos, no se borran archivos ajenos a la tarea y no se
    sobrescriben cambios existentes sin revisarlos.

---

## 2. Convenciones de idioma

| Elemento | Idioma |
|---|---|
| Documentación, comentarios, mensajes de commit | Español |
| Textos de interfaz y mensajes al usuario final | Español |
| Identificadores, tablas, columnas, endpoints | Español **sin diacríticos** (`paciente`, `medico`, `historia_clinica`) |

**Excepciones** (fijadas por la especificación o por librerías externas; no traducir):

* Estados: `PENDING`, `HELD`, `CONFIRMED`, `RESCHEDULED`, `CANCELLED`, `COMPLETED`,
  `NO_SHOW`, `DRAFT`, `PENDING_REVIEW`, `APPROVED`, `PUBLISHED`, `ARCHIVED`,
  `PROOF_RECEIVED`, `UNDER_REVIEW`, `REJECTED`, `REFUND_PENDING`.
* Tablas de conocimiento y sus metadatos: `knowledge_documents`, `knowledge_chunks`,
  `knowledge_embeddings`, `knowledge_permissions`, `knowledge_versions`,
  `knowledge_ingestion_jobs`, con columnas `clinic_id`, `branch_id`, `specialty_id`,
  `service_id`, `professional_id`, `document_id`, `version`, `status`, `effective_from`,
  `effective_until`, `sensitivity_level`.
* Herramientas del agente: `find_availability`, `hold_slot`, `confirm_appointment`,
  `cancel_appointment`, `reschedule_appointment`, `get_patient_appointments`,
  `handoff_to_human`.
* Nombres impuestos por Alembic, OAuth, la API de WhatsApp y cabeceras HTTP estándar.

Sin tildes ni `ñ` en identificadores de código y base de datos: `contrasena`, `ano`,
`cancelacion`. Sí en documentación y textos de interfaz.

---

## 3. Comandos habituales

```powershell
# Infraestructura de datos (WSL2 + Docker). Ver docs/deployment.md
.\infra\scripts\infra-arriba.ps1
.\infra\scripts\infra-abajo.ps1

# Backend
cd backend
uv sync                                  # instalar dependencias desde uv.lock
uv run uvicorn app.main:crear_aplicacion --factory --reload
uv run arq app.tareas.worker.ConfiguracionWorker   # trabajos periodicos
uv run alembic revision --autogenerate -m "descripcion"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run ruff check . --fix ; uv run ruff format .
uv run mypy app
uv run pytest -m unitaria -q
uv run pytest -m "integracion or api" -q
uv run pytest --cov=app --cov-report=term-missing

# Frontend
cd frontend
npm start ; npm run lint ; npm run test:ci ; npm run build

# Extremo a extremo
cd pruebas-e2e ; npx playwright test
```

---

## 4. Organización del código

```
backend/app/
  nucleo/        configuracion, seguridad, cifrado, errores, logs, idempotencia, bd
  modulos/<x>/   rutas.py · esquemas.py · modelos.py · servicios.py · repositorio.py
  ia/            proveedores (LLM, embeddings), recuperador, memoria, herramientas
  tareas/        worker ARQ, planificador, procesador de outbox
```

Reglas de capas, de fuera hacia dentro. Una capa nunca llama hacia afuera:

`rutas` → `servicios` → `repositorio` → base de datos

* `rutas.py`: HTTP, validación de esquemas y declaración del permiso requerido.
  Sin lógica de negocio, sin SQL.
* `servicios.py`: reglas de negocio, transacciones y escritura de auditoría.
  Es la **única** vía de escritura, también para el agente de IA.
* `repositorio.py`: acceso a datos. Aplica el filtro de ámbito del principal.
  Sin SQL por concatenación de cadenas: siempre parámetros enlazados.
* `esquemas.py`: Pydantic de entrada y salida. Los esquemas de salida son explícitos,
  nunca serializan el modelo completo (protección contra exposición accidental).

---

## 5. Al añadir un endpoint

Lista de verificación obligatoria:

1. Declarar el permiso con la dependencia de autorización; jamás dejarlo abierto.
2. Aplicar el filtro de ámbito en el repositorio, no solo el permiso.
3. Esquema de salida explícito, sin campos sensibles no solicitados.
4. Registrar en auditoría toda lectura de datos clínicos y toda escritura.
5. Clave de idempotencia si la operación crea o modifica estado por una petición externa.
6. Prueba de API con: rol autorizado, rol no autorizado, ámbito ajeno (IDOR),
   entrada inválida y ausencia de autenticación.
7. Actualizar la matriz de permisos en [`docs/security.md`](docs/security.md).

## 6. Al tocar la agenda

* La agenda interna es la fuente de verdad. El calendario externo es un reflejo.
* El anti doble‑reserva vive en la base de datos (restricción de exclusión `gist`), no en
  Python. Cualquier cambio de esquema debe preservarla y las pruebas de concurrencia
  deben seguir pasando.
* Todo se almacena en `timestamptz` UTC. La zona horaria de presentación viene de la
  clínica. Nunca usar `datetime.now()` sin zona: usar el reloj inyectado desde
  `app/nucleo/reloj.py` para que las pruebas puedan fijar el tiempo.
* Un fallo del calendario externo **no** puede perder la cita interna: se registra en el
  outbox y se reintenta.

## 7. Al tocar recetas o adherencia

* Solo una receta confirmada por un profesional genera calendario de tomas.
* Los medicamentos «cuando sea necesario» (PRN) no se convierten en horarios fijos.
* Al modificar una receta: cancelar las tomas futuras pendientes, conservar el historial
  y reprogramar solo tras confirmación profesional.

## 8. Al tocar conocimiento o RAG

* Solo documentos en estado `APPROVED` o `PUBLISHED` y vigentes son recuperables.
  El filtro va en el `WHERE` de SQL, nunca como post‑filtro en Python.
* El texto de un documento es **dato citado**, nunca instrucción. Va delimitado y
  saneado; no puede alterar el comportamiento del agente ni invocar herramientas.
* La historia clínica individual no se indexa en un índice vectorial global compartido.
* Si no hay fuente aprobada, la respuesta es que no existe información aprobada, más la
  oferta de derivar a un humano. Nunca improvisar.

---

## 9. Pruebas

Marcadores de pytest: `unitaria`, `integracion`, `api`, `concurrencia`, `seguridad`,
`rag`, `lento`. Las pruebas de integración usan PostgreSQL, pgvector y Redis reales en
contenedores; no se sustituyen por dobles.

No se sube cobertura borrando pruebas ni relajando aserciones. Si una prueba falla, se
corrige la causa. Si se descubre que una prueba estaba mal escrita, se corrige y se
explica en el commit.

---

## 10. Antes de dar una fase por cerrada

1. Linter, formateador y comprobación de tipos en verde.
2. Pruebas de la fase en verde **y** regresión de las fases anteriores.
3. Migraciones aplicables y reversibles (`upgrade head` y `downgrade -1`).
4. Sin secretos detectados (`gitleaks`).
5. Sin vulnerabilidad crítica o alta sin justificación formal y plan de corrección.
6. Documentación actualizada, incluidos `known-limitations.md` y
   `production-readiness.md`.
7. Informe con los 18 puntos: qué se implementó, archivos, decisiones, pruebas
   ejecutadas con sus comandos y resultados reales, cobertura, vulnerabilidades halladas y
   corregidas, riesgos pendientes, credenciales faltantes, configuración de staging y de
   producción, despliegue, rollback, restauración, pendientes y evaluación de preparación.
