# ADR-0020 — Identidad de quien escribe por WhatsApp

* **Estado:** aceptada
* **Fecha:** 2026-09-14
* **Decidida por:** el responsable del proyecto, a consulta explícita del equipo
  de desarrollo (CLAUDE.md, regla 11: una ambigüedad que afecta la seguridad
  clínica se detiene y se pregunta)
* **Relacionada con:** [ADR-0017](0017-frontera-de-la-automatizacion-entrante.md),
  [ADR-0019](0019-la-frontera-de-las-herramientas-del-agente.md)

---

## Contexto

Un teléfono **no identifica a una persona**. Una madre gestiona las citas de sus
tres hijos desde el mismo número. Un teléfono también puede estar prestado,
perdido, robado o reasignado a otro abonado.

Hasta ahora el sistema respondía a esa ambigüedad de la forma más segura
posible: no identificaba a nadie y derivaba la conversación entera a una
persona (ADR-0017). Correcto, y con un coste real: **cada respuesta de un
paciente generaba trabajo para recepción**.

Ejecutar «CANCELAR» exige responder antes a «la cita de quién». Equivocarse
significa cancelarle la cita a quien no era —un daño real, y no reversible desde
el punto de vista de quien se queda sin atención.

## Decisión

Cuando un número corresponde a varios pacientes:

1. Se consulta **qué pacientes tienen ese número**.
2. Se ofrece una **lista numerada** de opciones.
3. **Se espera a que quien escribe elija.** Sin elección no hay paciente
   resuelto y no se ejecuta nada.

### Tres límites que la decisión no contradice y que se implementan con ella

**1. Elegir de una lista NO es verificar identidad.** Es desambiguar. El
`nivel_verificacion` del paciente no cambia por haber pulsado «2», y sigue
gobernando qué se puede hacer después. Confundir las dos cosas convertiría una
pregunta de menú en una credencial: bastaría con tener el teléfono en la mano
para ascender de `NO_VERIFICADO` a `TELEFONO`.

**2. La lista se minimiza.** Se muestra el nombre de pila y la inicial del
apellido —«Ana P.»—. Suficiente para que una madre distinga a sus hijos, y lo
menos posible para quien tenga ese aparato sin deberlo tener. **Nunca** el
número de documento (permite suplantar en otros trámites), ni la fecha de
nacimiento, ni nada clínico (regla 10: se lee en una pantalla de bloqueo).

**3. Demasiados candidatos no se enumeran.** Por encima de cinco se deriva sin
listar. Un número que aparece en ocho fichas no es una familia: es un dato mal
cargado o un teléfono compartido, y enumerar ocho nombres a quien tenga ese
aparato es una fuga, no una ayuda.

### La lista se guarda, no se recalcula

Las opciones se persisten **con su orden** en `conversacion.seleccion_pendiente`.
Reconstruirlas al recibir la respuesta abriría una ventana real: entre la oferta
y el «2» puede haberse creado una ficha nueva con ese mismo teléfono, y entonces
la segunda opción sería otra persona.

### La lista caduca

Quince minutos. Un «2» respondido al día siguiente contesta a una pregunta que
quien escribe ya no recuerda.

Cuando llega una respuesta tardía, el sistema **vuelve a ofrecer una lista
nueva** en lugar de callar: descartar la caducada sin más dejaría a quien
escribe sin forma de continuar.

## Lo que esta decisión **no** autoriza

Resolver la identidad no cambia [ADR-0017](0017-frontera-de-la-automatizacion-entrante.md).
El webhook **sigue sin ejecutar** ninguna intención que cambie el estado de una
cita, de una oferta o de una toma. Saber de quién habla el hilo es condición
necesaria para automatizar; no es condición suficiente.

Lo que sí cambia: la conversación llega a la persona de recepción **ya
atribuida**, en lugar de llegar con un número y sin nombre.

## Consecuencias

**A favor**

* La conversación queda atribuida al paciente correcto, elegido por quien
  escribe y no adivinado por el sistema.
* Es condición previa del agente conversacional (E‑23): sin ella, las
  herramientas no pueden recibir un `paciente_id` fiable.
* El estado por defecto sigue siendo «no sé quién es».

**En contra, y hay que decirlo**

* **La lista revela nombres de pila a quien tenga el teléfono.** Es el coste
  aceptado de la decisión, reducido por la minimización y por el tope de cinco,
  pero no eliminado. Un teléfono reasignado recibiría hasta cinco nombres de
  pila con inicial.
* Una elección puede ser deliberadamente falsa. Quien tenga el teléfono puede
  elegir a cualquiera de la lista. **Por eso elegir no verifica**: lo que se
  haga después sigue sujeto al nivel de verificación del paciente elegido.
* Añade un turno de conversación al flujo más común de una familia.

## Pendiente de validación jurídica

Mostrar nombres de pila asociados a un número es un tratamiento de datos
personales. **Si es proporcionado bajo la LOPDP, y si requiere aviso previo al
paciente al registrar su teléfono, lo tiene que determinar el asesor jurídico de
la clínica** (E‑2). Este ADR documenta la decisión técnica y su justificación;
no afirma que sea conforme.

## Verificación

`pruebas/integracion/test_identidad_telefono.py` y
`pruebas/unitarias/test_identidad_opciones.py` — 40 pruebas. Las que sostienen
la decisión, una por límite:

* sin elección no hay paciente resuelto;
* elegir **no** sube el nivel de verificación;
* la elección se resuelve contra la lista guardada, no contra una consulta
  nueva;
* el texto ofrecido no contiene documento, apellido completo ni nada clínico;
* por encima del tope no se enumera;
* una lista caducada no resuelve nada.
