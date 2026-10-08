# Pruebas de extremo a extremo

Navegador real, frontend real, API real y PostgreSQL real. Los proveedores
externos funcionan con adaptadores locales durante esta verificación; no se
envían mensajes ni se realizan llamadas pagadas.

**Última revisión de visibilidad:** **67/67 en 7,7 minutos**. La ficha ofrece
Faciograma y Documentos y PDF como pestañas directas y conserva la cita al
cambiarlas. Se prueban versiones/anulación del mapa, axe en la ficha, PDF de
presupuesto/cotización/receta y solicitudes sandbox. Equipo cubre también editar
una cuenta, quitar/restaurar acceso y conservar su perfil. El selector de Recetas
acepta el contador de borradores en su nombre accesible. Después del ajuste N3 y
de reiniciar la API, los cuatro escenarios de documentos pasan **4/4 en 46,3 s**.
La corrida usa API 8020 y BD exclusiva; 4200/8000 se verificó aparte mediante
lectura y capturas. [Informe](../docs/verificacion-2026-10-07.md#faciograma-visible-y-documentos-desde-la-ficha).

**Revisión del 2026-10-07, CRUD y documentos:** 66/66 escenarios Chromium en
7,8 minutos, seis roles y axe en las 22 rutas del menú. Se añaden edición/baja/
reactivación administrativa, presupuesto desde la ficha con cita, PDF real,
versionado/anulación y enlace privado sandbox; faciograma con teclado,
persistencia, PDF y anchos de 1440/768/390 px. La demografía interceptada respeta
`URL_API` para mantener el aislamiento. La API y BD temporales se eliminaron al
terminar; permanecen los servicios de desarrollo. [Informe](../docs/verificacion-2026-10-07.md#crud-faciograma-y-documentos).

## Qué se prueba aquí, y qué no

**No** se prueban las reglas de dominio. Esas ya tienen más de mil pruebas en el
backend que las cubren mejor y en una fracción del tiempo. Repetirlas a través
del navegador daría una suite lenta y frágil que tarda diez veces más en decir
lo mismo.

Lo que **solo** se puede comprobar aquí es que las piezas encajan:

* que la sesión se propaga del formulario al interceptor y de ahí a la API;
* que **el guardia de navegación y el permiso que el backend exige coinciden**
  —una discrepancia da una sección visible cuyas peticiones fallan en bucle, o
  una sección oculta a quien sí tiene derecho a usarla;
* que un 403 del servidor se convierte en un límite legible y no en un error
  rojo que parece una avería;
* que lo que se ve en pantalla es lo que la API devolvió.

## Cómo se ejecuta

Requiere la infraestructura, la API y el frontend **ya arrancados**. No se
levantan desde aquí a propósito: `webServer` de Playwright los mataría al
terminar, y en este proyecto el servidor de desarrollo es algo que la persona
deja corriendo mientras trabaja.

```powershell
# 1. API aislada del código actual, sin tocar una API de desarrollo que ya esté abierta
cd backend
$env:LIMITE_LOGIN_POR_MINUTO='200'
$env:PROVEEDOR_EMBEDDINGS='mock' # CI local: evita depender del extra opcional fastembed
uv run uvicorn app.main:crear_aplicacion --factory --host 127.0.0.1 --port 8002

# 2. Frontend, en otra terminal
cd frontend
npm start

# 3. Escenarios, en otra terminal
cd pruebas-e2e
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
# Playwright reescribe las llamadas del navegador hacia la API aislada en 8002.
$env:URL_API='http://127.0.0.1:8002/api/v1'
npx playwright test
```

### Auditoría automatizada de accesibilidad

La auditoría usa axe-core y las reglas WCAG 2.2 A/AA dentro de Chromium. Incluye
acceso, panel, agenda, historia clínica y configuración; además inicia sesión con
cada uno de los seis roles, recorre las secciones que ese rol puede abrir y analiza
cada pantalla. La unión de esos menús debe cubrir las 22 rutas (incluidas Ayuda y
Gastos y caja) para que la prueba no pase si se olvida una sección nueva. Son diez
recorridos E2E.

Antes de cada análisis se espera a que terminen las animaciones de entrada de
Motion (los bucles infinitos de los gráficos decorativos no cuentan): se audita la
pantalla asentada, no un fotograma a media opacidad. Por eso cada recorrido por
rol tiene un límite de 120 s; administración audita más de veinte pantallas.

```powershell
npm run test:a11y
```

El test falla si axe detecta una infracción. La auditoría complementa, pero no
sustituye, las pruebas manuales de teclado, lector de pantalla y zoom; tampoco
cubre todavía todas las rutas ni estados interactivos del producto.

La API aislada debe iniciarse con `LIMITE_LOGIN_POR_MINUTO=200`; asignar ese valor
solo en la terminal de Playwright no cambia la configuración del servidor. El
fixture `apoyo/prueba.ts` reescribe las llamadas del navegador al valor de
`URL_API`, de modo que el frontend de desarrollo puede seguir abierto mientras
las pruebas usan otra instancia.

En una base que ya tenga pacientes, si la cuenta local profesional no ve una
nota con versión anterior, se pueden preparar solo esos escenarios clínicos
desde la carpeta `backend` con:

```powershell
uv run python -m app.semillas.cargar --solo-historia-clinica
```

El comando solo opera en local/desarrollo, verifica que la clínica sea sintética
y no vuelve a cargar pacientes, citas ni documentos de conocimiento.

### Por qué hay que subir el límite de acceso

`limite_login_por_minuto` vale **10** por defecto, y es correcto: frena un
ataque por fuerza bruta contra el formulario.

Cada escenario inicia sesión de nuevo porque **los tokens viven solo en
memoria** (ADR‑0016) y no se pueden sembrar con `storageState`. Treinta
escenarios son más de diez accesos por minuto, así que el limitador los frena
—el control funcionando— y la suite falla de forma aparentemente aleatoria.

Subirlo es configuración del entorno de pruebas, **no** una relajación del
control en producción. Se documenta aquí para que nadie lo cambie en el `.env`
de un despliegue creyendo que arregla algo.

### Por qué los navegadores van en `D:`

El disco `C:` de este equipo está al límite. `PLAYWRIGHT_BROWSERS_PATH` apunta
a `D:/playwright-browsers`. Sin esa variable, Playwright descarga Chromium en
`C:` y falla.

## Cómo están escritos

**Se prepara por API y se actúa por interfaz.** Los escenarios clínicos
localizan por API sobre qué paciente probar —uno que tenga una versión anterior
de una nota, o calendario de tomas— y a partir de ahí todo ocurre en la
pantalla. La búsqueda pagina todos los pacientes autorizados para el rol y no
se limita a los registros más recientes.

Recorrer la interfaz a base de clics hasta dar con un paciente que tenga datos
hace la prueba lenta y, sobre todo, **dependiente de cómo siembre el
generador**: funciona hoy y falla dentro de dos meses por un motivo que no tiene
nada que ver con lo que comprueba.

La agenda admite vistas Día, Semana, Mes y Lista. Los ayudantes de E2E seleccionan
citas y huecos tanto en la lista (`.fila-dia`) como en el calendario por horas
(`app-calendario-agenda`); no se debe asumir que Lista está activa al abrir el módulo.
En formularios, selectores accesibles deben incluir el indicador de campo obligatorio
cuando corresponda; por ejemplo, la Lista de espera presenta `Sede *` y `Servicio *`.

Se busca por **número de documento** y no por apellido: varios pacientes
sintéticos comparten apellido, y abrir «el primero que coincide» abre a otra
persona.

## Sin reintentos, tampoco en integración continua

`retries: 0`. Un reintento convierte una prueba intermitente en una que «pasa a
veces» y deja de avisar. Si un escenario falla de forma esporádica, el problema
es el escenario o el sistema, y hay que mirarlo.

## Sin paralelismo

Los escenarios comparten la base de datos de desarrollo y varios escriben en
ella. En paralelo, uno que crea una cita y otro que consulta la agenda del mismo
profesional se estorban, y el fallo aparece de forma intermitente.

Los escenarios que necesitan un turno buscan dentro del horizonte de 60 días
permitido por la API. Así siguen siendo repetibles aunque queden citas sintéticas
de corridas anteriores ocupando una semana cercana.

## Estado

La suite contiene **63 pruebas en 16 archivos**. Antes de añadir la regresión
del perfil de pacientes, la ejecución completa del
2026‑10‑07 aprobó **62/62 en 6,9 minutos**, sin reintentos, con el código
actual sobre `727c9f5`, Angular en 4200 y una API aislada en 8020. Se creó una
base temporal en PostgreSQL local, con extensiones, migraciones y semillas
sintéticas; la API usó IA/embeddings mock, WhatsApp/calendario sandbox y límite
E2E de 200. Los diez recorridos de axe cubrieron las **22 rutas** del menú para
los seis roles. Incluye formularios extensos, ventanas, persistencia por API,
pantallas de trabajo y navegación de pestañas por teclado. El límite normal
de desarrollo continúa en 10. [Detalle de las correcciones](../docs/verificacion-2026-10-07.md).

Después de esa corrida, la corrección del perfil pasó **2/2 recorridos
focalizados en 24,8 segundos**: axe del panel y el escenario nuevo de geometría.
El escenario 16 sustituye solo el desglose demográfico de la respuesta del
dashboard con valores sintéticos para comprobar textos largos, seis dígitos y
celdas protegidas. Comprueba límites y solapamientos en siete anchos entre 320
y 1440 px. La sesión y el resto de la respuesta proceden de la API real; no
escribe datos ni evalúa cálculos demográficos del backend.

| Archivo | Qué cubre |
|---|---|
| `01-acceso.spec.ts` | Redirección al acceso, seis roles locales disponibles, apertura del portal, alta de clínica y sucursal, y asignación de módulos con ámbito limitado a una sucursal |
| `02-autorizacion.spec.ts` | Que el menú coincide con los permisos reales, que recargar cierra la sesión y que **el token no queda en el navegador** |
| `03-pacientes.spec.ts` | Búsqueda, paginación, la ficha, y **los tres vacíos que no se pueden confundir** |
| `04-clinico.spec.ts` | Notas versionadas, ciclo del plan dental con control posterior, el límite del asistente, que **un PRN nunca aparece en el calendario de tomas**, y revisión/atención de alertas por omisiones |
| `05-demo-operativa.spec.ts` | Exportación agregada sin pacientes; reservas simple y recurrente desde una ventana Liquid Glass, reserva por simulador, reprogramación y cancelación, check-in, seguimiento de espera y ocupación accesible en dashboard, cierre de atención y registro de un pago |
| `06-conocimiento.spec.ts` | Consulta RAG desde la interfaz; muestra fuentes aprobadas y deriva las consultas sin respaldo |
| `07-imagenes.spec.ts` | El profesional carga una imagen clínica y la vuelve a ver desde la galería autenticada |
| `08-conversaciones.spec.ts` | El profesional abre la bandeja protegida de mensajes derivados |
| `09-lista-espera.spec.ts` | Recepción registra preferencias y una cita previa, libera un turno, confirma el reagendamiento y la siguiente oferta; verifica la llamada manual cuando falta consentimiento; no conecta WhatsApp |
| `10-equipo.spec.ts` | Administración crea un perfil, le da acceso desde Usuarios y roles con el rol Profesional y el perfil vinculado, edita la ficha y la desactiva; comprueba los cambios en la interfaz |
| `11-sedes.spec.ts` | Administración actualiza el teléfono de una sede desde Configuración, comprueba que se guarda por API y restaura el valor anterior para no alterar los datos locales |
| `12-recorrido-y-asistente.spec.ts` | Prolongación de atención, derivación, recorrido y asistente interno con configuración de JEV |
| `13-revision-riesgo.spec.ts` | Lectura y revisión administrativa de un documento marcado |
| `14-accesibilidad.spec.ts` | Diez recorridos axe: pantallas, ventanas y los seis roles en las 22 rutas del menú |
| `15-pantallas-trabajo.spec.ts` | Agenda y Pacientes en escritorio/móvil; acciones y paginación visibles, desplazamiento interno y pestañas clínicas con flechas, Inicio y Fin |
| `16-panel-demografia.spec.ts` | Perfil de pacientes con valores y etiquetas largas; siete anchos, sin recortes ni solapamientos y sin relleno para celdas protegidas |

## Lo que falta

La corrida completa más reciente aprobó **62/62 pruebas** el 2026‑10‑07 con la API actual, Angular y PostgreSQL. Gastos y caja y Ayuda se cubren por axe y navegación; el alta y anulación de gastos se verifican en pruebas API y de componente. La búsqueda de datos clínicos recorre todas las páginas autorizadas; si falta una historia versionada para el profesional local, la semilla incremental documentada arriba la agrega sin recargar pacientes ni citas. Aún faltan flujos que no corresponden a estos escenarios:

* **Reserva por WhatsApp simulado**, que depende del agente conversacional
  (E‑23) y del webhook, hoy sin conectar a herramientas.
* **Aceptación clínica integral**, con revisión de odontología, medicación,
  seguimiento y procedimientos por personal clínico de la clínica.
