# Estado de preparación para producción

> **Revisión actual en main (2026-10-07):** faciograma y Documentos y PDF visibles
> desde la ficha, cita conservada y CRUD de clínicas/cuentas probado por rol.
> Frontend 635/635; lint y build aprobados. Chromium 67/67 en 7,7 minutos, axe
> en las 22 rutas y en la ficha facial; cuatro recorridos documentales repetidos
> con la API final. Dos pruebas API verifican que emitir una receta sensible
> conserva N3 y bloquea su entrega por enlace. La regresión global nueva aprobó
> 1921 pruebas y omitió tres de Anthropic real en 10 min 36 s, sin cobertura.
> La corrida GitHub 37716853153 falló por la referencia de Trivy,
> el entorno de las rutas locales y el resumen de semillas; las tres causas
> están corregidas. La nueva corrida 37720408186 del commit funcional 41aa0dd
> aprobó seis trabajos; la suite backend remota seguía en ejecución al registrar
> la evidencia. Esta revisión
> actualiza funcionalidad local; los requisitos de producción siguientes
> continúan pendientes. [Informe](verificacion-2026-10-07.md#faciograma-visible-y-documentos-desde-la-ficha).

Las notas de pruebas siguientes conservan las revisiones anteriores a la
consolidación en main; la revisión vigente es la indicada arriba.

> **Estado actual de la rama (2026-10-07):** `claude/friendly-gates-o240sb` sobre `727c9f5`; frontend 605/605, lint y build pasan. Chromium 62/62 con API/BD temporal, seis roles y axe en 22 rutas. Backend completo: 1855 aprobadas, tres de Anthropic real omitidas y 87,89 % de cobertura en 19 min 39 s. Contrato/métricas 8/8; Ruff, formato, mypy y Bandit `-ll` aprobados. Los seis roles entran y abren su manual propio en los servicios de desarrollo. Las migraciones `029`/`030` están aplicadas y su reversión se verificó en una base vacía. [Informe de verificación](verificacion-2026-10-07.md). El sitio está disponible para revisión local en `http://localhost:4200/acceso`. La validación de proveedores reales y los requisitos de producción detallados abajo siguen pendientes.

> **Última auditoría formal:** 2026‑09‑14. **Actualización de pruebas:** 2026‑10‑07 ·
> La revisión vigente aprobó 1855 pruebas de backend y omitió tres llamadas optativas a Anthropic; cobertura global 87,89 %. Frontend: 605/605; sentencias 86,12 %, ramas 72,88 %, funciones 81,60 %, líneas 88,31 %. Ruff, formato, mypy y Bandit pasan. Las comprobaciones previas de `pip-audit`, Gitleaks y Trivy de las imágenes backend/worker se conservan como evidencia de aquella revisión; esta actualización no cambió dependencias ni Dockerfiles. La verificación combinada de todo el pipeline CI aún no se ha ejecutado en una sola corrida; DAST y pruebas de carga siguen pendientes.
> **E2E actual:** 62/62 pruebas en 6,9 minutos contra API y PostgreSQL temporales. Incluye pantallas de trabajo en escritorio, 320/390 px, pestañas con teclado y las ventanas de anamnesis, notas SOAP, recetas, delegaciones, Formulario MSP 033 e imágenes. Diez recorridos axe cubren seis roles y 22 rutas del menú.
> Los resultados actuales se registran arriba y en `docs/test-plan.md`; las cifras antiguas de auditorías previas se conservan como historial.
> El 2026‑10‑06 también pasaron 5 pruebas API de asignación cuenta/perfil y 17 de administración de pacientes; el escenario E2E de equipo verificó ambos registros vinculados. Las pruebas focalizadas del upload PDF aprobaron 39 casos; 9 pruebas focalizadas del resumen local e historial de pagos también pasaron.
> La revisión añadió alertas automáticas de adherencia con auditoría y cobertura de worker/roles; los bloqueos de producción de este documento siguen vigentes.
>
> **Veredicto actual: el sistema NO está preparado para producción y no puede usarse con
> datos de pacientes reales.** No es una fórmula de cautela. Hay tres motivos concretos, y
> ninguno se resuelve escribiendo más código: el cumplimiento legal **no está validado**
> (E‑2), el camino real de WhatsApp **no se ha ejecutado nunca contra Meta** (E‑1), y
> **nada vigila** los eventos que el sistema emite —la cola `FALLIDO` del outbox puede
> crecer un fin de semana entero sin que nadie lo note.
>
> La restauración **sí** está verificada desde el 2026‑09‑13: era el tercer bloqueo y ha
> dejado de serlo. El procedimiento de incidentes, en cambio, está escrito y **sin
> ensayar**.
>
> La tabla siguiente refleja el estado **verificado**, no el planificado. `parcial` significa
> que hay evidencia de una parte y no del resto; se detalla cuál en cada fila.

---

## 1. Criterios de producción

Los 21 criterios exigidos, con su estado real. `no evaluado` significa que la
funcionalidad no existe todavía; **no** significa que esté bien.

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | No hay errores críticos | **parcial** | Verificación local 2026‑10‑07 sobre `claude/friendly-gates-o240sb`: backend completo 1855 aprobadas, tres de Anthropic real omitidas y 87,89 % de cobertura. Frontend 605/605 y Chromium 62/62. La corrección de la prueba del historial de reprogramación pasa dentro de la suite completa. La corrida CI completa, DAST y carga representativa siguen pendientes |
| 2 | Sin vulnerabilidades críticas o altas pendientes | **parcial** | `pip-audit --strict` y Trivy de ambas imágenes, con severidad HIGH/CRITICAL e ignorando solo hallazgos sin parche, no detectan vulnerabilidades corregibles. Bandit `-ll` sin hallazgos medianos/altos. DAST sigue pendiente |
| 3 | No existen secretos en el repositorio | **verificado localmente** | Gitleaks escaneó el historial completo y no encontró secretos; coincidencias sintéticas de pruebas se revisaron y se registraron por huella en `.gitleaksignore`. La corrida CI sigue pendiente |
| 4 | Las reservas concurrentes no generan duplicados | **verificado** | Restricción de exclusión `gist`; prueba de concurrencia real con 50 participantes y `asyncio.Barrier` sobre conexiones separadas |
| 5 | La lista de espera funciona automáticamente | **parcial** | 55 pruebas focalizadas cubren selección, franjas locales, outbox, expiración, reagendamiento con cita previa, cadena limitada, rollback ante la restricción lXCLUDl y diez aceptaciones concurrentes por servicio y HTTP. Una solicitud obtiene 200 y nueve 409; solo se crea una cita. La **entrega real** del aviso depende de Meta (E‑1) |
| 6 | Los calendarios se sincronizan | **parcial** | El flujo completo esta verificado con adaptador sandbox: OAuth con `state` firmado y de un solo uso, tokens cifrados y ligados al profesional, publicacion, retirada y **reconciliacion de cambios externos** -- borrado y movimiento manual del profesional (85 pruebas). Lo que falta: el **adaptador real de Google** y la renovacion automatica del token de acceso (E‑19). `MODO_CALENDARIO=google` no arranca, a proposito |
| 7 | Los recordatorios son persistentes y reintentables | **parcial** | Los avisos de citas confirmadas se guardan de forma durable (24 h y 3 h); los de tomas se generan al confirmar recetas y cubren solo pautas fijas. Se sustituyen/cancelan al modificar o cerrar su entidad. Un cron cada minuto materializa los vencidos en el outbox; el worker respeta el consentimiento específico y el outbox gestiona deduplicación, reintentos y huérfanos. Los recorridos se probaron contra PostgreSQL aislado. **Falta verificar la entrega real contra Meta** (E‑1)
| 8 | Los permisos impiden accesos indebidos | **verificado** | Permiso + ámbito de 4 dimensiones + relación asistencial, aplicados en el `WHERE`. 404 y no 403 fuera de ámbito. La colección vigente incluye 698 casos con marcador `seguridad`, dentro de la regresión global aprobada. Los tres fallos previos del filtro de ámbito se conservan corregidos |
| 9 | La historia clínica está protegida | **verificado** | Append‑only por disparador, versionado con autor y motivo, atacado con SQL directo en las pruebas |
| 10 | Los medicamentos solo usan recetas aprobadas | **verificado** | Disparador `toma_exige_receta_confirmada`; los PRN no generan horarios fijos |
| 11 | La IA no modifica datos sin autorización | **parcial** | El **bucle del modelo ya existe** y un LLM real invoca el catálogo vigente de ocho herramientas (`app/ia/proveedor_claude.py`, `app/ia/seleccion_llm.py`), verificado previamente contra la API de Anthropic y PostgreSQL (`pruebas/integracion/test_agente_modelo_real.py`, ejecución manual). La herramienta de pagos es solo de lectura. Las garantías de [ADR‑0019](decisiones/0019-la-frontera-de-las-herramientas-del-agente.md) se sostienen con el modelo al mando: catálogo cerrado, ninguna herramienta toca contenido clínico; el principal viaja fuera de los argumentos; el ámbito se verifica contra PostgreSQL real; toda invocación —incluida la denegada— queda auditada como `AGENTE_IA`; el límite clínico se evalúa **antes** del bucle, así que no depende del modelo. Una respuesta inservible del modelo —vacía, truncada, rechazada, con dos invocaciones, o un fallo de red— deriva a una persona (18 pruebas unitarias). Lo que falta: **la calidad de la elección del modelo no está medida** (E‑23), y el webhook sigue sin invocar el bucle (ADR‑0017) — hoy solo lo alcanza el endpoint de demostración, restringido al entorno local |
| 12 | El RAG no filtra información entre pacientes | **verificado** | Los filtros van en el `WHERE` de una consulta única (ADR‑0013), con **21 pruebas de casos negativos** —otra clínica, otra sede, otra especialidad, por encima del nivel— cada una con su prueba de control. La recuperación exige que el fragmento sea de la versión vigente; la migración `20261006_026` y las pruebas verifican que versiones históricas no reaparecen al aprobar una corrección. La historia clínica individual **no se indexa** en ningún índice vectorial (RF‑M07). Una prueba de arquitectura recorre el AST de `app/` y verifica que no hay otra vía de consulta |
| 13 | Los documentos vencidos no son recuperados | **verificado** | Vigencia, estado y archivado filtran en el `WHERE`. Probado con el documento vencido, el que aún no entra en vigor, el archivado y el borrador, incluido el caso en que el texto del documento **son las palabras exactas de la consulta** |
| 14 | Los respaldos se pueden restaurar | **verificado** | Ciclo completo **ejecutado** el 2026‑09‑13 con `infra/scripts/verificar-respaldo.sh`: 11 comprobaciones, 0 fallos. Volcado cifrado no legible en claro, clave incorrecta rechazada, recuentos idénticos uno a uno, `pgvector` 0.8.6 e índice HNSW restaurados, y **las 2 restricciones de exclusión siguen vigentes** — una restauración que las perdiera daría una base que acepta dos pacientes a la misma hora. Lo **no** cubierto se declara en [`backup-and-restore.md`](backup-and-restore.md): sin programación automática, sin retención, sin copia fuera del equipo, sin PITR, sin RTO/RPO medidos |
| 15 | El sistema soporta las pruebas de carga definidas | **parcial** | Ejecutada el 2026‑09‑14 ([`pruebas-carga/`](../pruebas-carga/README.md)): 2 314 peticiones, **0 errores inesperados**, y lo que de verdad importa — **0 reservas duplicadas** con 8 usuarios virtuales peleando por el mismo turno durante 30 s, que produjeron 37 rechazos correctos con 409. Latencia p95: 88 ms en disponibilidad, 161 ms en reserva. **Lo que estos números no dicen**: corren contra un portátil con una base de 384 KB. Faltan carga sostenida de horas, el worker bajo carga y la búsqueda RAG. **Volumen (2026‑10‑08):** con 40 000 pacientes y 200 000 citas sintéticas se registraron las consultas de todas las secciones; cinco recorrían la tabla entera (sala de espera, cancelaciones, ocupación, pacientes nuevos y búsqueda por nombre) y se corrigieron con índices de la migración 036 y dos reescrituras, de ~30–340 ms a < 1 ms por consulta ([`pruebas-carga/`](../pruebas-carga/README.md#volumen-consultas-con-40000-pacientes-y-200000-citas)) |
| 16 | El pipeline CI/CD está funcionando | **parcial** | 7 trabajos y puerta de fusión escritos; YAML validado y cada puerta comprobada a mano en local. El repositorio tiene remoto y recibió actualizaciones de GitHub; esta revisión ejecutó las pruebas locales y no comprobó el resultado de GitHub Actions |
| 17 | Existe documentación de operación | **parcial** | 24 documentos y 19 ADR. Ya existen `monitoring.md`, `backup-and-restore.md` e `incident-response.md`. Lo que falta no es documentación: **el procedimiento de incidentes no se ha ensayado** y no hay guardia definida |
| 18 | Existe procedimiento de rollback | **parcial** | El rollback de esquema **sí está verificado** (`upgrade → downgrade -1 → upgrade` en cada migración). El rollback de despliegue está documentado y sin probar |
| 19 | Existe procedimiento de restauración | **verificado** | Documentado **y ejecutado** ([`backup-and-restore.md`](backup-and-restore.md), sección 3). Restaura sobre una base nueva, nunca sobre la dañada |
| 20 | Existe monitoreo | **parcial** | [`monitoring.md`](monitoring.md) define las señales; `/metrics`, Prometheus local (15 días) y cuatro reglas se probaron con el objetivo Windows/WSL `UP`. El perfil local no entrega avisos: faltan Alertmanager, destinatarios, guardia, señales de auditoría/Redis y despliegue de producción |
| 21 | Pruebas de aceptación con escenarios de clínica | **parcial** | La suite E2E actual aprobó **62/62 pruebas** contra navegador, frontend, API y PostgreSQL aislados ([`pruebas-e2e/`](../pruebas-e2e/README.md)); cubrió reservas, exportación agregada, equipo, sedes, menú móvil, pantallas de trabajo, ventanas clínicas, carga de imágenes y axe en 22 rutas. Siguen pendientes la reserva por WhatsApp simulado (depende de E‑23), reglas de prioridad/escalado de reportes clínicos y aceptación clínica integral; el reporte explícito ya crea un aviso persistente y auditado que el equipo autorizado puede marcar como revisado |
| 22 | Todas las limitaciones documentadas | **hecho** | 24 limitaciones estructurales y 9 restricciones deliberadas en [`known-limitations.md`](known-limitations.md) |
| 23 | Notificaciones sin datos clínicos | **verificado** | 40 pruebas recorren el catálogo completo de plantillas: ninguna admite ni menciona diagnóstico, medicamento ni motivo de consulta (regla 10, RF‑K07) |
| 24 | Los eventos del calendario externo no contienen datos clínicos | **verificado** | RF‑I09. `construir_evento` **no acepta** paciente ni servicio, y una prueba inspecciona su firma para que siga siendo así. Comprobado también sobre lo que de verdad sale hacia el proveedor (ADR‑0018) |

**Resumen: 10 de 24 verificados, 13 parciales, 0 sin evaluar, 1 hecho** (el 22, que no es
un criterio de funcionamiento sino de documentación).

Se mueven en la auditoría original: el criterio 14 y el 19 pasan a **verificado** con la
restauración ejecutada; el 20 y el 21 pasan de «no evaluado» a **parcial** — ya existe la
definición de qué vigilar y la suite E2E actual aprobó 62/62 escenarios. El monitoreo
local no entrega avisos; todavía faltan los escenarios que dependen de proveedores
reales y la aceptación clínica integral.

El 15 también deja de estar sin evaluar: la prueba de carga se ejecutó. **Ya no queda
ningún criterio sin evaluar**; los 13 parciales lo son por razones concretas que cada
fila detalla, no por falta de medición.

Los criterios 23 y 24 se añaden en la Fase 4: no estaban en la lista original y son
condiciones de protección de datos que sí se pueden verificar, y se han verificado.

---

## 2. Bloqueos que no se resuelven escribiendo código

Estos cuatro puntos permanecerán abiertos aunque todas las fases técnicas se completen.
Dependen del usuario y de terceros.

| # | Bloqueo | Quién lo resuelve | Consecuencia si no se resuelve |
|---|---|---|---|
| **B‑1** | **Revisión jurídica en Ecuador** (19 puntos en `security.md`) | El usuario con un profesional jurídico y la clínica | **No se puede operar con pacientes reales.** ls el bloqueo de mayor prioridad del proyecto (riesgo L‑01) |
| **B‑2** | Credenciales de WhatsApp Business, número verificado y aprobación de las 10 plantillas por Meta | El usuario y Meta | **El código real está escrito y no se ha ejecutado contra Meta.** Lo verificado es todo lo que rodea al envío (outbox, deduplicación, reintentos, firma, conciliación). Lo que falta es concreto: que Meta acepte el cuerpo que construye `AdaptadorWhatsAppCloud`, que sus códigos de error sean los de `CODIGOS_PERMANENTES` y que las plantillas se aprueben con el texto de `plantillas.py`. Los 6 pasos de cierre están en la sección 7 de [`whatsapp-integration.md`](whatsapp-integration.md) |
| **B‑3** | Proyecto de Google Cloud con OAuth verificado | El usuario y Google | La sincronización real de calendarios queda sin verificar |
| **B‑4** | Entorno de alojamiento de producción, dominio y TLS | El usuario | Sin HTTPS público no hay webhook de Meta y no hay producción |

---

## 3. Condiciones mínimas para declarar preparación

No se declarará el sistema listo hasta que **todas** se cumplan con evidencia:

1. Los 24 criterios de la sección 1 en estado `hecho`, cada uno con la salida real de la
   prueba que lo verifica.
2. Ejecución completa de la suite: unitarias, integración, API, extremo a extremo,
   concurrencia, seguridad, RAG, carga y recuperación.
3. Cobertura de backend ≥ 80 % y de frontend ≥ 70 %, medida y publicada.
4. Cero vulnerabilidades críticas o altas sin justificación formal y plan de corrección
   con fecha.
5. Restauración de respaldo ejecutada sobre una instancia limpia, con comparación de
   recuentos de filas.
6. Rollback de versión y de migración ejecutados en preproducción.
7. Las 60 pruebas E2E actuales y los escenarios de aceptación clínica faltantes en verde.
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
| 2026‑09‑12 | 4 (WhatsApp) | **No preparado.** Outbox de entrega, catálogo de plantillas sin datos clínicos y webhook con firma validada, verificados con 236 pruebas contra PostgreSQL real y 33 comprobaciones sobre la API arrancada. lse ejercicio manual encontró, con 891 pruebas en verde, que **una `BAJA` por WhatsApp no daba de baja al paciente** por el formato del número; corregido con un índice funcional y 6 pruebas de regresión. **El camino real hacia Meta no está verificado** y así se declara (E‑1). Se corrigió además la medición de cobertura del proyecto, que llevaba varias fases mal medida por el greenlet de SQLAlchemy async |
| 2026‑09‑12 | 4 (calendarios) | **No preparado.** OAuth con `state` firmado y de un solo uso, tokens cifrados con AES‑GCM ligados al profesional, publicación de eventos **sin datos clínicos** (ADR‑0018) y reconciliación de borrados y cambios externos, verificado con 85 pruebas y adaptador sandbox. **Falta el adaptador real de Google** y la renovación automática del token (E‑19); `MODO_CALENDARIO=google` no arranca, a propósito |
| 2026‑09‑12 | 6 (conocimiento y RAG) | **No preparado.** Base de conocimiento con pgvector, búsqueda híbrida con los filtros de autorización dentro del SQL, ciclo de vida del documento y defensa anti inyección, con 80 pruebas `rag`. El arnés de evaluación destapó **dos fallos propios que se tapaban mutuamente**: el umbral de similitud no se aplicaba —la búsqueda nunca habría podido decir «no tengo información aprobada»— y la consulta textual unía los términos con `AND`, así que casi nunca coincidía. Corregidos y medidos: Hit@3 100 %, y una pregunta sin documentación devuelve **0** resultados (antes: el corpus entero). **La calidad se midió con el proveedor simulado, no con un modelo real** (E‑9) |
| 2026‑10‑05 | Recordatorios | **Parcial.** Los avisos de citas y de tomas de pautas fijas ya se programan de forma durable y el cron los materializa en el outbox. Suspensión y registro de toma invalidan avisos pendientes; los de medicación exigen consentimiento propio y no contienen el nombre del medicamento. Verificados contra PostgreSQL aislado. La entrega real a Meta sigue pendiente
| 2026‑10‑07 | 1, 9, 11 | **No preparado.** Interfaz de vidrio líquido con movimiento (Motion, diferido) y gráficos en movimiento; centro de Ayuda con un manual por rol (tarea 11.1); libro de gastos de solo anulación y flujo de caja en base de caja (ADR‑0021). Verificado en local con pruebas unitarias, de API, de componente y E2E. No cambia ningún bloqueo externo: legal, proveedores reales, monitoreo y despliegue siguen pendientes; el rendimiento del vidrio no se midió en la tableta real (E‑14) |
# Estado de la ampliación 2026-10-08

El agente por paciente, periodontograma, analítica local y fotografías privadas
se verifican en desarrollo con datos sintéticos y PostgreSQL real. Véase
[evidencia de ejecución](verificacion-2026-10-08.md#agente-periodontograma-analitica-y-fotografias).
La entrega local no declara el producto preparado para producción.

Para desplegar: aplicar `alembic upgrade head` (`032`–`035`), actualizar API y
worker juntos, conservar el almacén cifrado de archivos y sus claves. Validar
roles, especialidades y ámbitos reales del cliente; el acceso por botones se
mantiene limitado al desarrollo. Configurar proveedores desde la interfaz y
verificar cada integración con credenciales del cliente antes de habilitar envíos.

En producción, respaldar base y objetos cifrados y practicar restauración.
Para revertir aplicación, preservar las tablas clínicas y las fotos. El
`downgrade` de estas migraciones elimina las tablas incorporadas: usarlo solo
en un entorno descartable o con recuperación planificada; la reversión se
comprueba en bases temporales. La sesión del agente no sustituye el historial.
