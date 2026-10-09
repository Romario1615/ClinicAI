# ADR‑0025 — El agente atiende WhatsApp: qué consulta, qué cambia y cómo responde

**Estado:** aceptada · **Fecha:** 2026‑10‑09 · **Actualiza:** [ADR‑0017](0017-frontera-de-la-automatizacion-entrante.md)

---

## Contexto

Hasta ahora el webhook de WhatsApp reconoce la intención, registra el mensaje y
**deriva** a una persona (ADR‑0017). El agente con herramientas
(`app/ia/conversacion.py`, ADR‑0019) ya existe y se usa en el «Agente demo» y en
la ficha del paciente, pero no atiende el canal real.

La razón de ADR‑0017 sigue vigente: un teléfono no identifica a una persona, y
cambiar la cita equivocada de una familia es un error que nadie nota. ADR‑0020
añadió la elección de paciente cuando un número es compartido, y dejó escrito
que **elegir de una lista no verifica identidad**.

## Decisión

Decisión del usuario (2026‑10‑09): «consulta libre, cambia verificado»,
**apagado por defecto** por clínica.

### 1. Cuándo actúa el agente

Solo si se cumplen todas:

* la clínica tiene habilitada la integración `agente_whatsapp`
  (Configuración › Integraciones; apagada por defecto);
* la conversación tiene paciente resuelto (ADR‑0020) y no está `EN_HANDOFF` ni
  cerrada;
* el mensaje no lo resolvió antes una regla determinista (baja, comprobante,
  toma, aviso de tratamiento): esas rutas no cambian.

Si no, todo sigue como hoy: se deriva a una persona.

### 2. Qué puede hacer

| Acción | Herramientas | Requisito |
|---|---|---|
| Consultar | `find_availability`, `get_patient_appointments`, `get_patient_payments`, conocimiento publicado | Paciente resuelto |
| Cambiar | `hold_slot`, `confirm_appointment`, `cancel_appointment`, `reschedule_appointment` | **Número de un solo paciente** (no elegido de una lista) **y** `nivel_verificacion` ≥ `TELEFONO`, y además la confirmación expresa del paciente que ya exige la herramienta |

Sin los requisitos de cambio, el principal del agente **no lleva** los permisos
de escritura: la herramienta lo rechaza, el bucle deriva a recepción
(`handoff_to_human`) y la persona lo ve preparado en la bandeja. La barrera es
de permisos en el backend, no una instrucción al modelo.

El principal del agente es `AGENTE_IA`, con ámbito de **un paciente** y nivel
máximo `ADMINISTRATIVO`: no lee historia clínica. El límite clínico de
`limites.evaluar` se aplica antes del bucle, como en todos los canales: una
consulta clínica, una urgencia o la petición de una persona derivan siempre.

### 3. Cómo responde

La Cloud API solo admite texto libre dentro de la **ventana de 24 h** que abre
el mensaje del paciente. La respuesta se encola en el outbox como
`RESPUESTA_CONVERSACION` con destino `CONVERSACION` y sale como mensaje de
texto. Si al entregar la ventana ya cerró, el mensaje queda `FALLIDO`, no se
reintenta y queda a la vista del personal. Nunca se usa WhatsApp Web.

### 4. Por qué el texto libre no rompe la regla 10

El catálogo de plantillas sigue siendo la única vía de los mensajes que
**inicia** el sistema (recordatorios, avisos, promociones). Una respuesta
dentro de un hilo que abrió el paciente no es una notificación: es la
conversación que él empezó. Aun así:

* el texto del agente sale de los resultados de las herramientas, que son
  administrativos; el agente no diagnostica ni interpreta (ADR‑0019);
* la plantilla `RESPUESTA_CONVERSACION` declara un único hueco, `mensaje`, que
  no está en `VARIABLES_PROHIBIDAS`;
* no se adjunta ningún dato que el agente no pueda leer con su ámbito.

### 5. Memoria

La memoria del agente (turnos ofrecidos, cita en curso) se guarda en
`conversacion.agente` (JSONB) y caduca con el hilo. No guarda el texto de los
mensajes: esos ya están en `mensaje_entrante` y en el outbox.

## Consecuencias

* Con la integración apagada, nada cambia.
* Una familia que comparte número consulta, pero no cambia citas sin pasar por
  recepción. Es el coste aceptado de la política.
* Las respuestas quedan en el outbox con su estado de entrega: la bandeja puede
  mostrarlas sin una tabla nueva.
* Falta, y queda fuera de este ADR: responder desde la bandeja, asignar y
  cerrar hilos, credenciales reales de Meta y la evaluación del agente (E‑23).

## Verificación

Pruebas en `pruebas/integracion/test_agente_whatsapp.py`: integración apagada
→ deriva; paciente verificado con número propio → consulta y aparta con
confirmación; número compartido o paciente sin verificar → consulta sí, cambio
deriva; conversación en handoff → el agente no responde; ventana vencida → la
respuesta queda `FALLIDO`; la auditoría registra `AGENTE_IA` como actor.
