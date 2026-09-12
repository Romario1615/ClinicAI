# Informe de avance

> **Fecha:** 2026‑09‑12 · 19 commits · Fases 0, 0b y 3 cerradas; 1, 2, 5 y 7 en curso.

Este informe cubre los 18 puntos exigidos. Está escrito para ser contrastado: cada cifra
procede de una ejecución real cuyo comando se indica, y lo que no se ha verificado se dice
que no se ha verificado.

---

## 1. Qué se implementó

| Área | Estado |
|---|---|
| Infraestructura local (WSL2 + Docker, PostgreSQL 16 + pgvector, Redis) | operativa |
| Modelo de datos | **47 tablas** migradas, reversibles |
| Autenticación (Argon2id, JWT, refresco rotativo, TOTP, bloqueo) | completa |
| RBAC con ámbito de 4 dimensiones + relación asistencial | completo |
| Auditoría append‑only con redacción activa | completa |
| Agenda: disponibilidad, reserva, ciclo de estados, anti doble‑reserva | completa |
| Worker ARQ: expiración de bloqueos temporales | completo |
| Catálogo y pacientes (lectura) | completo |
| Historia clínica versionada, recetas, tomas, adherencia | servicios y API completos |
| Lista de espera con oferta única por turno | servicios completos |
| API HTTP | **33 rutas** |
| Frontend Angular 19 PWA | 9 pantallas; agenda conectada al backend real |
| CI/CD con puertas de fallo | completo, **sin ejecutar en GitHub** |

**No implementado:** WhatsApp, calendarios externos, RAG, dashboard, predicciones, pagos,
E2E, pruebas de carga, y la preparación de producción.

---

## 2. Archivos y módulos tocados

```
backend/app/
  nucleo/        configuracion · seguridad · autorizacion · auditoria · bd · errores
                 errores_bd · idempotencia · registro · reloj · dependencias · limite_tasa
  api/           middleware · manejadores
  modulos/       agenda · auditoria · historia · lista_espera · organizacion
                 outbox · pacientes · profesionales · usuarios
  tareas/        worker ARQ · contexto · agenda
  semillas/      catalogos · sinteticos · cargar
frontend/src/app/
  nucleo/        modelos · servicios · guardias · interceptores · utilidades
  compartido/    estados · insignia-estado
  paginas/       acceso · agenda · demostracion
infra/           compose · docker (backend, worker, postgres) · scripts · wsl
.github/workflows/ci.yml
docs/            17 documentos + 16 ADR
```

---

## 3. Decisiones tomadas

Las 16 ADR están en [`docs/decisiones/`](decisiones/). Las que más condicionan el sistema:

* **ADR‑0009** — El anti doble‑reserva es una restricción de exclusión `gist` de
  PostgreSQL, no lógica de aplicación.
* **ADR‑0010** — Todo en `timestamptz` UTC; reloj inyectable, con una regla de lint que
  prohíbe `datetime.now()` fuera de `reloj.py`.
* **ADR‑0011** — Historia clínica append‑only, sostenida por un disparador.
* **ADR‑0016** — El token de refresco viaja en el cuerpo, no en cookie; la defensa es
  detectar su duplicado, no ocultarlo.

Decisiones no cubiertas por ADR pero con consecuencia:

* Las reglas que pueden dañar a un paciente viven en el **motor**, no en el servicio: tres
  disparadores y varias restricciones `CHECK`. Un servicio se puede rodear añadiendo otro
  camino de escritura; un disparador no.
* **Ámbito vacío = sin acceso**, en las cuatro dimensiones y sin excepciones.
* El límite de tasa **falla cerrado en autenticación** y abierto en el resto.

---

## 4. Pruebas ejecutadas, con sus comandos y resultados reales

```
cd backend
uv run pytest --cov=app -q            663 passed · cobertura 90 %
uv run pytest -m unitaria -q          308
uv run pytest -m integracion -q       243
uv run pytest -m api -q               110
uv run pytest -m concurrencia -q       12
uv run pytest -m seguridad -q         235
uv run ruff check .                   All checks passed
uv run ruff format --check .          todos los archivos formateados
uv run mypy app                       no issues found in 66 source files
uv run bandit -r app -ll              sin hallazgos de severidad media o alta
uv run alembic upgrade head           aplicada
uv run alembic downgrade -1 && upgrade head    reversible
uv run alembic check                  No new upgrade operations detected

cd frontend
npm run lint                          All files pass linting
npx tsc --noEmit                      sin errores
npm run test:ci                       67 SUCCESS
npm run build                         299.92 kB inicial · 86.50 kB transferidos
```

Los marcadores se solapan: una prueba de IDOR cuenta como `api` y como `seguridad`.

