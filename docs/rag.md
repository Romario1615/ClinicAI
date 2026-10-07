# Base de conocimiento y recuperación (RAG)

> **Última actualización:** 2026‑10‑06 · E‑20 ACL documental resuelto; carga de PDF textual disponible con protección de archivo.
>
> El proyecto ya tiene un circuito de agente con herramientas administrativas y un
> simulador local. El webhook de WhatsApp todavía deriva los mensajes al personal y no
> invoca ese circuito. Este documento describe la base de conocimiento, la recuperación
> y el contexto citado. La evaluación reproducible usa embeddings simulados; la calidad
> semántica con embeddings reales sigue pendiente (E‑9).

---

## 1. La decisión que lo condiciona todo: pre‑filtro, no post‑filtro

El patrón habitual en los tutoriales de RAG es recuperar los `k` fragmentos más parecidos y
descartar después los que el usuario no puede ver. Tiene dos fallos, y el segundo se nota
menos que el primero:

1. **Seguridad.** Cualquier olvido en el descarte es una fuga. Y el descarte vive en Python,
   donde una condición nueva se añade en un sitio y se olvida en otro.
2. **Funcional.** Si los `k` más parecidos pertenecen todos a otra sede, el resultado queda
   **vacío** aunque existiera documentación válida. El usuario ve «no tengo información»
   sobre algo que sí está documentado.

Aquí el motor solo considera fragmentos autorizados
([ADR‑0013](decisiones/0013-rag-hibrido-con-filtros-sql.md)), así que `k` resultados son `k`
resultados útiles.

### Una sola puerta

```python
RepositorioConocimiento.buscar_conocimiento_autorizado(
    consulta=..., vector=..., modelo_embeddings=..., contexto=...,  # obligatorio
)
```

No existe otra vía de consulta a `knowledge_chunks`. **Una prueba de arquitectura recorre el
árbol de sintaxis de todo `app/`** y falla si algún módulo fuera de los tres autorizados
referencia esas tablas. Se usa AST y no `grep` porque los docstrings las mencionan a menudo
—precisamente porque están documentadas— y un `import` partido en varias líneas se le
escaparía a una búsqueda de texto.

`ContextoAutorizacion` **no tiene valores por defecto**, y hay una prueba que lo verifica
sobre la propia dataclass: un contexto con defaults permisivos sería la forma más fácil de
introducir una fuga, bastaría olvidar un campo al construirlo.

### Las dos ramas filtran igual, y eso no es casualidad

La búsqueda es híbrida: dos rankings fusionados con RRF. Eso significa **dos subconsultas**,
y si los filtros de una divergieran de los de la otra aunque fuera en una condición, la rama
más laxa sería la fuga.

Por eso las condiciones se construyen **una sola vez**, en `_condiciones`, y se aplican a
ambas. Hay una prueba que inserta un fragmento archivado cuyo texto son **las palabras
exactas de la consulta** —lo que la rama textual puntuaría primero— y comprueba que no
aparece.

---

## 2. La desnormalización de `knowledge_chunks`

La tabla repite `clinic_id`, `branch_id`, `specialty_id`, `status`, la vigencia y
`sensitivity_level`, que ya están en `knowledge_documents`.

Duplicar datos normalmente es un error. Aquí es lo que permite que **todo el filtro de
autorización viva en un único `WHERE` sobre una sola tabla, sin uniones**. Una unión se puede
omitir por error en una consulta nueva, y esa omisión sería una fuga entre sedes o entre
especialidades. Sin uniones, el filtro es una lista de condiciones que o están o no están.

**El precio es mantener la copia sincronizada, y se paga en un solo sitio:** cada cambio de
estado o de vigencia propaga a los fragmentos **en la misma transacción**. Si se propagara
después, existiría una ventana en la que un documento archivado seguiría respondiendo
preguntas de pacientes.

La propagación toca **todas las versiones**, no solo la vigente: una versión antigua que
conservara `status = 'PUBLISHED'` seguiría siendo recuperable.

---

