# ADR‑0017 — Qué se ejecuta y qué se deriva al recibir un mensaje de WhatsApp

**Estado:** aceptada · **Fecha:** 2026‑09‑12 · **Fase:** 4

---

## Contexto

El webhook de WhatsApp entrega mensajes de pacientes. El sistema reconoce la intención de
algunos —`CONFIRMAR`, `CANCELAR`, `SI`, `TOMADA`, `BAJA`, `ALTA`, `AYUDA`— y hay que
decidir cuáles ejecuta por sí mismo y cuáles pasan a una persona.

La tentación es ejecutarlas todas: es lo que hace útil un canal de WhatsApp, y lo que
cualquiera espera de él. Un paciente responde «CANCELAR» y su cita se libera; el turno
pasa a la lista de espera; nadie del personal interviene.

El problema no es reconocer la intención. Es responder a la pregunta que viene después.

## El obstáculo real

Para cancelar una cita hay que saber **de quién**. Lo único que trae el webhook es un
número de teléfono, y en este sistema **un teléfono no identifica a una persona**. No es
una carencia del modelo de datos: es una decisión explícita de
[`pacientes/modelos.py`](../../backend/app/modulos/pacientes/modelos.py), donde
`telefono_whatsapp` tiene índice **no único** con este comentario:

> Un teléfono puede ser familiar (una madre gestiona las citas de tres hijos).

Ese caso no es marginal en una clínica. Es el habitual en pediatría, en geriatría y en
cualquier consulta donde alguien acompaña a otra persona. Si el sistema resuelve la
identidad eligiendo uno de los pacientes que comparten el número, cancelará la cita
equivocada de una familia con una probabilidad que no es despreciable.

Y ese error tiene una asimetría importante: el paciente cuya cita se canceló por error
**no se enterará**. Recibirá, si acaso, un mensaje de cancelación que creerá dirigido a
otro miembro de la familia. Se presentará a una cita que ya no existe, o no se presentará
nunca.

## Decisión

**Se reconoce la intención, se registra y se deriva a una persona. Con una excepción.**

| Intención | Qué hace el sistema |
|---|---|
| `CONFIRMAR`, `CANCELAR`, `ACEPTAR_OFERTA`, `REGISTRAR_TOMA` | Reconoce, registra, **deriva** (`EN_HANDOFF`) |
| `ALTA` | Reconoce, registra, **deriva** |
| `AYUDA`, `DESCONOCIDA` | Registra, **deriva** |
| `BAJA` | **Ejecuta**: revoca el consentimiento y cierra el hilo |

### Por qué `BAJA` sí se ejecuta

Es el único caso donde **no hacer nada es peor que equivocarse**. Si alguien pide que
dejen de escribirle y el sistema espera a que una persona lo lea el lunes, le sigue
escribiendo el fin de semana. Eso es exactamente lo que la política de WhatsApp prohíbe y
lo que hace que el paciente silencie el canal —y con él, los recordatorios que sí le
servían.

Además, el error posible tiene reverso: dar de baja a quien no quería se corrige volviendo
a dar de alta. El error contrario —seguir escribiendo a quien pidió que pararan— no se
corrige.

Se revoca el consentimiento de **todos** los pacientes que comparten el número, por el
mismo criterio: ante la duda, dejar de escribir. La revocación marca `revocado_en` y no
borra la fila, porque hay que poder demostrar que hubo consentimiento durante el periodo
en que se enviaron mensajes.

### Por qué `ALTA` no se ejecuta, aunque parezca simétrica

Otorgar consentimiento exige registrar **qué texto aceptó el paciente y su versión**: el
modelo `Consentimiento` guarda `version_texto` y `texto_hash` precisamente para que ante
una reclamación haya respuesta a «qué acepté exactamente». Un «ALTA» suelto no contiene esa
evidencia.

La revocación no necesita evidencia del texto. El consentimiento sí. La asimetría es real y
no un descuido.

### Por qué no hay ningún modelo de lenguaje en este camino

El reconocimiento es **coincidencia exacta de frase normalizada** contra un catálogo
cerrado ([`intenciones.py`](../../backend/app/modulos/conversaciones/intenciones.py)).
Se normalizan mayúsculas, tildes, puntuación y espacios —porque el paciente escribe
«asistiré» tanto como «asistire»— y nada más.

