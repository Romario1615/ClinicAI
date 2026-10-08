# Continuar en local

Nota de traspaso del 2026-10-08. Resume qué quedó hecho en la rama
`claude/friendly-gates-o240sb`, cómo dejar el entorno local al día y qué falta,
con el estado de cada hallazgo de las dos revisiones de código.

Nada de esto equivale a preparación para producción ni a validación clínica o
legal. Las pruebas contra APIs externas reales (Meta/WhatsApp, Google Calendar,
Anthropic, SRI) siguen pendientes por decisión del proyecto.

---

## 1. Poner el entorno local al día

```powershell
cd C:\ruta\a\ClinicAI
git fetch origin
git switch claude/friendly-gates-o240sb
git pull origin claude/friendly-gates-o240sb

.\infra\scripts\infra-arriba.ps1                       # PostgreSQL y Redis

cd backend
uv sync --frozen --extra dev --extra llm               # lo mismo que hace CI
uv run alembic upgrade head                            # hasta 20261007_031
uv run python -m app.semillas.cargar --solo-catalogos  # permisos nuevos a los roles

cd ..\frontend
npm ci                                                 # Node 22.22.3 o superior

cd ..\pruebas-e2e
npm ci
```

Después, reiniciar la API y `npm start`, y volver a iniciar sesión para que el
menú cargue los permisos nuevos.

Las pruebas del simulador local (`test_demo_operativa.py` y
`test_agente_conocimiento_api.py`) solo pasan con `ENTORNO=local`; con
`ENTORNO=desarrollo` fallan 8 de ellas por diseño, no por regresión.

---

## 2. Lo que quedó hecho

| Commit | Qué |
|---|---|
| `86a2c17` | Marcadores de pytest que faltaban: 33 pruebas que ninguna etapa de CI seleccionaba. |
| `a2ae137` | Pantalla de trabajo sin desplazamiento en escritorio (base común, pestañas `app-pestanas`, indicadores compactos) y Pacientes adaptada. |
| `d8f3794` | Agenda, Lista de espera e Historia clínica sin desplazamiento; ventana flotante con `ocupada`, `cambiosSinGuardar`, `error` y devolución del foco. |
| `727c9f5` | Armazón y galería: foco al cerrar menú y avisos, contenido `inert` bajo el cajón móvil, error de subida visible, `/gastos` en la matriz de rutas. |
| este commit | Correcciones de la primera revisión en backend (series de agenda, ocupación del panel, bloqueos de consultorio, semillas, `.dockerignore`, matriz de seguridad) y en Agenda e Historia clínica (errores dentro de las ventanas, cierre durante el guardado, confirmación antes de descartar, foco, pruebas de componente de las series). |

Evidencia de este último commit, ejecutada sobre `ada0c73` más estos cambios:

* Backend: Ruff, formato y mypy en verde; `alembic check` sin cambios;
  917 unitarias; 335 pruebas focalizadas de agenda, series, ocupación,
  bloqueos, semillas (también en base limpia), anti doble reserva,
  concurrencia y autorización.
* Frontend: lint en verde. En la corrida completa aprobaron 648 de 655; las 7
  que fallaban eran del spec nuevo de Agenda, cuyo doble de `ActivatedRoute`
  no daba tu `queryParamMap`. Tras ajustarlo, ese archivo pasa 8/8 (no se
  repitió la corrida completa).
* **No ejecutado** sobre este commit: la batería completa de integración/API,
  la suite E2E ni la medición de pantallas. Deben correrse antes de dar nada
  por cerrado.

Base verificada antes de estos cambios, sobre `ada0c73` tal como lo subiste:
frontend 632/632, lint y build (463 kB); backend 895 unitarias, 1007 de
integración/API aprobadas y 3 omitidas (Anthropic real); la migración 031 baja
y vuelve a subir; el único fallo real era la prueba de semillas en base limpia,
corregida aquí.

Decisión tomada al corregir las series (documentada en
`docs/decisiones/0009-anti-doble-reserva-en-base-de-datos.md`): `MENSUAL`
significa el mismo día de la semana cada 4 semanas, para que caiga en días en
que el profesional atiende. Máximos por frecuencia: SEMANAL 53, QUINCENAL 27,
MENSUAL 13 (todas dentro de un año). El frontend usa la misma tabla.

---

