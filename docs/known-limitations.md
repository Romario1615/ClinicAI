# Limitaciones conocidas y riesgos residuales

> **Última actualización:** 2026‑09‑12 · Fase 4.
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
| E‑1 | **El camino real de WhatsApp no está verificado; el de Google Calendar no está implementado** | No hay credenciales y no se inventan (ADR‑0012, regla 3) | **WhatsApp (Fase 4):** el outbox, la deduplicación, los reintentos, la firma del webhook y la conciliación de estados están verificados contra PostgreSQL real y adaptador sandbox (236 pruebas, más 33 comprobaciones sobre la API arrancada). Lo **no** verificado es concreto: que Meta acepte el cuerpo que construye `AdaptadorWhatsAppCloud`, que sus códigos de error sean los de `CODIGOS_PERMANENTES`, y que las plantillas se aprueben con el texto de `plantillas.py`. Ni un mensaje ha salido hacia Meta. Cierre: los 6 puntos de la sección 7 de [`whatsapp-integration.md`](whatsapp-integration.md). **Google Calendar (Fase 4):** el flujo completo esta implementado y verificado con adaptador sandbox -- OAuth con `state` firmado y de un solo uso, tokens cifrados y ligados al profesional, publicacion, retirada y reconciliacion de cambios externos (85 pruebas). Lo que **no** existe: el adaptador real contra la API de Google, y la renovacion automatica del token de acceso. `MODO_CALENDARIO=google` lanza `NotImplementedError` al arrancar, a proposito. Cierre: los 6 puntos de la seccion 9 de [`calendar-integration.md`](calendar-integration.md) |
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

| E‑13 | **Ninguna intención entrante que cambie el estado de una cita se ejecuta automáticamente** | Un teléfono no identifica a una persona: es familiar con frecuencia (ADR‑0017) | `CONFIRMAR`, `CANCELAR`, `SI` y `TOMADA` se reconocen, se registran y se **derivan a una persona**. Consecuencia operativa real: **cada respuesta de un paciente genera trabajo para recepción**. El índice `ix_conversacion_en_handoff` existe para trabajar esa cola por antigüedad. Se revisa en la Fase 6, con las herramientas del agente |
| E‑14 | **La recuperación de mensajes huérfanos puede duplicar un envío** | Si el worker muere *después* de entregar y *antes* de registrarlo, el mensaje vuelve a la cola | Elección deliberada: ante la duda se prefiere que el paciente reciba dos veces un recordatorio a que no lo reciba. Ventana de exposición: 15 minutos (`MINUTOS_HUERFANO`) |
| E‑15 | **El reconocimiento de intención no interpreta lenguaje natural** | Coincidencia exacta de frase normalizada, sin modelo de lenguaje (ADR‑0017) | «no creo que pueda ir» no cancela nada. El personal atiende mensajes que una máquina podría haber resuelto; a cambio, la máquina nunca resuelve mal uno que no entendió. **No es una carencia a corregir** |
| E‑16 | **Los canales de correo y calendario usan el adaptador sandbox** | No están implementados todavía (Fases 4b y 10) | Un mensaje de canal `CORREO` se marca `ENTREGADO` sin que salga nada. El worker lo avisa en el arranque (`outbox.canal_en_sandbox`); **no debe interpretarse como entrega real** |

| E‑17 | **El evento del calendario externo no identifica al paciente ni el servicio** | El calendario de Google es un tercero: lo que se escribe ahi sale del control de acceso del sistema (ADR‑0018, RF‑I09) | El profesional ve «Cita reservada», la sede y un enlace. **No puede preparar la consulta desde su calendario.** Es una decision, no una carencia: la respuesta es que la vista de agenda del sistema sea lo bastante buena, no relajar esto |
| E‑18 | **Un cambio externo en el calendario produce trabajo manual** | Si el profesional mueve un evento a mano, el sistema marca conflicto y **no sobrescribe** | Pisarlo destruiria una decision del profesional que puede implicar reprogramar a un paciente. Consecuencia operativa: cada movimiento manual en Google Calendar exige que alguien lo resuelva. El worker avisa con `calendario.conflictos_pendientes`; si nadie mira, la agenda interna y la externa divergen en silencio |
| E‑19 | **El token de acceso del calendario no se renueva solo** | Falta implementarlo (Fase 4b) | El token de refresco se guarda y la conexion se marca `TOKEN_VENCIDO` correctamente, pero hoy **hay que volver a autorizar a mano**. Ningun evento se pierde -- quedan pendientes y se publican al reconectar --, pero la sincronizacion se detiene hasta que el profesional actue |

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
| 1 · Prototipo visual | en curso | Angular 19 PWA con acceso, agenda **conectada al backend real** (disponibilidad, reserva idempotente, confirmación, cancelación, cierre e inasistencia) y siete pantallas más. **Seis de ellas usan datos sintéticos** y lo declaran en la propia pantalla y en la navegación. Faltan: escritura de pacientes, reprogramación desde la interfaz y las pantallas que dependen de las Fases 4 a 9 |
| 2 · Backend y seguridad | en curso | Modelo de datos, migraciones, autenticación, RBAC con ámbito, auditoría, capa HTTP, límite de tasa, OpenAPI, catálogo y pacientes (lectura) implementados y probados. **Falta la escritura**: crear y editar pacientes, y la administración de usuarios, roles y ámbitos |
| 3 · Agenda | **cerrada** | Disponibilidad, servicios, rutas HTTP, anti doble‑reserva bajo concurrencia real y barrido de bloqueos vencidos, todo con pruebas. El worker ARQ ejecuta el barrido cada minuto; su corrección está probada, pero **su ejecución continuada en un despliegue real no se ha verificado todavía** — eso corresponde a la Fase 10 |
| 4 · WhatsApp y calendarios | pendiente | E‑1 |
| 5 · Lista de espera | en curso | Modelo y servicio con la garantía de **una oferta activa por turno** (índice único parcial + bloqueo consultivo), verificada con dos aceptaciones simultáneas en conexiones reales. 26 pruebas. **Faltan** las rutas HTTP, el disparo automático al cancelar una cita y el envío del aviso por outbox |
| 6 · Conocimiento y RAG | pendiente | E‑3, E‑9, E‑12 |
| 7 · Historia clínica y medicamentos | en curso | Modelo, **tres garantías clínicas en disparadores**, servicios, nueve rutas HTTP y relación asistencial obligatoria. 73 pruebas. **Faltan** los recordatorios de toma por outbox, el cálculo periódico de alertas en el worker y la pantalla real de la interfaz |
| 8 · Dashboard y predicciones | pendiente | E‑4, E‑5 |
| 9 · Pagos | pendiente | — |
| 10 · Producción | pendiente | E‑2, E‑10, E‑11, D‑4 |
