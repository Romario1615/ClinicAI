# Plataforma de Gestión Clínica

Sistema de gestión clínica multi‑sede con agenda, agente de WhatsApp, sincronización de
calendarios, lista de espera inteligente, historia clínica versionada, recetas con
seguimiento de adherencia, base de conocimiento con RAG, pagos asistidos, dashboard y
auditoría.

> **Estado actual: fases 0, 0b, 3, 4 y 6 cerradas. 1, 2, 5, 7, 8 y 9 en curso.**
>
> Implementado y verificado, con evidencia de ejecución real: infraestructura local
> (PostgreSQL 16 + pgvector 0.8.6, Redis), migraciones reversibles, autenticación y RBAC
> con ámbito de cuatro dimensiones, la **protección anti doble‑reserva en el motor de base
> de datos** —comprobada con 50 participantes simultáneos—, historia clínica append‑only,
> recetas con calendario de tomas, lista de espera, el **outbox de entrega con el webhook
> de WhatsApp**, la **sincronización de calendarios con reconciliación de cambios
> externos**, la base de conocimiento con RAG que **sabe decir que no sabe**, la **capa de
> herramientas del agente** con su frontera clínica, pagos administrativos, dashboard, y la
> **restauración de respaldos verificada de extremo a extremo**.
>
> **60 operaciones HTTP** y 9 pantallas de Angular, todas conectadas al backend real.
>
> **1267 pruebas** en el backend, **114** en el frontend y **20 de extremo a extremo**
> contra navegador real.
>
> **Lo que no está verificado, dicho sin rodeos:** ni un mensaje ha salido hacia Meta ni un
> evento hacia Google —no hay credenciales y no se inventan—, no existe el adaptador real
> de Google Calendar, **ningún modelo de lenguaje ha invocado nunca las herramientas del
> agente** (existe el recinto; el modelo todavía no está dentro), **nada vigila** los
> eventos que el sistema emite, **no hay pruebas de carga**, el procedimiento de
> incidentes **no se ha ensayado**, y no hay validación jurídica.
>
> El estado real frente a los criterios de producción está en
> [`docs/production-readiness.md`](docs/production-readiness.md), y los riesgos residuales
> en [`docs/known-limitations.md`](docs/known-limitations.md).
> Este sistema **no está aprobado para uso con datos de pacientes reales**.

---

## Aviso de seguridad y alcance

* **Nunca** se usan datos reales de pacientes en desarrollo, pruebas o demostraciones.
  Todo dato de trabajo es sintético, generado con Faker en español.
* La información clínica se trata como información altamente sensible.
* El cumplimiento legal (LOPDP del Ecuador y normativa sanitaria) **no está validado**.
  Los puntos que requieren revisión de un profesional jurídico están listados en
  [`docs/security.md`](docs/security.md).
* La IA **no puede** modificar la base de datos por sí misma, ni crear o cambiar
  recetas, dosis o tratamientos. La frontera está en
  [`CLAUDE.md`](CLAUDE.md) (reglas 4 y 5) y en
  [`docs/decisiones/0017-frontera-de-la-automatizacion-entrante.md`](docs/decisiones/0017-frontera-de-la-automatizacion-entrante.md).

---

## Arquitectura en una línea

Angular 19 PWA → FastAPI (Python 3.11) → PostgreSQL 16 + pgvector · Redis · worker de
tareas con outbox transaccional en PostgreSQL. Proveedores de LLM y embeddings detrás de
interfaces abstractas. Detalle completo en [`docs/architecture.md`](docs/architecture.md).

---

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `backend/` | API FastAPI, dominio, capa de IA, tareas, migraciones Alembic y pruebas |
| `frontend/` | Aplicación Angular 19 PWA |
| `infra/` | Dockerfiles, ficheros compose, aprovisionamiento de WSL2 y scripts |
| `pruebas-e2e/` | Escenarios Playwright de extremo a extremo |
| `pruebas-carga/` | Escenarios de carga k6 |
| `datos-sinteticos/` | Semillas y generadores de datos sintéticos |
| `docs/` | Arquitectura, seguridad, modelo de amenazas, operación y decisiones (ADR) |
| `.github/workflows/` | Pipeline de integración y entrega continua |

---

## Requisitos

| Herramienta | Versión verificada en el entorno de desarrollo |
|---|---|
| Python | 3.11.9 |
| Node.js / npm | 22.23.1 / 11.2.0 |
| Git | 2.44 |
| Docker + Compose | Dentro de WSL2 (ver nota de Windows) |

### Nota para Windows

En el equipo de desarrollo actual Docker Desktop **no es viable** (disco C: sin espacio) y
pgvector **no compila de forma nativa** (sin MSVC). Por eso la infraestructura de datos se
ejecuta dentro de **WSL2 con Docker Engine**, con el sistema de archivos en `D:`.
La distribución se llama **`clinica`**. El procedimiento está en
[`docs/deployment.md`](docs/deployment.md) y los scripts en [`infra/wsl/`](infra/wsl/). Razonamiento en
[`docs/decisiones/0002-infraestructura-local-wsl2-docker.md`](docs/decisiones/0002-infraestructura-local-wsl2-docker.md).

