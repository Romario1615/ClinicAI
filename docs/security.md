# Seguridad y privacidad

> Fase 0. Este documento define los controles exigidos y su estado. **El estado real de
> implementación y verificación está en la última columna de cada tabla y en
> [`production-readiness.md`](production-readiness.md).** Nada aquí debe leerse como
> afirmación de cumplimiento.

---

## Acceso entre especialistas

El rol concede operaciones; el perfil profesional determina la especialidad.
En una sesión clínica, el comodín de especialidades se reduce a la propia y a
los identificadores concedidos expresamente. Las cuentas administrativas sin
capacidades clínicas conservan su ámbito operativo. Un perfil inactivo, anulado
o vinculado a otra clínica pierde las capacidades clínicas y de adherencia.
Perder el perfil nunca convierte al especialista en asistencia con alcance general.

La lectura de notas, imágenes clínicas, planes, odontogramas, periodoncia,
anamnesis capturada y Formulario 033 filtra autores en SQL dentro de la clínica
y de las especialidades autorizadas. El resumen clínico conserva ese filtro;
medicación/adherencia mantienen la reserva N3 y las fechas de citas respetan
el ámbito de agenda. Paciente, relación asistencial, permisos y módulos siguen
siendo requisitos independientes. Los identificadores directos y referencias
entre registros están sujetos a los mismos controles.

| Operación clínica | Responsabilidad exigida |
|---|---|
| Corregir una nota o Formulario 033 | Autor de la versión vigente |
| Anular una imagen clínica | Persona que la cargó |
| Cambiar un plan o sus procedimientos | Profesional responsable del plan |
| Editar/anular faciograma o documento | Profesional autor; conserva historial |
| Confirmar, suspender o sustituir receta | Responsable o delegación vigente de su firma; la nueva versión mantiene al responsable |
| Anexar hallazgos al odontograma compartido | Permiso, relación y área autorizada; nueva versión trazable |

Las recetas confirmadas continúan disponibles entre especialidades para
consultar medicación, respetando N3. Borradores e historial de otra área requieren
ámbito explícito o delegación vigente. La delegación de firma no concede acceso
a las notas del delegante; al revocarla se niega inmediatamente la siguiente
escritura. `puede_gestionar` permite presentar acciones en la interfaz; el
servidor vuelve a comprobar permiso, firma y vigencia en cada mutación.

Una atención de un colega no puede usarse para firmar una nota, cargar una
imagen clínica o crear un documento propio. Una vez que un perfil tiene
registros clínicos, la edición de su especialidad responde 409: trasladar el
perfil trasladaría también el acceso a la historia anterior. Su nombre,
contactos, sedes y estado siguen siendo editables.

## Documentos y faciograma

La ampliación del 2026-10-07 reutiliza permisos existentes; no concede lectura
clínica a recepción ni administración. [ADR-0022](decisiones/0022-crud-faciograma-y-documentos-privados.md).

| Operación API (prefijo `/api/v1`) | Control y ámbito |
|---|---|
| `GET /plataforma/clinicas/{id}/datos` | Superadministración + lectura de clínica |
| `PUT /plataforma/clinicas/{id}/datos`, `/{id}/estado` | Superadministración + escritura de clínica; baja reversible y revocación de sesiones |
| `PUT /plataforma/clinicas/usuarios/{id}/datos`, `/{id}/estado` | Superadministración + permiso de edición/baja de usuario; cuentas de plataforma protegidas |
| `PUT /usuarios/{id}/datos` | Edición de usuario; SQL limitado a su clínica; revoca sesiones sin alterar roles/vínculo |
| `GET /pacientes/{id}/contextos-atencion` | Lectura de agenda y ámbito del paciente/citas |
| `GET /historia/faciograma/zonas` | Lectura de historia; catálogo sin datos de pacientes |
| `GET /historia/pacientes/{id}/registros` y `/{registro}/pdf` | Lectura clínica, relación asistencial, clínica, sede, especialidad, módulos y sensibilidad; lectura auditada |
| `POST /historia/pacientes/{id}/registros`, `/{registro}/anulacion` | Escritura clínica; mismo ámbito; versión sucesora/anulación solo por el autor, con motivo |
| `POST /historia/planes/{id}/presupuesto-documento` | Escritura clínica, lectura autorizada del plan y módulo activo; cita/sede validadas |
| `POST /historia/pacientes/{id}/registros/{registro}/whatsapp` | Lectura/escritura clínica, versión vigente N2 no facial, destinatario confirmado y consentimiento específico |
| `POST /publico/documentos/{token}/acceso` | Token aleatorio y verificación de identidad, vigencia, clínica activa, cinco errores máximos y límite por IP; sin sesión de personal |

Los enlaces caducan en 1–30 días. El aviso de WhatsApp no contiene información
clínica. El worker verifica de nuevo vigencia y consentimiento antes de enviar;
la revocación de consentimiento no retira un enlace ya entregado. Corregir o
anular el registro invalida sus enlaces anteriores. Descargas con `no-store`,
`nosniff` y política de referrer restrictiva. Tokens almacenados como hash más
copia cifrada; no se imprimen en logs. N3 y faciogramas no admiten enlace público.
Los PDFs conservan trazabilidad, pero no incorporan firma certificada.
La copia PDF de una receta conserva el nivel más restrictivo entre el solicitado
para el documento y el de la receta confirmada. Marcarla N3 nunca se reduce a N2
al copiar la pauta. Las copias de recetas no admiten edición directa: primero se
corrige la receta original y después se emite su copia. Dos regresiones API
comprueban la clasificación, el rechazo de edición y la denegación de WhatsApp.

## 1. Clasificación de la información

| Nivel | Contenido | Quién accede |
|---|---|---|
| **N0 · Público** | Servicios, precios, horarios, dirección, preparación de exámenes | Cualquiera, incluido el agente |
| **N1 · Administrativo** | Nombre, teléfono, existencia y hora de una cita, estado de pago | Recepción, administración, profesional tratante |
| **N2 · Clínico** | Motivo de consulta, notas de evolución, diagnósticos, recetas, exámenes, alergias | Profesional con relación asistencial; asistencia según ámbito |
| **N3 · Clínico sensible** | Salud mental, salud sexual y reproductiva, VIH, adicciones, violencia | Solo profesional tratante, con registro de acceso reforzado |

**Recepción no accede a N2 ni N3.** Ve que existe una cita, con quién y a qué hora; no ve
el motivo de consulta, el diagnóstico ni la medicación. Es una regla de negocio, no una
preferencia de interfaz, y se aplica en el backend.

El nivel N3 se marca a nivel de registro (`sensitivity_level`) y requiere que el
profesional tenga relación asistencial activa registrada, no solo el rol.
Antecedentes, versiones de notas, recetas, imágenes clínicas, odontogramas y
planes dentales permiten N2/N3. Los procedimientos heredan el nivel del plan.
Crear o leer N3 requiere además `historia_clinica.leer_sensible`; las consultas
filtran esos registros en SQL y la auditoría conserva el nivel. También se
filtran sus referencias en el resumen clínico, los indicadores y las fotos
vinculadas a procedimientos; la agenda impide a recepción reservar fases de un
plan N3 y los avisos automáticos por fases no se encolan para esos planes. La
redacción local excluye antecedentes, notas y planes N3 aunque quien la solicita
pueda leerlos; recetas e imágenes tampoco se envían al redactor. Otros tipos
clínicos todavía no permiten clasificarse N3 de forma individual.

---

## 2. Matriz de permisos

Leyenda: **✓** permitido · **○** permitido solo dentro de su ámbito o con relación
asistencial · **—** denegado.

