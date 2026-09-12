# Estado de preparación para producción

> **Última actualización:** 2026‑09‑12 · Fases 0, 0b, 3 y 4 (WhatsApp) cerradas.
>
> **Veredicto actual: el sistema NO está preparado para producción y no puede usarse con
> datos de pacientes reales.** No es una fórmula de cautela. Hay tres motivos concretos, y
> ninguno se resuelve escribiendo más código: el cumplimiento legal no está validado (E‑2),
> la restauración de copias no está probada —y un respaldo sin restauración verificada no
> cuenta—, y el camino real de WhatsApp no se ha ejecutado nunca contra Meta (E‑1).
>
> La tabla siguiente refleja el estado **verificado**, no el planificado. `parcial` significa
> que hay evidencia de una parte y no del resto; se detalla cuál en cada fila.

---

## 1. Criterios de producción

Los 21 criterios exigidos, con su estado real. `no evaluado` significa que la
funcionalidad no existe todavía; **no** significa que esté bien.

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | No hay errores críticos | **parcial** | 899 pruebas en verde, `ruff`/`mypy --strict` sin hallazgos. Pero sin E2E, sin carga y sin DAST, «no hay errores críticos» es una afirmación que no se puede sostener |
| 2 | Sin vulnerabilidades críticas o altas pendientes | **parcial** | `pip-audit --strict` → sin vulnerabilidades conocidas; `bandit -r app -ll` sin hallazgos. 44 vulnerabilidades corregidas (ver informe). **Falta DAST y Trivy sobre imágenes construidas** |
| 3 | No existen secretos en el repositorio | **parcial** | `.env` excluido, `.env.example` sin un valor real, secretos de prueba sintéticos. `gitleaks` **no está instalado localmente**; corre en el pipeline, que nunca se ha ejecutado |
| 4 | Las reservas concurrentes no generan duplicados | **verificado** | Restricción de exclusión `gist`; prueba de concurrencia real con 50 participantes y `asyncio.Barrier` sobre conexiones separadas |
| 5 | La lista de espera funciona automáticamente | **parcial** | Servicios y una sola oferta activa por turno verificados; **faltan rutas HTTP y el disparo automático al liberarse un turno** |
| 6 | Los calendarios se sincronizan | **no evaluado** | Fase 4b. **Sin credenciales de Google y sin implementar** |
| 7 | Los recordatorios son persistentes y reintentables | **parcial** | El outbox está verificado: deduplicación por restricción única, retroceso exponencial con tope, recuperación de huérfanos, `FOR UPDATE SKIP LOCKED` (25 pruebas de integración). **Falta el planificador que crea los recordatorios** al confirmar una cita o una receta, y la entrega real contra Meta (E‑1) |
| 8 | Los permisos impiden accesos indebidos | **verificado** | Permiso + ámbito de 4 dimensiones + relación asistencial, aplicados en el `WHERE`. 404 y no 403 fuera de ámbito. 355 pruebas con marcador `seguridad`. Tres fallos propios del filtro de ámbito encontrados y corregidos |
| 9 | La historia clínica está protegida | **verificado** | Append‑only por disparador, versionado con autor y motivo, atacado con SQL directo en las pruebas |
| 10 | Los medicamentos solo usan recetas aprobadas | **verificado** | Disparador `toma_exige_receta_confirmada`; los PRN no generan horarios fijos |
| 11 | La IA no modifica datos sin autorización | **no evaluado** | Las herramientas del agente no existen todavía (Fase 6). Lo que sí existe: el servicio clínico rechaza a un principal con `es_agente`, y el webhook **no ejecuta ninguna intención que cambie una cita** (ADR‑0017) |
| 12 | El RAG no filtra información entre pacientes | **no evaluado** | Fase 6. Diseñado en ADR‑0013 |
| 13 | Los documentos vencidos no son recuperados | **no evaluado** | Fase 6 |
| 14 | Los respaldos se pueden restaurar | **no evaluado** | Fase 10. **Un respaldo sin restauración probada no cuenta** |
| 15 | El sistema soporta las pruebas de carga definidas | **no evaluado** | Fase 10 |
| 16 | El pipeline CI/CD está funcionando | **parcial** | 7 trabajos y puerta de fusión escritos; YAML validado y cada puerta comprobada a mano en local. **Nunca ejecutado en GitHub**: el repositorio no tiene remoto |
| 17 | Existe documentación de operación | **parcial** | 18 documentos y 17 ADR. Faltan `monitoring.md`, `backup-and-restore.md`, `incident-response.md`, `calendar-integration.md`, `rag.md` |
| 18 | Existe procedimiento de rollback | **parcial** | El rollback de esquema **sí está verificado** (`upgrade → downgrade -1 → upgrade` en cada migración). El rollback de despliegue está documentado y sin probar |
| 19 | Existe procedimiento de restauración | **parcial** | Documentado, sin ejecutar |
| 20 | Existe monitoreo | **no evaluado** | Fase 10. Ya hay eventos que exigen vigilancia y nadie los vigila: la cola `FALLIDO` del outbox, `limite_tasa.sin_contador.permitido` y `whatsapp.numero_sin_clinica` |
| 21 | Pruebas de aceptación con escenarios de clínica | **no evaluado** | Fase 10. Los 21 escenarios E2E no existen |
| 22 | Todas las limitaciones documentadas | **hecho** | 16 limitaciones estructurales en [`known-limitations.md`](known-limitations.md) |
| 23 | Notificaciones sin datos clínicos | **verificado** | 40 pruebas recorren el catálogo completo de plantillas: ninguna admite ni menciona diagnóstico, medicamento ni motivo de consulta (regla 10, RF‑K07) |

