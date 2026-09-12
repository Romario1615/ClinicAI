# Plan de pruebas

> **Última actualización:** 2026‑09‑12 · Fases 0–4 cerradas · 899 pruebas.

Este documento dice **qué se prueba, con qué, y por qué de esa forma**. No es un
inventario de pruebas: el inventario está en el código. Lo que aquí importa son las
decisiones que hacen que una suite verde signifique algo.

---

## 1. Principio: probar el sistema, no el código

Tres reglas que se aplican sin excepción:

**Las garantías del motor se prueban contra el motor.** El anti doble‑reserva no es lógica
de Python: es una restricción de exclusión GiST (ADR‑0009). Una suite que sustituya
PostgreSQL por SQLite prueba el código y no el sistema, y daría verde sobre un esquema
que permite dos pacientes a la misma hora. Las pruebas de integración usan PostgreSQL 16
con pgvector y Redis reales, en contenedores.

**La concurrencia se prueba con concurrencia real.** No con dobles, no con mocks de
transacción: con varias conexiones distintas y una `asyncio.Barrier` que las suelta a la
vez. Es la única forma de observar el interbloqueo que aparece con 50 participantes y que
no aparece con dos.

**Probar las piezas no prueba el cableado.** Esta regla se añadió después de un fallo
real: `configurar_registro` combinaba un factory de structlog con un procesador
incompatible, y **toda** línea de registro lanzaba `AttributeError`. La suite estaba verde
porque cada prueba invocaba el procesador de redacción de forma aislada y ninguna llamaba
a la configuración y después emitía una línea. En la API eso habría sido un 500 en la
primera petición. Desde entonces hay pruebas de arranque para la configuración de logs y
para el worker.

**Una suite verde no sustituye a ejercer el sistema.** Regla añadida tras encontrar tres
fallos del filtro de ámbito —uno de ellos dejaba a la recepción sin poder agendar nada, y
otro exponía las citas de todos los profesionales a quien tuviera el ámbito de profesional
vacío— **arrancando la API y recorriendo el flujo real**, con 557 pruebas en verde.

Vivían en el espacio entre lo que las fixtures suponían y lo que los datos reales tienen:
las fixtures construían el `Principal` a mano, con un ámbito que ningún rol real produce.
Por eso ahora existe una comprobación de extremo a extremo contra la base con datos
sintéticos —login, catálogo, disponibilidad, reserva idempotente, colisión de turno,
cancelación e IDOR— que se ejecuta antes de dar una fase por cerrada, y por eso las
pruebas de ámbito verifican **dimensión por dimensión** con una prueba de control que
confirma que el caso permitido sí devuelve datos. Sin esa prueba de control, las demás
pasarían por el motivo equivocado.

**La regla se volvió a cumplir en la Fase 4, y con un fallo peor.** Con 891 pruebas en
verde, ejercer el sistema arrancado contra las semillas reales destapó que **un paciente que
respondía `BAJA` por WhatsApp no quedaba dado de baja**: la columna guarda el número como lo
escribió el personal («+593 99 900 0333») y el webhook entrega solo dígitos
(«593999000333»), así que la revocación de consentimiento no encontraba a quien revocar y el
sistema le seguía escribiendo.

Las fixtures guardaban el número **ya normalizado**, que es justo lo que el panel no hace.
Las 26 pruebas del webhook pasaban por el motivo equivocado. Es el mismo sitio donde vivían
los tres fallos de ámbito: el espacio entre lo que la fixture supone y lo que los datos
reales tienen.

De ahí dos consecuencias para las pruebas de este repositorio:

* **Una fixture debe guardar el dato en la forma más incómoda que admita el sistema**, no en
  la más cómoda para la aserción. El teléfono se guarda ahora con «+» y espacios.
* **Los identificadores de las pruebas se generan por prueba, no son constantes del módulo.**
  El `phone_number_id` estaba fijo, y bastó que un ejercicio manual insertara una fila de
  configuración con ese mismo valor para que 20 pruebas fallaran por datos ajenos. Igual con
  contar filas: `SELECT count(*)` sobre una tabla entera supone una base vacía, y la de
  desarrollo no lo está.

