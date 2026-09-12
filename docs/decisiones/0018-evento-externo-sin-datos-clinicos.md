# ADR‑0018 — Qué lleva un evento en el calendario externo del profesional

**Estado:** aceptada · **Fecha:** 2026‑09‑12 · **Fase:** 4 (calendarios)

---

## Contexto

La agenda interna se refleja en el calendario del profesional para que no se reserve
encima. La pregunta es qué se escribe en ese evento.

Lo natural sería el título completo: «Consulta de traumatología — María Torres». Es lo que
hace cualquier agenda profesional, es lo que el profesional espera, y es lo que hace el
calendario realmente útil de un vistazo.

El requisito RF‑I09 dice, en una línea: *«Los eventos externos no contienen datos
clínicos»*. Este ADR existe porque cumplirlo tiene un coste que conviene dejar razonado, y
porque la frontera exacta —qué cuenta como dato clínico— hay que decidirla.

## El problema

**El calendario de Google es un tercero.** Lo que se escribe ahí sale del sistema:

* Deja de estar bajo su control de acceso, su auditoría y su política de retención.
* Queda en la cuenta personal del profesional, en su teléfono, en su portátil y en
  cualquier dispositivo donde la tenga sincronizada.
* Es visible para quien tenga acceso a esa cuenta, incluidos los compartidos que el
  profesional haya configurado años atrás y no recuerde.
* Sale del país, y su tratamiento queda sujeto a los términos de un proveedor sobre el que
  la clínica no decide.

Y el dato no tiene que ser un diagnóstico para revelar uno. **El nombre del servicio basta
por sí solo**: «Consulta oncológica» en el calendario de un médico, cruzado con el nombre
del paciente, es un diagnóstico con nombre y apellidos. La especialidad **es** información
de salud.

## Decisión

**El evento externo lleva un título fijo, la ubicación física, el rango de horas y un
enlace al sistema. Nada más.**

| Se publica | No se publica |
|---|---|
| Título fijo: «Cita reservada» | Nombre del paciente, ni sus iniciales, ni su documento |
| Sede y consultorio | Nombre del servicio o de la especialidad |
| Inicio y fin | Motivo de consulta, diagnóstico, medicación |
| Enlace a la cita en el sistema | Notas, observaciones, teléfono del paciente |
| Referencia interna (`cita:<uuid>`) | — |

El título **no es parametrizable**, y eso es deliberado: en el momento en que admita una
variable, alguien pondrá ahí el servicio. La descripción explica al profesional por qué no
ve más y dónde mirar; sin esa explicación, el primero que abra su calendario pensará que el
sistema está roto y pedirá que se añada el paciente.

### La sede y el consultorio se validan

Son datos de ubicación física, no clínicos. Pero son **texto libre que el operador
controla**, y una sede llamada «Centro Oncológico» revelaría exactamente lo mismo que un
título con el servicio. Se comprueban contra la lista de palabras prohibidas antes de
publicarlas; si una sede se llama así, el evento se rechaza y hay que decidir qué hacer —
que es mejor que publicarlo sin que nadie se entere.

### Cómo se hace cumplir

El mismo patrón que las plantillas de mensajería
([`plantillas.py`](../../backend/app/mensajeria/plantillas.py)), y por el mismo motivo:

1. **`construir_evento` no recibe esos datos.** No se puede filtrar lo que no llega. Hay
   una prueba que inspecciona la firma de la función y falla si alguien añade un parámetro
   de paciente o de servicio.
2. **`EventoExterno` tiene un conjunto cerrado de campos.** Sin diccionario de «extras»:
   ahí es donde acabaría el dato.
3. **`verificar` se ejecuta también en el adaptador**, justo antes de publicar. Es la
   última barrera para el código que no pase por `construir_evento`.
4. Una prueba de integración comprueba que **lo que de verdad sale hacia el proveedor** no
   nombra al paciente ni al servicio — no solo que la función se comporte.

## Consecuencias

**Lo que gana el sistema.** El calendario externo funciona como un espejo de
ocupación: impide la doble reserva, que es su propósito, sin exportar historial clínico a
un tercero. Si mañana la cuenta de Google de un profesional se ve comprometida, lo que hay
ahí son huecos ocupados, no una lista de pacientes con sus especialidades.

**Lo que cuesta.** El calendario es bastante menos útil de lo que un profesional espera.
No puede preparar la consulta desde su teléfono, ni saber a quién va a ver sin abrir el
sistema. Esa fricción es real y es la queja previsible.

La respuesta a esa queja no es relajar esto: es que el sistema tenga una vista de agenda
propia lo bastante buena —y accesible desde el móvil— para que no haga falta. Está en la
Fase 1.

**Lo que no resuelve.** Que la clínica **quiera** publicar el nombre del paciente. Es una
decisión que puede tomar, y que implica una transferencia de datos personales de salud a un
tercero: exige base legal, información al paciente y revisión jurídica (limitación E‑2). No
se implementa «por si acaso» un interruptor para eso; si se pide, se diseña entonces, con
su propio ADR y su revisión.

## Alternativas descartadas

**Publicar solo las iniciales del paciente.** Parece un término medio y no lo es: en una
clínica pequeña, unas iniciales más una hora identifican a una persona igual de bien que su
nombre. Y sigue exportando la relación paciente‑profesional‑fecha.

**Publicar el servicio pero no el paciente.** Descartada porque la especialidad es el dato
que más revela. «Consulta de infectología, martes a las 9» en el calendario de un médico,
combinado con cualquier otra fuente, es peor que un nombre suelto.

**Cifrar la descripción y dejar el nombre en el título.** No tiene sentido: el punto no es
que el dato sea ilegible para Google, es que no debe estar ahí. Y un título cifrado
convierte el calendario en ruido.

**Hacerlo configurable por clínica, con el valor privado por defecto.** Es la opción que
más se parece a «dejar que el cliente decida», y se descarta para esta fase por dos
motivos: un interruptor que exporta datos de salud a un tercero necesita base legal
documentada antes de existir, y un valor por defecto seguro que cualquiera puede cambiar sin
entender la consecuencia no protege a nadie. Si la clínica lo pide, se diseña con revisión
jurídica.

---

## Referencias

* RF‑I09 en [`requirements.md`](../requirements.md)
* CLAUDE.md, regla 10 — el mismo principio en las notificaciones
* [ADR‑0012 — Adaptadores sandbox](0012-adaptadores-sandbox.md)
* [`calendar-integration.md`](../calendar-integration.md)
* `backend/pruebas/unitarias/test_eventos_calendario.py` —
  `test_no_se_puede_colar_nada_del_paciente_ni_del_servicio`
* `backend/pruebas/integracion/test_calendario.py` —
  `test_el_evento_publicado_no_lleva_datos_del_paciente`