**Resumen: 6 de 23 verificados, 10 parciales, 7 sin evaluar.**

El criterio 23 se añade en la Fase 4: no estaba en la lista original y es una condición de
protección de datos que sí se puede verificar y se ha verificado.

---

## 2. Bloqueos que no se resuelven escribiendo código

Estos cuatro puntos permanecerán abiertos aunque todas las fases técnicas se completen.
Dependen del usuario y de terceros.

| # | Bloqueo | Quién lo resuelve | Consecuencia si no se resuelve |
|---|---|---|---|
| **B‑1** | **Revisión jurídica en Ecuador** (19 puntos en `security.md`) | El usuario con un profesional jurídico y la clínica | **No se puede operar con pacientes reales.** Es el bloqueo de mayor prioridad del proyecto (riesgo L‑01) |
| **B‑2** | Credenciales de WhatsApp Business, número verificado y aprobación de las 10 plantillas por Meta | El usuario y Meta | **El código real está escrito y no se ha ejecutado contra Meta.** Lo verificado es todo lo que rodea al envío (outbox, deduplicación, reintentos, firma, conciliación). Lo que falta es concreto: que Meta acepte el cuerpo que construye `AdaptadorWhatsAppCloud`, que sus códigos de error sean los de `CODIGOS_PERMANENTES` y que las plantillas se aprueben con el texto de `plantillas.py`. Los 6 pasos de cierre están en la sección 7 de [`whatsapp-integration.md`](whatsapp-integration.md) |
| **B‑3** | Proyecto de Google Cloud con OAuth verificado | El usuario y Google | La sincronización real de calendarios queda sin verificar |
| **B‑4** | Entorno de alojamiento de producción, dominio y TLS | El usuario | Sin HTTPS público no hay webhook de Meta y no hay producción |

---

## 3. Condiciones mínimas para declarar preparación

No se declarará el sistema listo hasta que **todas** se cumplan con evidencia:

1. Los 22 criterios de la sección 1 en estado `hecho`, cada uno con la salida real de la
   prueba que lo verifica.
2. Ejecución completa de la suite: unitarias, integración, API, extremo a extremo,
   concurrencia, seguridad, RAG, carga y recuperación.
3. Cobertura de backend ≥ 80 % y de frontend ≥ 70 %, medida y publicada.
4. Cero vulnerabilidades críticas o altas sin justificación formal y plan de corrección
   con fecha.
5. Restauración de respaldo ejecutada sobre una instancia limpia, con comparación de
   recuentos de filas.
6. Rollback de versión y de migración ejecutados en preproducción.
7. Los 21 escenarios de aceptación clínica en verde.
8. **Verificación contra los proveedores reales** de WhatsApp y Google en
   preproducción, no solo contra el sandbox.
9. **Revisión jurídica completada** y decisiones de la clínica registradas sobre
   retención, consentimientos y nivel de verificación de pacientes.
10. Monitoreo activo con alertas y umbrales definidos.

---

## 4. Historial de evaluaciones

| Fecha | Fase | Veredicto |
|---|---|---|
| 2026‑09‑11 | 0 | **No preparado.** Análisis, arquitectura, modelo de datos, modelo de amenazas, matriz de permisos y backlog documentados. Sin código funcional. Cuatro bloqueos externos identificados |
| 2026‑09‑12 | 0b, 2, 3, 7, 5 | **No preparado.** Infraestructura, modelo de datos (49 tablas), autenticación, RBAC con ámbito, agenda con anti doble‑reserva verificado bajo concurrencia real, historia clínica append‑only y lista de espera. Tres fallos propios del filtro de ámbito encontrados **ejerciendo el sistema** con la suite en verde |
| 2026‑09‑12 | 4 (WhatsApp) | **No preparado.** Outbox de entrega, catálogo de plantillas sin datos clínicos y webhook con firma validada, verificados con 236 pruebas contra PostgreSQL real y 33 comprobaciones sobre la API arrancada. Ese ejercicio manual encontró, con 891 pruebas en verde, que **una `BAJA` por WhatsApp no daba de baja al paciente** por el formato del número; corregido con un índice funcional y 6 pruebas de regresión. **El camino real hacia Meta no está verificado** y así se declara (E‑1). Se corrigió además la medición de cobertura del proyecto, que llevaba varias fases mal medida por el greenlet de SQLAlchemy async |