**Verificación de extremo a extremo** contra la base con datos sintéticos, con la API
arrancada de verdad:

```
login recepción            200 · 21 permisos · ámbito de 1 sede
catálogo                   1 sede · 4 especialidades · 8 servicios · 4 profesionales
disponibilidad             200 · 5 turnos · zona America/Guayaquil
reserva                    201 · CONFIRMED · fin calculado por el disparador
misma clave idempotencia   201 · mismo identificador
otra clave, mismo turno    409 TURNO_NO_DISPONIBLE
cancelación                200 · CANCELLED con motivo
cita ajena                 404 RECURSO_NO_ENCONTRADO
paciente ajeno             404 RECURSO_NO_ENCONTRADO
```

---

## 5. Cobertura

**Backend 90 %** (umbral del pipeline 80 %, RNF‑06). **Frontend 95,4 % sentencias,
87,3 % ramas, 90,7 % funciones** (umbrales 80/70/80).

Los módulos por debajo del 80 % y por qué: `nucleo/bd.py` (58 %, la parte no cubierta es
el ciclo de vida del motor, que se ejercita al arrancar); `agenda/repositorio.py` (69 %,
ramas de consulta de feriados y descansos aún sin caso de prueba);
`nucleo/idempotencia.py` (68 %, funciones que usará el webhook de WhatsApp).

---

## 6. Vulnerabilidades encontradas y corregidas

`pip-audit` encontró **44 vulnerabilidades conocidas en 3 paquetes** la primera vez que se
ejecutó la puerta:

| Paquete | Vulns | Acción |
|---|:--:|---|
| `cryptography` 46.0.7 | 7 | Subido a 50.0.1. **Cifra los secretos de 2FA y los tokens OAuth en reposo** |
| `pytest` 8.4.2 | 2 | Subido a 9.x (obligó a subir `pytest-asyncio` a 1.4) |
| `pillow` 11.3.0 | 35 | **Eliminado del árbol.** `fastembed` lo capa a `<12.0` y la corrección está en 12.1.1; entraba solo por el extra `[pil]` de `qrcode`, y el único uso de QR —el código TOTP— no lo necesita si se genera SVG |

Estado actual: `pip-audit --strict` → **No known vulnerabilities found**.

### Fallos de seguridad propios, encontrados y corregidos

1. **El filtro de ámbito de la agenda no filtraba con la lista vacía.** La condición era
   `if not todos_los_profesionales **and** profesionales`: con la lista vacía la rama no se
   ejecutaba y el principal veía las citas de todos. Igual con pacientes. Y la dimensión de
   especialidad **no se aplicaba en absoluto**.
2. **El control de relación asistencial era inerte por HTTP.** El principal nunca llevaba
   `profesional_id`, y ese campo es lo que lo activa. Cualquiera con
   `historia_clinica.leer` habría leído la historia de cualquier paciente de su clínica.
3. **El registro estructurado reventaba en ejecución.** Toda línea lanzaba
   `AttributeError`; en la API habría sido un 500 en la primera petición. Además, los
   registros de librerías no pasaban por la redacción, y SQLAlchemy escribe las sentencias
   con sus parámetros —nombres, documentos y teléfonos de pacientes.
4. **`WWW-Authenticate` faltaba en la mayoría de los 401.**

Los tres primeros aparecieron **ejerciendo el sistema**, no ejecutando la suite: vivían en
el espacio entre lo que las fixtures suponían y lo que los datos reales tienen. Está
anotado como principio en `test-plan.md`.

---

## 7. Riesgos pendientes

Los 12 riesgos residuales están en [`known-limitations.md`](known-limitations.md). Los que
más pesan:

* **E‑2** El cumplimiento legal no está validado. **El sistema no puede operar con
  pacientes reales.** 19 puntos pendientes de revisión jurídica en `security.md`.
* **E‑10** La verificación TOTP usa el reloj de pared: el servidor **necesita NTP**, o el
  personal con 2FA obligatorio no podrá entrar.
* **E‑11** El límite de tasa falla abierto fuera de autenticación.
* **E‑7** La auditoría es inalterable desde la aplicación, no frente a un superusuario de
  base de datos.
* **D‑1** El disco C: del equipo de desarrollo está al límite por causas ajenas al
  proyecto (`C:\Windows\WinSxS`).

---

## 8. Credenciales que faltan

| Servicio | Estado | Consecuencia |
|---|---|---|
| WhatsApp Business Cloud API | **ausente** | La Fase 4 no se puede verificar contra el proveedor |
| Google Calendar (OAuth) | **ausente** | Ídem |
| Embeddings en la nube | ausente | Se usará `fastembed` local (ADR‑0007) |
| `ANTHROPIC_API_KEY` | presente en el entorno | Suficiente para la Fase 6 |