## 3. El filtro, condición por condición

| Condición | Qué impide |
|---|---|
| `clinic_id = :clinica` | Que un fragmento de otra clínica sea visible. **Nunca admite excepción**, ni para un administrador |
| `status IN ('APPROVED','PUBLISHED')` | Que un borrador a medio escribir responda a un paciente (RF‑M05) |
| `effective_from <= ahora` | Que un tarifario del próximo trimestre se aplique hoy |
| `effective_until >= ahora` | Que un protocolo caducado siga pareciendo vigente |
| `sensitivity_level IN (…)` | Que recepción vea un documento clasificado como clínico sensible |
| `branch_id IS NULL OR IN (…)` | Que un instructivo de otra sede aparezca. Nulo = alcance general |
| `specialty_id IS NULL OR IN (…)` | Ídem con especialidad |

**Ámbito vacío = ningún acceso**, igual que en el resto del sistema: se expresa como una
condición imposible en lugar de un `return` anticipado, para que el filtro siga siendo una
lista de condiciones sin un camino de salida distinto que alguien pueda olvidar replicar.

El nivel de sensibilidad se compara por **la lista de niveles que el solicitante cubre**, no
con un `<=` sobre la cadena: «N10» ordenaría entre «N1» y «N2» si algún día se añade un nivel
de dos dígitos.

---

## 4. Búsqueda híbrida: dos cosas que había mal y que solo aparecieron al medir

### El umbral de similitud que no se aplicaba

`RAG_UMBRAL_SIMILITUD` estaba en la configuración desde la Fase 0 y **no se usaba**.

Sin umbral, la rama vectorial ordena por distancia y entrega los `n` primeros **por lejos que
estén**: siempre devuelve algo. Eso significaba que «no tengo información aprobada» (RF‑O06)
no se habría disparado casi nunca, y el agente habría citado como fuente el documento menos
irrelevante que encontrase —exactamente el fallo que esa regla existe para impedir.

La distancia coseno de pgvector va de 0 a 2 y la similitud es `1 − distancia`, así que un
umbral de 0,35 se traduce en una distancia máxima de 0,65. **El valor debe recalibrarse con
el modelo real**: lo que es «parecido» depende del modelo.

### El `AND` implícito de la búsqueda textual

`websearch_to_tsquery` une todos los términos con **AND**. La pregunta «cuántas horas de
ayuno necesito para el examen de sangre» solo encontraba un documento que contuviera *todas*
esas palabras —es decir, casi ninguno—. La rama textual no aportaba prácticamente nada, y no
se notaba porque la vectorial devolvía todo.

Se reescriben los `&` por `|` **sobre el `tsquery` ya construido**, no sobre el texto del
usuario: la consulta sigue pasando por `websearch_to_tsquery` como parámetro enlazado, así
que no hay forma de inyectar operadores. Con OR, el documento aparece si contiene alguna
palabra y `ts_rank_cd` lo ordena por cuántas y con qué peso —que es lo que se quiere de un
ranking que luego se fusiona.

**Cada fallo tapaba al otro.** Corregir el primero hizo fallar las pruebas de fuga, y eso
destapó el segundo.

### La fusión RRF

Opera sobre las **posiciones**, no sobre las puntuaciones: la distancia coseno y `ts_rank_cd`
están en escalas distintas y normalizarlas exigiría calibrarlas con datos. `K = 60` es el
valor del artículo original; amortigua la diferencia entre las primeras posiciones para que
el primero de una lista no aplaste a los demás.

`RAG_PESO_VECTORIAL` (0,6) reparte el peso entre ambas ramas.

### Por qué existe la mitad textual

La semántica sola falla justo donde más se nota: **el nombre exacto de un examen o de un
medicamento**, que el modelo de embeddings no distingue de sus vecinos. La configuración
`espanol_sin_tildes` aplica `unaccent` antes de derivar, así que «preparación» en el
documento y «preparacion» en la consulta coinciden —sin eso, media base de conocimiento
sería invisible según cómo escribiera cada uno.

