# ClinicAI: entorno local

Actualizado el 2026-10-06. Esta guía describe el entorno local de ClinicAI, el
acceso de desarrollo por roles y las verificaciones ejecutadas. El entorno usa
cuentas y datos sintéticos; no representa una clínica real ni prepara por sí
solo un despliegue de producción.

La aplicación Angular trabaja contra FastAPI y PostgreSQL. Las operaciones de
pacientes, agenda, historia clínica y pagos se guardan en la base local. El
simulador del agente permite recorrer una reserva sin llamar a un proveedor de
modelos.

Esta entrega no acredita preparación para producción. El estado de los requisitos
externos y operativos se mantiene en [preparación para producción](production-readiness.md)
y [limitaciones conocidas](known-limitations.md).

## Preparación y arranque

El entorno necesita Python y las dependencias de `backend/.venv`, Node.js con las
dependencias del frontend, PostgreSQL con pgvector y Redis. En este equipo la
infraestructura de datos se ejecuta dentro de la distribución WSL2 `clinica`.
El aprovisionamiento inicial se explica en [despliegue](deployment.md).

Se utiliza el `.env` local existente, con `ENTORNO=local`. No es necesario sustituirlo
ni modificar credenciales externas para usar el simulador. Las cuentas y la clínica
sintéticas ya cargadas se reutilizan; volver a cargar la misma semilla devuelve un
aviso de clínica existente y no es un mecanismo para reiniciar los datos.

El arranque conjunto, desde la raíz del repositorio, es:

```powershell
.\infra\scripts\demo-local.ps1
```

El script comprueba PostgreSQL, Redis, migraciones, la salud de la API y una ruta
actual de OpenAPI. Si detecta una API antigua en el puerto 8000, se detiene con
un mensaje para evitar que la interfaz parezca conectada a una versión incompleta.
No detiene procesos que ya estaban ejecutándose. Antes de ejecutar manualmente
Uvicorn, comprueba que el puerto 8000 esté libre; no lances dos instancias.
La secuencia manual es:

```powershell
# Desde la raíz: infraestructura de datos
.\infra\scripts\mantener-wsl.ps1 -SegundoPlano
.\infra\scripts\infra-arriba.ps1

# En una terminal: migraciones y API
Set-Location backend
.\.venv\Scripts\python.exe -m herramientas.esperar_bd
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:crear_aplicacion --factory --host 127.0.0.1 --port 8000
```

En otra terminal, desde la raíz:

```powershell
Set-Location frontend
npm start
```

Para ejecutar también las tareas periódicas, en otra terminal desde la raíz:

```powershell
Set-Location backend
.\.venv\Scripts\arq.exe app.tareas.worker.ConfiguracionWorker
```

La API queda en `http://localhost:8000`, su comprobación de salud en
`http://localhost:8000/salud/listo`, la documentación HTTP en
`http://localhost:8000/docs` y la aplicación en `http://localhost:4200`.
En el arranque manual, `Ctrl+C` detiene el proceso de cada terminal. Detener los
procesos no elimina los datos locales.

## Acceso local por roles

En el entorno local, la pantalla muestra botones para los roles que cuentan con
una cuenta sintética activa. No solicita contraseña ni identificador de clínica.
La sesión local está restringida al entorno de desarrollo; no sustituye el inicio
de sesión normal ni se habilita en producción.

| Botón de acceso | Alcance que se puede revisar |
|---|---|
| Recepción | Agenda, pacientes y tareas administrativas permitidas |
| Asistencia clínica | Medicación y tareas de seguimiento permitidas |
| Profesional de salud | Historia clínica y pacientes dentro de su ámbito asistencial |
| Administración de clínica | Configuración de clínica, usuarios y roles autorizados |
| Auditoría | Funciones de consulta y revisión autorizadas |

La ruta de acceso local elige una cuenta sintética del rol solicitado; no permite
seleccionar otra clínica ni otra cuenta. La API vuelve a validar permisos, sede,
paciente y relación asistencial en cada operación. Los roles visibles pueden
variar si la semilla de esta instalación no creó una cuenta para alguno de ellos.

## Recorrido funcional

1. **Pacientes.** Buscar un paciente sintético, revisar su ficha administrativa,
   registrar otro con datos ficticios o editar sus datos de contacto. El formulario
   no concede verificación de identidad. Para una persona ficticia sin documento,
   elegir el tipo «Sin documento».
2. **Agenda.** Seleccionar sede, especialidad, servicio, profesional y una fecha
   futura con disponibilidad. Apartar un horario y confirmar antes de su caducidad.
   También se puede reprogramar o cancelar una cita, indicando el motivo solicitado.
   En **Configuración → Agenda y feriados**, Administración de clínica puede definir
   horarios semanales, descansos y cierres para una sede o para toda la clínica.
3. **Agente demo.** Elegir el simulador local, paciente, sede, servicio, profesional
   y fecha. Iniciar la simulación, pulsar «Buscar horarios», elegir uno y pulsar
   «Confirmar cita». «Mis citas» permite comprobar el resultado guardado. La agenda
   muestra esa misma cita.
4. **Derivación.** En el agente, pulsar «Hablar con una persona». La conversación
   queda derivada y deja de aceptar gestiones automáticas. «Nueva simulación» abre
   un recorrido independiente.