## 3. Rediseño «pantalla de trabajo»: reglas y pendientes

Lo que se pidió: interfaz intuitiva; en escritorio ningún módulo se desplaza
salvo las listas; formularios, detalles y filtros en ventanas flotantes; nada
se solapa; se adapta a cualquier pantalla.

Reglas (las piezas están en `frontend/src/styles.scss`, sección «Pantalla de
trabajo»):

* Escritorio es `@media (min-width: 821px) and (min-height: 600px)`. Debajo
  vuelve el desplazamiento normal (teléfono, tableta vertical).
* Raíz de la sección: `host: { class: 'pantalla' }`. Hijos: `.pantalla__fijo`
  (cabecera, indicadores, pestañas, filtros), `.pantalla__resto` (lo que crece),
  `.pantalla__columnas` (`--pantalla-columnas` para el reparto),
  `.desplazable` (marco de una lista o tabla: `class="tabla-envoltorio
  desplazable"`), `.tarjeta--llena`, `.sin-caja`.
* Bloques que no caben a la vez: `app-pestanas` (ids `{grupo}-pestana-{clave}`
  y `{grupo}-panel-{clave}`).
* Alta, edición, detalle y filtros avanzados: `app-ventana-flotante` con
  `[ocupada]="guardando()"`, `[cambiosSinGuardar]="hayCambios()"` y
  `[error]="error()"`. El error dentro de la ventana, nunca detrás.
* Criterio de aceptación: sin desplazamiento del documento ni del área de
  contenido en 1920×1080, 1440×900, 1366×768, 1280×720 y 1024×768; sin
  solapes, cortes ni desborde horizontal también en 768×1024, 390×844 y
  360×740. Tu escenario `pruebas-e2e/escenarios/15-pantallas-trabajo.spec.ts`
  es el sitio natural para automatizarlo.
* Ejemplos terminados: Pacientes (`a2ae137`), Agenda, Lista de espera e
  Historia clínica (`d8f3794`).

Adaptadas en la rama `claude/pantallas-sin-scroll` (2026-10-08), medidas con
datos sintéticos en los ocho tamaños: sin desplazamiento de la página de
1920×1080 a 1024×768 y sin desborde horizontal en 768×1024, 390×844 y 360×740.
Alto previo a 1366×768 entre paréntesis.

| Pantalla | Cómo queda |
|---|---|
| Panel (3832 px) | Seis pestañas: Resumen, Hoy, Cifras del periodo, Distribución, Pacientes y Seguimiento; periodo y filtros compartidos arriba. |
| Pagos (5317 px) | Pestañas Pagos y Cargos y saldos; exportación CSV en ventana flotante. |
| Equipo (5019 px) | Lista en rejilla dentro de su tarjeta. |
| Conocimiento (3458 px) | Documentos y consulta en dos columnas; accesos del documento y flujo 1→4 (en pantallas bajas) en ventanas flotantes. |
| Automatizaciones (3375 px) | Una pestaña por fase de la atención. |
| Catálogo (3058 px) | Pestañas Sedes y consultorios, Especialidades, Módulos de historia, Servicios y Profesionales. |
| Ayuda (2800 px) | Rol y límites a un lado, tareas al otro. |
| Conversaciones, Asistente, Agente demo | Historial desplazable; campo de escribir y acciones siempre visibles. |
| Configuración (hasta 1636 px) | Cada sección desplaza en su marco; Integraciones compacta. |
| Usuarios (6514 px) | Pestañas propias con filtros fijos y tabla desplazable. |
| Plataforma (33 954 px) | Organizaciones (y sus sedes) y accesos del personal en dos columnas, con buscador en cada lista. En tableta y móvil cada lista desplaza en su tarjeta (de 58 007 a 1 269 px a 390 × 844). |
| Medicamentos (3418 px) | Listado con tabla desplazable; detalle con avisos y tomas en dos columnas. |
| Gastos y caja | Indicadores fijos; movimientos y libro en dos columnas. Por debajo de 1366 px de ancho el libro ocupa todo el ancho y los movimientos se abren en una ventana flotante. |

Correcciones de paso en esas pantallas: la ventana no se cierra durante el
guardado en Equipo, Catálogo, Automatizaciones y Accesos del documento
(hallazgo 32, salvo los diálogos de reserva de la agenda); un `<main>` anidado
en Conversaciones; el título de Conocimiento ilegible; la barra de secciones
de Configuración que desbordaba la página a 768 px.