---

## 5. Evaluación (RF‑O08)

Medido el **2026‑09‑12**, con el proveedor simulado, sobre un corpus de 5 documentos y 10
preguntas escritas como las haría un paciente (no copiando el texto del documento):

| Métrica | Valor |
|---|---|
| Hit@1 | **80 %** |
| Hit@3 | **100 %** |
| Hit@5 | **100 %** |
| Resultados por consulta | mín. 1, máx. 4, media **2,5** de 5 documentos |
| Pregunta sin documentación | **0 resultados** (antes de la corrección: 5) |

**Qué mide esto y qué no.** El proveedor simulado deriva el vector del hash del texto y no
entiende nada, así que la mitad vectorial aporta ruido y **lo que hace acertar es la mitad
textual**. Sigue siendo útil por dos motivos:

1. Mide el **suelo**. Si la búsqueda encuentra el documento correcto incluso con la mitad
   vectorial ciega, el fallo de un caso nuevo apunta al filtro o a la fusión, no al modelo.
2. Los **casos negativos no dependen del modelo en absoluto**. Un documento archivado,
   vencido o de otra sede no se recupera por el `WHERE`, no por el vector. Un cero ahí es un
   cero de verdad.

Los umbrales de la suite (Hit@3 ≥ 80 %, Hit@1 ≥ 70 %) quedan por debajo de lo medido para que
un cambio menor no la rompa. **Bajarlos para que pase una prueba sería falsear la
evaluación**, y así está escrito en el archivo.

La medición con el modelo real está pendiente y es lo que cierra la
[limitación E‑9](known-limitations.md).

---

## 6. Defensa contra inyección de prompt

Razonada en [ADR‑0014](decisiones/0014-defensa-prompt-injection.md). Hay **dos** defensas y
conviene no confundirlas.

### La que de verdad protege

El agente **no escribe en la base de datos ni ejecuta nada por su cuenta**. Solo invoca las
herramientas de `app/ia/herramientas/`, que pasan por la capa de servicios con el principal y
el ámbito del solicitante (CLAUDE.md, regla 4). Una inyección que convenza al modelo de
«cancelar la cita 123» no consigue nada: la herramienta comprueba permisos igual que si la
invocara una persona.

### La que reduce la superficie

* **Al ingerir** se analiza el texto contra un catálogo de patrones. El resultado se guarda
  **completo** —qué patrones y dónde— en `resultado_analisis_inyeccion`: ante un documento
  marcado hay que poder explicarle al autor por qué, y un falso positivo solo se corrige
  viendo qué lo disparó.
* **Se marca, no se rechaza.** Un protocolo legítimo puede contener «ignore las indicaciones
  previas si hay fiebre». Lo que se bloquea es la **aprobación**, hasta que una persona lo
  revise de forma explícita con nota y fecha. Y esa revisión exige el permiso de aprobación:
  **quien sube el archivo no puede levantar su propia alerta**.
* **Se busca sobre el texto normalizado** —sin tildes, sin caracteres invisibles, con espacios
  colapsados—. La evasión más barata es escribir «ignóra» o meter un espacio de ancho cero en
  medio de la palabra, y normalizar las neutraliza sin una carrera de patrones imposible de
  ganar.
* **Al construir el prompt**, el contenido va envuelto entre delimitadores con una
  advertencia **antes y después**: lo último que lee un modelo pesa más, así que ponerla solo
  al principio deja el ataque en la posición más favorable.
* **El contenido no puede cerrar el bloque.** Es el único ataque que el saneado detiene por
  completo, y por eso existe: si el documento incluyera la cadena de cierre, lo que siguiera
  quedaría fuera del bloque y el modelo lo leería como instrucción del sistema.

Seis pruebas comprueban que **el texto clínico legítimo no se marca**. Una detección que
marca todo no la mira nadie.

> **Ninguna defensa contra inyección de prompt es completa** (limitación E‑3). Lo que se
> afirma es acotado: que una inyección no otorga acceso a datos no autorizados ni capacidad
> de escritura, porque esas capacidades no existen detrás del modelo. **No** se afirma que el
> modelo sea inmune a decir algo incorrecto.