5. **Pagos.** Seleccionar paciente y cita, registrar importe, método y referencia
   opcional. El registro empieza pendiente. Los cambios de estado requieren el
   permiso de validación. Esta pantalla registra la gestión administrativa; no
   procesa un cobro bancario.
6. **Resumen de actividad.** Seleccionar un período que incluya las citas creadas
   y actualizar. Los recuentos proceden de la agenda. Los importes sólo se muestran
   cuando la cuenta dispone de `pago.leer`.
7. **Lista de espera.** Registrar una entrada compatible con un turno futuro;
   cancelar una cita que lo libere, revisar la oferta y resolverla desde el panel.
   Las ofertas pendientes de llamada requieren actuación de recepción.

Historia clínica, medicamentos y conocimiento permiten completar la revisión con
sus datos sintéticos y los permisos correspondientes. Los detalles de las
herramientas del agente están en [agente.md](agente.md).

## Los dos modos del agente

| Modo | Selección | Comportamiento |
|---|---|---|
| `simulado` | Predeterminado | Guion administrativo local. No llama al proveedor de modelos. Usa las herramientas reales y guarda las operaciones autorizadas en la base local. |
| `configurado` | Elección explícita en «Asistente» | Usa el proveedor seleccionado en el servidor. Si se ha configurado un proveedor externo, puede enviar la conversación sintética y los datos administrativos permitidos a ese proveedor. |

El simulador reconoce frases concretas como `buscar horarios`, `mis citas`,
`confirmar` y `hablar con una persona`, además de la selección numérica de horarios.
El flujo consulta hasta siete días y ofrece como máximo cinco horarios por
respuesta. No debe interpretarse su guion como una evaluación de comprensión de
lenguaje natural.

La sesión del agente simulado dura dos horas y pertenece al usuario y a la clínica
que la abrieron. Los endpoints `/api/v1/agente-demo/` sólo están habilitados en
el entorno `local`. La pantalla no envía mensajes de WhatsApp. El webhook de
WhatsApp conserva su flujo separado de reconocimiento y derivación; no invoca
este bucle conversacional.

El agente no crea ni modifica recetas, dosis, tratamientos o diagnósticos. Las
peticiones clínicas se derivan al personal. Las herramientas administrativas
operan con el ámbito del solicitante y registran auditoría. La disponibilidad
depende de la agenda existente: si un horario ya se ocupó, debe buscarse otro.

Desde **Configuración → Disponibilidad del equipo**, los roles con `agenda.configurar`
o `profesional.gestionar` pueden elegir una sede y profesional y mantener sus
franjas semanales, duración de cita y vigencias. La pantalla indica cuando no hay
franjas particulares y se usa el horario general de la sede.

Desde **Equipo clínico** (permiso `profesional.gestionar`) se crean y editan perfiles,
se les asignan especialidades y una o más sedes, y se puede activar o desactivar su
participación. El acceso de usuario y sus roles se mantienen en **Usuarios y roles**.

## Evidencia disponible

Ejecuciones verificadas el 2026-10-06:

| Comprobación | Resultado registrado |
|---|---|
| Pruebas de backend | **1640 aprobadas, 3 omitidas** en la suite completa |
| Pruebas focalizadas de lista de espera | **55 aprobadas**; incluye rollback real ante la restricción de PostgreSQL y diez respuestas HTTP concurrentes |
| Suite E2E | **56 pruebas aprobadas** con navegador, frontend, API y PostgreSQL; incluye exportación agregada desde Agenda, control posterior dentro del ciclo del plan dental, edición de sede, menú móvil y axe en 20 rutas del menú |
| Pruebas de frontend | **377 aprobadas**; cobertura: **88,92 %** líneas, **72,17 %** ramas y **81,38 %** funciones, sobre sus umbrales |
| Estática del backend | Ruff aprobado en los módulos tocados en esta revisión |
| Pruebas omitidas | Tres integraciones que requieren `PRUEBAS_LLM_REAL=1` y llaman a Anthropic |

Las tres integraciones opcionales se omitieron; no se llamó a Anthropic, Meta ni
Google. Las pruebas E2E usan los adaptadores locales/sandbox y no verifican la
entrega real de proveedores externos. Los resultados no acreditan su integración.

Comando para repetir la suite backend desde la carpeta backend:

```powershell
uv run pytest -q
```

La suite E2E se ejecuta desde la carpeta pruebas-e2e con npx playwright test,
con la API actual y el frontend iniciados según la guía E2E. Para ejecutar los
casos individuales del frontend sin aplicar la puerta de cobertura, usa
npx ng test --watch=false --code-coverage=false desde frontend.

La puerta de cobertura frontend pasó en la ejecución actual. La suite E2E completa
también se ejecutó; sus resultados no sustituyen la verificación de proveedores
externos ni la aceptación clínica integral.

## Límites de esta entrega

El entorno local utiliza únicamente datos sintéticos. No acredita entrega real por
Meta, sincronización con Google Calendar, calidad de elección del modelo ni calidad
semántica con embeddings reales. El arranque local y las pruebas no sustituyen la
revisión jurídica, la infraestructura de producción, la monitorización activa o
los ensayos operativos pendientes.

Los documentos de estado general contienen también hitos históricos; para esta
entrega debe distinguirse la evidencia fechada de esta guía de los resultados de
fases anteriores. Las limitaciones detalladas y los criterios pendientes siguen
en [known-limitations.md](known-limitations.md) y
[production-readiness.md](production-readiness.md).
