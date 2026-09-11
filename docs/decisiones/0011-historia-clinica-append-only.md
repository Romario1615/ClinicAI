# ADR‑0011 — Historia clínica append‑only y versionada

* **Estado:** aceptada
* **Fecha:** 2026‑09‑11

## Contexto

El requisito es explícito: «no sobrescribas silenciosamente notas clínicas», y hay que
conservar usuario creador, fecha, fecha de modificación, versión anterior y motivo de la
modificación. Una historia clínica es también un documento con valor legal: la capacidad
de demostrar qué se escribió, cuándo y por quién es parte de su función.

Un `UPDATE` sobre la fila de la nota destruye la versión anterior. Un disparador de
auditoría que guarde el valor previo ayuda, pero deja el estado válido y el histórico en
sistemas distintos y no captura el motivo del cambio.

## Decisión

Dos tablas por entidad clínica versionable (notas de evolución, diagnósticos,
indicaciones, recetas):

```
nota_evolucion            -- cabecera estable: identidad y puntero a la versión vigente
  id, paciente_id, profesional_id_creador, cita_id
  version_vigente_id, creado_en, estado

nota_evolucion_version    -- inmutable, una fila por versión
  id, nota_evolucion_id, numero_version
  contenido (jsonb estructurado), motivo_consulta, antecedentes,
  indicaciones, diagnosticos
  autor_id, creado_en
  motivo_modificacion        -- obligatorio a partir de la versión 2
  version_anterior_id
```

* Las filas de versión **nunca** se actualizan ni se borran. Editar una nota inserta una
  versión nueva y mueve el puntero `version_vigente_id`.
* `motivo_modificacion` es obligatorio desde la segunda versión. Se aplica con una
  restricción `CHECK`, no solo en la validación de la aplicación.
* Un permiso de revocación por parte del backend impide que la aplicación emita `DELETE`
  sobre las tablas de versión; el rol de base de datos de la aplicación no tiene ese
  privilegio.
* Borrar no existe como operación de negocio: se marca `estado = 'ANULADA'` con motivo, y
  el contenido permanece.

## Consecuencias

* Se puede reconstruir el estado de la historia clínica en cualquier instante pasado.
* La lectura del estado vigente cuesta una unión por el puntero de versión; se resuelve
  con índice y, si hace falta, con una vista materializada.
* Crece el volumen de datos. Aceptable: los registros clínicos tienen periodos de
  conservación legales largos, y la política de retención está en
  [`../security.md`](../security.md).
* La eliminación por solicitud del titular de los datos entra en conflicto con los plazos
  legales de conservación de historia clínica. **Es un punto que requiere revisión
  jurídica**; está listado como pendiente legal y no se resuelve por decisión técnica.
