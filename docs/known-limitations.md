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
| 0b · Infraestructura | en curso | — |
| 1 · Prototipo visual | pendiente | — |
| 2 · Backend y seguridad | pendiente | — |
| 3 · Agenda | pendiente | — |
| 4 · WhatsApp y calendarios | pendiente | E‑1 |
| 5 · Lista de espera | pendiente | — |
| 6 · Conocimiento y RAG | pendiente | E‑3, E‑9 |
| 7 · Historia clínica y medicamentos | pendiente | — |
| 8 · Dashboard y predicciones | pendiente | E‑4, E‑5 |
| 9 · Pagos | pendiente | — |
| 10 · Producción | pendiente | E‑2, D‑4 |
