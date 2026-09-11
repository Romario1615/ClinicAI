# ADR‑0013 — RAG híbrido con los filtros de permiso dentro del SQL

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

La base de conocimiento debe filtrarse por permisos, especialidad, sede y vigencia, y la
evaluación exige demostrar cero fugas entre pacientes y entre especialidades, y que los
documentos archivados o vencidos nunca se recuperan.

Hay dos formas de aplicar esos filtros:

1. **Post‑filtro:** recuperar los `k` fragmentos más similares y descartar después los no
   autorizados. Es el patrón más común en los tutoriales de RAG y tiene dos fallos
   graves. El primero es de seguridad: cualquier olvido en el descarte convierte la
   búsqueda en una fuga. El segundo es funcional: si los `k` más similares pertenecen
   todos a otra sede, el resultado queda vacío aunque existiera documentación válida.
2. **Pre‑filtro en SQL:** el motor solo considera fragmentos autorizados.

## Decisión

**Los filtros van en la cláusula `WHERE` de la consulta SQL, nunca como paso posterior en
Python.** La recuperación es una única sentencia contra PostgreSQL que combina:

* **Búsqueda semántica:** `pgvector` con índice HNSW y distancia coseno.
* **Búsqueda textual:** `tsvector` con configuración `spanish` más `pg_trgm` para
  tolerar errores de escritura y buscar coincidencias exactas de términos como el nombre
  de un examen.
* **Fusión RRF** (Reciprocal Rank Fusion) de ambos rankings, con el peso relativo en
  `RAG_PESO_VECTORIAL`. RRF se elige porque opera sobre las posiciones y no exige
  normalizar puntuaciones de escalas distintas.

Condiciones obligatorias en el `WHERE`, aplicadas siempre y en el mismo lugar:

```sql
WHERE kc.clinic_id = :clinica_id
  AND (kc.branch_id     IS NULL OR kc.branch_id     = ANY(:sedes_autorizadas))
  AND (kc.specialty_id  IS NULL OR kc.specialty_id  = ANY(:especialidades_autorizadas))
  AND kd.status IN ('APPROVED', 'PUBLISHED')
  AND kc.version = kd.version_vigente
  AND kc.effective_from <= :ahora
  AND (kc.effective_until IS NULL OR kc.effective_until >= :ahora)
  AND kc.sensitivity_level <= :nivel_maximo_solicitante
```

Se implementa en **una sola función** de repositorio,
`buscar_conocimiento_autorizado(...)`, que exige el contexto de autorización como
parámetro obligatorio. No existe ninguna otra vía de consulta a `knowledge_chunks` desde
la capa de IA. Una prueba de arquitectura verifica que ningún otro módulo consulta esas
tablas directamente.

Además, la historia clínica individual **no** se indexa en un índice vectorial global
compartido. La información del paciente llega al agente desde datos estructurados de
PostgreSQL, ya filtrados por relación asistencial. Si en el futuro se añade un índice
vectorial por paciente, será una tabla con `paciente_id` obligatorio en el mismo patrón
de pre‑filtro.

## Consecuencias

* La fuga por filtro olvidado deja de ser posible desde la capa de IA: no hay camino que
  no pase por la función autorizada.
* Un permiso ausente produce «no tengo información aprobada», no una respuesta con datos
  de otra sede.
* Coste de rendimiento: HNSW con pre‑filtro puede necesitar explorar más candidatos para
  devolver `k` resultados. Se compensa con `RAG_TOP_K_CANDIDATOS` y con índices
  compuestos sobre las columnas de filtro. Se mide en las pruebas de carga.
* El arnés de evaluación incluye casos negativos deliberados: documento archivado,
  documento vencido, documento de otra sede y de otra especialidad. Si alguno se
  recupera, la prueba falla.
