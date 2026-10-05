# Seguridad y privacidad

> Fase 0. Este documento define los controles exigidos y su estado. **El estado real de
> implementación y verificación está en la última columna de cada tabla y en
> [`production-readiness.md`](production-readiness.md).** Nada aquí debe leerse como
> afirmación de cumplimiento.

---

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

---

## 2. Matriz de permisos

Leyenda: **✓** permitido · **○** permitido solo dentro de su ámbito o con relación
asistencial · **—** denegado.

| Permiso | Superadmin | Admin clínica | Recepción | Profesional | Asistente | Auditor |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `clinica.leer` / `clinica.escribir` | ✓ | ○ / ○ | — | — | — | ✓ / — |
| `sede.gestionar` | ✓ | ○ | — | — | — | — |
| `especialidad.gestionar` | ✓ | ○ | — | — | — | — |
| `servicio.gestionar` | ✓ | ○ | — | — | — | — |
| `usuario.crear` / `usuario.desactivar` | ✓ | ○ | — | — | — | — |
| `rol.asignar` | ✓ | ○ | — | — | — | — |
| `profesional.gestionar` | ✓ | ○ | — | ○ (propio) | — | — |
| `agenda.leer` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `cita.crear` / `cita.reprogramar` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.cancelar` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.marcar_inasistencia` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.registrar_llegada` | ✓ | ○ | ○ | ○ | ○ | — |
| `cita.iniciar_atencion` | ✓ | ○ | — | ○ | ○ | — |
| `cita.completar` | ✓ | ○ | — | ○ | ○ | — |
| `bloqueo.gestionar` | ✓ | ○ | ○ | ○ (propio) | — | — |
| `paciente.leer_administrativo` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `paciente.crear` / `paciente.editar` | ✓ | ○ | ○ | ○ | ○ | — |
| **`historia_clinica.leer`** | — | — | **—** | **○** | ○ (limitado) | ○ (solo metadatos) |
| **`historia_clinica.escribir`** | — | — | — | **○** | — | — |
| **`historia_clinica.leer_sensible`** (N3) | — | — | — | ○ | — | — |
| `diagnostico.registrar` | — | — | — | ○ | — | — |
| **`receta.crear` / `receta.confirmar`** | — | — | — | **○** | — | — |
| `receta.leer` | — | — | — | ○ | ○ | ○ (metadatos) |
| **`imagen_clinica.leer` / `imagen_clinica.cargar`** (N2) | — | — | — | ○ | ○ | — |
| **`odontograma.leer`** | — | — | — | ○ | ○ | — |
| **`odontograma.escribir`** | — | — | — | **○** | — | — |
| **`plan_tratamiento.leer`** | — | — | — | ○ | ○ | — |
| **`plan_tratamiento.escribir`** | — | — | — | **○** | — | — |
| `adherencia.leer` | — | ○ | — | ○ | ○ | ○ |
| `alerta_adherencia.atender` | — | ○ | — | ○ | ○ | — |
| `pago.registrar` / `pago.validar` | ✓ | ○ | ○ / ○ | — | — | ✓ (leer) |
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
* El acceso del profesional a N2 y N3 exige **relación asistencial** registrada (cita
  pasada o futura, asignación explícita o derivación), no solo pertenecer a la clínica.
* Un permiso sin ámbito asignado equivale a alcance nulo, no a alcance total.
* **La foto de perfil del paciente es N1**, no N2: se ve con `paciente.leer_administrativo` y
  se cambia con `paciente.editar`. Radiografías y fotos clínicas son N2 y exigen
  `imagen_clinica.*`, relación asistencial (si el principal es profesional) y auditoría de
  cada descarga.
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
| `POST /api/v1/usuarios` | `usuario.crear` + `rol.asignar` | Correo globalmente único; roles limitados a la clínica; contraseña inicial marcada para cambio |
| `PUT /api/v1/usuarios/{id}/roles` | `rol.asignar` | El usuario debe pertenecer a la clínica del principal; reemplaza asignaciones dentro de esa clínica |
| `PUT /api/v1/usuarios/{id}/estado` | `usuario.editar` para reactivar, `usuario.desactivar` para desactivar | Solo en la clínica del principal; la desactivación revoca sus sesiones activas |
| `GET /api/v1/configuracion/integraciones` | `configuracion.escribir` | Devuelve los ajustes y solo el indicador de presencia de cada credencial; las claves nunca se devuelven |
| `PUT /api/v1/configuracion/integraciones/{codigo}` | `configuracion.escribir` | Lista cerrada de proveedores y campos; cifra cada secreto con contexto ligado a clínica, proveedor y campo; rota por versiones sin copiar secretos al historial y audita el cambio |
| `POST /api/v1/autenticacion/cambio-contrasena` | — (solo autenticación propia) | Comprueba la contraseña inicial, registra auditoría y revoca sesiones al terminar |
| `GET /salud/vivo` · `GET /salud/listo` | — (público) | No revelan versión, configuración ni datos; `listo` solo nombra extensiones de PostgreSQL ausentes |
| `GET /api/v1/agenda/disponibilidad` | `agenda.leer` | Es una lectura y aun así exige permiso: la disponibilidad revela la carga de trabajo y las ausencias del profesional. Sede fuera de ámbito → **404** |
| `GET /api/v1/agenda/citas` | `agenda.leer` | El filtro de ámbito va en el `WHERE`; el total se cuenta con los mismos filtros que el listado |
| `GET /api/v1/dashboard/` | `dashboard.leer` | Conteos y métricas operativas agregadas con el mismo ámbito de agenda. Los importes aparecen solo si también tiene `pago.leer`; la espera se agrupa por hora de llegada |
| `POST /api/v1/dashboard/analisis-ia` | `dashboard.leer` + `configuracion.escribir` | Envía a Anthropic únicamente métricas agregadas del periodo, incluida la espera; audita la solicitud y no envía nombres ni identificadores de pacientes |
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
| `GET /api/v1/catalogo/clinica` | `agenda.leer` | Devuelve **la** clínica del solicitante; no acepta identificador, para no invitar a probarlos. No expone la identificación fiscal |
| `GET /api/v1/catalogo/sedes` | `agenda.leer` | Filtrado por ámbito de sede. Devuelve la zona horaria **efectiva** (sede o, si no la fija, clínica) |
| `GET /api/v1/catalogo/consultorios` | `agenda.leer` | Se une con `sede` para obtener `clinica_id`: `consultorio` no lo lleva |
| `GET /api/v1/catalogo/especialidades` · `/servicios` | `agenda.leer` | Filtrado por ámbito de especialidad. Ámbito vacío → lista vacía |
| `GET /api/v1/catalogo/profesionales` | `agenda.leer` | `EXISTS` sobre `profesional_sede`, no unión: un profesional en dos sedes no debe aparecer duplicado. No expone su WhatsApp ni su correo de calendario |
| `GET /api/v1/catalogo/profesionales/{id}` | `agenda.leer` | Fuera de ámbito → **404** |
| `GET /api/v1/conocimiento/documentos` | `conocimiento.leer` | El listado filtra clínica, sede, especialidad, sensibilidad y ACL; los metadatos de documentos restringidos tampoco se revelan |
| `POST /api/v1/conocimiento/busqueda` | `conocimiento.leer` | El filtro del SQL hibrido aplica clínica, vigencia, sede, especialidad, sensibilidad y ACL del documento tanto al ranking vectorial como al textual. Si existe ACL, exige un grant coincidente por ID de rol vigente, usuario, sede o especialidad y `puede_leer`; una denegación directa prevalece. El agente requiere además `puede_usar_en_agente`. Sin filas de ACL se conserva el alcance general del documento. |
| `GET /api/v1/conocimiento/permisos/opciones` | `conocimiento.aprobar` | Solo devuelve roles globales/de la clínica y usuarios, sedes y especialidades activos de la clínica del principal |
| `GET/PUT /api/v1/conocimiento/documentos/{id}/permisos` | `conocimiento.aprobar` | Reemplazo atómico; valida pertenencia clínica de cada ID, rechaza duplicados y agente sin lectura, denegaciones directas prevalecen y cada cambio queda auditado. Documento ajeno → 404 |
| `GET /api/v1/pacientes/` | `paciente.leer_administrativo` | Término mínimo de 3 caracteres (devuelve `termino_ignorado`); documento por coincidencia **exacta**, nunca parcial; techo de 100 resultados. **No se audita fila por fila** |
| `GET /api/v1/pacientes/{id}` | `paciente.leer_administrativo` | **Se audita** (`paciente.consultado`). Fuera de ámbito → 404, indistinguible de inexistente. Solo ficha administrativa: nada clínico |
| `GET /api/v1/conversaciones/pendientes/cuenta` · `/conversaciones` | `conversacion.leer` | Solo hilos reales de WhatsApp derivados a una persona; ámbito por clínica y pacientes asignados. El conteo y la bandeja quedan auditados |
| `GET /api/v1/conversaciones/{id}` | `conversacion.leer` + alcance N2 | Devuelve mensajes entrantes sin la carga cruda del proveedor; cada lectura queda auditada como N2. Conversación ajena o fuera de ámbito → 404 |
| `GET /api/v1/historia/pacientes/{id}/notas` | `historia_clinica.leer` | **Exige además relación asistencial vigente.** Se audita (`historia_clinica.consultada`, N2) antes de responder |
| `POST /api/v1/historia/notas` | `historia_clinica.escribir` | Exige relación asistencial. Los diagnósticos requieren además `diagnostico.registrar` |
| `POST /api/v1/historia/notas/{raiz}/correccion` | `historia_clinica.escribir` | Crea una versión nueva; **no reescribe nada**. Motivo obligatorio, mínimo 5 caracteres |
| `GET /api/v1/historia/pacientes/{id}/recetas` | `receta.leer` | Exige relación asistencial |
| `POST /api/v1/historia/recetas` | `receta.crear` | Nace en **BORRADOR**, nunca confirmada |
| `POST /api/v1/historia/recetas/{id}/confirmacion` | `receta.confirmar` | Único camino que genera tomas; un disparador lo respalda. `tomas_generadas = 0` es correcto para un PRN |
| `POST /api/v1/historia/recetas/{id}/suspension` | `receta.confirmar` | Cancela las tomas **futuras**; las pasadas quedan intactas |
| `POST /api/v1/historia/tomas/{id}/registro` | `adherencia.leer` o `receta.leer` | No acepta una toma futura |
| `POST /api/v1/historia/recetas/{id}/adherencia` | `adherencia.leer` | Cuenta omisiones y crea una alerta si se cumple el umbral; registra auditoría y **no interpreta clínicamente** |
| `GET /api/v1/historia/adherencia/alertas` | `adherencia.leer` | Solo alertas abiertas dentro de clínica, ámbito y relación asistencial; cada paciente se audita |
| `POST /api/v1/historia/adherencia/alertas/{id}/atencion` | `alerta_adherencia.atender` | Cierra una alerta dentro del ámbito; la acción se audita, y no agrega datos clínicos a la auditoría |
| `POST /api/v1/agenda/citas` con `consultorio_id` | `cita.crear` | El consultorio debe existir, estar activo y ser **de la sede de la cita**; de otra sede o inexistente → 404, inactivo → 422. El choque de sala lo resuelve la restricción `gist` → 409 |
| `GET /api/v1/automatizaciones`, `PUT /api/v1/automatizaciones/{codigo}` | Ver: `configuracion.escribir` o `auditoria.leer`; cambiar: `configuracion.escribir` | Estado por clínica versionado en `configuracion_clinica`; cambio con motivo y auditoría `automatizacion.cambiada`. Los flujos obligatorios (aviso de cambio de cita, derivación a persona, comprobantes) no se apagan. Un flujo apagado no encola mensajes |
| `GET /api/v1/historia/pacientes/{id}/resumen-clinico` | `historia_clinica.leer` + relación asistencial | Resumen estructurado sin IA; antecedentes N3 solo con `historia_clinica.leer_sensible`. Auditado como `historia_clinica.consultada` |
| `POST /api/v1/historia/pacientes/{id}/resumen-clinico/redaccion` | Ídem | Solo IA **local** (Ollama en la máquina o red privada; se rechaza otra URL). Sin identificadores en el prompt, instrucciones sin diagnósticos ni recomendaciones, el texto no se guarda. Auditado `historia_clinica.resumen_redactado`. Desactivado por defecto |
| `POST /api/v1/historia/pacientes/{id}/indicaciones`, `GET` ídem, `PATCH /api/v1/historia/indicaciones/{id}/anulacion` | Escribir: `historia_clinica.escribir`; leer: `historia_clinica.leer`; ambos con relación asistencial | Se guarda el hash del token. El WhatsApp es genérico (regla 10). Append-only: anular exige motivo |
| `POST /api/v1/publico/indicaciones/{token}/acceso` | **Sin sesión** | Verifica fecha de nacimiento (o 4 últimos del documento); límite 10/min por IP; bloqueo al 5.º fallo; misma respuesta para enlace inexistente, caducado o anulado. Lecturas y fallos auditados con el paciente como actor |
| `GET /api/v1/dashboard/indicadores` | Sesión de personal (el agente IA se rechaza) | Cada bloque se calcula **solo** con el permiso de lectura de su módulo (`agenda.leer`, `paciente.leer_administrativo`, `pago.leer`, `usuario.leer`, etc.); sin permiso el bloque es `null`. Aplica el ámbito con las consultas autorizadas de cada módulo. Devuelve solo conteos e importes agregados: ningún nombre, documento ni dato clínico |
| `GET/POST /api/v1/pacientes/{id}/imagenes` | `imagen_clinica.leer` / `imagen_clinica.cargar` | Relación asistencial. Tipo real por contenido (JPEG, PNG, WebP), metadatos EXIF/GPS eliminados, cifrado AES‑GCM ligado al id antes del almacén. El listado se audita. `procedimiento_id` opcional: solo un procedimiento de un plan del mismo paciente y clínica (si no, 404) |
| `GET /api/v1/imagenes/{id}/contenido` | `imagen_clinica.leer` (clínica) o `paciente.leer_administrativo` (perfil) | El alcance se comprueba con el paciente **real** de la imagen (cierra el IDOR). **Cada descarga clínica se audita**. Sin URL firmada: todo pasa por el API |
| `GET/POST /api/v1/pacientes/{id}/foto-perfil` | `paciente.leer_administrativo` / `paciente.editar` | N1. Mismo saneado y cifrado que una imagen clínica |
| `/api/v1/odontologia/pacientes/{id}/odontograma*` | `odontograma.leer` / `odontograma.escribir` | Versiones append‑only; un disparador rechaza `UPDATE`/`DELETE` salvo apagar `vigente`. Control optimista por versión |
| `POST /api/v1/odontologia/planes-tratamiento/{id}/aceptacion` | `plan_tratamiento.escribir` | Solo el profesional responsable. **Registra** una aceptación firmada en papel (medio y referencia obligatorios, exigidos por `CHECK`); no es firma digital del paciente |
| `POST /api/v1/odontologia/procedimientos/{id}/completado` | `plan_tratamiento.escribir` | Plan aceptado. Con resultado, crea una versión del odontograma ligada al procedimiento. Si cierra una fase y quedan otras, encola un recordatorio **sin datos clínicos** (requiere consentimiento de WhatsApp) |
| `GET /api/v1/pacientes/{id}/consentimientos` · `/consentimientos/textos` | `paciente.leer_administrativo` | Estado por tipo y textos vigentes. Paciente fuera de ámbito → 404 |
| `POST /api/v1/pacientes/{id}/consentimientos` · `/{tipo}/revocacion` | `consentimiento.gestionar` | Exige confirmar la lectura y la versión vigente del texto; guarda el hash del texto exacto. La revocación no borra la fila. Ambos se auditan |
| `GET/POST /api/v1/odontologia/pacientes/{id}/indice-placa` | `odontograma.leer` / `odontograma.escribir` | Índice de O'Leary. Relación asistencial; porcentaje calculado en el servidor; registros inmutables (disparador). Lectura auditada |
| `POST /api/v1/historia/recetas` · `/{id}/confirmacion` (firma) | `receta.crear` / `receta.confirmar` | Firma propia, o por otro **solo con delegación vigente** registrada por administración; sin ella → 403. La auditoría marca `firma_delegada` y quién actuó |
| `GET/POST /api/v1/profesionales/delegaciones` · `/{id}/revocacion` | `profesional.gestionar` | Delegación de firma con vigencia y motivo obligatorios; se revoca, no se borra. `GET /delegaciones/mias` (`receta.crear` o `receta.confirmar`) muestra por quién puede firmar el profesional |
| `POST /api/v1/historia/notas` · `/{raiz}/correccion` (autoría) | `historia_clinica.escribir` | **El autor sale de la sesión.** Antes se aceptaba cualquier `profesional_id` del cuerpo (se podía firmar a nombre de otro); ahora un valor distinto → 403. Una `cita_id` de otro paciente → 404 |
| `GET/POST /api/v1/odontologia/plantillas-plan` · `/{id}/retiro` | `plan_tratamiento.leer` / `plan_tratamiento.escribir` | Catálogo de la clínica, sin datos de pacientes. Se retiran con motivo; nunca se borran |
| `/api/v1/promociones/campanas*` (lectura, borrador, imagen, audiencia) | `promocion.gestionar` | La audiencia es un **recuento**, nunca una lista de pacientes. El segmento solo usa sede y antigüedad de la última visita |
| `POST /api/v1/promociones/campanas/{id}/aprobacion` · `/envio` · `/cancelacion` | `promocion.aprobar` | Sin imagen no se aprueba (`CHECK`). Solo pacientes con consentimiento `PROMOCIONES` vigente; el outbox lo vuelve a comprobar por mensaje. Clave de deduplicación por campaña y paciente |
| `GET /api/v1/whatsapp/webhook` | — (**público**) | Reto de verificación de Meta. Compara `hub.verify_token` en **tiempo constante** y devuelve el reto en texto plano. Token incorrecto → 403 |
| `POST /api/v1/whatsapp/webhook` | — (**público**) | **El único endpoint sin autenticación que escribe.** Lo que lo autoriza es la firma HMAC‑SHA256 sobre el **cuerpo crudo**, comparada con `compare_digest`. Firma inválida → **403 sin escribir nada**, auditado como `webhook.firma_invalida` (acción con alerta). Deduplicación por restricción única en `mensaje_entrante.external_id`. Límite de 120/min por IP (falla abierto, E‑11) y tope de 1 MB. Responde 200 ante cualquier otro fallo, a propósito: un 5xx repetido le cuesta al sistema la suscripción del webhook. **Ninguna intención cambia el estado de una cita** (ADR‑0017); las únicas que ejecutan son `BAJA` (revoca todo) y `BAJA_PROMOCIONES` (solo publicidad), siempre por frase exacta. El modelo de decisión (Jev o reglas) solo **etiqueta y prioriza** la derivación de mensajes libres; nunca ejecuta. La respuesta es un acuse de recibo y no contiene ningún dato del paciente |
| `GET /api/v1/calendario/conexiones` | `profesional.conectar_calendario` | Solo las **propias**. El filtro es por `principal.profesional_id`, no por un parámetro: no hay forma de pedir las de otro. No devuelve los tokens, ni cifrados |
| `POST /api/v1/calendario/oauth/inicio` | `profesional.conectar_calendario` | Devuelve la URL de consentimiento con un `state` firmado (HMAC), vigencia de 15 min y de un solo uso. Sin `GOOGLE_CLIENT_ID` → 503 con el modo a usar |
| `GET /api/v1/calendario/oauth/callback` | — (**público**) | Lo llama el navegador redirigido por Google. Lo autoriza el `state` firmado: firma en tiempo constante, caducidad, y **consumo** registrado en `clave_idempotencia` (su restricción única es la garantía, no un `SELECT` previo). Se consume **antes** de canjear el código. Los tokens se guardan cifrados con AES-GCM y contexto `profesional_id`, y no salen en la respuesta |
| `POST /api/v1/calendario/conexiones/{id}/desconexion` | `profesional.conectar_calendario` | Conexión de otro → **404**, no 403. Pone los tokens a nulo y conserva la fila. Motivo obligatorio; se audita (`calendario.desconectado`) |
| `POST /api/v1/calendario/conexiones/{id}/sincronizacion` | `profesional.conectar_calendario` | Conexión de otro → 404 |
| `GET /api/v1/calendario/conexiones/{id}/eventos` | `profesional.conectar_calendario` | Solo estados de sincronización: ni paciente, ni servicio, ni motivo (RF-I09). Conexión de otro → 404 |

### Acceso de emergencia

Un profesional puede necesitar la historia de un paciente que no es suyo (urgencia,
cobertura de turno). Se implementa como **acceso declarado**: se exige motivo escrito, se
concede por tiempo limitado, se marca en auditoría como acceso de emergencia y genera
notificación al administrador de la clínica. No se bloquea la atención, pero no pasa
desapercibido.

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