| Permiso | Superadmin | Admin clínica | Recepción | Profesional | Asistente | Auditor |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `clinica.leer` / `clinica.escribir` | ✓ | ○ / ○ | ○ / — | ○ / — | ○ / — | ✓ / — |
| `sede.gestionar` | ✓ | ○ | — | — | — | — |
| `especialidad.gestionar` | ✓ | ○ | — | — | — | — |
| `servicio.gestionar` | ✓ | ○ | — | — | — | — |
| `profesional.leer` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `usuario.crear` / `usuario.desactivar` | ✓ | ○ | — | — | — | — |
| `usuario.leer` | ✓ | ○ | — | — | — | ✓ |
| `usuario.editar` | ✓ | ○ | — | — | — | — |
| `rol.asignar` | ✓ | ○ | — | — | — | — |
| `paciente.verificar_identidad` | ✓ | ○ | — | — | — | — |
| `profesional.gestionar` | ✓ | ○ | — | — | — | — |
| `profesional.conectar_calendario` | — | — | — | ○ (propio) | — | — |
| `agenda.leer` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `agenda.configurar` (horarios, pausas y feriados de sede o clínica) | ✓ | ○ | — | — | — | — |
| `cita.crear` / `cita.reprogramar` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.cancelar` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.marcar_inasistencia` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.registrar_llegada` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.iniciar_atencion` | ✓ | ○ | — | ○ | ○ | — |
| `cita.completar` | ✓ | ○ | — | ○ | ○ | — |
| `bloqueo.gestionar` | ✓ | ○ | ○ | ○ (propio) | — | — |
| `paciente.leer_administrativo` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `paciente.crear` / `paciente.editar` | ✓ | ○ | ○ | ○ | ○ | — |
| `consentimiento.gestionar` | ✓ | ○ | ○ | — | — | — |
| **`historia_clinica.leer`** | — | — | **—** | **○** | — | — |
| `historia_clinica.leer_metadatos` | — | ○ | — | ○ | ○ | ○ |
| **`historia_clinica.escribir`** | — | — | — | **○** | — | — |
| **`historia_clinica.leer_sensible`** (N3) | — | — | — | ○ | — | — |
| `diagnostico.registrar` | — | — | — | ○ | — | — |
| **`receta.crear` / `receta.confirmar`** | — | — | — | **○** | — | — |
| `receta.leer` | — | — | — | ○ | ○ | — |
| **`imagen_clinica.leer` / `imagen_clinica.cargar`** (N2; N3 requiere `historia_clinica.leer_sensible`) | — | — | — | ○ | ○ | — |
| **`odontograma.leer`** | — | — | — | ○ | ○ | — |
| **`odontograma.escribir`** | — | — | — | **○** | — | — |
| **`plan_tratamiento.leer`** | — | — | — | ○ | ○ | — |
| **`plan_tratamiento.escribir`** | — | — | — | **○** | — | — |
| `adherencia.leer` | — | ○ | — | ○ | ○ | ○ |
| `alerta_adherencia.atender` | — | ○ | — | ○ | ○ | — |
| `pago.registrar` / `pago.validar` | ✓ | ○ | ○ / ○ | — | — | — / — |
| `conocimiento.cargar` | ✓ | ○ | — | ○ | — | — |
| **`conocimiento.aprobar`** | ✓ | ○ | — | ○ (su especialidad) | — | — |
| `conocimiento.archivar` | ✓ | ○ | — | ○ | — | — |
| `promocion.gestionar` | ✓ | ○ | — | — | — | — |
| **`promocion.aprobar`** | ✓ | ○ | — | — | — | — |
| `lista_espera.gestionar` | ✓ | ○ | ○ | ○ | ○ | — |
| `conversacion.leer` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `conversacion.responder` | ✓ | ○ | ○ | ○ | ○ | — |
| `dashboard.leer` | ✓ | ○ | ○ (limitado) | ○ (propio) | — | ✓ |
| `prediccion.consultar` | ✓ | ○ | — | ○ | — | ✓ |
| `reporte.exportar` | ✓ | ○ | ○ (resumen agregado de agenda) | — | — | ✓ |
| `pago.leer` | ✓ | ○ | ○ | — | — | ✓ |
| `gasto.leer` (libro de gastos y flujo de caja) | ✓ | ○ | — | — | — | ✓ |
| `gasto.registrar` (registrar y anular gastos) | ✓ | ○ | — | — | — | — |
| `conocimiento.leer` | ✓ | ○ | ○ | ○ | ○ | ○ |
| `conversacion.tomar` | ✓ | ○ | ○ | ○ | ○ | — |
| `acceso_emergencia.solicitar` | — | — | — | ○ | — | — |
| **`auditoria.leer`** | ✓ | ○ | — | — | — | **✓** |
| `configuracion.escribir` | ✓ | ○ | — | — | — | — |
| `exportacion.solicitar` | ✓ | ○ | — | — | — | ✓ |

Observaciones que importan:

* **El superadministrador no accede a la historia clínica.** Es un rol de operación de la
  plataforma, no asistencial. Separar la administración técnica del acceso clínico evita
  que una cuenta técnica comprometida exponga datos de pacientes.
* **El auditor no lee contenido clínico**, solo metadatos y la pista de auditoría: quién
  accedió a qué y cuándo. Puede verificar sin ver.
* **El administrador de clínica tampoco lee historia clínica.** Gestiona la organización.
* **Asistencia clínica puede cerrar una cita** tras terminar el trabajo operativo; no recibe
  por ello acceso para escribir la historia ni el odontograma.
* Recepción puede exportar únicamente el resumen diario de agenda por estado; no contiene
  nombres, identificadores ni filas de pacientes. El servidor vuelve a comprobar el ámbito.
* El acceso del profesional a N2 y N3 exige **relación asistencial** registrada (cita
  pasada o futura, asignación explícita o derivación), no solo pertenecer a la clínica.
* Un permiso sin ámbito asignado equivale a alcance nulo, no a alcance total.
* **La auditoría es append‑only en PostgreSQL:** disparadores rechazan `UPDATE`, `DELETE` y `TRUNCATE` con SQLSTATE `42501`, incluso cuando la cuenta local es dueña del esquema. En producción, el proceso debe usar una cuenta distinta del dueño para que no pueda desactivar ni quitar estos disparadores; la separación de roles sigue pendiente en el despliegue.
* **La foto de perfil del paciente es N1**, no N2: se ve con `paciente.leer_administrativo` y
  se cambia con `paciente.editar`. Radiografías y fotos clínicas son N2 y exigen
  `imagen_clinica.*`, relación asistencial (si el principal es profesional) y auditoría de
  cada descarga.
* **La historia se revisa desde una especialidad.** Odontograma, placa, planes e imágenes clínicas
  exigen, además del permiso, una especialidad permitida al principal que tenga ese módulo activo
  (`exige_modulo`); si no, 403. Las notas se filtran por la especialidad del autor en el `WHERE`.
  Alergias, medicamentos y recetas se comparten entre especialidades por seguridad clínica.
* **La foto de una persona del equipo es N1.** La ve el personal de la misma clínica (nunca el
  agente) y la cambia la propia persona o quien tiene `usuario.editar`. Mismo saneado y cifrado
  que la foto del paciente; cambiarla deja la anterior como no vigente.
* **Solo el profesional escribe odontograma y plan.** El asistente los consulta para
  preparar el sillón y sube radiografías y fotos, pero no registra hallazgos.
* **Promociones: quien redacta no tiene por qué aprobar.** `promocion.aprobar` es el único
  que envía. Ningún rol asistencial tiene permisos de promoción.
* **La interfaz oculta lo que el rol no puede hacer, el backend lo impide.** Menú, rutas,
  pestañas de la ficha y botones se muestran solo con el permiso que el endpoint exige
  (`guardiaPermiso` en rutas; `tienePermiso` en componentes). Ocultar es comodidad: la
  autorización real sigue siendo la del backend. Cambios de esta revisión: el *Agente
  demo* (simulador) exige `configuracion.escribir`, ya no `conversacion.responder`; la
  ruta `/catalogo` exige `agenda.leer` (antes solo autenticación); la ficha del paciente
  muestra historia, recetas, odontograma, plan e imágenes solo con su permiso de lectura.
* **Usuarios y roles** incluye la tabla «Qué puede hacer cada rol», calculada de los
  permisos reales de cada rol: *Gestiona* (algún permiso de escritura), *Consulta* (solo
  lectura), *Solo registros* (`historia_clinica.leer_metadatos`: sabe que existe un
  registro y quién lo consultó, no su contenido) y *Sin acceso*.

### Permiso exigido por cada endpoint

