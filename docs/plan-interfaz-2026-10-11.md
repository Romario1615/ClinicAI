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
