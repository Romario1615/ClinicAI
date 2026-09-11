# Limitaciones conocidas y riesgos residuales

> **Última actualización:** 2026‑09‑11 · Fase 0.
>
> Este documento existe para que nadie deduzca capacidades que el sistema no tiene. Se
> actualiza al cerrar cada fase. Una limitación resuelta no se borra: se marca como
> resuelta con la evidencia.

---

## 1. Limitaciones de la Fase 0

| # | Limitación | Impacto | Plan |
|---|---|---|---|
| F0‑1 | **No existe código funcional.** Solo análisis, arquitectura y documentación | El sistema no hace nada todavía | Fases 1‑10 |
| F0‑2 | Los diseños de este repositorio no están validados por implementación | Un diseño puede resultar impracticable al programarlo | Cada ADR se revisa al implementar la fase correspondiente |
| F0‑3 | La infraestructura local no está aprovisionada | Nada ejecutable aún | Fase 0b |

---

## 2. Limitaciones estructurales que persistirán

Estas no desaparecen al terminar las fases. Son propiedades del alcance acordado.

| # | Limitación | Por qué | Consecuencia práctica |
|---|---|---|---|
| E‑1 | **Las integraciones reales de WhatsApp y Google Calendar no están verificadas** | No hay credenciales (ADR‑0012) | El sandbox demuestra que nuestra lógica cumple el contrato **documentado**. No demuestra que el proveedor real se comporte igual. Hace falta verificación en preproducción con credenciales |
| E‑2 | **El cumplimiento legal no está validado** | Requiere un profesional jurídico | El sistema **no puede operar con pacientes reales**. 19 puntos en [`security.md`](security.md) |
| E‑3 | **Ninguna defensa contra inyección de prompt es completa** | Propiedad del estado del arte | Lo garantizado es que una inyección no otorga acceso a datos no autorizados ni escritura, porque esas capacidades no existen detrás del modelo (ADR‑0014) |
| E‑4 | **Las predicciones son apoyo operativo, no criterio clínico** | Decisión de diseño | No pueden cambiar tratamientos, negar atención ni clasificar pacientes. Su exactitud se reportará medida sobre datos sintéticos, que no representan la realidad de una clínica |
| E‑5 | **Los modelos predictivos se entrenarán con datos sintéticos** | No hay datos históricos reales | Sus métricas no son extrapolables. Requieren reentrenamiento con datos reales tras meses de operación |
| E‑6 | **El agente no da asesoramiento clínico** | Seguridad del paciente | Ante cualquier consulta clínica deriva a un humano. Es una limitación deliberada, no una carencia a corregir |
| E‑7 | La auditoría es inalterable **desde la aplicación**, no frente a un superusuario de base de datos | Límite del alcance del repositorio | Mitigarlo exige separación de funciones en infraestructura |
| E‑8 | El cifrado en reposo del volumen depende del despliegue | Fuera del repositorio | Debe resolverlo el entorno de producción |
| E‑9 | La calidad de recuperación con embeddings locales pequeños es inferior a la de modelos comerciales grandes | ADR‑0007 | Se medirá y publicará. Si no alcanza el umbral, la decisión se revisa |
| E‑10 | **La verificación TOTP usa el reloj de pared del servidor, no el reloj inyectado** (ADR‑0010) | Un código TOTP se calcula contra la hora real del teléfono del usuario; validarlo contra un reloj de pruebas lo invalidaría en producción | Es la única excepción consciente a ADR‑0010, y está acotada a `verificar_codigo_totp`. Consecuencia operativa: **el servidor necesita sincronización horaria (NTP)**; con más de ~30 s de desfase el personal con 2FA obligatorio no podrá entrar. Se comprueba en la Fase 10 |
| E‑11 | **El límite de tasa falla abierto fuera de la autenticación** | Si Redis no responde, denegar toda la API dejaría la agenda de la clínica inoperativa, y en esos endpoints el atacante ya necesita un token válido | Los endpoints de autenticación sí fallan cerrados (nadie entra mientras Redis esté caído). En el resto se permite y se registra `limite_tasa.sin_contador.permitido`: durante una caída de Redis, un cliente autenticado puede exceder su cuota. La decisión está en `app/nucleo/limite_tasa.py`; **vigilar ese evento es parte de la monitorización** |
| E‑12 | **El extra `embeddings` arrastra una versión de Pillow con vulnerabilidades conocidas** | `fastembed` limita `pillow<12.0`, y la corrección está en 12.1.1 (ADR‑0007) | Pillow **no** está en el árbol base ni en la imagen del backend: solo aparece si se instala el extra `embeddings` para embeddings locales. Las vulnerabilidades son de códecs de imagen, que este sistema nunca invoca — usa fastembed solo para texto. Se revisa en cada actualización de fastembed; si sigue capado cuando llegue la Fase 6, se evalúa un proveedor de embeddings alternativo |

