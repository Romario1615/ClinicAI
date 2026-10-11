# Plan de interfaz · 2026‑10‑11 (para Codex)

> Encargado: **Codex** (implementa). **Claude** verifica la lógica visual al final.
> Auditorías de partida (las genera Haiku, solo lectura):
> `…/scratchpad/auditoria-scroll.md` y `…/scratchpad/inventario-botones.md`
> en `C:\Users\xavi9\AppData\Local\Temp\claude\d--Sistema-IA-de-Clinicas\0a1e071c-9ef5-48af-9c4d-352e53743587\`.
> Si aún no existen cuando empieces, haz primero los puntos 1, 2, 5 y 6.

Reglas: CLAUDE.md y AGENTS.md. Solo frontend y pruebas (sin backend ni
migraciones). Commits pequeños por punto, con rutas explícitas, mensaje en
español con pruebas y resultados. Sin push. Si otro agente tiene cambios sin
confirmar en un archivo, no lo pises: anótalo en AGENTS.md.

## 1. Al entrar, la Agenda

* Tras iniciar sesión el destino por omisión es `/agenda` (hoy `/panel`, en
  `paginas/acceso/acceso.component.ts` y la redirección `''` de
  `app.routes.ts`). Si el rol no tiene `agenda.leer`, ir a la primera sección
  permitida (Panel para quien no ve agenda). `?destino=` sigue mandando.
* Ajusta specs y E2E que esperan `/panel` tras el acceso (`apoyo/sesion.ts`
  acepta `/(panel|agenda)`).

## 2. La ficha del paciente abre en el Odontograma

* En `compartido/ficha-paciente.component.ts` la pestaña inicial pasa de
  `resumen` a `odontograma` **cuando esa pestaña está disponible** (permiso
  `odontograma.leer`, acceso clínico y módulo activo en la especialidad). Si no
  lo está (recepción, estética), queda en `resumen`. Si se abre con una pestaña
  pedida explícitamente, se respeta.

## 3. Sin desplazamiento de página; el scroll solo dentro de tarjetas

* En escritorio (≥ 821 × 600) **ninguna sección desplaza la página ni su
  anfitrión**; lo que no cabe desplaza dentro de su tarjeta (`.desplazable`).
  Excepción pedida por el usuario el 2026‑10‑09: **el Panel puede desplazar**
  en vertical dentro del área de contenido.
* **Toda lista o tabla que hoy esté fuera de una tarjeta va dentro de una**
  (`tarjeta tarjeta--llena` + marco `desplazable`). Usa la auditoría de Haiku.
* Revisa también ventanas flotantes y pestañas internas de la ficha.
* Extiende `pruebas-e2e/escenarios/15-pantallas-trabajo.spec.ts` para cubrir
  los roles recepción y profesional además de administración, y para fallar si
  aparece una lista fuera de tarjeta en escritorio.

## 4. Botones y acciones con lógica de negocio

Con el inventario de Haiku, módulo por módulo:

* Acciones destructivas o irreversibles (anular, cancelar cita, cerrar,
  desactivar, quitar acceso) piden confirmación y dicen la consecuencia.
* Un botón de guardar se desactiva mientras envía; no hay dobles envíos.
* Un mismo texto hace lo mismo en toda la app; nada de «Aceptar/OK/Enviar» sin
  contexto: el verbo nombra la acción («Confirmar cita», «Registrar pago»).
* Orden: acción principal a la derecha/abajo y única por ventana; secundarias
  como `boton` normal; destructivas `boton--peligro`.
* Lo que no tenga sentido para el negocio (p. ej. un botón visible a un rol que
  luego recibe 403) se oculta según permisos.
* Si una corrección cambia una regla de negocio (no solo presentación), **no la
  apliques**: déjala listada en AGENTS.md para que Claude la confirme con el
  usuario.

## 5. Analítica IA: arreglar el diseño visual

* El usuario pide arreglar su diseño. Aplica el método de
  `C:\Users\xavi9\.claude\plugins\cache\impeccable\impeccable\4.5.0\skills\impeccable\reference\critique.md`
  y `…\reference\polish.md` (léelos): jerarquía clara (qué es lo importante en
  la primera vista), sin cabecera ilustrada que robe alto, cifras legibles,
  contraste AA, gráficos alineados y sin solapes, pantalla de trabajo sin
  desplazamiento (cada bloque desplaza en su tarjeta), móvil correcto.

## 6. Datos de demostración del frontend

* `frontend/src/app/datos-sinteticos/catalogo.ts` aún lista Medicina General,
  Fisioterapia y Nutrición: pásalo a las especialidades odontológicas y
  Estética facial que ya usa la semilla del backend
  (`backend/app/semillas/sinteticos.py`), con sus servicios.

## Verificación obligatoria por punto

`cd frontend; npx ng lint; npx ng test --no-watch --no-coverage; npx ng build`
y, para 1–3, los E2E afectados con la API aislada (`pruebas-e2e/README.md`).
Al terminar, nota «Codex → Claude» en AGENTS.md con hashes y pendientes.

## Anexo A · Revisión de Claude tras los puntos 1–6 (2026‑10‑11)

Verificado por Claude en navegador (1440 × 900): los seis roles entran en
`/agenda`; 21 rutas de administración sin desplazamiento de página; la ficha
abre en Odontograma con Periodoncia disponible. Analítica mostraba 0 citas por
la semilla (corregido en `b43f473`). Quedan estos fallos de lógica:

7. **Agenda por rol.** Hoy preselecciona el primer servicio y el primer
   profesional (`agenda.component.ts` ~680‑697), así que recepción y
   administración ven la columna de una sola persona. Regla: el rol
   profesional abre en **su propia** agenda; los demás abren con
   Especialidad y Profesional en «Todos» (vista de todo el equipo del día).
   El servicio solo hace falta para buscar huecos o reservar: no debe
   filtrar la vista inicial. En vista Día la etiqueta de la primera hora
   queda tapada por la cabecera de columnas («10:00» cortado): corregir.
8. **Ficha: el odontograma debe verse.** La cabecera (apoyo/agente,
   «Revisando como», «Herramientas del paciente», dos filas de pestañas)
   deja ~380 px al odontograma y la arcada inferior queda bajo el pliegue a
   1440 × 900. Compactar: una sola fila de pestañas desplazable o agrupada,
   «Revisando como» y «Herramientas» en una franja, de modo que las dos
   arcadas permanentes quepan sin desplazar a 1440 × 900.
9. **Dos botones de edición.** «Editar datos del paciente» (columna izquierda)
   y «Editar ficha» (pie) confunden. Dejar uno con verbo claro, o renombrar
   según lo que realmente edita cada uno.
10. **Dentición por edad (presentación).** A una paciente de 5 años el selector
    abre en «Permanente». Cuando el paciente **no tiene odontograma guardado**,
    proponer por edad: < 6 años temporal, 6–12 mixta, ≥ 13 permanente; si hay
    registro, respetar el guardado. El profesional siempre puede cambiarlo.
    Es un valor por omisión de la plantilla, no un dato clínico; documentarlo
    en el ADR del odontograma.
11. **Accesibilidad Analítica.** `analitica.component.html` usa `<main>`
    dentro del `<main id="contenido">` del armazón: cambiar a `<section>` o
    `<div>` con `aria-labelledby`.
12. **Datos de prueba en la base de desarrollo.** Existe un paciente
    «Espera 1b2e1cf6-7, Paciente» creado por una prueba E2E contra la API de
    desarrollo. Revisar qué escenario no usa la API aislada y corregirlo
    (no borrar datos a mano).

Verificación: la misma del plan, más E2E de agenda y ficha con la API aislada.

## Anexo B · Segunda revisión de Claude (2026‑10‑11)

Comprobado tras `c8fe63f`…`6b2bf4e`: la ficha muestra las dos arcadas a
1440 × 900, la dentición temporal se propone a los 5 años, queda una sola
acción de edición y Analítica ya no anida `<main>`. E2E 25, 26 y 30 pasan
11/11 con API aislada recién sembrada (los 4 fallos anotados venían de una API
en 8002 con datos antiguos). Quedan en Agenda, vista Día:

13. **Filtro y columnas coherentes.** Con «Profesional = Abril Manuel» (rol
    profesional, lunes 12‑10) se dibujan además columnas de otros tres
    profesionales con nombres de pacientes. Si hay un profesional elegido, la
    vista Día muestra solo su columna; con «Todos», una columna por
    profesional con turno ese día. No cambies qué datos devuelve la API: si el
    rol profesional recibe citas ajenas, anótalo en AGENTS.md para Claude.
14. **Pie consistente.** El pie dice «0 citas · 0 min reservados · sin huecos
    libres» con dos citas visibles. Debe contar lo que la rejilla muestra.
15. **Primera hora visible.** La etiqueta de la primera hora («08:00») sigue
    tapada por la cabecera de columnas: la rejilla debe empezar debajo.
16. **Día sin turnos.** Con «Todos» en domingo aparece una rejilla vacía con
    las horas a la derecha y sin columnas. Mostrar un estado vacío claro
    («Sin turnos de atención este día») con acceso al próximo día con
    turnos, y las horas siempre a la izquierda.

Verificación: la del plan, más E2E 25, 26, 30 y los de agenda con API aislada
y base recién sembrada (no reutilices una API con datos antiguos).
17. **Regresión E2E completa.** Suite completa con API aislada recién sembrada
    (8031, `--workers=1`): 156 aprobadas, 15 fallidas, 1 omitida (29,1 min).
    Casi todas esperan el comportamiento anterior y deben actualizarse a lo
    pedido por el usuario (acceso en Agenda, ficha en Odontograma, Analítica
    compacta), sin relajar lo que verifican:
    `01-acceso:32` y `02-autorizacion:19` (enlaces del menú no visibles: el
    grupo abierto ahora es «Atención clínica»; abrir el grupo antes de buscar),
    `03-pacientes:59` (ir a la pestaña Resumen antes de buscar «Datos
    personales»), `14-accesibilidad:50`, `16-panel-demografia:5`,
    `29-panel-contexto:5` (navegar al Panel en vez de suponerlo),
    `18-periodontograma-analitica-agente:124` (título nuevo de Analítica),
    `19-ficha-agente-diseno:8` (correo ya no en `.ficha__datos dd`),
    `33-menu-categorias:9` ×4 y `:39`. Investigar como posible defecto real
    `04-clinico:276` (timeout en `waitForResponse`, 90 s) y
    `28-revision-modulos:17` (timeout en `waitForResponse`, 120 s). Registro
    en `%TEMP%\e2e-completa.log`. Cerrar con la suite completa en verde.

## Anexo C · Decisiones del usuario: «como el software odontológico» (2026‑10‑11)

El usuario pidió resolver los pendientes como lo hace el software dental del
mercado. Referencias consultadas: ayuda de Carestream SoftDent/Sensei,
MacPractice, Dentally y el manual de seguridad de Open Dental.

18. **Dentición por edad (confirmado).** Igual que SoftDent, Sensei, MacPractice
    y Dentally: la dentición inicial se propone por edad **solo al crear** el
    primer odontograma; después la cambia el profesional a mano. Se mantiene lo
    hecho en `9e3701a` (< 6 temporal, 6–12 mixta, ≥ 13 permanente). Añadir un
    texto breve junto al selector: «Propuesta por edad; puede cambiarla».
19. **Permisos por perfil, administrados por la clínica.** Como los grupos de
    usuarios de Open Dental: los permisos se asignan por rol y solo
    Administración de clínica (y Superadministrador) los edita, en
    Usuarios/Seguridad. En la interfaz **se ocultan** los botones de acciones
    que el rol no puede ejecutar (según los permisos del principal ya
    cargados); el backend sigue rechazando con 403 como control real. Si algo
    no puede ocultarse (p. ej. depende del registro), mostrar el motivo en
    lugar de un error genérico.
20. **Cambios de configuración con «Guardar» explícito.** Como las ventanas de
    configuración con Aceptar/Guardar: en Conocimiento, quitar una regla de
    permiso modifica el borrador y se persiste al pulsar «Guardar cambios».
    Añadir aviso de cambios sin guardar al cerrar o salir y deshabilitar
    «Guardar» si no hay cambios.

Verificación: la del plan; pruebas unitarias de ocultación por permiso para al
menos Agenda, Pacientes, Catálogo, Conocimiento y Usuarios, y E2E por rol con
la API aislada (8031).
21. **Edades de dentición configurables (backend listo en `fa63cac`).**
    `denticionSugeridaPorEdad` debe usar los cortes de la clínica:
    `GET /api/v1/historia/denticion-por-edad` → `{edad_mixta, edad_permanente}`
    (permiso `odontograma.leer`; si falla, usar 6 y 13). En Catálogo, junto a
    los módulos de historia por especialidad, un bloque «Dentición propuesta
    por edad» para quien tenga `especialidad.gestionar`:
    `PUT /api/v1/catalogo/denticion-por-edad` con `edad_mixta`,
    `edad_permanente` (1–21, mixta < permanente) y `motivo` (5–300). Guardado
    explícito, como en el punto 20.