---

## 7. Ciclo de vida de un documento

```
   DRAFT ──► PENDING_REVIEW ──► APPROVED ──► PUBLISHED
     ▲            │   │             │            │
     └────────────┘   │             │            │
     (el revisor      │             │            │
      pide cambios)   │             ▼            ▼
                      │        ┌─────────────────┐
                      │        │   retirar para  │
                      │        │    corregir     │──► DRAFT
                      │        └─────────────────┘
                      ▼             │            │
                  ARCHIVED ◄────────┴────────────┘   (terminal)
```

**`APPROVED → DRAFT` existe por un caso concreto** que la primera versión de la máquina de
estados no cubría: alguien detecta que el protocolo dice 8 horas de ayuno y son 12. Sin ese
camino, la única salida sería archivar y crear un documento nuevo —perdiendo la identidad y
el historial de versiones por corregir una cifra—, y mientras tanto el agente seguiría
citando el dato equivocado. Volver a borrador retira los fragmentos de la recuperación en el
acto, porque heredan el estado.

`ARCHIVED` es **terminal**. Permitir el regreso haría que la fecha de archivado dejara de
significar nada.

### Reglas que el motor sostiene

| Restricción | Qué impide |
|---|---|
| `aprobado_con_responsable` | Un documento aprobado sin constancia de quién lo aprobó (RF‑M04) |
| `aprobado_exige_version` | Un documento aprobado y **vacío**: el agente lo contaría como fuente y no devolvería nada |
| `vigencia_coherente` | Una vigencia que termina antes de empezar |
| `archivado_con_fecha` | Un archivado sin cuándo |
| `uq_knowledge_embeddings_chunk_modelo` | Que un reindexado a medias deje dos vectores del mismo modelo y el fragmento aparezca duplicado |

### Subir contenido no lo hace recuperable

Una versión nueva **no cambia el estado del documento**. Un documento publicado sigue
publicado con su versión vigente mientras la nueva se revisa. Si subir contenido devolviera
el documento a borrador, el agente se quedaría sin la versión aprobada que sí estaba en uso;
y si lo publicara, subir un archivo sería la vía para colar texto sin aprobar.

---

## 8. Fragmentación

| Parámetro | Valor | Por qué |
|---|---|---|
| `RAG_TAMANO_FRAGMENTO` | 900 car. | Más grande diluye el parecido —el vector promedia varios temas—; más pequeño pierde el contexto |
| `RAG_SOLAPE_FRAGMENTO` | 150 car. | **Una instrucción puede quedar partida por la mitad** |

El solape no es una precaución abstracta: «No comer nada desde las 22:00. / Puede beber agua»
en dos fragmentos sin solape produce uno que dice que no coma nada y otro que dice que beba
agua. Recuperar solo el primero da una respuesta incompleta sobre una preparación de examen.

Se corta en límites naturales —párrafo, luego frase, y solo si no hay más remedio a mitad de
frase—. Cortar por número de caracteres parte palabras y produce fragmentos que empiezan a
media frase, peor tanto para la búsqueda textual como para quien revisa por qué el agente
respondió algo.

Los fragmentos por debajo de 80 caracteres se fusionan con el siguiente: «## Preparación»
recuperado por sí solo no responde nada.

---

## 9. Lo que no está indexado, y no por descuido

**La historia clínica individual no se indexa en un índice vectorial global** (RF‑M07). La
información del paciente llega al agente desde datos estructurados de PostgreSQL, ya
filtrados por relación asistencial.

El motivo es que un índice vectorial compartido es exactamente el tipo de estructura donde
una fuga entre pacientes es difícil de detectar: no falla, simplemente devuelve el fragmento
de otra persona con buena puntuación. Si algún día hace falta, será una tabla con
`paciente_id` obligatorio en el mismo patrón de pre‑filtro.

---

## 10. Configuración