Esta tabla es el contrato de autorización de la API y se actualiza **en el mismo commit**
que añade el endpoint. Un endpoint que no aparezca aquí es un endpoint cuya autorización
nadie revisó.

Recordatorio: el permiso responde «puede ejecutar esta operación». El **ámbito** responde
«sobre qué datos», y lo aplica el repositorio en el `WHERE` de la consulta. Ninguno de los
dos sustituye al otro; un endpoint con permiso correcto y sin filtro de ámbito tiene un
IDOR.

| Método y ruta | Permiso | Notas |
|---|---|---|
| `POST /api/v1/autenticacion/sesion` | — (público) | Límite de tasa por IP y por cuenta, más estricto que el general. Falla cerrado si Redis no responde |
| `POST /api/v1/autenticacion/refresco` | — (lo autoriza el propio refresco) | Límite de tasa por IP |
| `POST /api/v1/autenticacion/cierre` | — (lo autoriza el propio refresco) | No exige token de acceso válido: cerrar sesión debe funcionar con el de acceso ya caducado |
| `GET /api/v1/autenticacion/yo` | — (solo autenticación) | Devuelve permisos y ámbito **leídos de la base**, no del token |
| `GET /api/v1/usuarios` · `GET /api/v1/usuarios/roles` | `usuario.leer` | Solo usuarios y roles globales o de la clínica del principal |
| `GET /api/v1/usuarios/permisos` | `rol.asignar` | Solo permisos que el principal puede delegar; excluye permisos asistenciales |
| `POST /api/v1/usuarios/roles` | `rol.asignar` | Rol local a la clínica. No puede conceder permisos que quien lo crea no posee |
| `POST /api/v1/usuarios` | `usuario.crear` + `rol.asignar` | Correo globalmente único; roles limitados a la clínica; contraseña inicial marcada para cambio. El rol de sistema Profesional incluye sus capacidades predefinidas, pero exige una ficha profesional activa y libre dentro de la misma clínica; solo exceptúa `acceso_emergencia.solicitar` y `profesional.conectar_calendario` de la comprobación de delegación. Un rol personalizado no recibe esa excepción |
| `PUT /api/v1/usuarios/{id}/roles` | `rol.asignar` | El usuario debe pertenecer a la clínica del principal; reemplaza asignaciones dentro de esa clínica. Cambiar la ficha libera la anterior; una ficha ocupada por otra cuenta se rechaza |
| `PUT /api/v1/usuarios/{id}/estado` | `usuario.editar` para reactivar, `usuario.desactivar` para desactivar | Solo en la clínica del principal; la desactivación revoca sus sesiones activas |
| `GET /api/v1/usuarios/{id}/foto` · `GET /api/v1/profesionales/{id}/foto` | Personal con sesión (no el agente) | N1. Solo personas y fichas de la clínica del principal; otra clínica responde 404; sin foto responde 204 |
| `PUT /api/v1/usuarios/{id}/foto` | La propia persona o `usuario.editar` | Solo en la clínica del principal; tipo real por contenido, sin EXIF, cifrada; auditada `usuario.foto_actualizada` |
| `GET /api/v1/configuracion/integraciones` | `configuracion.escribir` | Devuelve los ajustes y solo el indicador de presencia de cada credencial; las claves nunca se devuelven |
| `PUT /api/v1/configuracion/integraciones/{codigo}` | `configuracion.escribir` | Lista cerrada de proveedores y campos; cifra cada secreto con contexto ligado a clínica, proveedor y campo; rota por versiones sin copiar secretos al historial y audita el cambio |
| `GET /api/v1/ayuda/manuales` | Personal con sesión (nunca el agente) y segundo factor cumplido si el rol lo exige | N0. Devuelve solo los manuales de los roles **vigentes del propio principal**, sin parámetros; un rol de otra clínica nunca aporta manual (filtro `clinica_id` en SQL). Cada sección exige los permisos que describe, cruzados con los efectivos de la sesión, así que retirar un permiso la retira del manual. No se audita: no es lectura clínica ni escritura |
| `POST /api/v1/autenticacion/cambio-contrasena` | — (solo autenticación propia) | Comprueba la contraseña inicial, registra auditoría y revoca sesiones al terminar |
| `GET /salud/vivo` · `GET /salud/listo` | — (público) | No revelan versión, configuración ni datos; `listo` solo nombra extensiones de PostgreSQL ausentes |
| `GET /api/v1/agenda/disponibilidad` | `agenda.leer` | Es una lectura y aun así exige permiso: la disponibilidad revela la carga de trabajo y las ausencias del profesional. Sede fuera de ámbito → **404** |
| `/api/v1/configuracion/agenda/sedes/{id}/horarios` · `/horarios/{id}` | `agenda.leer` para consultar; `agenda.configurar` para crear, editar o eliminar | Todas las operaciones se acotan a clínica y sedes autorizadas; descansos dentro de la franja; periodos solapados → **409** |
| `/api/v1/configuracion/agenda/feriados` | `agenda.leer` para consultar; `agenda.configurar` para crear, editar o eliminar | Cierres de clínica solo con ámbito de todas las sedes; cierres parciales deben tener horas completas y no solaparse |
| `/api/v1/agenda/bloqueos` · `/agenda/bloqueos/{id}` | `bloqueo.gestionar` | Clínica y sedes del principal; con ámbito de profesionales limitado, solo se pueden crear y gestionar bloqueos de profesionales incluidos. Toda la sede o consultorios requieren ámbito de todos los profesionales. Al coincidir citas activas, la API devuelve 409 sin datos del paciente y requiere `aceptar_citas_afectadas=true`; alta, cambios y eliminación quedan auditados. |
| `/api/v1/profesionales/{id}/agenda` · `/{franja_id}` | `agenda.configurar` o `profesional.gestionar` para modificar; `agenda.leer`, `agenda.configurar`, `profesional.leer` o `profesional.gestionar` para consultar | El profesional debe pertenecer a la clínica y a la sede y respetar el ámbito de especialidad, sede y profesional; las horas guardadas se interpretan en la zona horaria local de la sede. Se rechazan franjas horarias y vigencias superpuestas; todas las mutaciones se auditan. |
| `GET/POST /api/v1/profesionales/gestion` · `PUT /api/v1/profesionales/gestion/{id}` | `profesional.gestionar` | Clínica, especialidad, profesional y sedes dentro del ámbito; los ámbitos parciales conservan asignaciones de sedes no visibles. El alta, cambios y lecturas de la ficha se auditan; los contactos solo se exponen a gestores autorizados. |
| `GET /api/v1/agenda/citas` | `agenda.leer` | El filtro de ámbito va en el `WHERE`; el total se cuenta con los mismos filtros que el listado |
| `GET /api/v1/dashboard/` | `dashboard.leer` | Conteos y métricas operativas agregadas con el mismo ámbito de agenda. Las métricas de adherencia solo aparecen al conceder además `adherencia.leer` y reutilizan el ámbito de historia y relación asistencial. Los importes requieren `pago.leer`; la espera se agrupa por hora de llegada |
| `POST /api/v1/dashboard/analisis-local` | `dashboard.leer` | Reglas deterministas sobre las mismas métricas agregadas y el ámbito de agenda; los importes solo aparecen con `pago.leer`; no llama a proveedores externos |
| `POST /api/v1/dashboard/analisis-ia` | `dashboard.leer` + `configuracion.escribir` | Envía a Anthropic únicamente métricas operativas agregadas del periodo, incluida la espera y recuperación de turnos. Excluye métricas de adherencia; audita la solicitud y no envía nombres ni identificadores de pacientes |
| `GET /api/v1/pagos/{id}/historial` | `pago.leer` | Solo pagos dentro del ámbito del usuario; devuelve estado anterior/nuevo, responsable, fecha y comentario administrativo. La tabla tiene bloqueo PostgreSQL contra edición y borrado |
| `GET/POST /api/v1/pagos/cargos/` | `pago.leer` / `pago.registrar` | Filtra y crea cargos dentro de las citas autorizadas. El filtro de vencidos usa saldo confirmado y fecha local efectiva de sede/clínica; excluye cargos sin total o sin saldo pendiente |
| `PATCH /api/v1/pagos/cargos/{id}/total` · `/vencimiento` | `pago.validar` | Conciliación y vencimiento dentro del ámbito; ambas acciones se auditan. El total histórico y la fecha solo pueden fijarse una vez; PostgreSQL rechaza cambios posteriores |
| `GET/POST /api/v1/pagos/{id}/comprobantes` | `pago.leer` / `pago.registrar` | Listado y carga auditados; PDF/JPEG/PNG/WebP con firma real y tamaño limitado. PDF rechaza JavaScript, acciones activas y adjuntos. Almacén cifrado, antivirus requerido en producción, transición atómica a `PROOF_RECEIVED`; metadatos append‑only |
| `GET /api/v1/gastos` | `gasto.leer` | Libro de gastos de la clínica del principal; el `WHERE` limita a sedes del ámbito y solo muestra gastos sin sede (de toda la clínica) con ámbito de todas las sedes. El total del filtro suma solo los vigentes |
| `POST /api/v1/gastos` | `gasto.registrar` | Exige `Idempotency-Key`; no acepta `clinica_id`; la sede debe estar en el ámbito (si no, 404) y un gasto sin sede exige ámbito de todas las sedes; fecha no futura en la zona de la sede; USD; auditado `gasto.registrado` |
| `POST /api/v1/gastos/{id}/anulacion` | `gasto.registrar` | Motivo obligatorio; una sola vez (409 la segunda); fuera de ámbito 404; auditado `gasto.anulado`. Un disparador PostgreSQL impide cualquier otro `UPDATE`, todo `DELETE` y `TRUNCATE` (ADR-0021) |
| `GET /api/v1/gastos/flujo` | `gasto.leer` + `pago.leer` | Base de caja: pagos `CONFIRMED` por fecha local de registro menos gastos vigentes, por día y categoría; periodo de 1 a 366 días, `hasta` exclusivo; sin datos de pacientes |
| `GET /api/v1/pagos/comprobantes/{id}/contenido` | `pago.leer` | La consulta aplica el ámbito del pago en SQL; cada descarga se audita, no expone URL directa de almacenamiento y se entrega como adjunto privado con `nosniff` |
| `GET /api/v1/agenda/citas/{id}` | `agenda.leer` | Cita fuera de ámbito → **404**, indistinguible de una inexistente |
| `POST /api/v1/agenda/citas` | `cita.crear` | Acepta `Idempotency-Key`. El `origen` lo fija el servidor, no el cliente |
| `POST /api/v1/agenda/citas/bloqueos` | `cita.crear` | Crea un `HELD` con caducidad obligatoria |
| `POST /api/v1/agenda/citas/{id}/confirmacion` | `cita.crear` | Un bloqueo vencido no se confirma: 409 |
| `POST /api/v1/agenda/citas/{id}/cancelacion` | `cita.cancelar` | Motivo obligatorio, exigido también por la base de datos |
| `POST /api/v1/agenda/citas/{id}/reprogramacion` | `cita.reprogramar` | Conserva el identificador de la cita; el horario anterior queda en `cita_historial` |
| `POST /api/v1/agenda/citas/{id}/completado` | `cita.completar` | |
| `POST /api/v1/agenda/citas/{id}/inasistencia` | `cita.marcar_inasistencia` | Estado propio, no una cancelación: alimenta la predicción de ausentismo |
| `POST /api/v1/agenda/citas/{id}/llegada` | `cita.registrar_llegada` | Recepción confirma la llegada; se conserva el estado de la cita y se guarda la hora real |
| `POST /api/v1/agenda/citas/{id}/inicio-atencion` | `cita.iniciar_atencion` | Requiere llegada registrada; permite medir espera real. Una cita con llegada no puede marcarse como inasistencia |
| `GET /api/v1/catalogo/clinica` | `agenda.leer`, `clinica.leer`, `configuracion.escribir` o `plan_tratamiento.leer` | Devuelve **la** clínica del solicitante; no acepta identificador, para no invitar a probarlos. No expone la identificación fiscal. `plan_tratamiento.leer` lo necesita para generar el presupuesto imprimible del plan autorizado |
| `GET /api/v1/catalogo/sedes` | `agenda.leer` | Filtrado por ámbito de sede. Devuelve la zona horaria **efectiva** (sede o, si no la fija, clínica) |
| `GET /api/v1/catalogo/consultorios` | `agenda.leer` | Se une con `sede` para obtener `clinica_id`: `consultorio` no lo lleva |
| `GET /api/v1/catalogo/especialidades/gestion`, `POST /api/v1/catalogo/especialidades`, `PUT /api/v1/catalogo/especialidades/{id}`, `PATCH /api/v1/catalogo/especialidades/{id}/estado` | `especialidad.gestionar` | Solo filas de la clínica de sesión; baja lógica por estado. Desactivar se rechaza mientras existan servicios activos. Todas las mutaciones quedan auditadas |
| `GET /api/v1/catalogo/servicios/gestion`, `POST /api/v1/catalogo/servicios`, `PUT /api/v1/catalogo/servicios/{id}`, `PATCH /api/v1/catalogo/servicios/{id}/estado` | `servicio.gestionar` | La especialidad debe estar activa y pertenecer a la clínica; el servicio no puede moverse de especialidad al editarlo. Todas las mutaciones quedan auditadas |
| `GET /api/v1/catalogo/consultorios/gestion` | `sede.gestionar` | Incluye inactivos; limita clínica y sedes al ámbito del principal |
| `POST /api/v1/catalogo/consultorios` | `sede.gestionar` | Comprueba que la sede exista, esté activa y pertenezca al ámbito; registra auditoría |
| `PUT /api/v1/catalogo/consultorios/{id}` y `PATCH /api/v1/catalogo/consultorios/{id}/estado` | `sede.gestionar` | Resuelve la sede propietaria y devuelve 404 fuera del ámbito; registra auditoría |
| `GET /api/v1/catalogo/especialidades` · `/servicios` | `agenda.leer` | Filtrado por ámbito de especialidad. Ámbito vacío → lista vacía |
| `GET /api/v1/catalogo/profesionales` | `agenda.leer` | `EXISTS` sobre `profesional_sede`, no unión: un profesional en dos sedes no debe aparecer duplicado. No expone su WhatsApp ni su correo de calendario |
| `GET /api/v1/catalogo/profesionales/{id}` | `agenda.leer` | Fuera de ámbito → **404** |
| `GET /api/v1/conocimiento/documentos` | `conocimiento.leer` | El listado filtra clínica, sede, especialidad, sensibilidad y ACL; los metadatos de documentos restringidos tampoco se revelan |
| `POST /api/v1/conocimiento/busqueda` | `conocimiento.leer` | El filtro del SQL hibrido aplica clínica, vigencia, sede, especialidad, sensibilidad y ACL del documento tanto al ranking vectorial como al textual. Si existe ACL, exige un grant coincidente por ID de rol vigente, usuario, sede o especialidad y `puede_leer`; una denegación directa prevalece. El agente requiere además `puede_usar_en_agente`. Sin filas de ACL se conserva el alcance general del documento. |
| `GET /api/v1/conocimiento/permisos/opciones` | `conocimiento.aprobar` | Solo devuelve roles globales/de la clínica y usuarios, sedes y especialidades activos de la clínica del principal |
| `GET/PUT /api/v1/conocimiento/documentos/{id}/permisos` | `conocimiento.aprobar` | Reemplazo atómico; valida pertenencia clínica de cada ID, rechaza duplicados y agente sin lectura, denegaciones directas prevalecen y cada cambio queda auditado. Documento ajeno → 404 |
| `GET/POST /api/v1/conocimiento/documentos/{id}/revision-de-riesgo` | `conocimiento.aprobar` | GET devuelve hallazgos y texto de la versión vigente con el mismo filtro que el listado (clínica, sensibilidad, sede, especialidad, ACL); la lectura se audita (`conocimiento.riesgo_leido`). POST desbloquea la aprobación con nota obligatoria. Quien solo carga → 403; documento ajeno → 404 |
| `GET /api/v1/pacientes/` | `paciente.leer_administrativo` | Término mínimo de 3 caracteres (devuelve `termino_ignorado`); documento por coincidencia **exacta**, nunca parcial; techo de 100 resultados. **No se audita fila por fila** |
| `GET /api/v1/pacientes/{id}` | `paciente.leer_administrativo` | **Se audita** (`paciente.consultado`). Fuera de ámbito → 404, indistinguible de inexistente. Solo ficha administrativa: nada clínico |
| `GET /api/v1/conversaciones/pendientes/cuenta` · `/conversaciones` | `conversacion.leer` | Solo hilos reales de WhatsApp derivados a una persona; ámbito por clínica y pacientes asignados. El conteo y la bandeja quedan auditados |
| `GET /api/v1/conversaciones/{id}` | `conversacion.leer` + alcance N2 | Devuelve mensajes entrantes sin la carga cruda del proveedor; cada lectura queda auditada como N2. Conversación ajena o fuera de ámbito → 404 |
| `GET /api/v1/pacientes/{id}/acceso-clinico` | `paciente.leer_administrativo` | Solo sí/no, sin contenido clínico: si quien pregunta puede pedir los datos clínicos (relación asistencial vigente para profesionales; el agente, nunca). Paciente fuera de ámbito → 404 como el resto. Evita que la ficha encadene 404 en notas, odontograma, planes e imágenes. No se audita como lectura clínica |
| `GET /api/v1/historia/pacientes/{id}/notas` | `historia_clinica.leer` | **Exige además relación asistencial vigente.** Filtra versiones N3 en SQL si falta `historia_clinica.leer_sensible`; se audita antes de responder y el evento sube a N3 si devolvió una nota sensible. Paciente inexistente, fuera de ámbito o sin relación → 404 indistinguible. Solo devuelve notas de autores de la especialidad desde la que se revisa (`especialidad_id`; sin él, la propia del profesional). Pedir una especialidad no permitida → 403; la auditoría registra `especialidades_revisadas` |
| `GET /api/v1/historia/especialidades` | `historia_clinica.leer`, `odontograma.leer`, `plan_tratamiento.leer` o `imagen_clinica.leer` | Especialidades desde las que revisa el principal: un profesional, la suya y las asignadas explícitamente (el comodín no abre las ajenas); el resto del personal, las de su ámbito. Nunca el agente |
| `GET /api/v1/catalogo/especialidades/modulos-historia` · `PUT /api/v1/catalogo/especialidades/{id}/modulos-historia` | `especialidad.gestionar` | Módulos de historia por especialidad (odontograma, periodoncia, planes, imágenes). Solo la clínica del principal (otra → 404); cambiar exige motivo, versiona `configuracion_clinica.modulos_historia` y audita `especialidad.modulos_cambiados` |
| `GET /api/v1/agenda/pacientes/{id}/recorrido` | `agenda.leer` (nunca el agente) | Todo lo que pasó con el paciente en la clínica, desde `cita_historial` (append-only), filtrado por el ámbito de agenda. Sin datos clínicos: el motivo de una derivación no se guarda aquí. Auditado `paciente.recorrido_consultado` |
| `POST /api/v1/agenda/citas/{id}/consultorio` · `/salida` | `cita.registrar_llegada` | Exige llegada registrada; el consultorio debe ser de la sede y la exclusión por consultorio sigue en la base de datos. Auditados |
| `GET /api/v1/agenda/citas/{id}/derivacion/opciones` · `POST /derivacion` | `historia_clinica.escribir` **y** `cita.crear` | Si el principal es profesional, exige relación asistencial vigente. Crea la cita de destino con la llegada registrada y la relación asistencial `DERIVACION`. El motivo clínico va como nota de interconsulta, no aquí. Auditado `cita.derivada` |
| `POST /api/v1/agenda/citas/{id}/prolongacion` | `cita.iniciar_atencion` | Solo con la atención en curso; 5–120 min. Sin choque se aplica; con choque queda pendiente y **nunca** se resuelve sola. La exclusión `gist` sigue impidiendo el solapamiento |
| `GET /api/v1/agenda/prolongaciones` · `GET /citas/{id}/prolongacion/opciones` · `POST /prolongacion/resolucion` | `cita.reprogramar` | Recepción decide cada paciente afectado (otro profesional, más tarde o no aplicar con motivo). El paciente movido recibe `CITA_REPROGRAMACION` (hora, sede y profesional, sin datos clínicos). Auditados |
| `GET /api/v1/asistente/sugerencias` · `POST /api/v1/asistente/mensajes` | Personal con sesión (nunca el agente); cada intención exige el permiso de su pantalla | Intención por reglas, no por modelo. Resumen clínico solo con relación asistencial (auditado). No responde decisiones clínicas. Solo crea **borradores** (`DRAFT` de conocimiento, campaña en borrador). Respuestas solo desde documentos aprobados. Cada mensaje se audita (`asistente.consultado`) sin guardar el texto |
| `PUT /api/v1/configuracion/integraciones/typesafe` · `/respuestas_ia` | `configuracion.escribir` | JEV: no se habilita sin clave; la clave se cifra con contexto de clínica y nunca vuelve a salir; umbral 0,5–0,99. Respuestas: Ollama solo en loopback o red privada; Anthropic solo si su integración está habilitada con clave. Versionado y auditado |
| `POST /api/v1/configuracion/integraciones/typesafe/prueba` | `configuracion.escribir` | Envía a JEV un mensaje **sintético** fijo, sin datos de pacientes; informa si respondió o si se usó el respaldo por reglas. Auditado `integracion.probada` |
| `POST /api/v1/historia/notas` | `historia_clinica.escribir` | Exige relación asistencial. N3 requiere además `historia_clinica.leer_sensible`; la creación se audita con su nivel. Los diagnósticos requieren además `diagnostico.registrar` |
| `POST /api/v1/historia/notas/{raiz}/correccion` | `historia_clinica.escribir` | Crea una versión nueva; **no reescribe nada**. Motivo obligatorio, mínimo 5 caracteres. No permite rebajar una raíz N3; la versión nueva hereda N3 y la auditoría también |
| `GET /api/v1/historia/pacientes/{id}/recetas` | `receta.leer` | Exige relación asistencial para profesionales; N3 se filtra en SQL si falta `historia_clinica.leer_sensible`. Cada receta devuelta queda auditada con su sensibilidad, sin datos de medicamento |
| `POST /api/v1/historia/recetas` | `receta.crear` | Nace en **BORRADOR**, nunca confirmada; crear N3 requiere `historia_clinica.leer_sensible` y se audita con ese nivel |
| `POST /api/v1/historia/recetas/{id}/versiones` | `receta.crear` + `receta.confirmar` | Hereda la sensibilidad de la versión anterior; el acceso N3 se filtra antes de modificarla y la auditoría conserva ese nivel |
| `POST /api/v1/historia/recetas/{id}/confirmacion` | `receta.confirmar` | Único camino que genera tomas; un disparador lo respalda. `tomas_generadas = 0` es correcto para un PRN. La auditoría registra la sensibilidad de la receta |
| `POST /api/v1/historia/recetas/{id}/suspension` | `receta.confirmar` | Cancela las tomas **futuras**; las pasadas quedan intactas. N3 conserva auditoría reforzada |
| `POST /api/v1/historia/tomas/{id}/registro` | `adherencia.leer` o `receta.leer` | No acepta una toma futura |
| `POST /api/v1/historia/recetas/{id}/adherencia` | `adherencia.leer` | Cuenta omisiones y crea una alerta si se cumple el umbral; registra auditoría y **no interpreta clínicamente** |
| `GET /api/v1/historia/adherencia/alertas` | `adherencia.leer` | Solo alertas abiertas dentro de clínica, ámbito y relación asistencial; cada paciente se audita |
| `POST /api/v1/historia/adherencia/alertas/{id}/atencion` | `alerta_adherencia.atender` | Cierra una alerta dentro del ámbito; la acción se audita, y no agrega datos clínicos a la auditoría |
| `POST /api/v1/agenda/citas` con `consultorio_id` | `cita.crear` | El consultorio debe existir, estar activo y ser **de la sede de la cita**; de otra sede o inexistente → 404, inactivo → 422. El choque de sala lo resuelve la restricción `gist` → 409 |
| `GET /api/v1/automatizaciones`, `PUT /api/v1/automatizaciones/{codigo}` | Ver: `configuracion.escribir` o `auditoria.leer`; cambiar: `configuracion.escribir` | Estado por clínica versionado en `configuracion_clinica`; el principal de sesión determina la clínica, sin aceptar un identificador del cliente. `test_el_estado_de_automatizaciones_no_se_cruza_entre_clinicas` verifica que un cambio no altera el estado visible de otra clínica. Cambio con motivo y auditoría `automatizacion.cambiada`. Los flujos obligatorios (aviso de cambio de cita, derivación a persona, comprobantes) no se apagan. Un flujo apagado no encola mensajes |
| `GET /api/v1/historia/pacientes/{id}/resumen-clinico` | `historia_clinica.leer` + relación asistencial | Resumen estructurado sin IA; antecedentes y notas N3 solo con `historia_clinica.leer_sensible`, con filtro SQL. Si incluye N3, la lectura se audita como N3. El acceso sin permiso, fuera de ámbito, sin paciente o sin relación asistencial responde 404 indistinguible; la falta de permiso queda registrada por la dependencia de autorización. La interfaz permite solicitar acceso temporal de emergencia con motivo sin afirmar por qué el dato no está disponible. |
| `POST /api/v1/historia/pacientes/{id}/anamnesis/alergias` · `/antecedentes` | `historia_clinica.escribir` + identidad profesional y relación asistencial; N3 exige además `historia_clinica.leer_sensible` | Clínica y ámbito de paciente se validan en servidor. Alergia activa duplicada → 409. Antecedentes se agregan sin reescribir los anteriores. Nivel sensible registrado en auditoría sin copiar texto clínico a metadatos. |
| `POST /api/v1/historia/pacientes/{id}/anamnesis/alergias/{alergia_id}/desactivacion` | `historia_clinica.escribir` + identidad profesional y relación asistencial | Solo desactiva alergia activa del paciente indicado; requiere motivo y conserva la fila. Audita la referencia y paciente sin copiar sustancia o motivo |
| `POST /api/v1/historia/pacientes/{id}/resumen-clinico/redaccion` | Ídem | Solo IA **local** (Ollama en la máquina o red privada; se rechaza otra URL). Sin identificadores, antecedentes ni notas N3 en el prompt, incluso si quien lo pide puede leerlos; instrucciones sin diagnósticos ni recomendaciones, el texto no se guarda. Auditado `historia_clinica.resumen_redactado`. Desactivado por defecto |
| `POST /api/v1/historia/pacientes/{id}/indicaciones`, `GET` ídem, `PATCH /api/v1/historia/indicaciones/{id}/anulacion` | Escribir: `historia_clinica.escribir`; leer: `historia_clinica.leer`; ambos con relación asistencial | Se guarda el hash del token. El WhatsApp es genérico (regla 10). Append-only: anular exige motivo |
| `POST /api/v1/publico/indicaciones/{token}/acceso` | **Sin sesión** | Verifica fecha de nacimiento (o 4 últimos del documento); límite 10/min por IP; bloqueo al 5.º fallo; misma respuesta para enlace inexistente, caducado o anulado. Lecturas y fallos auditados con el paciente como actor |
| `GET /api/v1/dashboard/indicadores` | Sesión de personal (el agente IA se rechaza) | Cada bloque se calcula **solo** con el permiso de lectura de su módulo (`agenda.leer`, `paciente.leer_administrativo`, `pago.leer`, `usuario.leer`, etc.); sin permiso el bloque es `null`. Aplica el ámbito con las consultas autorizadas de cada módulo. Devuelve solo conteos e importes agregados: ningún nombre, documento ni dato clínico |
| `GET/POST /api/v1/pacientes/{id}/imagenes` | `imagen_clinica.leer` / `imagen_clinica.cargar` | Relación asistencial. N3 requiere además `historia_clinica.leer_sensible`; las filas N3 se filtran en SQL al listar y el nivel se audita. Tipo real por contenido (JPEG, PNG, WebP), metadatos EXIF/GPS eliminados, cifrado AES‑GCM ligado al id antes del almacén. `procedimiento_id` opcional: solo un procedimiento de un plan del mismo paciente y clínica (si no, 404) |
| `GET /api/v1/imagenes/{id}/contenido` | `imagen_clinica.leer` (clínica) o `paciente.leer_administrativo` (perfil) | El alcance se comprueba con el paciente **real** de la imagen (cierra el IDOR); N3 devuelve 404 sin permiso sensible. **Cada descarga clínica se audita con su nivel**. Sin URL firmada: todo pasa por el API |
| `GET/POST /api/v1/pacientes/{id}/foto-perfil` | `paciente.leer_administrativo` / `paciente.editar` | N1. Mismo saneado y cifrado que una imagen clínica |
| `/api/v1/odontologia/pacientes/{id}/odontograma*` | `odontograma.leer` / `odontograma.escribir` | Versiones append‑only; un disparador rechaza `UPDATE`/`DELETE` salvo apagar `vigente`. Control optimista por versión |
| `POST /api/v1/odontologia/planes-tratamiento/{id}/aceptacion` | `plan_tratamiento.escribir` | Solo el profesional responsable. **Registra** una aceptación firmada en papel (medio y referencia obligatorios, exigidos por `CHECK`); no es firma digital del paciente |
| `POST /api/v1/odontologia/procedimientos/{id}/completado` | `plan_tratamiento.escribir` | Plan aceptado. Con resultado, crea una versión del odontograma ligada al procedimiento. Si cierra una fase y quedan otras, encola un recordatorio **sin datos clínicos** (requiere consentimiento de WhatsApp) |
| `GET /api/v1/pacientes/{id}/consentimientos` · `/consentimientos/textos` | `paciente.leer_administrativo` | Estado por tipo y textos vigentes. Paciente fuera de ámbito → 404 |
| `POST /api/v1/pacientes/{id}/consentimientos` · `/{tipo}/revocacion` | `consentimiento.gestionar` | Exige confirmar la lectura y la versión vigente del texto; guarda el hash del texto exacto. La revocación no borra la fila. Ambos se auditan |
| `GET/POST /api/v1/odontologia/pacientes/{id}/indice-placa` | `odontograma.leer` / `odontograma.escribir` | Índice de O'Leary. Relación asistencial; porcentaje calculado en el servidor; registros inmutables (disparador). Lectura auditada |
| `POST /api/v1/historia/recetas` · `/{id}/confirmacion` (firma) | `receta.crear` / `receta.confirmar` | Firma propia, o por otro **solo con delegación vigente** registrada por administración; sin ella → 403. La auditoría marca `firma_delegada` y quién actuó |
| `POST /api/v1/historia/recetas/{id}/versiones` | `receta.crear` + `receta.confirmar` | Bloquea y verifica la receta confirmada y la relación asistencial; requiere motivo y firma propia o delegada. Conserva receta, líneas y tomas pasadas, suspende la anterior, cancela tomas/avisos futuros y crea el reemplazo en una transacción. Disparadores PostgreSQL impiden reescribir o borrar recetas firmadas y sus líneas |
| `GET/POST /api/v1/profesionales/delegaciones` · `/{id}/revocacion` | `profesional.gestionar` | Delegación de firma con vigencia y motivo obligatorios; se revoca, no se borra. `GET /delegaciones/mias` (`receta.crear` o `receta.confirmar`) muestra por quién puede firmar el profesional |
| `POST /api/v1/historia/notas` · `/{raiz}/correccion` (autoría) | `historia_clinica.escribir` | **El autor sale de la sesión.** Antes se aceptaba cualquier `profesional_id` del cuerpo (se podía firmar a nombre de otro); ahora un valor distinto → 403. Una `cita_id` de otro paciente → 404 |
| `GET/POST /api/v1/odontologia/plantillas-plan` · `/{id}/retiro` | `plan_tratamiento.leer` / `plan_tratamiento.escribir` | Catálogo de la clínica, sin datos de pacientes. Se retiran con motivo; nunca se borran |
| `/api/v1/promociones/campanas*` (lectura, borrador, imagen, audiencia) | `promocion.gestionar` | La audiencia es un **recuento**, nunca una lista de pacientes. El segmento solo usa sede y antigüedad de la última visita |
| `POST /api/v1/promociones/campanas/{id}/aprobacion` · `/envio` · `/cancelacion` | `promocion.aprobar` | Sin imagen no se aprueba (`CHECK`). Solo pacientes con consentimiento `PROMOCIONES` vigente; el outbox lo vuelve a comprobar por mensaje. Clave de deduplicación por campaña y paciente |
| `GET /api/v1/whatsapp/webhook` | — (**público**) | Reto de verificación de Meta. Compara `hub.verify_token` en **tiempo constante** y devuelve el reto en texto plano. Token incorrecto → 403 |
| `POST /api/v1/whatsapp/webhook` | — (**público**) | **El único endpoint sin autenticación que escribe.** Lo que lo autoriza es la firma HMAC‑SHA256 sobre el **cuerpo crudo**, comparada con `compare_digest`. Firma inválida → **403 sin escribir nada**, auditado como `webhook.firma_invalida` (acción con alerta). Deduplicación por restricción única en `mensaje_entrante.external_id`. Límite de 120/min por IP (falla abierto, E‑11) y tope de 1 MB. Responde 200 ante cualquier otro fallo, a propósito: un 5xx repetido le cuesta al sistema la suscripción del webhook. **Ninguna intención cambia el estado de una cita** (ADR‑0017). `BAJA` y `BAJA_PROMOCIONES` ejecutan retiros de consentimiento por frase exacta. Las cinco respuestas de medicación solo actúan si el hilo identifica inequívocamente al paciente y existe una toma dentro de la ventana: `TOMADA` registra adherencia; `RECORDARME DESPUÉS` programa un aviso separado a 30 minutos sin alterar la hora prescrita; `NO PUDE TOMARLA` registra omisión y deriva al equipo; `AYUDA` deriva a una persona; una frase explícita de problema crea revisión clínica persistente y deriva al equipo. Los mensajes salientes no nombran medicamento ni dosis. El modelo de decisión (Jev o reglas) solo **etiqueta y prioriza** la derivación de mensajes libres; nunca ejecuta. La confirmación del webhook no contiene datos del paciente |
| `GET /api/v1/calendario/conexiones` | `profesional.conectar_calendario` | Solo las **propias**. El filtro es por `principal.profesional_id`, no por un parámetro: no hay forma de pedir las de otro. No devuelve los tokens, ni cifrados |
| `POST /api/v1/calendario/oauth/inicio` | `profesional.conectar_calendario` | Devuelve la URL de consentimiento con un `state` firmado (HMAC), vigencia de 15 min y de un solo uso. Sin `GOOGLE_CLIENT_ID` → 503 con el modo a usar |
| `GET /api/v1/calendario/oauth/callback` | — (**público**) | Lo llama el navegador redirigido por Google. Lo autoriza el `state` firmado: firma en tiempo constante, caducidad, y **consumo** registrado en `clave_idempotencia` (su restricción única es la garantía, no un `SELECT` previo). Se consume **antes** de canjear el código. Los tokens se guardan cifrados con AES-GCM y contexto `profesional_id`, y no salen en la respuesta |
| `POST /api/v1/calendario/conexiones/{id}/desconexion` | `profesional.conectar_calendario` | Conexión de otro → **404**, no 403. Pone los tokens a nulo y conserva la fila. Motivo obligatorio; se audita (`calendario.desconectado`) |
| `POST /api/v1/calendario/conexiones/{id}/sincronizacion` | `profesional.conectar_calendario` | Conexión de otro → 404 |
| `GET /api/v1/calendario/conexiones/{id}/eventos` | `profesional.conectar_calendario` | Solo estados de sincronización: ni paciente, ni servicio, ni motivo (RF-I09). Conexión de otro → 404 |

