# Ficha y herramientas desde Agenda — 2026-10-09

## 1. Solicitud

Permitir el mismo acceso a herramientas al abrir la ficha del paciente desde
una cita de Agenda, conservando su contexto y los permisos por especialidad.

## 2. Implementación

El detalle de la cita mantiene **Ver ficha del paciente** y añade **Elegir qué
registrar**. La segunda acción abre la ficha compartida y su selector. Elegir
una herramienta lleva su panel al área visible y al foco. Cerrar la ficha
limpia la solicitud inicial y restaura el detalle de la cita.

## 3. Contexto y ventanas

Se transmiten paciente y cita original. El selector espera el renderizado de
la ficha para entrar después en la capa modal nativa y conservar controles
activos. Se verifica acceso normal, acceso directo y reapertura móvil, sin
repetir automáticamente el selector al cerrar. La etiqueta de Historia evita
confundir el área consultada con la especialidad real de la cita.

## 4. Causa adicional encontrada

El profesional de una cita nueva no tenía relación asistencial tras iniciar
la atención: una nota devolvía 404. La llegada y el inicio estaban registrados,
pero solo las semillas, derivaciones y el inicio sin cita creaban ese vínculo.
El inicio de la cita ahora lo crea para su profesional asignado y activo.

## 5. Decisiones

El vínculo exige iniciar explícitamente la atención, cita confirmada o
reprogramada y llegada registrada. Abrir una ficha, reservar o registrar la
llegada no concede escritura. Se reutiliza un vínculo permanente vigente;
los revocados y los de emergencia permanecen separados. Se bloquea el paciente
para serializar la comprobación y creación. La transacción incluye auditoría
del vínculo y del inicio. Sin migración ni actualización masiva histórica.

## 6. Archivos

Frontend: Agenda HTML/TS/spec; ficha compartida; selector compartido y spec;
etiqueta de Historia. Backend: Agenda servicios/repositorio, documentación del
modelo de relación, manuales de Ayuda y API de Agenda. Navegador: escenario 25.
README, arquitectura, ADR-0026, seguridad, limitaciones, preparación, AGENTS y
este informe reflejan el recorrido y las decisiones.

## 7. Permisos

`cita.iniciar_atencion` y ámbito validado antes de crear el vínculo. El vínculo
pertenece al profesional de la cita, nunca concede permisos por sí mismo.
Registrar sigue exigiendo perfil vigente, permiso clínico, especialidad propia
y controles de autoría. Recepción consulta y conserva sus acciones
administrativas. N3/Formulario 033 mantienen su permiso adicional.

## 8. Pruebas API

`pytest pruebas/api/test_agenda_api.py -q --no-cov`: **71/71**, 137,60 s, antes
de añadir dos casos de baja profesional. Una ejecución adicional selecciona
las seis regresiones nuevas: vínculo inexistente/vigente/revocado/emergencia,
profesional inactivo y anulado. Comprueban lectura sin vínculo, ausencia de
concesión al agendar/llegar, auditoría, nota con cita, rechazo de repetición y
conservación de relaciones previas. **6/6**, 14,52 s: cuatro casos repetidos
y dos adicionales. Total distinto de esta suite: **73 casos aprobados**.

## 9. Regresión backend

`pytest pruebas/integracion/test_servicio_agenda.py pruebas/api/test_recorrido_api.py
pruebas/api/test_historia_api.py pruebas/unitarias/test_ayuda_manuales.py -q --no-cov`:
**115/115**, 132,27 s. Junto a Agenda son **188 casos distintos aprobados**.
Incluye restricciones de reserva, derivación, seguridad
de Historia y manuales independientes. Todas las pruebas API/integración usan
PostgreSQL exclusivo y transacciones reversibles. No se repitió la batería
completa de 2220 pruebas ni se midió una nueva cobertura backend.

## 10. Interfaz completa y cobertura

`npm.cmd run test:ci -- --runner-config=../tmp/qa-20261009-ficha-agenda/vitest.config.mjs`:
**829/829**, 107 archivos, 277,28 s; configuración temporal con `maxWorkers: 2`.
Cobertura: instrucciones **85,56 %**, ramas **72,92 %**, funciones **81,57 %**,
líneas **87,95 %**. Se mantienen los umbrales y las aserciones.

## 11. Navegador