Delegaciones, Seguridad, Promociones y Analítica caben sin cambios.

La regla se comprueba sola en `pruebas-e2e/escenarios/15-pantallas-trabajo.spec.ts`:
recorre todas las secciones del menú (administración y superadministración) a
1366 × 768 y 1024 × 768 sin desplazamiento de página ni de sección, y a
390 × 844 sin desborde horizontal.

Siguen pendientes:

* Las páginas públicas (solo adaptación).

Gastos y caja no se veía con ningún rol porque la base local no tenía los
permisos `gasto.leer` y `gasto.registrar`. Si `python -m app.semillas.cargar
--verificar` informa de permisos ausentes, sincronice con
`python -m app.semillas.cargar --solo-catalogos` (idempotente, no toca los
datos sintéticos).

---

## 4. Primera revisión (`8cbbee5` y `864885e`): 40 hallazgos confirmados

| # | Sev. | Hallazgo | Dónde | Estado |
|---|---|---|---|---|
| 0 | alta | La ocupación ignora citas COMPLETED y NO_SHOW: cualquier periodo pasado sale cerca del 0 % | `backend/…/modulos/dashboard/ocupacion_agenda.py:296` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 1 | media | La serie rechaza horarios libres porque exige que cada fecha coincida con la rejilla de turnos de ese día | `backend/…/modulos/agenda/servicios.py:490` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 2 | media | La serie crea hasta 53 citas confirmadas para un paciente_id sin comprobar su clínica ni el ámbito del solicitante (IDOR heredado de _crear_cita) | `backend/…/modulos/agenda/servicios.py:346` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 3 | media | El endpoint nuevo no tiene las pruebas obligatorias de autorización, IDOR, entrada inválida y falta de autenticación | `backend/pruebas/api/test_agenda_api.py:602` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 4 | media | La prueba nueva de semillas falla en una base limpia (13 recetas frente a 12) porque la receta de adherencia no se suma al resumen | `backend/pruebas/integracion/test_semillas.py:355` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 5 | media | El error al subir una imagen se pinta fuera del <dialog> modal: queda tapado e inerte | `frontend/…/compartido/galeria-imagenes.component.html:92` | Corregido (727c9f5) |
| 6 | media | Escape cierra el menú móvil y el panel de avisos (role=dialog) sin devolver el foco; el cajón fijo deja tabular hacia contenido tapado | `frontend/…/app.component.ts:280` | Corregido (727c9f5) |
| 7 | media | Un 409 al crear una serie cierra el diálogo y borra el mensaje; la rama de error de 'serie' nunca se muestra | `frontend/…/paginas/agenda/agenda.component.ts:1056` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 8 | media | Promociones: se eliminó la validación del formulario y los errores del servidor quedan fuera del diálogo | `frontend/…/paginas/promociones/promociones.component.html:88` | **Pendiente** |
| 9 | media | E2E: el selector '.ocupacion-agenda' no existe en el panel y la prueba de ocupación falla siempre | `pruebas-e2e/escenarios/05-demo-operativa.spec.ts:401` | **Pendiente** |
| 10 | media | Anamnesis: el error de guardado se pinta detrás del modal y no se ve | `frontend/…/paginas/historia-clinica/anamnesis-captura.component.ts:51` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 11 | media | Planes de tratamiento: los errores de validación y de guardado quedan detrás del modal | `frontend/…/paginas/historia-clinica/planes-tratamiento.component.html:19` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 12 | media | Horarios y feriados: los errores de guardar o eliminar no se ven con la ventana abierta | `frontend/…/paginas/configuracion/agenda-configuracion.component.ts:19` | **Pendiente** |
| 13 | media | IA: cancelar la ventana no revierte los cambios y la tarjeta muestra un estado que no está guardado | `frontend/…/paginas/configuracion/integraciones-ia.component.ts:218` | **Pendiente** |
| 14 | media | IA: el error del servidor (p. ej. URL de Ollama no privada) se pinta fuera de la ventana | `frontend/…/paginas/configuracion/integraciones-ia.component.ts:52` | **Pendiente** |
| 15 | baja | QUINCENAL acepta 53 citas: la serie dura dos años, aunque el límite dice un año | `backend/…/modulos/agenda/esquemas.py:134` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 16 | baja | MENSUAL repite el mismo número de día y cae en días de la semana en que el profesional no atiende | `backend/…/modulos/agenda/servicios.py:160` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 17 | baja | Las pruebas unitarias nuevas no llevan el marcador `unitaria` y el paso «Pruebas unitarias» de CI las descarta | `backend/pruebas/unitarias/test_series_agenda.py:1` | Corregido (86a2c17) |
| 18 | baja | La matriz de docs/security.md no incluye POST /agenda/citas/series | `backend/…/modulos/agenda/rutas.py:466` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 19 | baja | Un bloqueo de un solo consultorio se descuenta como cierre de toda la sede | `backend/…/modulos/dashboard/ocupacion_agenda.py:344` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 20 | baja | Bucle de CPU O(pares × días × bloqueos) que bloquea el event loop en cada carga del dashboard | `backend/…/modulos/dashboard/ocupacion_agenda.py:377` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 21 | baja | La prueba API no cubre feriados, bloqueos, plantilla propia ni restricciones de ámbito que el indicador dice descontar | `backend/pruebas/api/test_dashboard_ocupacion_api.py:18` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 22 | baja | .dockerignore solo excluye rutas de la raíz; `COPY backend/ ./` mete en las imágenes construidas en local backend/almacenamiento y cualquier .env o clave anidada | `.dockerignore:4` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 23 | baja | Con cierraConEscape=false, un `cancel` no cancelable (segundo gesto de atrás en Android sin activación) cierra el <dialog> nativo y deja la ventana fantasma con el scroll bloqueado | `frontend/…/compartido/ventana-flotante.component.ts:353` | Corregido (d8f3794) |
| 24 | baja | La galería no desactiva Escape ni la X durante la subida: la ventana se desvanece y reaparece, y un fallo durante la salida borra el error | `frontend/…/compartido/galeria-imagenes.component.html:15` | Corregido (727c9f5) |
| 25 | baja | La matriz de app.routes.spec.ts omite /gastos mientras app.routes.ts queda excluido de la cobertura | `frontend/…/app.routes.spec.ts:60` | Corregido (727c9f5) |
| 26 | baja | Comentario en inglés en app.component.scss (CLAUDE.md exige comentarios en español) | `frontend/…/app.component.scss:440` | Corregido (727c9f5) |
| 27 | baja | Reprogramar: Escape o la X cierran la ventana durante el guardado y el éxito no llega a la agenda | `frontend/…/paginas/agenda/reprogramar-cita.component.ts:17` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 28 | baja | E2E: la ocupación de 'hoy' depende del día de la semana y falla los domingos | `pruebas-e2e/escenarios/05-demo-operativa.spec.ts:396` | **Pendiente** |
| 29 | baja | E2E de serie: no elige la hora de inicio y no verifica la periodicidad semanal | `pruebas-e2e/escenarios/05-demo-operativa.spec.ts:218` | **Pendiente** |
| 30 | baja | La serie QUINCENAL admite 53 citas (dos años), contra el límite declarado de un año | `frontend/…/paginas/agenda/agenda.component.ts:355` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 31 | baja | El flujo de creación de series no tiene pruebas de componente (AgendaComponent no tiene spec) | `frontend/…/paginas/agenda/agenda.component.ts:1007` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 32 | baja | Los diálogos de reserva, catálogo y equipo se pueden cerrar durante el guardado y el resultado se pierde o se informa mal | `frontend/…/paginas/equipo/equipo.component.ts:168` | **Pendiente** |
| 33 | baja | Spec de plataforma: la prueba dice que cancela el alta de sede pero lo que hace es crearla | `frontend/…/paginas/plataforma/plataforma.component.spec.ts:131` | **Pendiente** |
| 34 | baja | Spec del panel: 'muestra la ocupación solo con capacidad real' no prueba el caso sin capacidad | `frontend/…/paginas/panel/panel.component.spec.ts:198` | **Pendiente** |
| 35 | baja | Escape, la X o Cancelar descartan sin confirmación notas SOAP, recetas, anamnesis y planes a medio escribir | `frontend/…/paginas/historia-clinica/nota-editor.component.ts:208` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |
| 36 | baja | Anamnesis (configuración): 'Publicar versión' publica el último borrador guardado y descarta las ediciones abiertas | `frontend/…/paginas/configuracion/anamnesis-configuracion.component.ts:271` | **Pendiente** |
| 37 | baja | Cierres sin comprobar el guardado en curso: la X del 033 y el Cancelar de agenda y bloqueos cierran a mitad de petición | `frontend/…/paginas/historia-clinica/formulario-033.component.ts:256` | Parcial: Corregida la X del Formulario 033; falta «Cancelar» en horarios y bloqueos de Configuración. |
| 38 | baja | Bloqueos y disponibilidad del equipo: el error al eliminar queda detrás de la confirmación y aparecen alertas viejas o vacías en la edición | `frontend/…/paginas/configuracion/agenda-profesionales.component.ts:112` | **Pendiente** |
| 39 | baja | El foco no vuelve al botón de origen al cerrar el editor de nota, receta o 033 (WCAG 2.4.3) | `frontend/…/paginas/historia-clinica/historia-clinica.component.html:161` | Corregido en este commit; pruebas focalizadas en verde, sin revisión adversarial |