---

## Puesta en marcha local

```powershell
# 1. Configuración
Copy-Item .env.example .env
#    Complete .env. Genere los secretos así (no reutilice valores de ejemplo):
#    python -c "import secrets; print(secrets.token_urlsafe(64))"
#    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Infraestructura de datos (PostgreSQL + pgvector + Redis)
.\infra\wsl\aprovisionar.ps1                     # solo la primera vez
#    Anclar la distribución: sin esto WSL se apaga entre comandos y reinicia
#    los contenedores, con fallos de conexión aparentemente aleatorios.
#    Explicación en docs/deployment.md
.\infra\scripts\mantener-wsl.ps1 -SegundoPlano
.\infra\scripts\infra-arriba.ps1

# 3. Backend
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install uv; uv sync
uv run python -m herramientas.esperar_bd            # espera a que la BD responda
uv run alembic upgrade head
uv run python -m app.semillas.cargar                # catálogos + datos sintéticos
uv run uvicorn app.main:crear_aplicacion --factory --reload
uv run arq app.tareas.worker.ConfiguracionWorker   # trabajos periodicos

# 4. Frontend
cd ..\frontend
npm ci
npm start
```

* API y documentación OpenAPI: `http://localhost:8000/docs`
* Aplicación web: `http://localhost:4200`
* Comprobación de salud: `http://localhost:8000/salud`

Credenciales de los usuarios sintéticos: se imprimen al ejecutar la carga de semillas.
No existen credenciales por defecto embebidas en el código.

---

## Pruebas

```powershell
# Backend
cd backend
uv run ruff check . ; uv run ruff format --check .
uv run mypy app
uv run pytest -m unitaria -q
uv run pytest -m "integracion or api" -q     # requiere la infraestructura arriba
uv run pytest -m concurrencia -q
uv run pytest -m rag -q
uv run pytest --cov=app --cov-report=term-missing

# Frontend
cd ..\frontend
npm run lint ; npx tsc --noEmit ; npm test -- --watch=false ; npm run build

# Extremo a extremo y carga
cd ..\pruebas-e2e  ; npx playwright test
cd ..\pruebas-carga ; k6 run reservas.js
```

El plan de pruebas completo, con los escenarios obligatorios y los resultados de la
última ejecución, está en [`docs/test-plan.md`](docs/test-plan.md).

---

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Arquitectura, componentes y flujos |
| [`docs/requirements.md`](docs/requirements.md) | Requisitos y criterios de aceptación |
| [`docs/data-model.md`](docs/data-model.md) | Modelo de datos y diagrama de entidades |
| [`docs/security.md`](docs/security.md) | Controles, política de acceso y retención |
| [`docs/threat-model.md`](docs/threat-model.md) | Modelo de amenazas y matriz de riesgos |
| [`docs/rag.md`](docs/rag.md) | Recuperación, permisos y anti prompt injection |
| [`docs/agente.md`](docs/agente.md) | Las siete herramientas, la frontera clínica y lo que aún falta |
| [`docs/backup-and-restore.md`](docs/backup-and-restore.md) | Respaldo cifrado y la restauración **ya verificada** |
| [`docs/monitoring.md`](docs/monitoring.md) | Qué vigilar y por qué; qué emite ya el sistema |
| [`docs/incident-response.md`](docs/incident-response.md) | Clasificación por daño al paciente y guías por tipo |
| [`docs/whatsapp-integration.md`](docs/whatsapp-integration.md) | Webhooks, plantillas y entrega |
| [`docs/calendar-integration.md`](docs/calendar-integration.md) | OAuth, sincronización y reconciliación |
| [`docs/deployment.md`](docs/deployment.md) | Despliegue local, staging, producción y rollback |
| `docs/backup-and-restore.md` | Respaldo y restauración verificada — **pendiente** |
| `docs/monitoring.md` | Métricas, logs y alertas — **pendiente** |
| `docs/incident-response.md` | Respuesta a incidentes — **pendiente** |
| [`docs/production-readiness.md`](docs/production-readiness.md) | Estado real frente a los criterios de producción |
| [`docs/test-plan.md`](docs/test-plan.md) | Qué se prueba, con qué, por qué de esa forma, y la evidencia de la última ejecución |
| [`docs/known-limitations.md`](docs/known-limitations.md) | Limitaciones y riesgos residuales |
| [`docs/backlog.md`](docs/backlog.md) | Backlog por fases con criterios de aceptación |
| [`docs/decisiones/`](docs/decisiones/) | Registros de decisiones de arquitectura (ADR) |
| [`docs/informe-avance.md`](docs/informe-avance.md) | **Estado real del proyecto**, con los 18 puntos exigidos y sus evidencias |

---

## Licencia y titularidad

Proyecto privado. Sin licencia de distribución definida.
