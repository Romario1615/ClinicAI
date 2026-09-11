# Estado de preparación para producción

> **Última actualización:** 2026‑09‑11 · Fase 0 cerrada.
>
> **Veredicto actual: el sistema NO está preparado para producción y no puede usarse con
> datos de pacientes reales.** Esto no es una fórmula de cautela: no existe todavía código
> funcional. La tabla siguiente refleja el estado verificado, no el planificado.

---

## 1. Criterios de producción

Los 21 criterios exigidos, con su estado real. `no evaluado` significa que la
funcionalidad no existe todavía; **no** significa que esté bien.

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | No hay errores críticos | **no evaluado** | Sin código funcional |
| 2 | Sin vulnerabilidades críticas o altas pendientes | **no evaluado** | Sin escaneo ejecutado; solo documentación |
| 3 | No existen secretos en el repositorio | **parcial** | Por construcción: `.env` excluido y `.env.example` sin valores reales. `gitleaks` aún no ejecutado |
| 4 | Las reservas concurrentes no generan duplicados | **no evaluado** | Diseñado en ADR‑0009, sin implementar |
| 5 | La lista de espera funciona automáticamente | **no evaluado** | Fase 5 |
| 6 | Los calendarios se sincronizan | **no evaluado** | Fase 4. **Sin credenciales de Google** |
| 7 | Los recordatorios son persistentes y reintentables | **no evaluado** | Diseñado en ADR‑0008, sin implementar |
| 8 | Los permisos impiden accesos indebidos | **no evaluado** | Matriz definida en `security.md`, sin implementar |
| 9 | La historia clínica está protegida | **no evaluado** | Diseñado en ADR‑0011 |
| 10 | Los medicamentos solo usan recetas aprobadas | **no evaluado** | Fase 7 |
| 11 | La IA no modifica datos sin autorización | **no evaluado** | Frontera diseñada, sin implementar |
| 12 | El RAG no filtra información entre pacientes | **no evaluado** | Diseñado en ADR‑0013 |
| 13 | Los documentos vencidos no son recuperados | **no evaluado** | Fase 6 |
| 14 | Los respaldos se pueden restaurar | **no evaluado** | Fase 10. Un respaldo sin restauración probada no cuenta |
| 15 | El sistema soporta las pruebas de carga definidas | **no evaluado** | Fase 10 |
| 16 | El pipeline CI/CD está funcionando | **no evaluado** | Fase 2 |
| 17 | Existe documentación de operación | **parcial** | Documentos creados; procedimientos sin ejecutar |
| 18 | Existe procedimiento de rollback | **parcial** | Documentado, sin probar |
| 19 | Existe procedimiento de restauración | **parcial** | Documentado, sin probar |
| 20 | Existe monitoreo | **no evaluado** | Fase 10 |
| 21 | Pruebas de aceptación con escenarios de clínica | **no evaluado** | Fase 10 |
| 22 | Todas las limitaciones documentadas | **hecho** | [`known-limitations.md`](known-limitations.md) |

**Resumen: 1 de 22 cumplido, 5 parciales, 16 sin evaluar.**

---

## 2. Bloqueos que no se resuelven escribiendo código

Estos cuatro puntos permanecerán abiertos aunque todas las fases técnicas se completen.
Dependen del usuario y de terceros.

| # | Bloqueo | Quién lo resuelve | Consecuencia si no se resuelve |
|---|---|---|---|
| **B‑1** | **Revisión jurídica en Ecuador** (19 puntos en `security.md`) | El usuario con un profesional jurídico y la clínica | **No se puede operar con pacientes reales.** Es el bloqueo de mayor prioridad del proyecto (riesgo L‑01) |
| **B‑2** | Credenciales de WhatsApp Business y plantillas aprobadas por Meta | El usuario y Meta | La ruta real de mensajería queda sin verificar. El sandbox demuestra que nuestra lógica cumple el contrato documentado, no que el proveedor real se comporte igual |
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