| Variable | Valor | Para qué |
|---|---|---|
| `PROVEEDOR_EMBEDDINGS` | `fastembed` \| `mock` | Un modo desconocido **falla**, no cae al simulado |
| `MODELO_EMBEDDINGS` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Multilingüe, 384 dimensiones. `intfloat/multilingual-e5-small` no existe en fastembed 0.7. Los prefijos `passage:`/`query:` solo se aplican a modelos E5 |
| `DIMENSION_EMBEDDINGS` | 384 | Cambiarla exige migración: `vector(n)` lleva la dimensión en el esquema |
| `RAG_TOP_K` | 8 | Fragmentos devueltos (tope duro: 20) |
| `RAG_TOP_K_CANDIDATOS` | 40 | Candidatos por ranking antes de fusionar |
| `RAG_UMBRAL_SIMILITUD` | 0,35 | **Recalibrar con el modelo real** |
| `RAG_PESO_VECTORIAL` | 0,6 | Reparto entre las dos ramas |
| `RAG_EXIGIR_FUENTE` | `true` | No se desactiva |

### El proveedor simulado

Deriva el vector de SHA‑256 del texto normalizado. Es determinista —dos ejecuciones dan el
mismo vector—, instantáneo y no descarga nada. **No mide parecido semántico.**

Existe por dos motivos: el modelo real descarga cientos de megabytes (inviable en CI limpio y
en este equipo, ADR‑0003), y sobre todo porque **la recuperación debe ser reproducible**: una
prueba que afirma «este documento se recupera antes que aquel» solo vale si los vectores son
los mismos en cada ejecución.

Se identifica como `simulado:sha256` en la columna `modelo`, así que si un vector de pruebas
acabara en una base real se ve de un vistazo.

---

## 11. Endpoints y permisos

| Endpoint | Permiso | Nota |
|---|---|---|
| `GET /conocimiento/documentos` | `conocimiento.leer` | Solo los de la clínica |
| `POST /conocimiento/documentos` | `conocimiento.cargar` | Nace en `DRAFT` |
| `POST /…/{id}/versiones` | `conocimiento.cargar` | **No cambia el estado** |
| `POST /…/{id}/estado` | `cargar` + `aprobar` o `archivar` según el destino | Quien carga no aprueba |
| `POST /…/{id}/revision-de-riesgo` | `conocimiento.aprobar` | Quien sube no levanta su propia alerta |
| `POST /conocimiento/busqueda` | `conocimiento.leer` | Se audita con las **fuentes** |

**La auditoría registra las fuentes, no la consulta.** El texto puede contener el motivo por
el que alguien pregunta —«me duele el pecho, preparación para…»— y eso es información de
salud. Lo que hay que poder reconstruir ante «por qué el agente le dijo esto a un paciente»
es qué documentos se usaron. Hay una prueba que lo comprueba.

---

## 12. Qué falta

1. **El agente conversacional.** Esto es la recuperación; falta quien la use, con sus
   herramientas (`find_availability`, `handoff_to_human`…) y su memoria de conversación.
2. **Medir con el modelo real** (E‑9). Hasta entonces, las cifras de la sección 5 miden el
   suelo, no la calidad.
3. **PDF escaneados y texto visualmente oculto.** El servidor extrae texto seleccionable de
   documentos de hasta 20 MB, 200 páginas y 500 000 caracteres; rechaza cifrado y acciones
   activas. En producción ClamAV es obligatorio. Este entorno de desarrollo no tiene ClamAV
   conectado; la API y la pantalla avisan que el análisis no está disponible. No se conserva el PDF.
   OCR y análisis de capas/posición del texto no están implementados.
4. **La reanudación de ingesta la hace el worker.** La fuente y el trabajo se guardan antes de
   generar embeddings. El barrido de ARQ recoge cada minuto hasta diez trabajos `PENDIENTE`;
   `FOR UPDATE SKIP LOCKED` permite repartirlos entre réplicas y el procesamiento es
   transaccional e idempotente. Si el proveedor falla de forma controlada, el trabajo queda
   `FALLIDA` y no se reintenta en bucle; después de corregir el proveedor, el mismo contenido
   permite reintentar la misma versión. La copia temporal se elimina al completar.