Ninguna se ha inventado. Cuando llegue la Fase 4 se implementarán adaptador real y
adaptador sandbox, y **se declarará explícitamente que el camino real no está verificado**.

---

## 9–11. Configuración de staging, producción y despliegue

Documentado en [`deployment.md`](deployment.md). Existen `Dockerfile.backend` y
`Dockerfile.worker` —dos etapas, usuario sin privilegios, `uv sync --frozen`—, y el
pipeline los construye y los pasa por Trivy.

**No existe entorno de staging** (D‑4). Los procedimientos están escritos y probados en
local; no en una infraestructura equivalente a producción.

---

## 12–13. Rollback y restauración

**Rollback de esquema:** verificado. Cada migración se prueba con
`upgrade → downgrade -1 → upgrade`, y el pipeline lo repite en cada ejecución.

**Restauración desde copia de seguridad: NO verificada.** Es trabajo de la Fase 10, y
hasta que una restauración real se ejecute y se compruebe, **no hay copia de seguridad
válida**. Es la afirmación que más conviene no adelantar.

---

## 14. Qué queda pendiente

| Fase | Estado |
|---|---|
| 1 · Prototipo visual | en curso · 6 de 9 pantallas con datos sintéticos |
| 2 · Backend y seguridad | en curso · falta escritura de pacientes y administración de usuarios |
| 4 · WhatsApp y calendarios | **no empezada** |
| 5 · Lista de espera | en curso · faltan rutas HTTP y disparo automático |
| 6 · Conocimiento y RAG | **no empezada** · 0 pruebas `rag` |
| 7 · Historia clínica | en curso · faltan recordatorios por outbox y pantalla real |
| 8 · Dashboard y predicciones | **no empezada** |
| 9 · Pagos | **no empezada** |
| 10 · Producción | **no empezada** |

También pendientes: los 21 escenarios E2E con Playwright, las pruebas de carga con k6,
DAST, y seis documentos (`rag.md`, `whatsapp-integration.md`, `calendar-integration.md`,
`monitoring.md`, `backup-and-restore.md`, `incident-response.md`).

---

## 15. Evaluación de preparación para producción

**No está listo para producción, y no está cerca.** Con evidencia, punto por punto:

| Criterio | Estado |
|---|:--:|
| Datos y migraciones reversibles | ✅ verificado |
| Autenticación y autorización | ✅ verificado, con 4 fallos propios corregidos |
| Anti doble‑reserva bajo concurrencia real | ✅ verificado con 50 participantes |
| Garantías clínicas en el motor | ✅ verificado atacándolas con SQL directo |
| Auditoría y redacción de registros | ✅ verificado |
| Pipeline con puertas de fallo | ⚠️ escrito y validado en local; **nunca ejecutado en GitHub** |
| Imágenes de contenedor | ⚠️ escritas; **nunca construidas**, no hay Docker en el anfitrión |
| Interfaz de usuario | ⚠️ prototipo; 6 de 9 pantallas son maquetas |
| Comunicación con pacientes | ❌ no existe |
| Historia clínica en la interfaz | ❌ maqueta |
| Pruebas E2E, carga, DAST, recuperación | ❌ no existen |
| Restauración de copias verificada | ❌ no existe |
| Validación legal (Ecuador) | ❌ no existe |

Lo que hay es una **columna vertebral sólida y verificada**: datos, seguridad, agenda y
núcleo clínico. Lo que falta es más de la mitad del alcance acordado.

---

## 16–18. Notas finales

**Lo que este informe no afirma.** No se dice en ningún punto que el sistema sea seguro,
que no tenga riesgos ni que cumpla la normativa. Se dice qué se probó, con qué comando y
con qué resultado.

**Sobre el pipeline.** El repositorio no tiene remoto configurado, así que el workflow no
se ha ejecutado nunca en GitHub. Su sintaxis YAML está validada y cada puerta se comprobó
a mano en local, una por una. Lo que no se ha verificado es el comportamiento de los
contenedores de servicio ni de las acciones de terceros en el ejecutor.

**Sobre las seis pruebas mal escritas.** Durante el trabajo se descubrió que seis pruebas
propias estaban mal: tres asumían comportamientos de disponibilidad que el motor no tiene,
una ordenaba por un UUID aleatorio creyendo que era un orden estable, una esperaba 423
donde el diseño usa 401 a propósito, y una medía la caducidad del token creyendo que medía
la del bloqueo. Cada una se corrigió y se explicó en el mensaje del commit correspondiente.
Se listan aquí porque una suite verde cuyas pruebas nadie revisa no vale más que no tener
suite.