**Un porcentaje de cobertura es una medición, y una medición puede estar mal.** Regla
añadida en la Fase 4, al ver que `conversaciones/servicios.py` aparecía al 65 % con 26
pruebas de API que lo recorren entero. La causa no era el código ni las pruebas: SQLAlchemy
async ejecuta el código que rodea a cada consulta dentro de un greenlet (`greenlet_spawn`),
y `coverage` no traza esas líneas sin `concurrency = ["thread", "greenlet"]`.

El síntoma empuja en la dirección contraria a la útil: invita a escribir pruebas para
líneas que ya estaban probadas, y **oculta las que de verdad no lo están**. Corregirlo
subió la cobertura total de 89,18 % a 91,63 % sin añadir una sola prueba —y dejó a la vista
dos huecos reales (`destinatarios.py` al 41 %, la cancelación de recordatorios sin cubrir)
que el ruido tapaba.

Antes de creerse un número bajo, conviene comprobar que la línea se ejecuta de verdad: un
`print` o un fallo provocado a propósito lo resuelven en un minuto.

---

## 2. Marcadores y qué cubre cada uno

Los marcadores no son etiquetas decorativas: determinan qué se ejecuta en cada paso del
pipeline y qué infraestructura necesita.

| Marcador | Necesita | Qué cubre | Estado |
|---|---|---|:--:|
| `unitaria` | nada | lógica pura: motor de disponibilidad, redacción de logs, autorización, traducción de errores, criptografía | **308** |
| `integracion` | PostgreSQL, Redis | restricciones, disparadores, índices parciales, aislamiento transaccional, servicios completos, semillas, worker | **157** |
| `api` | PostgreSQL, Redis | contorno HTTP: códigos de estado, forma del cuerpo, cabeceras, **quién puede llamar a qué** | **71** |
| `concurrencia` | PostgreSQL | carreras reales por el mismo turno, con conexiones separadas | **10** |
| `seguridad` | según el caso | un control de seguridad concreto por prueba | **162** |
| `rag` | PostgreSQL + pgvector | recuperación, filtros de permiso, resistencia a inyección de prompt | **0 — Fase 6** |
| `lento` | — | tarda más de cinco segundos | — |

Los marcadores se solapan a propósito: una prueba de IDOR es `api` **y** `seguridad`.

**Total actual: 564 pruebas (backend) y 67 (frontend). Cobertura 90 % y 95 %** (umbral del pipeline: 80 %, RNF‑06).

---

## 3. Lo que se prueba porque puede hacer daño

Esta sección lista, por dominio, las propiedades que la suite verifica. Están escritas
como afirmaciones comprobables, no como áreas.

### Agenda y concurrencia

* Dos reservas simultáneas del mismo turno producen **una sola cita**. Verificado con 50
  participantes reales.
* El invariante se comprueba **en SQL** — cero pares de citas activas solapadas — y no
  contando ganadores. Una prueba anterior contaba ganadores y estaba mal: con rangos
  semiabiertos `[inicio, fin)`, `[13:45,14:15)` y `[14:15,14:45)` no se solapan.
* Parte de los rechazos bajo carga llegan como **interbloqueo** (SQLSTATE 40P01), no como
  violación de exclusión (23P01). Tratar solo el segundo dejaría una fracción de las
  reservas devolviendo 500 bajo competencia real.
* Un bloqueo temporal vencido **no se puede confirmar**: ese turno pudo ofrecerse ya a
  otra persona.
* El barrido libera solo lo vencido, con el límite exacto al segundo, y el turno queda
  **realmente** libre — comprobado reservándolo otra vez, no leyendo el estado de la fila.

### Autenticación

* Correo inexistente, contraseña incorrecta y cuenta desactivada devuelven **el mismo
  código, el mismo mensaje y el mismo estado HTTP**. Distinguirlos permitiría enumerar al
  personal de la clínica.