---

## 5. Segunda revisión (`682c271` y `ada0c73`)

### 5.1 Confirmados por un verificador (documentos privados)

| Sev. | Hallazgo | Dónde | Estado |
|---|---|---|---|
| alta | El enlace público entrega el PDF sin verificar identidad si el paciente no tiene fecha de nacimiento ni documento | `backend/app/modulos/documentos/rutas.py:504` | **Pendiente** |
| media | El presupuesto desde un plan devuelve 500 por un ValidationError sin capturar | `backend/app/modulos/documentos/rutas.py:250` | **Pendiente** |
| media | El PDF sustituye por «?» los caracteres fuera de cp1252 y deja ambigua la dosis de una receta | `backend/app/modulos/documentos/pdf.py:40` | **Pendiente** |
| media | La fecha de emisión del PDF se imprime en UTC ISO y no en la zona horaria de la clínica | `backend/app/modulos/documentos/servicios.py:283` | **Pendiente** |
| baja | El PDF muestra el literal 'None' en la duración y en el documento del paciente | `backend/app/modulos/documentos/servicios.py:339` | **Pendiente** |
| baja | El token del enlace se guarda en claro en outbox_mensaje.carga_util y security.md lo niega | `backend/app/modulos/documentos/rutas.py:426` | **Pendiente** |
| baja | El acceso público revela que el documento era una receta suspendida antes de verificar identidad | `backend/app/modulos/documentos/rutas.py:492` | **Pendiente** |
| baja | Los saltos de línea de observaciones e instrucciones se pierden en el PDF | `backend/app/modulos/documentos/pdf.py:28` | **Pendiente** |
| baja | La auditoría del acceso público no registra IP ni número de intentos | `backend/app/modulos/documentos/rutas.py:512` | **Pendiente** |
| baja | La prueba de inyección en PDF no verifica la inyección | `backend/pruebas/unitarias/test_pdf_documentos.py:15` | **Pendiente** |

