# Plan · Interfaz con método impeccable + UI/UX y acciones guiadas en el chat interno (2026‑10‑13)

> Encargados: **Codex** (frontend, en sandbox `workspace-write`, sin commits) y
> **Claude** (backend, revisión de diffs y commits). Haiku genera lo largo y
> repetitivo; Sonnet revisa; Claude verifica cada hallazgo contra el código.
> Reglas: CLAUDE.md y AGENTS.md. Orden: anexo K (en curso) → **Parte N** →
> Parte L; la Parte M (chat) avanza en paralelo en el backend.

---

## Parte N · Ficha como módulo, sin ventanas flotantes, inicio en Agenda (PRIORIDAD)

Pedido del usuario (2026‑10‑13). Va **antes** de la Parte L: no se pule lo
que se va a rehacer. Lo del anexo K que toque ventanas que desaparecen se
reaprovecha en la nueva ubicación.

### N1 · La ficha del paciente es un módulo, no una ventana

* Ruta propia `/pacientes/:id` (y `/pacientes/:id/:pestana`), pantalla de
  trabajo igual que el resto de módulos y que Historia clínica: menú lateral
  visible, cabecera del paciente compacta (nombre, edad, documento,
  verificación, alertas, próxima cita) y miga «Pacientes › Nombre».
* Contiene el **historial completo del paciente**: pestaña «Historial» con
  la cronología unificada (citas, atenciones, notas, recetas, versiones de
  odontograma/faciograma/periodontograma, planes y presupuestos, pagos,
  documentos e imágenes), filtrable por tipo y por especialidad, con los
  mismos permisos y auditoría de lectura que hoy.
* Todos los accesos llevan a esa ruta: «Ver ficha» en Pacientes, bloque de
  cita en Agenda (`?cita=<id>` conserva el contexto de la atención), buscador
  superior, Lista de espera, Pagos, Conversaciones. Historia clínica deja de
  duplicar la ficha: queda como entrada de búsqueda/listado que abre la misma
  ruta (ajustar según la auditoría de redundancia de Haiku,
  `tmp/auditoria-redundancia.md`).
* Botón «Volver» y navegación del navegador (atrás/adelante) funcionan; la URL
  se puede compartir dentro de la clínica (la autorización sigue en el
  backend).

### N2 · Lo primero que se ve en la ficha: su carta clínica actual

* Profesional con especialidad dental y acceso clínico → **Odontograma**.
* Profesional de estética / cuidado facial (módulo `faciograma` activo en su
  especialidad) → **Faciograma**.
* Sin acceso clínico o sin esos módulos (recepción, administración) →
  Resumen.
* Siempre la **información actual**: la versión vigente, con fecha, autor y
  número de versión visibles; las anteriores en el Historial. Sin versión: el
  estado vacío ofrece crear la primera (dentición propuesta por edad).
* Una pestaña pedida en la URL o desde la cita se respeta.

### N3 · Sin ventanas flotantes, salvo las permitidas

Hoy hay 92 usos de `app-ventana-flotante` en 50 archivos. Quedan **solo**:

* Panel de **notificaciones** (campana).
* **Mensajes rápidos** (respuesta rápida a una conversación / chat).
* **Vistas rápidas de menú**: buscador de secciones y resultados del buscador
  superior (sin formularios dentro).

Todo lo demás pasa al área de trabajo, sin superponerse:

* **Crear/editar** (cita, paciente, pago, gasto, usuario, catálogo,
  configuración, documentos, promociones): panel de detalle fijo dentro de la
  pantalla (columna derecha de la rejilla de trabajo) o ruta propia
  (`/agenda/nueva`, `/pacientes/nuevo`…) cuando el formulario es largo. En
  móvil, a pantalla completa como ruta.
* **Editores clínicos** (nota SOAP, receta, piezas del odontograma,
  periodontograma, plan, anamnesis, formulario 033, faciograma): dentro de su
  pestaña de la ficha, en línea.
* **Confirmaciones destructivas** (cancelar, anular, retirar, desactivar): en
  línea en el propio botón o fila («¿Cancelar la cita? Motivo… [Confirmar]
  [Volver]»), sin modal.
* Guardas: cambios sin guardar avisan al salir de la ruta (`canDeactivate`),
  como ya hace Conocimiento.
* **Haiku** genera el inventario `tmp/inventario-ventanas.md` (archivo,
  propósito, destino propuesto según estas reglas); **Codex** migra módulo por
  módulo (Agenda → Ficha → Pacientes → Pagos → resto) dejando la app
  funcionando en cada paso; **Sonnet** revisa; **Claude** verifica y confirma.
* Prueba E2E nueva: falla si aparece un `dialog[open]` fuera de la lista
  permitida en cualquier ruta recorrida por los seis roles.

### N4 · Al iniciar sesión, la Agenda