El escenario 25 aprueba **2/2**, 44,7 s. El profesional inicia la primera
atención desde la interfaz, registra una nota y verifica paciente/cita en la
respuesta 201. Recepción consulta sin acciones de nota o receta. Ambos recorren
acceso normal/directo, 1366×768 y 390×844, foco visible y retorno al turno.
Regresión conjunta 12/15/17/22/24/25: **20/20**, 6,4 minutos, sin reintentos.
Incluye las diez herramientas, seis roles, historia, derivación, PDF y
solicitudes WhatsApp sandbox, teclado y pantallas de trabajo adaptables.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
$env:URL_API='http://127.0.0.1:8020/api/v1'
npx.cmd playwright test escenarios/12-recorrido-y-asistente.spec.ts escenarios/15-pantallas-trabajo.spec.ts escenarios/17-registros-y-documentos.spec.ts escenarios/22-ficha-compartida-marca.spec.ts escenarios/24-menu-herramientas.spec.ts escenarios/25-ficha-desde-agenda.spec.ts --project=chromium
```

## 12. Incidentes de pruebas y correcciones

La primera batería frontend obtuvo 814/829; los fallos iniciales fueron
timeouts al ejecutar tareas intensivas en paralelo, seguidos de errores de
limpieza de TestBed. La repetición completa limita trabajadores a dos y
aprueba todas las pruebas sin ampliar timeouts ni alterar expectativas.
En la prueba nueva de API faltaba el permiso explícito de consulta compartida
en su rol personalizado: se añadió a su fixture, conservando el control real.

El primer fixture de navegador intentaba usar un profesional de una sede
ajena a Recepción. Se corrigió para consultar catálogos según cada rol y
preparar las citas con Administración. El escenario también vuelve a abrir
la cita tras Iniciar atención, porque la agenda recarga y cierra su detalle,
y comprueba la visibilidad del panel completo de evolución y antecedentes:
su título de notas no siempre cabe junto a todos los antecedentes en móvil.

## 13. Calidad

Ruff y formato aprobados; mypy **255 archivos**, sin errores. Lint y compilación
frontend aprobados sin avisos: paquete inicial **468,69 kB**. Bandit de los
archivos modificados aprobado. El escaneo más amplio detectó dos B101 bajos
preexistentes en `agenda/disponibilidad.py`: aserciones de invariantes, sin
hallazgos medios/altos. Ese archivo permanece sin cambios.

## 14. Seguridad y dependencias

No se añadieron paquetes, permisos ni credenciales. `npm.cmd audit --json`
informa **cero vulnerabilidades**. `gitleaks git --pre-commit --staged --redact`
aprueba el índice sin secretos; `git diff --cached --check` aprobado. Las reglas de
ámbito, autoría, clínica, sensibilidad y registro por especialidad permanecen.
Este bloque no realiza nuevas pruebas de penetración ni carga representativa.

## 15. Entorno y configuración

API temporal 8020 y BD exclusiva `clinicai_qa_agenda_7a3ac83f`, migraciones hasta
038, semillas sintéticas, LLM/embeddings mock, WhatsApp/calendario sandbox,
Redis 14 y almacenamiento propio bajo `tmp/qa-20261009-ficha-agenda/almacen`.
El navegador usa la aplicación local 4200 redirigiendo sus peticiones a la API
temporal. No se emplean pacientes reales ni proveedores contratados.

## 16. Despliegue, reversión y restauración

Bloque local en `main`, sin publicación ni despliegue. No cambia el esquema:
revertir el commit revierte interfaz y creación del vínculo al iniciar, pero
no borra relaciones ni notas ya registradas. Restaurar datos requiere el
procedimiento de respaldo existente. Para staging/producción se mantienen
credenciales por entorno, migraciones vigentes y aceptación de la clínica.

## 17. Limpieza

API temporal 8020 detenida y base exclusiva eliminada. El almacén temporal no
creó objetos. Aplicación 4200 y API 8000 comprobadas con HTTP **200**.
Los resultados y auxiliares quedan en `tmp`, ignorados por Git. Se conservan
aplicación 4200, API 8000, base de desarrollo y cambios ajenos.

## 18. Preparación y pendientes

El recorrido de Agenda se valida localmente con roles y ámbitos diferentes.
Las citas históricas ya iniciadas sin vínculo no se reparan al consultarlas;
el inicio profesional explícito sin cita permite establecer responsabilidad.
No se modifica el historial ni se inventan mediciones. La aceptación clínica,
proveedores reales y requisitos de producción documentados siguen pendientes.
