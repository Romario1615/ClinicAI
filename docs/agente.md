# El agente conversacional

> **Estado (2026-10-06):** la capa de herramientas y el **bucle del modelo**
> estan construidos y probados. El catalogo tiene ocho herramientas, incluida
> la consulta de pagos; el modelo real (`ProveedorClaude`) fue verificado contra
> la API y PostgreSQL.
> Lo que **no** esta medido es si el modelo elige bien: eso exige su propia
> evaluacion y es la limitacion E-23.
>
> El bucle solo es alcanzable hoy desde el endpoint de demostracion, que esta
> restringido al entorno local.
>
> El webhook de WhatsApp sigue rigiendose por [ADR-0017](decisiones/0017-frontera-de-la-automatizacion-entrante.md):
> reconoce intenciones, **ejecuta solo la baja de consentimiento** y deriva todo
> lo demas a una persona.

Decision de diseno completa en
[ADR-0019](decisiones/0019-la-frontera-de-las-herramientas-del-agente.md).

---

## 1. Por que el orden es este

Construir el bucle del modelo antes que la frontera habria sido construir
exactamente lo que las reglas 4 y 5 de [`CLAUDE.md`](../CLAUDE.md) prohiben: un
modelo de lenguaje con acceso a la capa de datos y sin un limite verificable.

La frontera primero permite una afirmacion que se puede comprobar: **cuando el
modelo entre, no habra una sola operacion clinica a su alcance**, porque no
existe la herramienta que la haria.

## 2. Las ocho herramientas

Los nombres estan en ingles por decision normativa de la especificacion
([ADR-0015](decisiones/0015-convencion-idioma.md)). El catalogo es cerrado.

| Herramienta | Permiso | Escribe | Que hace |
|---|---|---|---|
| `find_availability` | `agenda.leer` | no | Turnos libres. Devuelve **como maximo 5** |
| `hold_slot` | `cita.crear` | si | Aparta un turno con caducidad |
| `confirm_appointment` | `cita.crear` | si | Pasa a `CONFIRMED` |
| `cancel_appointment` | `cita.cancelar` | si | Cancela. Exige motivo y 24 h de antelacion |
| `reschedule_appointment` | `cita.reprogramar` | si | Mueve de hora. Exige motivo |
| `get_patient_appointments` | `agenda.leer` | no | Citas futuras: fecha, hora y estado |
| `get_patient_payments` | `pago.leer` | no | Cargos y pagos asociados; no registra ni cobra nada |
| `handoff_to_human` | *ninguno* | si | Pasa la conversacion a una persona |

**Por que `handoff_to_human` no exige permiso.** Derivar no accede a ningun
dato. Exigirle permiso significaria que un principal mal configurado se queda
sin la unica salida segura del sistema, justo cuando mas la necesita.

**Por que 5 turnos y no todos.** No es una limitacion tecnica: un mensaje de
WhatsApp con cuarenta horarios no lo lee nadie. El campo `hay_mas` le dice al
modelo que puede ofrecer acotar.

**Por que `get_patient_appointments` no devuelve el servicio.** El nombre de un
servicio revela la especialidad, y la especialidad revela la condicion de quien
la recibe. Devuelve fecha, hora y estado, y nada mas (regla 10).

## 3. Lo que el modelo decide y lo que no

```
┌─ El modelo elige ────────────┐   ┌─ El sistema impone ──────────────┐
│  que herramienta invocar     │   │  quien es el solicitante          │
│  con que fecha, que servicio │   │  que permisos tiene               │
│  que profesional, que sede   │   │  sobre que clinica, sede,         │
│  que motivo textual          │   │    especialidad y pacientes       │
└──────────────────────────────┘   │  que nivel de informacion alcanza │
                                   └───────────────────────────────────┘
        argumentos                          ContextoHerramienta
     (entrada no fiable)               (del token o canal verificado)
```

El principal **nunca** se construye a partir de texto del usuario ni de la
salida de un modelo. Una prueba recorre los esquemas JSON de las ocho
herramientas y falla si alguna admite `clinica_id`, `permisos`, `ambito`,
`principal` o `rol`.

Que el modelo invente un `paciente_id` no es un agujero: el filtro de ambito lo
excluye y la operacion responde como si no existiera. Verificado contra
PostgreSQL real creando una cita de otro paciente e intentando leerla y
cancelarla.

## 4. El limite clinico

Dos capas, y conviene no confundirlas.

**La garantia es estructural.** No hay herramienta que cree o modifique una
receta, una dosis, una via, una frecuencia ni un tratamiento. No estan
prohibidas: no existen.

**`limites.py` es la segunda capa**, con otro proposito: que el agente
reconozca una peticion clinica y derive, en lugar de contestar «no tengo esa
herramienta» a quien dice que le sienta mal un medicamento.

Nueve senales, agrupadas por motivo:

| Motivo | Ejemplos que lo disparan |
|---|---|
| `MEDICACION` | cambiar o bajar la dosis · dejar de tomar · se me olvido una toma · recetar |
| `REACCION_ADVERSA` | me cayo mal · sarpullido · efecto secundario · alergia |
| `SINTOMA_O_DIAGNOSTICO` | me duele · tengo fiebre · que tengo · es grave |
| `URGENCIA_DECLARADA` | urgente · emergencia · socorro |
| `DATOS_DE_TERCERO` | para mi madre · la cita de mi hijo · para un familiar |

Esta calibrado para **equivocarse hacia la derivacion**. El coste de derivar de
mas lo paga el personal con su tiempo; el de derivar de menos lo paga un
paciente.

Lo que este modulo **no** hace: decidir si algo es urgente ni interpretar
sintomas. Clasificar una reaccion adversa como grave o leve es un juicio
clinico, y hacerlo seria exactamente lo que la regla 5 prohibe. Todo sale por
el mismo sitio.

**Lo que se le dice al paciente nunca menciona contenido clinico.** Hay una
prueba que recorre los nueve textos buscando «diagnostico», «medicamento»,
«dosis», «receta», «sintoma», «enfermedad» y «pastilla». Son mensajes de
WhatsApp: pueden leerse en una pantalla de bloqueo.

## 5. El despachador

Toda invocacion pasa por `despachar`, y ahi ocurren cuatro cosas en orden:

1. **Resolver el nombre.** Uno que no este se deniega y se audita. Un modelo
   puede inventarse `delete_patient`; lo que no puede es que exista.
2. **Validar los argumentos** contra el esquema.
3. **Comprobar el permiso.** La capa de servicios lo vuelve a comprobar —es
   ella la autoridad—, pero fallar aqui deja una denegacion con el nombre de la
   herramienta, que es lo que despues se investiga.
4. **Auditar el resultado**, sea cual sea.

El actor se registra como `AGENTE_IA`. No concede nada: sirve para distinguir
lo que hizo la automatizacion de lo que hizo una persona.
`HERRAMIENTA_DENEGADA` esta en `ACCIONES_CON_ALERTA`.

### Traduccion de errores

| Error de dominio | Que se le dice | ¿Sigue el agente? |
|---|---|---|
| `TurnoNoDisponible` | «Ese horario acaba de ocuparse. Puedo buscarle otro» | si |
| `BloqueoExpirado` | «Se agoto el tiempo. Volvemos a mirar la disponibilidad» | si |
| `RecursoNoEncontrado` | «No encuentro esa cita a su nombre» | no |
| `PoliticaCancelacionViolada` | «Falta muy poco para su cita y no puedo cancelarla yo» | no |
| Cualquier otro / inesperado | «Prefiero no arriesgarme a entenderle mal» | no |

Los dos primeros se quedan en el agente porque ofrecen una alternativa dentro
de la conversacion. Derivar cada colision de turno llenaria la cola del
personal, que es justo lo que el agente existe para evitar.

Una excepcion inesperada se registra entera con `logger.exception` y al
paciente se le deriva. **Nunca sale el mensaje interno**: puede contener
nombres de tabla o fragmentos de consulta.

> **Coste declarado.** Durante el desarrollo esto oculta fallos triviales. Un
> atributo mal escrito en `find_availability` se presento como «le paso con una
> persona» en lugar de reventar. El log lo registro correctamente, pero quien
> mire solo el resultado de la herramienta no lo vera. Al depurar, mirar el log.

## 6. Idempotencia

`hold_slot` deriva su clave de la conversacion, la accion y el instante del
turno, con `calcular_clave_deduplicacion`. No se genera al azar **a proposito**:
un reintento del canal —y WhatsApp reintenta— tiene que producir la misma
clave y devolver la misma cita, no una segunda.

Se pasa por el derivador con hash en lugar de concatenar texto porque la marca
de tiempo ISO lleva el `+` del desplazamiento horario, y el alfabeto que admite
`validar_clave_cliente` no lo incluye.

Verificado: dos `hold_slot` identicos devuelven el mismo `cita_id` y dejan
**una** fila en `cita`. Dos pacientes distintos sobre el mismo turno: uno gana y
el otro recibe la oferta de otro horario.

## 7. Zonas horarias

Todo argumento de fecha exige zona. Un `datetime` ingenuo procedente de un
modelo es una fuente de error especialmente mala: el modelo no sabe en que zona
esta la clinica y el sistema no puede adivinarlo, asi que la cita quedaria
desplazada unas horas **sin que nadie lo note hasta que el paciente llegue**.

`find_availability` devuelve ademas `zona_horaria` de la sede, para que el
agente pueda decir «las diez de la manana» en vez de un instante con
desplazamiento.

Los turnos se ofrecen con `fin_consulta`, no con `fin`: el intervalo reservado
incluye la preparacion, y decirle al paciente que su consulta de 30 minutos
dura 40 le hace calcular mal a que hora sale.

## 8. El proveedor del modelo