Ya implementado (`17874ad`): destino por omisión `/agenda`; sin
`agenda.leer`, la primera sección permitida. Se mantiene y se cubre en el E2E
de N3 para los seis roles.

### N5 · Cierre de citas solo desde su hora (ADR‑0031, backend en `2d509ba`)

* En Agenda y en la ficha, «Marcar atendida» e «Inasistencia» de una cita
  futura se muestran deshabilitadas con el motivo («Disponible desde las
  10:30») o se ocultan; «Marcar atendida» sí se permite si la atención ya se
  inició. El 409 del backend se muestra con su texto.
* E2E que cerraban citas futuras (revisar 04, 25, 42, 43 y los de cargo por
  tarifa): registrar llegada e iniciar la atención antes de completar, o
  sembrar la cita en una hora ya iniciada. Sin relajar aserciones.

---

## Parte L · Revisión y corrección de la interfaz con el método de las skills

Las skills están instaladas en la máquina; Codex debe **leer los archivos** y
aplicar su método, no resumirlo de memoria:

* impeccable 4.5.0 —
  `C:\Users\xavi9\.claude\plugins\cache\impeccable\impeccable\4.5.0\skills\impeccable\reference\`:
  `critique.md`, `audit.md`, `layout.md`, `clarify.md`, `harden.md`,
  `polish.md`, `typeset.md`, `colorize.md`, `distill.md`.
* UI/UX Pro Max 2.13.0 —
  `C:\Users\xavi9\.claude\plugins\cache\ui-ux-pro-max-skill\ui-ux-pro-max\2.13.0\.claude\skills\ui-ux-pro-max\SKILL.md`
  (categorías de reglas por prioridad y la lista «Before Delivering App UI»).

Contexto de producto: software de **clínica dental** para recepción y
odontólogos que trabajan con prisa y en pantallas de escritorio. Referentes:
Open Dental, Dentalink. Sistema visual existente: tokens de
`frontend/src/styles.scss` (`--espacio-*`, `--toque-minimo`, colores);
no se crea otro sistema visual.

Orden por módulo (Agenda → Ficha/Odontograma → Pacientes → Pagos → Lista de
espera → Historia → Conocimiento → Conversaciones → Configuración/Usuarios →
Panel/Analítica):

1. **Critique** (`critique.md`): evaluación de diseño + evidencia del
   navegador. Evidencia de partida: `tmp/auditoria-nielsen/` (capturas,
   `mediciones.json`, `informe-nielsen.md`). Regenerarla con
   `AUDITORIA_NIELSEN=1 … 99-auditoria-nielsen.spec.ts` tras cada módulo.
2. **Audit** (`audit.md`): accesibilidad, rendimiento, tema claro/oscuro,
   responsive e integridad de implementación; puntuación por módulo.
3. **Layout** (`layout.md`): tesis espacial por pantalla (qué se ve primero,
   agrupación, alineación a la rejilla, distancias con tokens). Sin scroll
   de página salvo el Panel; scroll solo dentro de tarjetas.
4. **Clarify** (`clarify.md`): verbos de botones, etiquetas, errores, estados
   vacíos, de carga y de éxito, en el vocabulario de la clínica.
5. **Harden** (`harden.md`): textos largos, nombres compuestos, cifras
   grandes, errores de red, permisos insuficientes (mensaje, no 403 crudo).
6. **Polish** (`polish.md`) y checklist «Before Delivering App UI» de
   UI/UX Pro Max: estados de interacción, foco visible, contraste AA,
   objetivos ≥ 24 px, iconos coherentes.
7. **Verificar**: lint, `ng test`, build, E2E del módulo con API 8031 y nueva
   medición; las métricas de `mediciones.json` (pegados, irregulares,
   objetivos pequeños, recortados) no pueden subir; solapes y scroll de página
   en 0.

Entregable por módulo: una nota corta en `AGENTS.md` con la puntuación de
audit antes/después y los archivos tocados. Lo que cambie una regla de negocio
se anota para Claude, no se aplica.

---

## Parte M · Chat interno: primero respuestas guiadas que modifican datos

### Objetivo

Que el personal pueda pedir en el chat de la clínica cosas como «agenda a
Ana Pérez mañana a las 10 con limpieza», «cancela la cita de Juan de las 4»
o «apunta a María en lista de espera», y que el chat responda con una
**respuesta genérica guiada** (una tarjeta de propuesta con los datos
reconocidos y lo que falta) que, **tras confirmar**, modifica la base de datos
por la misma vía que la interfaz.

### Principios (no negociables)

1. **Sin modelo de lenguaje en esta fase.** Intenciones y datos se reconocen
   con reglas deterministas (`backend/app/modulos/asistente/intenciones.py`),
   como hoy. Un LLM podrá más adelante redactar o extraer, nunca decidir ni
   ejecutar (CLAUDE.md §1.4).
2. **El chat no escribe.** El backend del asistente solo devuelve una
   *propuesta de acción*; la escritura la hace el frontend al confirmar,
   llamando a los **endpoints existentes** (`POST /agenda/citas`,
   `/reprogramacion`, `/cancelacion`, `/llegada`, `POST /lista-espera/`,
   `PATCH /pacientes/{id}`) con `Idempotency-Key`. Mismos permisos, ámbito,
   validaciones y auditoría que la interfaz. No hay rutas de escritura nuevas.
3. **Nada se escribe sin confirmación explícita** y con resumen legible de lo
   que va a pasar. Acciones destructivas (cancelar) piden motivo.
4. **Nada clínico.** Recetas, dosis, odontograma, notas, diagnósticos, planes:
   siguen derivando con `DECISION_CLINICA`/`handoff_to_human`. Cobros quedan
   fuera de esta fase.
5. **Solo se ofrece lo que el usuario puede hacer** (permisos del principal);
   si no puede, la respuesta lo dice y no muestra el botón.

### Acciones de la fase 1

| Intención | Ejemplos | Datos a completar | Endpoint al confirmar |
|---|---|---|---|
| `ACCION_AGENDAR` | «agenda a Ana mañana 10:00 limpieza» | paciente, servicio, profesional, fecha/hora, sede | `POST /agenda/citas` |
| `ACCION_REPROGRAMAR` | «pasa la cita de Juan al jueves» | cita, nueva fecha/hora, motivo | `POST /agenda/citas/{id}/reprogramacion` |
| `ACCION_CANCELAR` | «cancela la cita de Juan de las 4» | cita, motivo | `POST /agenda/citas/{id}/cancelacion` |
| `ACCION_CONFIRMAR` | «confirma la cita de María» | cita | endpoint de confirmación existente |
| `ACCION_LLEGADA` | «llegó Pedro» | cita de hoy | `POST /agenda/citas/{id}/llegada` |
| `ACCION_ESPERA` | «apunta a Lucía en lista de espera para ortodoncia» | paciente, servicio/especialidad, preferencia | `POST /lista-espera/` |
| `ACCION_CONTACTO` | «cambia el teléfono de Ana a 099…» | paciente, campo, valor | `PATCH /pacientes/{id}` |

(Los nombres exactos de rutas se toman de `backend/app/modulos/*/rutas.py`.)

### Respuesta genérica guiada (relleno de huecos)

Contrato de `POST /asistente/mensajes` ampliado con `propuesta_accion`:
`{tipo, resumen, campos: {...reconocidos}, faltantes: [...], opciones: {campo: [...]}, requiere_motivo, endpoint, metodo}`.

* Falta el paciente → «¿Para qué paciente?» + buscador (nombres por lotes).
* Falta la hora → «Estos son los próximos horarios libres:» + 3–5 opciones de
  `GET /agenda/disponibilidad`.
* Varias citas posibles → lista para elegir, nunca se adivina.
* Fechas relativas («mañana», «el lunes», «a las 4») se resuelven con el reloj
  inyectado y la zona de la clínica; si es ambiguo, se pregunta.
* Tras confirmar: mensaje de resultado con enlace a la cita/paciente y, si el
  endpoint lo permite, acción de deshacer (p. ej. cancelar la cita recién
  creada).

### Reparto

* **Claude (backend)**: intenciones y extracción de datos con reglas, módulo
  `asistente/acciones.py` que arma la propuesta (lecturas de ámbito: pacientes,
  citas, disponibilidad), esquemas de salida explícitos, permisos, auditoría de
  la propuesta mostrada. Pruebas: tabla de frases → intención/campos, frases
  clínicas que **no** generan acción, sin permiso no hay propuesta, IDOR
  (paciente/cita ajenos no aparecen), fechas relativas con reloj fijo.
* **Codex (frontend)**: tarjeta de propuesta en `asistente.component.ts`
  (campos editables, selección de opciones, «Confirmar» / «Descartar»),
  llamada al endpoint existente con `Idempotency-Key`, estados de
  envío/éxito/error, accesible. Unitarias y E2E `45-chat-acciones.spec.ts`:
  agendar, cancelar con motivo y apuntar en lista de espera desde el chat.
* **Haiku**: tabla grande de frases de prueba (variantes de redacción en
  español de Ecuador) para las pruebas de intención.
* **Sonnet**: revisión de seguridad (que ninguna frase lleve a escritura
  clínica ni salte confirmación) y de usabilidad del flujo.

### Fuera de alcance de la fase 1

Cobros y pagos, acciones clínicas, el agente de WhatsApp (ya tiene su propia
política ADR‑0025), uso de LLM. Se documenta en un ADR nuevo.