5. **Reindexado al cambiar de modelo.** La columna `modelo` permite convivir con dos.
   `uv run python -m herramientas.reindexar_conocimiento` genera los vectores que faltan para
   el modelo configurado; es idempotente y no toca el texto. No corre solo: se lanza tras
   cambiar `PROVEEDOR_EMBEDDINGS` o `MODELO_EMBEDDINGS`.
6. **Latencia bajo carga** (RNF‑03, P95 < 2 s). Sin medir: HNSW con pre‑filtro puede
   necesitar explorar más grafo para reunir `k` candidatos, y eso solo se ve con volumen.

La recuperación filtra `knowledge_chunks.vigente` junto con estado, clínica, vigencia y ACL.
Para cargar cambios a un documento aprobado o publicado, primero se devuelve a borrador;
el contenido deja de responder hasta que la versión nueva se revisa y aprueba. Las versiones
históricas permanecen para trazabilidad, pero nunca vuelven a las respuestas del RAG.

La preparación durable se confirma antes de calcular embeddings. Si el proveedor falla, la
API devuelve 503, deja el trabajo `FALLIDA` con un mensaje saneado y conserva temporalmente
el texto fuente. Al reintentar el mismo contenido, recupera la misma versión. El indexado y
el cambio de versión vigente se confirman en una sola transacción.

---

## 13. Evidencia

```
uv run pytest -m rag -q          →  82 passed (80 anteriores + 2 rutas PDF)
uv run pytest -q                 →  1140 passed
uv run pytest --cov=app          →  92,0 %
uv run ruff check . ; mypy app   →  sin hallazgos
alembic upgrade/downgrade/upgrade → reversible
```

Verificado en el motor:

```
\d knowledge_embeddings
  → "ix_knowledge_embeddings_hnsw" hnsw (embedding vector_cosine_ops)
       WITH (m='16', ef_construction='64')

SELECT is_generated, generation_expression FROM information_schema.columns
  WHERE table_name='knowledge_chunks' AND column_name='contenido_tsv';
  → ALWAYS | to_tsvector('espanol_sin_tildes'::regconfig, contenido)
```

| Suite | Casos | Qué cubre |
|---|---|---|
| `test_rag_fugas.py` | 21 | Siete casos negativos, cada uno con su prueba de control |
| `test_conocimiento_api.py` | 23 | Separación de permisos, auditoría sin la consulta, ingesta PDF |
| `test_conocimiento_archivos.py` | 10 | Tipo, tamaño, páginas/texto, acciones activas, cifrado, texto extraíble y antivirus |
| `test_fragmentacion.py` | 19 | Cortes, solape, parámetros inválidos |
| `test_embeddings.py` | 13 | Determinismo, normalización, selección de proveedor |
| `test_conocimiento.py` | 23 | Ciclo de vida, propagación a fragmentos y recuperación exclusiva de la versión vigente |
| `test_saneamiento.py` | 34 | Patrones, evasiones, falsos positivos |
| `test_recuperador.py` | 9 | Contexto citado, sin fuente |
| `test_evaluacion_rag.py` | 7 | Hit@K y casos negativos deliberados |
| `test_arquitectura_rag.py` | 6 | Una sola puerta a `knowledge_chunks`, y que el sembrador solo escribe |

Además, **31 comprobaciones sobre la API arrancada** con los datos sembrados: listado,
búsqueda con y sin respuesta, que el borrador y el archivado no se recuperan, el ciclo de
vida completo, el bloqueo por inyección con su revisión manual, y la retirada para corregir.
0 fallos.

Las semillas cargan **9 documentos en los cinco estados** (`--embeddings mock` evita
descargar el modelo). Que no todos estén publicados es deliberado: un conjunto donde todo es
recuperable no permite comprobar a mano que un borrador **no** aparece.