### Acceso de emergencia

Un profesional activo puede necesitar la historia de un paciente que no es suyo (urgencia,
cobertura de turno). Desde Historia puede solicitar acceso con un motivo escrito de al menos
12 caracteres. Se crea una relación asistencial `EMERGENCIA` que caduca a los 30 minutos;
la lectura vuelve a denegarse automáticamente después de ese plazo. La concesión se marca en
auditoría y genera una notificación administrativa dentro de ClinicAI. El aviso muestra al
profesional y los horarios, no la identidad del paciente ni el motivo clínico; el equipo con
`auditoria.leer` puede marcarlo como revisado. La lectura de la historia se registra por sus
controles normales. Esta excepción no concede permiso para escribir notas ni firmar recetas.

---

## 3. Controles técnicos

### Autenticación y sesiones

| Control | Implementación | Estado |
|---|---|---|
| Hash de contraseñas | Argon2id, parámetros según OWASP | **implementado y probado** |
| Política de contraseñas | longitud mínima 12, comprobación contra lista de filtradas | Fase 2 |
| Token de acceso | JWT de 15 min, sin permisos en el contenido | **implementado y probado** |
| Token de refresco | rotativo, hash en base de datos, revocable | **implementado y probado** |
| Revocación inmediata de acceso | Cada petición valida que la familia conserve un refresco vigente; cierre de sesión, desactivación o cambio global de clínica/roles invalida JWT de acceso existentes | **implementado y probado** |
| Detección de robo de token | reutilizar un refresco rotado revoca la familia de sesiones | **implementado y probado** |
| Segundo factor | TOTP obligatorio para superadmin, admin y auditor | **implementado y probado**; ver E‑10 en `known-limitations.md` (usa reloj de pared, exige NTP) |
| Bloqueo por intentos | 5 intentos, 15 min de bloqueo, por cuenta y por IP | **implementado y probado** |
| Historial de accesos | tabla `historial_acceso` | **implementado y probado** |
| Verificación de correo | token de un solo uso con caducidad | Fase 2 |
| Recuperación de contraseña | token de un solo uso; respuesta idéntica exista o no la cuenta | Fase 2 |
| Expiración de sesión | inactividad y vida máxima absoluta | Fase 2 |