`ProveedorConversacional` es la costura, y hay dos implementaciones:

| Proveedor | `PROVEEDOR_LLM` | Que hace |
|---|---|---|
| `ProveedorDemostracion` | `mock` | Guion de cadenas fijas. Sin red ni credenciales; es el que usa el CI |
| `ProveedorClaude` | `anthropic` | Messages API de Anthropic con el catalogo publicado como herramientas |

Un valor no implementado —hoy `ollama`— **falla al arrancar** en lugar de caer
al proveedor simulado. Una clinica que cree tener un agente conversacional y
tiene un guion de cadenas fijas no lo descubre por un error, lo descubre por
las quejas.

### Que garantias sobreviven al modelo real

Ninguna de las de la seccion 3 depende de que el modelo se porte bien:

* el principal no viaja en los argumentos, lo pone `ContextoHerramienta`;
* el catalogo es cerrado: el modelo puede pedir `delete_patient`, lo que no
  puede es que exista;
* el limite clinico se evalua **antes** del bucle, asi que un mensaje sobre una
  reaccion adversa nunca llega al modelo;
* `MAXIMO_PASOS` acota el bucle y termina derivando.

### Decisiones de la peticion

* **Una herramienta por paso** (`disable_parallel_tool_use`). El bucle ejecuta
  una y devuelve un `tool_result`; con llamadas paralelas quedarian
  invocaciones sin responder.
* **Razonamiento adaptativo con esfuerzo `low`** (`LLM_ESFUERZO`). Elegir entre
  ocho herramientas administrativas no necesita mas, y el limite clinico no
  depende de lo que el modelo razone.
* **Sin parametros de muestreo.** Los modelos actuales rechazan `temperature`
  con el razonamiento activo. `LLM_TEMPERATURA` se conserva para un proveedor
  local futuro y hoy no se envia.
* **El prompt y el catalogo se cachean.** Son el prefijo estable de todas las
  peticiones de una conversacion.
* **Una instancia por turno.** La transcripcion vive en el proveedor, asi que
  la fabrica entrega uno nuevo en cada turno y comparte solo el cliente HTTP.

### Que sale hacia la API

Solo lo administrativo: los identificadores de la gestion, los horarios
ofrecidos y el texto que escribio el paciente, delimitado y saneado como dato
citado (ADR-0014). Los resultados de herramienta se recortan a una lista blanca
de campos en lugar de volcarse enteros, para que un campo nuevo en un servicio
no acabe saliendo del pais sin que nadie lo decida. Es un tratamiento de datos
personales por un encargado extranjero y esta declarado como tal (E-2).

### Cuando el modelo responde algo que no se puede usar

Respuesta vacia, truncada por `max_tokens`, rechazada por el propio modelo, con
dos invocaciones a la vez, o un fallo de red: **todas derivan a una persona**.
Ninguna deja a quien escribe sin respuesta ni propaga una excepcion al canal.

## 9. Lo que falta

| Pendiente | Por que importa |
|---|---|
| **Resolver la identidad del paciente en el webhook** | La desambiguacion existe (ADR-0020) pero el webhook aun no invoca el bucle |
| **Conectar el webhook** | Hoy el webhook deriva; no invoca herramientas |
| **Herramienta de consulta de conocimiento** | El RAG existe y esta probado, pero el agente no tiene herramienta para consultarlo |
| **Evaluacion del comportamiento del modelo** | Que el recinto sea correcto no dice nada sobre si el modelo elige bien dentro de el |

## 10. Pruebas

```bash
uv run pytest pruebas/unitarias/test_arquitectura_agente.py -q   # 35
uv run pytest pruebas/unitarias/test_limites_agente.py -q        # 42
uv run pytest pruebas/integracion/test_herramientas_agente.py -q # 17
uv run pytest pruebas/unitarias/test_proveedor_claude.py -q      # 18
uv run pytest pruebas/unitarias/test_seleccion_llm.py -q         # 5
```

Las del proveedor usan un doble del cliente: una llamada real cuesta dinero,
necesita red y no da el mismo resultado dos veces. No miden si el modelo
acierta —eso se evalua aparte—, sino que una respuesta rara no rompa el canal y
que lo que sale hacia la API este acotado.

El camino completo con el modelo real, contra PostgreSQL, se ejecuta a mano:

```bash
PRUEBAS_LLM_REAL=1 PROVEEDOR_LLM=anthropic   uv run pytest pruebas/integracion/test_agente_modelo_real.py -q  # 3
```

Esta apagada por defecto porque cuesta dinero, necesita red y su resultado
varia entre ejecuciones: las tres cosas la descalifican para el pipeline.

Las de arquitectura recorren el AST de `app/ia/herramientas/` y fallan si
alguna construye SQL o toca la sesion. Las de integracion corren contra
PostgreSQL real: el filtro de ambito vive en el `WHERE`, y un doble de prueba
devolveria lo que se le diga —incluida la cita de otra clinica— y pasaria sin
haber comprobado nada.