---

## 3. Limitaciones del entorno de desarrollo

| # | Limitación | Impacto |
|---|---|---|
| D‑1 | **Disco C: con 764 MB libres** | Ninguna herramienta puede instalarse en C:. Riesgo para la estabilidad de Windows. **Requiere acción del usuario**, no se resuelve desde el proyecto |
| D‑2 | 13.9 GB de RAM con MSSQLSERVER activo (~2.8 GB libres) | Las pruebas de carga competirán por memoria. Los resultados de carga en este equipo **no son extrapolables** a un servidor de producción |
| D‑3 | Docker corre dentro de WSL2, no de forma nativa | Rendimiento de entrada/salida inferior; los tiempos medidos localmente son pesimistas |
| D‑4 | No hay entorno de staging | Los procedimientos de despliegue, rollback y restauración se documentan y se prueban localmente; no en una infraestructura equivalente a producción |

---

## 4. Decisiones que limitan la funcionalidad a propósito

No son defectos. Se listan para que no se «arreglen» por error.

| # | Decisión | Motivo |
|---|---|---|
| P‑1 | El número de WhatsApp nunca basta para acceder a datos clínicos | Un teléfono puede ser familiar, robado o reasignado |
| P‑2 | Recepción no ve motivo de consulta, diagnóstico ni medicación | Mínimo privilegio sobre datos de salud |
| P‑3 | El superadministrador no accede a la historia clínica | Separar administración técnica de acceso clínico |
| P‑4 | Ningún mensaje de WhatsApp incluye diagnóstico ni nombre de medicamento | La pantalla bloqueada de un teléfono es un canal público |
| P‑5 | Los medicamentos «cuando sea necesario» no generan horarios automáticos | Un PRN convertido en pauta fija es un error de medicación |
| P‑6 | No existe sobreagendamiento | La restricción de exclusión lo impide por diseño |
| P‑7 | No se implementa borrado automático por retención sobre historia clínica | Un borrado mal configurado es irreversible; requiere validación jurídica |
| P‑8 | La IA no tiene ninguna herramienta de escritura clínica | No es una instrucción al modelo: la capacidad no existe |

---

## 5. Estado por fase

| Fase | Estado | Limitaciones abiertas |
|---|---|---|
| 0 · Análisis | **cerrada** | F0‑2 |
| 0b · Infraestructura | **cerrada** | D‑3 |
| 1 · Prototipo visual | pendiente | — |
| 2 · Backend y seguridad | en curso | Modelo de datos, migraciones, autenticación, RBAC con ámbito, auditoría, capa HTTP, límite de tasa y OpenAPI implementados y probados. **Faltan los endpoints de pacientes y de administración de usuarios** |
| 3 · Agenda | **cerrada** | Disponibilidad, servicios, rutas HTTP, anti doble‑reserva bajo concurrencia real y barrido de bloqueos vencidos, todo con pruebas. El worker ARQ ejecuta el barrido cada minuto; su corrección está probada, pero **su ejecución continuada en un despliegue real no se ha verificado todavía** — eso corresponde a la Fase 10 |
| 4 · WhatsApp y calendarios | pendiente | E‑1 |
| 5 · Lista de espera | pendiente | — |
| 6 · Conocimiento y RAG | pendiente | E‑3, E‑9, E‑12 |
| 7 · Historia clínica y medicamentos | pendiente | — |
| 8 · Dashboard y predicciones | pendiente | E‑4, E‑5 |
| 9 · Pagos | pendiente | — |
| 10 · Producción | pendiente | E‑2, E‑10, E‑11, D‑4 |
