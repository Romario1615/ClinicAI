# Matriz de formularios y consultas — 2026-10-09

Inventario estático: **66 formularios en 45 plantillas**, incluidos filtros y
compositores de chat. Las vistas de escritorio y móvil de Analítica comparten
el mismo componente. Cada plantilla tiene una suite de componente asociada.
El inventario no cuenta botones de acciones clínicas como formularios adicionales.

La batería de componentes prueba estados y contratos HTTP; API/integración
comprueba validaciones, transacciones, ámbito, auditoría y persistencia.
Chromium recorre los flujos entre pantallas y consulta el resultado mediante API.
La existencia de una suite no acredita por sí sola todas las combinaciones de
entradas: los resultados de ejecución y límites se registran en
[el informe de esta revisión](verificacion-formularios-2026-10-09.md).

## Revisión posterior por módulos y botones

El [inventario reproducible](../infra/scripts/inventariar-interfaz.mjs)
analiza **99 plantillas** con el compilador de Angular: **66 formularios** y
**502 declaraciones de botones**. Resultado del 2026-10-09: cero errores de
análisis y cero botones sin evento, navegación o acción nativa declarada.
Los bucles cuentan una declaración; los controles compartidos se contabilizan
en su componente. Ejecutar desde la raíz, con dependencias frontend instaladas:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
node infra/scripts/inventariar-interfaz.mjs > tmp/inventario-interfaz.json
```

La [matriz por módulos](verificacion-modulos-2026-10-09.md) relaciona esos
controles con pruebas de componentes, API y navegador. Añade recorridos de
catálogo, cuentas/roles, horarios/cierres, bloqueos, mensajería sandbox y
disponibilidad profesional; comprueba el resultado consultando la API.
Incluye regresiones de respuestas tardías, escrituras pendientes y escalas y
agregaciones de Analítica. La existencia de un handler sigue sin acreditar
todas las combinaciones de un control.

## Inventario

Rutas relativas a `frontend/src/app/`. Los enlaces abren el código y su prueba.

| Plantilla | Formularios | Suite de componente |
|---|---:|---|
| [compartido/agente-paciente.component.html](../frontend/src/app/compartido/agente-paciente.component.html) | 1 | [agente-paciente.component.spec.ts](../frontend/src/app/compartido/agente-paciente.component.spec.ts) |
| [compartido/buscador-global.component.ts](../frontend/src/app/compartido/buscador-global.component.ts) | 1 | [buscador-global.component.spec.ts](../frontend/src/app/compartido/buscador-global.component.spec.ts) |
| [compartido/chat-conversacional.component.ts](../frontend/src/app/compartido/chat-conversacional.component.ts) | 1 | [chat-conversacional.component.spec.ts](../frontend/src/app/compartido/chat-conversacional.component.spec.ts) |
| [compartido/editor-registro.component.ts](../frontend/src/app/compartido/editor-registro.component.ts) | 1 | [editor-registro.component.spec.ts](../frontend/src/app/compartido/editor-registro.component.spec.ts) |
| [compartido/galeria-imagenes.component.html](../frontend/src/app/compartido/galeria-imagenes.component.html) | 2 | [galeria-imagenes.component.spec.ts](../frontend/src/app/compartido/galeria-imagenes.component.spec.ts) |
| [compartido/registros-paciente.component.html](../frontend/src/app/compartido/registros-paciente.component.html) | 1 | [registros-paciente.component.spec.ts](../frontend/src/app/compartido/registros-paciente.component.spec.ts) |
| [paginas/acceso/acceso.component.html](../frontend/src/app/paginas/acceso/acceso.component.html) | 1 | [acceso.component.spec.ts](../frontend/src/app/paginas/acceso/acceso.component.spec.ts) |
| [paginas/agenda/agenda.component.html](../frontend/src/app/paginas/agenda/agenda.component.html) | 1 | [agenda.component.spec.ts](../frontend/src/app/paginas/agenda/agenda.component.spec.ts) |
| [paginas/agenda/reprogramar-cita.component.ts](../frontend/src/app/paginas/agenda/reprogramar-cita.component.ts) | 1 | [reprogramar-cita.component.spec.ts](../frontend/src/app/paginas/agenda/reprogramar-cita.component.spec.ts) |
| [paginas/agente-demo/agente-demo.component.html](../frontend/src/app/paginas/agente-demo/agente-demo.component.html) | 1 | [agente-demo.component.spec.ts](../frontend/src/app/paginas/agente-demo/agente-demo.component.spec.ts) |
| [paginas/analitica/analitica.component.html](../frontend/src/app/paginas/analitica/analitica.component.html) | 2 | [analitica.component.spec.ts](../frontend/src/app/paginas/analitica/analitica.component.spec.ts) |
| [paginas/cambiar-contrasena/cambiar-contrasena.component.ts](../frontend/src/app/paginas/cambiar-contrasena/cambiar-contrasena.component.ts) | 1 | [cambiar-contrasena.component.spec.ts](../frontend/src/app/paginas/cambiar-contrasena/cambiar-contrasena.component.spec.ts) |
| [paginas/catalogo/catalogo.component.ts](../frontend/src/app/paginas/catalogo/catalogo.component.ts) | 3 | [catalogo.component.spec.ts](../frontend/src/app/paginas/catalogo/catalogo.component.spec.ts) |
| [paginas/catalogo/modulos-especialidad.component.ts](../frontend/src/app/paginas/catalogo/modulos-especialidad.component.ts) | 1 | [modulos-especialidad.component.spec.ts](../frontend/src/app/paginas/catalogo/modulos-especialidad.component.spec.ts) |
| [paginas/configuracion/agenda-configuracion.component.ts](../frontend/src/app/paginas/configuracion/agenda-configuracion.component.ts) | 2 | [agenda-configuracion.component.spec.ts](../frontend/src/app/paginas/configuracion/agenda-configuracion.component.spec.ts) |
| [paginas/configuracion/agenda-profesionales.component.ts](../frontend/src/app/paginas/configuracion/agenda-profesionales.component.ts) | 1 | [agenda-profesionales.component.spec.ts](../frontend/src/app/paginas/configuracion/agenda-profesionales.component.spec.ts) |
| [paginas/configuracion/anamnesis-configuracion.component.ts](../frontend/src/app/paginas/configuracion/anamnesis-configuracion.component.ts) | 1 | [anamnesis-configuracion.component.spec.ts](../frontend/src/app/paginas/configuracion/anamnesis-configuracion.component.spec.ts) |
| [paginas/configuracion/bloqueos-agenda.component.ts](../frontend/src/app/paginas/configuracion/bloqueos-agenda.component.ts) | 1 | [bloqueos-agenda.component.spec.ts](../frontend/src/app/paginas/configuracion/bloqueos-agenda.component.spec.ts) |
| [paginas/configuracion/configuracion.component.ts](../frontend/src/app/paginas/configuracion/configuracion.component.ts) | 2 | [configuracion.component.spec.ts](../frontend/src/app/paginas/configuracion/configuracion.component.spec.ts) |
| [paginas/configuracion/integraciones-ia.component.ts](../frontend/src/app/paginas/configuracion/integraciones-ia.component.ts) | 2 | [integraciones-ia.component.spec.ts](../frontend/src/app/paginas/configuracion/integraciones-ia.component.spec.ts) |
| [paginas/configuracion/sedes-configuracion.component.ts](../frontend/src/app/paginas/configuracion/sedes-configuracion.component.ts) | 1 | [sedes-configuracion.component.spec.ts](../frontend/src/app/paginas/configuracion/sedes-configuracion.component.spec.ts) |
| [paginas/conocimiento/cargar-documento.component.ts](../frontend/src/app/paginas/conocimiento/cargar-documento.component.ts) | 1 | [cargar-documento.component.spec.ts](../frontend/src/app/paginas/conocimiento/cargar-documento.component.spec.ts) |
| [paginas/conocimiento/conocimiento.component.html](../frontend/src/app/paginas/conocimiento/conocimiento.component.html) | 1 | [conocimiento.component.spec.ts](../frontend/src/app/paginas/conocimiento/conocimiento.component.spec.ts) |
| [paginas/conocimiento/revision-riesgo.component.ts](../frontend/src/app/paginas/conocimiento/revision-riesgo.component.ts) | 1 | [revision-riesgo.component.spec.ts](../frontend/src/app/paginas/conocimiento/revision-riesgo.component.spec.ts) |
| [paginas/delegaciones/delegaciones.component.ts](../frontend/src/app/paginas/delegaciones/delegaciones.component.ts) | 1 | [delegaciones.component.spec.ts](../frontend/src/app/paginas/delegaciones/delegaciones.component.spec.ts) |
| [paginas/equipo/equipo.component.ts](../frontend/src/app/paginas/equipo/equipo.component.ts) | 1 | [equipo.component.spec.ts](../frontend/src/app/paginas/equipo/equipo.component.spec.ts) |
| [paginas/gastos/gastos.component.ts](../frontend/src/app/paginas/gastos/gastos.component.ts) | 3 | [gastos.component.spec.ts](../frontend/src/app/paginas/gastos/gastos.component.spec.ts) |
| [paginas/historia-clinica/anamnesis-captura.component.ts](../frontend/src/app/paginas/historia-clinica/anamnesis-captura.component.ts) | 1 | [anamnesis-captura.component.spec.ts](../frontend/src/app/paginas/historia-clinica/anamnesis-captura.component.spec.ts) |
| [paginas/historia-clinica/formulario-033.component.html](../frontend/src/app/paginas/historia-clinica/formulario-033.component.html) | 1 | [formulario-033.component.spec.ts](../frontend/src/app/paginas/historia-clinica/formulario-033.component.spec.ts) |
| [paginas/historia-clinica/historia-clinica.component.html](../frontend/src/app/paginas/historia-clinica/historia-clinica.component.html) | 1 | [historia-clinica.component.spec.ts](../frontend/src/app/paginas/historia-clinica/historia-clinica.component.spec.ts) |
| [paginas/historia-clinica/indicaciones-paciente.component.ts](../frontend/src/app/paginas/historia-clinica/indicaciones-paciente.component.ts) | 2 | [indicaciones-paciente.component.spec.ts](../frontend/src/app/paginas/historia-clinica/indicaciones-paciente.component.spec.ts) |
| [paginas/historia-clinica/nota-editor.component.ts](../frontend/src/app/paginas/historia-clinica/nota-editor.component.ts) | 1 | [nota-editor.component.spec.ts](../frontend/src/app/paginas/historia-clinica/nota-editor.component.spec.ts) |
| [paginas/historia-clinica/periodontograma.component.html](../frontend/src/app/paginas/historia-clinica/periodontograma.component.html) | 1 | [periodontograma.component.spec.ts](../frontend/src/app/paginas/historia-clinica/periodontograma.component.spec.ts) |
| [paginas/historia-clinica/planes-tratamiento.component.html](../frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.html) | 2 | [planes-tratamiento.component.spec.ts](../frontend/src/app/paginas/historia-clinica/planes-tratamiento.component.spec.ts) |
| [paginas/historia-clinica/receta-editor.component.ts](../frontend/src/app/paginas/historia-clinica/receta-editor.component.ts) | 1 | [receta-editor.component.spec.ts](../frontend/src/app/paginas/historia-clinica/receta-editor.component.spec.ts) |
| [paginas/historia-clinica/resumen-clinico.component.ts](../frontend/src/app/paginas/historia-clinica/resumen-clinico.component.ts) | 3 | [resumen-clinico.component.spec.ts](../frontend/src/app/paginas/historia-clinica/resumen-clinico.component.spec.ts) |
| [paginas/medicamentos/medicamentos.component.html](../frontend/src/app/paginas/medicamentos/medicamentos.component.html) | 1 | [medicamentos.component.spec.ts](../frontend/src/app/paginas/medicamentos/medicamentos.component.spec.ts) |
| [paginas/pacientes/editor-paciente.component.ts](../frontend/src/app/paginas/pacientes/editor-paciente.component.ts) | 1 | [editor-paciente.component.spec.ts](../frontend/src/app/paginas/pacientes/editor-paciente.component.spec.ts) |
| [paginas/pacientes/pacientes.component.html](../frontend/src/app/paginas/pacientes/pacientes.component.html) | 1 | [pacientes.component.spec.ts](../frontend/src/app/paginas/pacientes/pacientes.component.spec.ts) |
| [paginas/pagos/pagos.component.ts](../frontend/src/app/paginas/pagos/pagos.component.ts) | 6 | [pagos.component.spec.ts](../frontend/src/app/paginas/pagos/pagos.component.spec.ts) |
| [paginas/plataforma/plataforma.component.ts](../frontend/src/app/paginas/plataforma/plataforma.component.ts) | 3 | [plataforma.component.spec.ts](../frontend/src/app/paginas/plataforma/plataforma.component.spec.ts) |
| [paginas/promociones/promociones.component.html](../frontend/src/app/paginas/promociones/promociones.component.html) | 1 | [promociones.component.spec.ts](../frontend/src/app/paginas/promociones/promociones.component.spec.ts) |
| [paginas/publico/documentos-publicos.component.ts](../frontend/src/app/paginas/publico/documentos-publicos.component.ts) | 1 | [documentos-publicos.component.spec.ts](../frontend/src/app/paginas/publico/documentos-publicos.component.spec.ts) |
| [paginas/publico/indicaciones-publicas.component.ts](../frontend/src/app/paginas/publico/indicaciones-publicas.component.ts) | 1 | [indicaciones-publicas.component.spec.ts](../frontend/src/app/paginas/publico/indicaciones-publicas.component.spec.ts) |
| [paginas/usuarios/usuarios.component.ts](../frontend/src/app/paginas/usuarios/usuarios.component.ts) | 2 | [usuarios.component.spec.ts](../frontend/src/app/paginas/usuarios/usuarios.component.spec.ts) |

## Reglas comprobadas por dominio

| Dominio | Invariantes |
|---|---|
| Pacientes y consultas | Requeridos, documento coherente, correo/teléfono, idempotencia, edición rechazada conserva datos, búsqueda literal, paginación sin duplicados, ámbito clínico |
| Clínica, sedes, personal y roles | CRUD administrativo, nombres/estados, permisos por módulo/ámbito, perfil profesional y especialidad, sin acceso a otra clínica |
| Agenda, reservas, horarios, bloqueos y espera | Fechas y zonas horarias, anti doble reserva en PostgreSQL, recurrencia, idempotencia, estados y outbox |
| Notas, recetas, anamnesis y herramientas clínicas | Consulta N2 compartida, edición por profesional/especialidad, N3 independiente, versionado, autoría, auditoría y relación asistencial |
| Pagos, cargos y gastos | Importes exactos, estados, idempotencia, filtros y caja; anulaciones preservan trazabilidad |
| Fotos y documentos | Tipo/tamaño, contenido autenticado, ACL, reintento de fotos sin recrear registro, PDF y enlaces privados |
| Conocimiento y agentes | Fuentes aprobadas/vigentes, aislamiento, consentimiento, permisos, IA sin decisiones clínicas, confirmación administrativa y sandbox |
| Analítica y notificaciones | Ámbito, rangos y mínimos de muestra, cálculos de indicadores, datos ausentes y notificaciones sin información clínica |
| Seguridad y formularios públicos | Sesión, token, verificaciones, caducidad y bloqueo, delegaciones y auditoría de accesos |