El primero es el importante: si el paciente no tiene fecha de nacimiento ni
documento, el enlace público entrega el PDF sin verificar identidad.

### 5.2 Reportados y **sin verificar**

El verificador de estas áreas no llegó a ejecutarse (límite de uso). Son
hipótesis de un revisor: cada una hay que comprobarla antes de corregirla, y
algunas pueden no ser reales.

| Sev. | Hallazgo | Dónde |
|---|---|---|
| media | Iniciar sesión en una clínica inactiva revela si la contraseña es correcta, reinicia el contador de intentos y falsea ultimo_acceso_en | `backend/app/modulos/usuarios/servicios.py:926` |
| media | PUT /usuarios/{id}/datos permite a un rol con solo usuario.editar cambiar el correo (identificador de acceso) de cuentas con más privilegios | `backend/app/modulos/usuarios/administracion.py:346` |
| media | Desactivar una clínica no detiene recordatorios, mensajes ni el agente de WhatsApp | `backend/app/modulos/organizacion/plataforma.py:1032` |
| media | docs/security.md afirma que los tokens de enlace no se imprimen en logs, pero el registro de acceso guarda la ruta con el token | `docs/security.md:34` |
| media | Faltan casos de 'rol no autorizado' en las pruebas de los cinco endpoints nuevos (CLAUDE.md §5.6) | `backend/pruebas/api/test_crud_administrativo_api.py:25` |
| media | La agenda ignora la navegación con paciente o procedimiento_plan sin cita: «Agendar» del plan embebido y «Gestionar citas» no hacen nada | `frontend/src/app/paginas/agenda/agenda.component.ts:537` |
| media | «Ver ficha del paciente» desde una cita abre directamente la historia embebida y lee datos clínicos auditados que nadie pidió | `frontend/src/app/paginas/agenda/agenda.component.html:553` |
| media | Historia embebida: si falla la carga del paciente o caduca el acceso de emergencia, se queda en «Cargando pacientes...» y ofrece un buscador de otros pacientes | `frontend/src/app/paginas/historia-clinica/historia-clinica.component.ts:411` |
| media | El presupuesto impreso incluye el selector de sede, los mensajes de estado y los errores internos | `frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.html:394` |
| media | Pagos filtra en silencio por la cita de la URL y el filtro sigue aplicado aunque se vuelva a entrar por el menú «Pagos» | `frontend/src/app/paginas/pagos/pagos.component.ts:400` |
| media | Plataforma: los nuevos botones descolocan la fila de usuario en escritorio y desbordan en horizontal en móvil | `frontend/src/app/paginas/plataforma/plataforma.component.ts:109` |
| media | La especialidad cambiada desde «Atención y documentos» no recarga las notas de la ficha: muestra notas de otra especialidad | `frontend/src/app/compartido/atencion-paciente.component.ts:67` |
| media | Un documento RECETA cuya receta se suspendió o sustituyó se sigue mostrando como «Vigente» con la pauta antigua | `frontend/src/app/compartido/registros-paciente.component.html:13` |
| media | Página pública: cualquier fallo distinto de 401 se presenta como «documento no disponible, solicite un enlace nuevo» | `frontend/src/app/paginas/publico/documentos-publicos.component.ts:28` |
| media | Los botones del mapa facial se solapan (r=13 con centros a 18 y 23,3 unidades) | `frontend/src/app/compartido/mapa-facial.component.ts:18` |
| media | La comprobación «sin desbordamiento» de escritorio en 15 nunca puede fallar | `pruebas-e2e/escenarios/15-pantallas-trabajo.spec.ts:18` |
| media | El escenario 17 cambia la configuración de módulos de la especialidad y no la restaura | `pruebas-e2e/escenarios/17-registros-y-documentos.spec.ts:131` |
| media | La invalidación del enlace privado se «prueba» con un 404 que también daría cualquier token inválido | `pruebas-e2e/escenarios/17-registros-y-documentos.spec.ts:110` |
| media | El README E2E dice 63 pruebas en 16 archivos; hay 66 en 17 y la tabla omite el escenario 17 | `pruebas-e2e/README.md:150` |
| media | Cifras presentadas como «actuales» o «vigentes» que ya no describen la rama | `docs/production-readiness.md:3` |
| media | La verificación de CRUD, faciograma y documentos no tiene resultados pero se cita como evidencia | `docs/verificacion-2026-10-07.md:135` |
| baja | El downgrade de la migración 031 falla si existe algún consentimiento DOCUMENTOS_WHATSAPP | `backend/alembic/versions/20261007_2128_registros_paciente_y_documentos.py:196` |
| baja | La baja global de usuario se audita como usuario.modificado en lugar de usuario.desactivado | `backend/app/modulos/organizacion/plataforma.py:1139` |
| baja | La matriz de security.md atribuye a los endpoints de usuario de plataforma un permiso que el código no exige | `docs/security.md:19` |
| baja | DatosClinicaPlataforma guarda cadenas vacías: una segunda clínica con identificación fiscal en blanco choca con la restricción única | `backend/app/modulos/organizacion/plataforma.py:115` |
| baja | El cambio de módulos por omisión activa Faciograma sin intervención de administración en especialidades existentes | `backend/app/modulos/historia/especialidades.py:79` |
| baja | Los requisitos de las secciones nuevas del manual no reproducen las guardias reales | `backend/app/modulos/ayuda/manuales.py:1063` |
| baja | El select de sede del presupuesto tiene un nombre accesible distinto de su etiqueta visible | `frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.html:395` |
| baja | El botón «Guardar presupuesto y descargar PDF» depende de plan_tratamiento.escribir, pero el endpoint exige historia_clinica.escribir y perfil profesional | `frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.html:389` |
| baja | Cambiar la sede después de guardar el presupuesto reutiliza la clave de idempotencia y da conflicto | `frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.ts:583` |
| baja | «Editar datos» sobre la propia cuenta cierra la sesión sin avisar | `frontend/src/app/paginas/usuarios/usuarios.component.ts:217` |
| baja | La prueba «mantiene la vista previa e informa si falla la carga de sedes» no comprueba que la vista previa se mantenga | `frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.spec.ts:131` |
| baja | La descarga de PDF del personal pierde el mensaje del servidor: siempre muestra «Ocurrio un error inesperado.» | `frontend/src/app/nucleo/servicios/registros-paciente.service.ts:31` |
| baja | Recepción y auditoría leen que la especialidad de la cita «no está asignada a su cuenta» y que deben pedir acceso al administrador | `frontend/src/app/compartido/atencion-paciente.component.ts:24` |
| baja | Si fallan las citas de contexto, o la cita está fuera de las 100 más recientes, la historia de la pestaña queda oculta sin forma de reintentar | `frontend/src/app/compartido/atencion-paciente.component.ts:60` |
| baja | «Pagos de esta cita» sin cita elegida abre los pagos de toda la clínica, y «Gestionar citas» en /agenda no hace nada | `frontend/src/app/compartido/atencion-paciente.component.ts:73` |
| baja | WCAG 2.5.3 (Label in Name): el nombre accesible no contiene el texto visible en «Quitar zona» ni en los botones numerados del mapa | `frontend/src/app/compartido/registros-paciente.component.html:53` |
| baja | El editor permite elegir una sede distinta de la de la cita, cosa que el backend rechaza | `frontend/src/app/compartido/registros-paciente.component.html:42` |
| baja | El editor de registros se cierra con Escape sin pedir confirmación y se pierde lo escrito | `frontend/src/app/compartido/registros-paciente.component.html:38` |
| baja | Fechas en la zona horaria del navegador y no en la de la clínica o sede | `frontend/src/app/compartido/registros-paciente.component.html:13` |
| baja | La pestaña de atención anida una historia de 660 px como mínimo dentro de un cuerpo de ficha con su propio desplazamiento | `frontend/src/app/compartido/atencion-paciente.component.ts:32` |
| baja | Pruebas que no comprueban lo que anuncian, y la exclusión «/publico/» del interceptor sin prueba | `frontend/src/app/compartido/atencion-paciente.component.spec.ts:20` |
| baja | Estados en código interno visibles para el usuario («CONFIRMED», «OBSERVACION») | `frontend/src/app/compartido/atencion-paciente.component.ts:22` |
| baja | El faciograma «accesible» fija nombres accesibles con códigos internos y no ejecuta axe | `pruebas-e2e/escenarios/17-registros-y-documentos.spec.ts:143` |
| baja | Captura de pantalla a una ruta relativa al cwd, fuera del directorio de salida de Playwright | `pruebas-e2e/escenarios/17-registros-y-documentos.spec.ts:160` |
| baja | Aserción débil sobre las citas y dependencia de un paciente con cita en la especialidad del profesional | `pruebas-e2e/escenarios/17-registros-y-documentos.spec.ts:69` |
| baja | Selector exacto de la pestaña «Recetas» que falla cuando muestra la cuenta de borradores | `pruebas-e2e/escenarios/15-pantallas-trabajo.spec.ts:78` |
| baja | El envío por WhatsApp se ejecuta antes de comprobar que el modo es sandbox | `pruebas-e2e/escenarios/17-registros-y-documentos.spec.ts:102` |

---

## 6. Orden sugerido para seguir

1. Correr en local la batería completa sobre este commit: backend
   (`-m unitaria`, `-m "integracion or api"`, `-m concurrencia`), frontend
   (`npm run lint`, `npm run test:ci`, `npm run build`) y la suite E2E.
2. Corregir el hallazgo alto de documentos (identidad no verificada) y los
   medios de la sección 5.1.
3. Verificar y, si son reales, corregir los de la sección 5.2.
4. Corregir los pendientes de la sección 4.
5. Adaptar las pantallas pendientes de la sección 3, una por una, midiendo en
   los ocho tamaños.
6. Actualizar `docs/test-plan.md`, `docs/known-limitations.md` y
   `docs/production-readiness.md` con los resultados reales.
