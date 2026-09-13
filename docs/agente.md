# El agente conversacional

> **Estado (2026-09-13):** la **capa de herramientas** esta construida y probada.
> El **bucle del modelo no existe todavia**: no hay prompt de sistema, no hay
> conversacion con un LLM y ningun modelo ha invocado nunca estas herramientas.
> Lo que hay es el recinto; el modelo aun no esta dentro.
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

## 2. Las siete herramientas

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
salida de un modelo. Una prueba recorre los esquemas JSON de las siete
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

## 8. Lo que falta

| Pendiente | Por que importa |
|---|---|
| **El bucle del modelo** | Prompt de sistema, memoria de conversacion, eleccion de herramienta. Sin esto el agente no existe de cara al paciente |
| **Resolver la identidad del paciente** | Un telefono no identifica a una persona: una madre gestiona las citas de tres hijos desde el mismo numero. Sin resolverlo, el agente no puede operar por WhatsApp (ADR-0017) |
| **Conectar el webhook** | Hoy el webhook deriva; no invoca herramientas |
| **Herramienta de consulta de conocimiento** | El RAG existe y esta probado, pero el agente no tiene herramienta para consultarlo |
| **Evaluacion del comportamiento del modelo** | Que el recinto sea correcto no dice nada sobre si el modelo elige bien dentro de el |

## 9. Pruebas

```bash
uv run pytest pruebas/unitarias/test_arquitectura_agente.py -q   # 35
uv run pytest pruebas/unitarias/test_limites_agente.py -q        # 42
uv run pytest pruebas/integracion/test_herramientas_agente.py -q # 17
```

Las de arquitectura recorren el AST de `app/ia/herramientas/` y fallan si
alguna construye SQL o toca la sesion. Las de integracion corren contra
PostgreSQL real: el filtro de ambito vive en el `WHERE`, y un doble de prueba
devolveria lo que se le diga —incluida la cita de otra clinica— y pasaria sin
haber comprobado nada.