### Aplicación

| Control | Implementación | Estado |
|---|---|---|
| Autorización | permiso por endpoint (`exige_permiso`) + filtro de ámbito en repositorio + **relación asistencial** en la historia clínica | **implementado y probado**. La relación asistencial se activa por `profesional_id` en el principal, que se resuelve del usuario en cada petición |
| Protección IDOR | 404 para recursos fuera de ámbito; nunca 403 | **implementado y probado** en agenda, catálogo y pacientes: una prueba por cada transición de estado, porque basta con que una olvide el filtro |
| Ámbito vacío = sin acceso | las cuatro dimensiones (sede, especialidad, profesional, paciente) aplican la misma regla | **implementado y probado**, con una prueba por dimensión. Corrige un fallo real: el filtro de la agenda escribía `if not todos_los_profesionales **and** profesionales`, de modo que un ámbito vacío no filtraba nada; y la dimensión de especialidad no se aplicaba en absoluto |
| Inyección SQL | SQLAlchemy con parámetros enlazados; prohibido componer SQL por cadenas | Fase 2 |
| Validación de entrada | Pydantic v2 estricto; rechazo de campos no declarados; el valor rechazado **no** vuelve en la respuesta | **implementado y probado** |
| XSS | Angular escapa por defecto; `innerHTML` prohibido por lint; CSP sin `unsafe-inline` | Fase 1‑2 |
| CSRF | tokens en cabecera `Authorization`, nunca en cookie (ADR‑0016) | **implementado**; sin superficie CSRF mientras no haya cookie de sesión |
| SSRF | la obtención de documentos por URL usa lista blanca de destinos y bloquea rangos privados y metadatos de nube | Fase 6 |
| Límite de tasa | ventana deslizante en Redis, por IP y por cuenta, más estricto en el inicio de sesión | **implementado y probado**; falla cerrado en autenticación y abierto en el resto (E‑11) |
| Cabeceras | CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY`, `Cache-Control: no-store` | **implementado y probado**. HSTS lo pone el proxy inverso, no la aplicación: pendiente de la Fase 10 |
| CORS | lista explícita de orígenes; comodín rechazado en producción | **implementado** |
| Archivos | verificación del tipo real por contenido, no por extensión; límite de tamaño; nombre saneado; almacenamiento fuera de la raíz web | Fase 6 |
| Antivirus | análisis con clamd; en producción, carga rechazada si no está disponible | Fase 6 |
| Cifrado de tokens de terceros | AES‑GCM con clave de `CLAVE_CIFRADO_DATOS` | Fase 4 |
| Secretos | solo por entorno; `gitleaks` bloqueante en el pipeline | Fase 0 |

### Registros y observabilidad

Los logs son estructurados en JSON y **redactan** de forma activa: nombres, documentos,
teléfonos, correos, contenido de mensajes, diagnósticos y medicamentos no se escriben en
claro. Se registra el identificador del paciente, no sus datos. Los prompts enviados al
LLM se auditan con el contenido clínico sustituido por referencias.

Los registros de las librerías (uvicorn, SQLAlchemy, httpx) pasan por **la misma cadena
de redacción**, no por una salida paralela. Importa: SQLAlchemy escribe las sentencias con
sus parámetros enlazados, y esos parámetros son nombres, documentos y teléfonos de
pacientes. Hay una prueba que lo comprueba emitiendo una línea desde `sqlalchemy.engine`.

Existe además una prueba de seguridad que provoca errores en cada módulo y verifica que
ningún dato personal ni clínico aparece en la salida de los logs.

---

## 4. Política de acceso

1. **Mínimo privilegio.** Un rol nuevo parte de cero permisos.
2. **Ámbito explícito.** Toda asignación de rol declara su ámbito; sin ámbito, no hay
   acceso.
3. **Separación de funciones.** Quien administra la plataforma no lee datos clínicos;
   quien audita no modifica datos.
4. **Relación asistencial.** El acceso clínico requiere vínculo con el paciente.
5. **Revisión periódica.** Trimestral de cuentas activas, roles y ámbitos; el auditor
   dispone del informe.
6. **Baja inmediata.** Al desactivar un usuario se revocan todas sus sesiones en el acto.
7. **Todo acceso a datos clínicos se audita**, incluidas las lecturas.

---

## 5. Política de retención

| Dato | Retención propuesta | Base |
|---|---|---|
| Historia clínica y recetas | Conservación prolongada según normativa sanitaria | **Plazo exacto pendiente de validación jurídica** |
| Citas y su historial | Igual que la historia clínica | Forman parte del registro asistencial |
| Conversaciones de WhatsApp | 12 meses, después solo metadatos | Minimización |
| Contenido de mensajes | 12 meses | Minimización |
| Auditoría | 24 meses como mínimo | Trazabilidad e investigación de incidentes |
| Historial de accesos | 12 meses | Seguridad |
| Outbox entregado | 90 días | Operación |
| Comprobantes de pago | Según plazo tributario | **Pendiente de validación** |
| Documentos de conocimiento archivados | Indefinido con estado `ARCHIVED` | Trazabilidad de lo que el agente pudo responder |
| Respaldos | 30 días de retención cifrada | Operación |
| Predicciones | 12 meses | Evaluación de modelos |

Los plazos marcados como pendientes **no se implementan como borrado automático** hasta
que exista validación jurídica y acuerdo con la clínica. Un borrado automático mal
configurado sobre historia clínica es un daño irreversible.

---

## 6. Registro de tratamiento de datos

| Finalidad | Categorías | Base | Destinatarios | Transferencia internacional |
|---|---|---|---|---|
| Gestión de citas | Identificativos, contacto | Ejecución de la relación asistencial | Personal de la clínica | No |
| Atención clínica | Datos de salud | Relación asistencial | Profesional tratante | No |
| Recordatorios por WhatsApp | Contacto, hora de cita | Consentimiento | Meta Platforms | **Sí — Estados Unidos** |
| Recordatorios de medicación | Contacto, existencia de tratamiento (sin nombre del fármaco en el mensaje) | Consentimiento explícito | Meta Platforms | **Sí** |
| Sincronización de calendario | Hora, sede, referencia sin datos clínicos | Consentimiento del profesional | Google | **Sí — Estados Unidos** |
| Agente conversacional | Texto del mensaje, conocimiento aprobado | Consentimiento | Proveedor de LLM | **Sí** |
| Métricas y predicciones | Datos agregados y de comportamiento | Interés legítimo operativo | Interno | No |

Decisiones de minimización ya tomadas:

* Los mensajes de WhatsApp **no** contienen diagnóstico, motivo de consulta ni nombre de
  medicamento. Un recordatorio dice «tiene una toma programada», no qué fármaco.
* Los eventos de calendario **no** contienen datos clínicos; llevan la referencia interna
  de la cita, no el motivo.
* El agente **no** envía historia clínica al proveedor de LLM.
* El teléfono se almacena con hash en las tablas de conversación cuando el paciente no
  está identificado.

---

## 7. Puntos que requieren revisión legal en Ecuador

**No se afirma cumplimiento de ninguna norma.** Esta es la lista de lo que debe validar
un profesional jurídico junto con la clínica, antes de operar con pacientes reales.

**Protección de datos (LOPDP y su reglamento)**

1. Base de licitud aplicable a cada finalidad, en particular al tratamiento de datos de
   salud como categoría especial.
2. Contenido, forma y evidencia del consentimiento, y cómo se documenta su revocación.
3. Necesidad de **evaluación de impacto** por tratar datos de salud a escala con
   decisiones automatizadas de apoyo.
4. Designación de responsable de protección de datos y si la clínica está obligada.
5. **Transferencia internacional** hacia Meta, Google y el proveedor de LLM: mecanismo de
   legitimación, cláusulas contractuales y evaluación de garantías.
6. Contratos de encargo de tratamiento con cada proveedor.
7. Ejercicio de derechos: acceso, rectificación, eliminación, oposición y portabilidad, y
   **el conflicto entre el derecho de eliminación y el plazo legal de conservación de la
   historia clínica**.
8. Plazos y procedimiento de notificación de brechas a la autoridad y a los afectados.
9. Tratamiento de datos de menores de edad y régimen de consentimiento del representante.

**Normativa sanitaria**

10. Requisitos de la historia clínica electrónica según el Ministerio de Salud Pública:
    contenido mínimo, firma del profesional, inalterabilidad y plazos de conservación.
11. Validez legal de la **receta electrónica** y si se exige firma electrónica del
    profesional. Esto puede cambiar el diseño del módulo de recetas.
12. Requisitos de identificación del paciente para entregar información clínica por un
    canal remoto como WhatsApp.
13. Régimen de la telemedicina y del asesoramiento remoto, si la clínica lo ofrece.
14. Obligaciones de reporte epidemiológico.

**Consumidor y facturación**

15. Política de cancelación, cobros y reembolsos.
16. Requisitos de facturación electrónica del SRI para los pagos.
17. Reglas de comunicación comercial y su separación de los mensajes asistenciales.

**Cumplimiento de terceros**

18. Políticas de WhatsApp Business para uso sanitario y categorías de plantillas
    permitidas para contenido de salud.
19. Condiciones del proveedor de LLM en cuanto a retención, entrenamiento con los datos
    enviados y uso en contextos de salud.

---

## 8. Riesgo residual declarado

* Ninguna defensa contra inyección de prompt es completa. Lo garantizado es que una
  inyección exitosa no otorga acceso a datos no autorizados ni capacidad de escritura.
  Ver [ADR‑0014](decisiones/0014-defensa-prompt-injection.md).
* Las rutas reales contra WhatsApp Cloud API y Google Calendar están sin verificar por
  falta de credenciales. Ver [ADR‑0012](decisiones/0012-adaptadores-sandbox.md).
* El cumplimiento legal está **sin validar**; los 19 puntos anteriores son una lista de
  trabajo pendiente, no un informe de conformidad.
* El cifrado en reposo a nivel de disco depende del despliegue y no está resuelto en este
  repositorio.
* La cadena de custodia de los respaldos depende del entorno de producción, todavía por
  definir.