* El bloqueo por intentos **no cede ante la contraseña correcta**. Si cediera, no serviría.
* El contador de intentos **sobrevive a la excepción**. Es el fallo más fácil de introducir
  en la capa HTTP: si el manejador de errores deshiciera la transacción, el contador
  volvería a cero en cada intento y el bloqueo no se activaría nunca, con la suite del
  servicio en verde. Tiene una prueba de API dedicada.
* Reutilizar un token de refresco revoca **la familia completa** de sesiones.
* Retirar un permiso surte efecto **con el mismo token**, sin esperar a que caduque.

### Autorización y aislamiento

* La dependencia `exige_permiso` se prueba contra **endpoints de sonda** montados en la
  propia suite, con la dependencia real. Aísla el fallo y no caduca cuando cambie el
  endpoint que se hubiera usado de excusa.
* Un recurso fuera de ámbito devuelve **404, no 403**, y la respuesta es **indistinguible**
  de la de un recurso inexistente. Si se distinguieran, el 404 dejaría de proteger nada.
* El IDOR se prueba **transición por transición** (confirmar, cancelar, reprogramar,
  completar, inasistencia). Basta con que una sola olvide el filtro de ámbito para que la
  agenda de otra sede sea modificable desde fuera, y una prueba genérica sobre el detalle
  no lo detectaría.
* Una exclusión de ámbito gana a un comodín, y el ámbito vacío no da acceso a nada.

### Datos sensibles

* Los campos sensibles se redactan por nombre **y** por patrón de contenido, de forma
  recursiva.
* Los registros de **otras librerías** pasan por la misma cadena de redacción. Importa:
  SQLAlchemy escribe las sentencias con sus parámetros enlazados, y esos parámetros son
  nombres, documentos y teléfonos de pacientes. Hay una prueba que emite desde
  `sqlalchemy.engine`.
* Los esquemas de salida son explícitos. Hay pruebas que comprueban que `hash_contrasena`,
  `secreto_2fa_cifrado` e `intentos_fallidos` **no aparecen** en ninguna respuesta.
* Un error de validación no refleja el valor rechazado: ese valor puede ser una contraseña
  o el documento de un paciente.

### Datos sintéticos

Tras cargar las semillas se verifican cuatro invariantes, todas a cero: ninguna cita activa
solapada, ningún documento fuera del prefijo `99`, ningún correo fuera de
`example.invalid`, ningún paciente sin la marca `[SINTETICO]`.

---

## 4. Puertas del pipeline

Definidas en [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). El pipeline
**bloquea la fusión** ante cualquiera de estas condiciones:

| Puerta | Herramienta | Por qué bloquea |
|---|---|---|
| Lint y formato | `ruff` | Incluye reglas propias del proyecto, como la que prohíbe `datetime.now()` fuera de `reloj.py` (ADR‑0010) |
| Tipos | `mypy --strict` | Un `Optional` no comprobado en la resolución de ámbito se traduce en acceso indebido, no en un error visible |
| Seguridad estática | `bandit -ll` | Solo severidad media o superior: un informe con cien avisos irrelevantes se deja de leer |
| Pruebas | `pytest` por marcador y después completa | Los marcadores se ejecutan por separado para que el fallo diga **qué** falló |
| Cobertura | `pytest-cov`, `fail_under = 80` | RNF‑06 |
| Secretos | `gitleaks`, historial completo | Un secreto comprometido en un commit anterior sigue comprometido aunque el archivo ya no exista |
| Dependencias | `pip-audit --strict` sobre el bloqueo exportado | Se audita lo que se despliega, no lo que el ejecutor resolvió |
| Migraciones | `alembic upgrade` → `check` → `downgrade -1` → `upgrade` | Una migración irreversible convierte cualquier despliegue fallido en una restauración desde copia (RNF‑11) |
| Coherencia de modelos | `alembic check` | Detecta el modelo cambiado sin migración generada |
| Extensiones | consulta a `pg_extension` | Sin `btree_gist` no existe la garantía anti doble‑reserva; sin `vector` no hay conocimiento |
| Imágenes | `docker build` + `trivy` (HIGH, CRITICAL) | `ignore-unfixed`: una vulnerabilidad sin parche no se arregla bloqueando la fusión, se registra como riesgo |
| Frontend | `eslint`, `tsc --noEmit`, Karma, `ng build`, `npm audit` | Se **omite de forma explícita** mientras `frontend/package.json` no exista, en lugar de fallar: un rojo permanente acostumbra al equipo a ignorar los rojos |