Una interpretación probabilística de «no creo que pueda ir» no es base suficiente para
cancelar la cita de nadie. El coste de esta rigidez es que el personal atiende mensajes que
una máquina podría haber resuelto; el beneficio es que la máquina nunca resuelve mal uno
que no entendió.

El catálogo tampoco admite intenciones clínicas. No existe `CAMBIAR_DOSIS` ni
`REPORTAR_REACCION`: «la pastilla me da náuseas» es `DESCONOCIDA` y va a un profesional
(CLAUDE.md, regla 5). Hay una prueba que falla si alguien añade una intención clínica al
catálogo.

## Consecuencias

**Lo que gana el sistema.** Ninguna cita se cancela, se confirma ni se reprograma por una
inferencia sobre un número de teléfono. Ninguna toma de medicación se registra sin que una
persona lo confirme. El canal de WhatsApp no puede producir el error que más caro sale.

**Lo que cuesta.** El canal es menos autónomo de lo que un usuario espera. Cada
«CANCELAR» genera trabajo para recepción. En una clínica con volumen alto, esa cola es
real y visible: el índice `ix_conversacion_en_handoff` existe para que el personal la
trabaje ordenada por antigüedad.

**Lo que no es.** Esto **no** es una funcionalidad pendiente ni un atajo de la Fase 4.
Derivar es el comportamiento correcto mientras la identidad no se resuelva con algo más
que el número.

## Cuándo se revisa

Cuando existan las herramientas del agente
(`backend/app/ia/herramientas/`, Fase 6). Esas herramientas trabajan con un **principal y
un ámbito** (CLAUDE.md, regla 4), lo que significa que la identidad ya está resuelta antes
de invocarlas. Con eso, `get_patient_appointments` puede enumerar las citas asociadas al
número y `confirm_appointment` o `cancel_appointment` pueden actuar sobre **una** cita
concreta, elegida explícitamente.

El diseño de esa conversación —cómo se pide al paciente que elija entre las tres citas de
sus tres hijos, y qué se le muestra de cada una sin revelar datos clínicos— es una decisión
que afecta a la seguridad del paciente y se planteará entonces, con su propio ADR.

## Alternativas descartadas

**Ejecutar cuando el número corresponde a un solo paciente.** Es tentador: cubriría la
mayoría de los casos y derivaría solo los teléfonos compartidos. Se descarta porque la
unicidad de hoy no garantiza la de mañana —basta que la clínica registre al segundo hijo
para que el mismo mensaje pase a significar otra cosa—, y porque un comportamiento que
cambia según cuántos pacientes comparten el número es imposible de explicar al personal y
al paciente.

Lo que sí se hace con la unicidad: `Conversacion.paciente_id` se rellena solo cuando el
número corresponde a un único paciente, y queda nulo si es compartido. Eso ayuda al
personal sin decidir nada por él.

**Pedir el número de cédula por WhatsApp para confirmar la identidad.** Convertiría el
canal en un formulario de autenticación sobre un medio que no lo es, y entrenaría a los
pacientes a enviar su documento por mensaje —justo el hábito que un atacante quiere.
Contradice P‑1 en [`known-limitations.md`](../known-limitations.md).

**Ejecutar y permitir deshacer.** «Cancelo y si era un error se reprograma.» No funciona:
el turno liberado se ofrece a la lista de espera en minutos, y reprogramar significa
buscar otro hueco que puede no existir. La acción no es reversible en la práctica, aunque
lo sea en la base de datos.

---

## Referencias

* [ADR‑0008 — Outbox transaccional](0008-outbox-transaccional.md)
* [ADR‑0012 — Adaptadores sandbox](0012-adaptadores-sandbox.md)
* [`whatsapp-integration.md`](../whatsapp-integration.md)
* `backend/pruebas/api/test_webhook_whatsapp_api.py` —
  `test_ninguna_intencion_de_estado_se_ejecuta_sin_una_persona`
* `backend/pruebas/unitarias/test_intenciones.py` —
  `test_ningun_mensaje_clinico_produce_una_intencion_de_accion`
