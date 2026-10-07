# ADR-0019 — La frontera de las herramientas del agente

* **Estado:** aceptada
* **Fecha:** 2026-09-13
* **Contexto de reglas:** CLAUDE.md, reglas 4 y 5
* **Relacionada con:** [ADR-0014](0014-defensa-prompt-injection.md) (contenido como dato citado),
  [ADR-0017](0017-frontera-de-la-automatizacion-entrante.md) (que ejecuta el webhook)

---

## Contexto

El agente conversacional tiene que poder reservar, confirmar, cancelar y
reprogramar citas. Todas esas operaciones cambian estado, y la decision de
cual ejecutar la toma un modelo de lenguaje a partir de texto que escribe
alguien de fuera de la clinica.

Eso plantea un problema que no es el habitual de autorizacion. No basta con
preguntar «¿este usuario puede cancelar citas?». Hay que garantizar ademas que
el texto del paciente —o el texto de un PDF que alguien subio a la base de
conocimiento— **no pueda decidir sobre que datos se opera**. Un modelo al que
se le pide «cancela mi cita» y que puede elegir el `clinica_id` es un modelo al
que una inyeccion de prompt convierte en una via de acceso a otra clinica.

Y hay un segundo problema, de naturaleza distinta: que el agente no tome
decisiones clinicas. Ese no es un problema de permisos configurables. Es un
limite del producto.

## Decision

### 1. El agente no habla con la base de datos ni con los servicios

Habla con siete herramientas en `backend/app/ia/herramientas/`, y son ellas
las que llaman a la capa de servicios. El catalogo es cerrado y esta fijado por
la especificacion:

`find_availability` · `hold_slot` · `confirm_appointment` ·
`cancel_appointment` · `reschedule_appointment` · `get_patient_appointments` ·
`handoff_to_human`

No hay carga dinamica ni descubrimiento por modulo. Anadir una herramienta
obliga a tocar `NOMBRES_ESPERADOS` y a que falle una prueba, que es justo el
efecto buscado: convierte la adicion en una decision explicita en lugar de un
cambio que pasa inadvertido en una revision.

### 2. El «quien» nunca sale de los argumentos

El principal —permisos, ambito, clinica, paciente— viaja en
`ContextoHerramienta`, que construye quien orquesta a partir del token o del
canal verificado. Los esquemas de argumentos contienen **solo datos de
negocio**: identificadores de profesional, servicio, sede, cita y fechas.

Una prueba recorre los esquemas JSON de las siete herramientas y falla si
alguna admite `clinica_id`, `permisos`, `ambito`, `principal` o `rol`. La
separacion es estructural, no una convencion que se pueda olvidar.

Que el modelo pueda pasar un `paciente_id` o un `cita_id` inventado **no es un
agujero**: el filtro de ambito del repositorio los excluye y la operacion
responde como si no existieran. Hay pruebas de integracion que lo comprueban
contra PostgreSQL real, creando una cita de otro paciente e intentando leerla y
cancelarla.

### 3. La garantia clinica es la ausencia de capacidad, no una lista de prohibiciones

No existe ninguna herramienta que cree o modifique una receta, una dosis, una
via, una frecuencia o un tratamiento. No estan prohibidas: **no existen**. Una
lista negra de comportamientos habria que mantenerla, y su cobertura dependeria
de haber anticipado cada forma de pedir lo mismo.

`app/ia/herramientas/limites.py` anade una segunda capa, con otro proposito:
que el agente **reconozca** una peticion clinica y derive a una persona, en
lugar de responder «no tengo esa herramienta» a quien dice que le sienta mal un
medicamento. Esa respuesta es peor que inutil.

El catalogo de senales esta calibrado para equivocarse hacia la derivacion. El
coste de derivar de mas lo paga el personal con su tiempo; el de derivar de
menos lo paga un paciente.

### 4. Toda invocacion queda auditada, incluida la que se deniega

`despachar` escribe una entrada de auditoria en los cuatro caminos: nombre
inexistente, argumentos invalidos, permiso ausente y ejecucion. El actor se
registra como `AGENTE_IA`, que no concede nada pero permite revisar despues que
hizo la automatizacion sin reconstruirlo de los mensajes.

`HERRAMIENTA_DENEGADA` esta en `ACCIONES_CON_ALERTA`: si alguien consigue que
el modelo invoque nombres que no existen, es una senal de ataque, no un fallo
de transcripcion.

### 5. Lo inesperado se deriva, y no se le cuenta al paciente

Un error de dominio se traduce a un texto que se le puede leer a alguien
(«ese horario acaba de ocuparse, puedo buscarle otro»). Una excepcion
inesperada se registra entera con `logger.exception` y al paciente se le pasa
con una persona.

Lo que **nunca** sale es el mensaje interno de la excepcion: puede contener
nombres de tabla, identificadores o fragmentos de consulta, y en un canal
conversacional eso va directo a alguien de fuera.

Esto tiene un coste que conviene declarar: durante el desarrollo, un fallo
trivial —un atributo mal escrito— se presenta como «le paso con una persona» en
lugar de reventar. Ocurrio al construir esta capa. El log lo registro
correctamente, pero quien mire solo el resultado de la herramienta no lo vera.

## Consecuencias

**A favor**

* Una inyeccion de prompt no puede escalar privilegios: el modelo elige *que*
  herramienta, nunca *sobre que datos*.
* La frontera clinica no depende de la calidad de un clasificador.
* La auditoria distingue lo que hizo el agente de lo que hizo una persona.
* Anadir capacidad al agente es un acto deliberado que rompe una prueba.

**En contra**

* El agente deriva casos que una persona resolveria sola. Es intencionado y
  tiene coste operativo real para la clinica.
* Las siete herramientas no cubren lista de espera, pagos ni consulta de
  documentos. Cada una de esas capacidades sera una decision aparte.
* La deteccion de `limites.py` es una lista de expresiones sobre texto
  normalizado. No clasifica intenciones con fiabilidad y no se pretende que lo
  haga; su unica direccion segura de error es derivar de mas.

## Lo que esta decision **no** resuelve

El bucle del modelo —el prompt de sistema, la conversacion, la eleccion de
herramienta— **no esta construido**. Esta capa es el recinto; el modelo todavia
no esta dentro.

Es deliberado el orden: un bucle de herramientas sin frontera verificada es
precisamente lo que estas reglas existen para impedir. Mientras tanto, el
webhook de WhatsApp sigue rigiendose por ADR-0017 y no ejecuta ninguna
intencion que cambie una cita.

---

## Actualización del catálogo — 2026-10-06

La decisión original enumeraba siete herramientas. Desde entonces se agregó
`get_patient_payments`, de solo lectura y protegida por `pago.leer`; devuelve
los cargos y pagos que corresponden al paciente, pero no crea cargos, no
registra pagos y no procesa cobros. El catálogo vigente contiene ocho
herramientas. Las pruebas comprueban por cada una argumentos incompletos,
derivación y auditoría; las siete que leen o cambian datos también se prueban
sin permisos. El límite de escritura clínica permanece igual.

El bucle conversacional también fue implementado después de esta decisión,
con proveedor local de demostración y proveedor Claude. El webhook de WhatsApp
sigue fuera de ese bucle: esta actualización no cambia ADR‑0017 ni implica que
el agente se active en conversaciones reales.