**Hallazgo de la primera ejecución de estas puertas:** `pip-audit` encontró 44
vulnerabilidades conocidas en tres paquetes, incluidas 7 en `cryptography` —la biblioteca
que cifra los secretos de segundo factor y los tokens OAuth en reposo—. Se corrigieron
subiendo `cryptography` a 50.0.1 y `pytest` a 9.x, y **eliminando Pillow del árbol**: sus
35 vulnerabilidades no se podían corregir porque `fastembed` limita `pillow<12.0`, y el
único uso de QR (el código de provisionamiento TOTP) no necesita Pillow si se genera SVG.

---

## 5. Lo que este plan todavía no cubre

Declarado de forma explícita, no por omisión.

| Área | Estado | Fase |
|---|---|:--:|
| E2E con Playwright (21 escenarios) | **no empezado** | 1 y siguientes |
| Pruebas de contrato de API (`schemathesis`) | dependencia instalada, sin usar | 2 |
| Suite de WhatsApp (firma inválida, duplicado, reintento, estado de entrega) | **no empezado** | 4 |
| Suite de calendario (token vencido, evento borrado en el proveedor, conflicto) | **no empezado** | 4 |
| Evaluación de RAG (Hit@K, precisión, fugas entre pacientes y especialidades = 0) | **no empezado** | 6 |
| Suite de medicamentos, incluidos PRN y cancelación de recordatorios | **no empezado** | 7 |
| DAST sobre la API en ejecución | **no empezado** | 10 |
| Carga con k6 | **no empezado** | 10 |
| Recuperación ante caídas (Redis, PostgreSQL, proveedor externo) | **no empezado** | 10 |
| Restauración real desde copia de seguridad | **no empezado** | 10 |

**Una copia de seguridad no se declara válida hasta que se restaura y se verifica.** Esa
verificación es parte de la Fase 10 y hoy no existe.

---

## 6. Cómo ejecutarlo en local

```powershell
.\infra\scripts\infra-arriba.ps1          # PostgreSQL + Redis
cd backend
uv run alembic upgrade head
uv run python -m app.semillas.cargar --solo-catalogos

uv run pytest -m unitaria -q
uv run pytest -m "integracion or api" -q
uv run pytest -m concurrencia -q
uv run pytest -m seguridad -q
uv run pytest --cov=app --cov-report=term-missing

uv run ruff check . ; uv run ruff format --check .
uv run mypy app
uv run bandit -r app -ll
uv run alembic check
```

Auditoría de dependencias (se audita el bloqueo, no el entorno):

```powershell
uv export --frozen --no-emit-project --no-hashes --extra dev --extra llm -o requisitos.txt
uv run pip-audit --strict --desc -r requisitos.txt
```

---

## 7. Reglas sobre las propias pruebas

* **No se sube cobertura borrando pruebas ni relajando aserciones.** Si una prueba falla,
  se corrige la causa.
* **Si se descubre que una prueba estaba mal escrita, se corrige y se explica en el
  commit.** Ha pasado seis veces en este proyecto, y cada caso está documentado en el
  mensaje del commit correspondiente: tres asumían comportamientos de disponibilidad que
  el motor no tiene, una ordenaba por un UUID aleatorio creyendo que era un orden estable,
  una esperaba 423 donde el diseño usa 401 a propósito, y una medía la caducidad del token
  creyendo que medía la del bloqueo.
* **Las pruebas de seguridad no se desactivan.** Las que verifican que la IA no puede
  escribir en la base ni tomar decisiones clínicas, menos que ninguna.
* Ninguna prueba usa datos reales de pacientes. Nunca.
