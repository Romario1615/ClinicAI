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
| `bloqueo.gestionar` | ✓ | ○ | ○ | ○ (propio) | — | — |
| `paciente.leer_administrativo` | ✓ | ○ | ○ | ○ | ○ | ✓ |
| `paciente.crear` / `paciente.editar` | ✓ | ○ | ○ | ○ | ○ | — |
| **`historia_clinica.leer`** | — | — | **—** | **○** | ○ (limitado) | ○ (solo metadatos) |
| **`historia_clinica.escribir`** | — | — | — | **○** | — | — |
| **`historia_clinica.leer_sensible`** (N3) | — | — | — | ○ | — | — |
| `diagnostico.registrar` | — | — | — | ○ | — | — |
| **`receta.crear` / `receta.confirmar`** | — | — | — | **○** | — | — |
| `receta.leer` | — | — | — | ○ | ○ | ○ (metadatos) |
| `adherencia.leer` | — | ○ | — | ○ | ○ | ○ |
| `alerta_adherencia.atender` | — | ○ | — | ○ | ○ | — |
| `pago.registrar` / `pago.validar` | ✓ | ○ | ○ / ○ | — | — | ✓ (leer) |
| `conocimiento.cargar` | ✓ | ○ | — | ○ | — | — |
| **`conocimiento.aprobar`** | ✓ | ○ | — | ○ (su especialidad) | — | — |
| `conocimiento.archivar` | ✓ | ○ | — | ○ | — | — |
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
* El acceso del profesional a N2 y N3 exige **relación asistencial** registrada (cita
  pasada o futura, asignación explícita o derivación), no solo pertenecer a la clínica.
* Un permiso sin ámbito asignado equivale a alcance nulo, no a alcance total.

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
| `GET /salud/vivo` · `GET /salud/listo` | — (público) | No revelan versión, configuración ni datos; `listo` solo nombra extensiones de PostgreSQL ausentes |

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
| Autorización | permiso por endpoint (`exige_permiso`) + filtro de ámbito en repositorio | permiso **implementado y probado**; el filtro de ámbito por repositorio, pendiente en los endpoints aún no escritos |
| Protección IDOR | 404 para recursos fuera de ámbito; nunca 403 | Fase 2 |
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

Existe una prueba de seguridad específica que provoca errores en cada módulo y verifica
que ningún dato personal ni clínico aparece en la salida de los logs.

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
