# ADR‑0007 — Proveedores de IA abstractos: Claude para LLM, fastembed local para embeddings

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

La especificación exige una capa abstracta (`LLMProvider`, `EmbeddingProvider`,
`KnowledgeRetriever`, `AgentTools`, `ConversationMemory`) sin acoplar la aplicación a un
proveedor concreto, con credenciales por variable de entorno.

Inventario de credenciales y modelos disponibles:

* `ANTHROPIC_API_KEY` **presente** en el entorno del usuario.
* **Sin** claves de OpenAI, Voyage, Google ni Cohere → no hay proveedor de embeddings en
  la nube disponible.
* Ollama instalado con `llama3.2:3b` y `qwen3:4b`, **sin modelo de embeddings**
  descargado, y el servicio no estaba en ejecución.

Un detalle determinante: la API de Claude no ofrece un endpoint de embeddings, así que el
LLM y los embeddings tienen que resolverse por separado.

## Decisión

Tres implementaciones por interfaz, seleccionables por variable de entorno:

| Interfaz | Implementaciones | Por defecto en local | En CI |
|---|---|---|---|
| `LLMProvider` | `anthropic`, `ollama`, `mock` | `mock` | `mock` |
| `EmbeddingProvider` | `fastembed`, `ollama`, `mock` | `fastembed` | `mock` |

* **LLM: Claude.** La clave se lee exclusivamente de `ANTHROPIC_API_KEY`; no se escribe
  en el código, ni en `.env.example`, ni en las pruebas. Modelo configurable en
  `MODELO_LLM`.
* **Embeddings: `fastembed`** con `intfloat/multilingual-e5-small` (384 dimensiones),
  ejecutado en local vía ONNX. No requiere credencial, funciona sin red y es
  multilingüe, lo que importa porque el corpus está en español.
* **Mocks deterministas** para las pruebas: el LLM simulado responde según reglas
  declaradas y el de embeddings produce vectores estables a partir de un hash del texto.
  Así las pruebas de RAG son reproducibles y el CI no consume cuota ni red.

## Consecuencias

* El CI no necesita ninguna credencial de IA y las pruebas de RAG son deterministas.
* `DIMENSION_EMBEDDINGS` debe coincidir con la dimensión declarada en la migración de
  `pgvector`. Cambiar de modelo de embeddings exige una migración y **reindexar todo el
  corpus**; se documenta el procedimiento en [`../rag.md`](../rag.md).
* La calidad de recuperación de un modelo local pequeño es inferior a la de los
  embeddings comerciales grandes. No se asume: se mide con el arnés de evaluación
  (Hit@K, precisión, fundamentación) y el resultado se publica en
  [`../rag.md`](../rag.md). Si no alcanza el umbral, la decisión se revisa.
* Los modelos locales de Ollama (3B y 4B) se consideran insuficientes para el
  razonamiento del agente clínico y quedan solo como alternativa de desarrollo sin red.
* Riesgo de privacidad: enviar texto a un proveedor externo de LLM implica tratamiento de
  datos por un tercero. El agente **no** envía historia clínica al LLM; envía datos
  estructurados mínimos y fragmentos de conocimiento aprobado. Es un punto que requiere
  revisión legal y acuerdo con la clínica, listado en [`../security.md`](../security.md).
