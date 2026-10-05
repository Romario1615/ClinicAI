# Pruebas de extremo a extremo

Navegador real, frontend real, API real y PostgreSQL real. Sin dobles de ningún
tipo.

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
# 1. API, con el límite temporal de la suite E2E
cd backend
$env:LIMITE_LOGIN_POR_MINUTO='200'
uv run uvicorn app.main:crear_aplicacion --factory

# 2. Frontend, en otra terminal
cd frontend
npm start

# 3. Escenarios, en otra terminal
cd pruebas-e2e
$env:PLAYWRIGHT_BROWSERS_PATH='D:/playwright-browsers'
npx playwright test
```

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
pantalla.

Recorrer la interfaz a base de clics hasta dar con un paciente que tenga datos
hace la prueba lenta y, sobre todo, **dependiente de cómo siembre el
generador**: funciona hoy y falla dentro de dos meses por un motivo que no tiene
nada que ver con lo que comprueba.

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

La suite contiene **34 escenarios**. Última ejecución completa: **2026-10-05, 34/34 aprobados**. Incluye el recorrido de superadministración y el reagendamiento en lista de espera desde la interfaz: acepta el turno anticipado, cancela la cita anterior y ofrece su horario a la siguiente persona. También cubre la llamada manual cuando falta consentimiento. Para repetirla, inicia una sola instancia actual de la API con `LIMITE_LOGIN_POR_MINUTO=200`; el valor normal de desarrollo continúa en 10.

| Archivo | Qué cubre |
|---|---|
| `01-acceso.spec.ts` | Redirección al acceso, seis roles locales, apertura del portal, alta de clínica y asignación de módulos por superadministración |
| `02-autorizacion.spec.ts` | Que el menú coincide con los permisos reales, que recargar cierra la sesión y que **el token no queda en el navegador** |
| `03-pacientes.spec.ts` | Búsqueda, paginación, la ficha, y **los tres vacíos que no se pueden confundir** |
| `04-clinico.spec.ts` | Notas versionadas, ciclo del plan dental con control posterior, el límite del asistente, que **un PRN nunca aparece en el calendario de tomas**, y revisión/atención de alertas por omisiones |
| `05-demo-operativa.spec.ts` | Reserva, reprogramación y cancelación desde la agenda, check-in, seguimiento de espera en dashboard, cierre de atención y registro de un pago |
| `06-conocimiento.spec.ts` | Consulta RAG desde la interfaz; muestra fuentes aprobadas y deriva las consultas sin respaldo |
| `07-imagenes.spec.ts` | El profesional carga una imagen clínica y la vuelve a ver desde la galería autenticada |
| `08-conversaciones.spec.ts` | El profesional abre la bandeja protegida de mensajes derivados |
| `09-lista-espera.spec.ts` | Recepción registra preferencias y una cita previa, libera un turno, confirma el reagendamiento y la siguiente oferta; verifica la llamada manual cuando falta consentimiento; no conecta WhatsApp |

## Lo que falta

La suite actual contiene 34 escenarios y cubre acceso, autorización, pacientes,
historia clínica, medicación, búsqueda en conocimiento y operaciones de agenda,
pagos y lista de espera. Aún faltan:

* **Reserva completa desde la agenda**. La cancelación visual, la oferta
  resultante y su aceptación ya están cubiertas en el recorrido de lista de espera.
* **Reserva por WhatsApp simulado**, que depende del agente conversacional
  (E‑23) y del webhook, hoy sin conectar a herramientas.
* **Alerta clínica posterior al tratamiento** y aceptación clínica integral.
