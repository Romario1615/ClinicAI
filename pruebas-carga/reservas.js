/**
 * Carga sobre el camino de reserva.
 *
 * Que se mide aqui y por que este camino
 * --------------------------------------
 * La reserva es el unico camino del sistema donde la correccion depende de una
 * garantia del motor bajo concurrencia -- la restriccion de exclusion que
 * impide dos citas solapadas. Todo lo demas puede ir lento; esto no puede ir
 * **mal**.
 *
 * De ahi que el umbral que importa no sea la latencia, sino este:
 *
 *   reservas_duplicadas = 0
 *
 * Es decir: por muchos intentos simultaneos que reciba el mismo turno, o se
 * crea una cita o se rechaza con 409. Nunca dos. Si ese contador sube, la
 * prueba falla aunque la latencia sea excelente.
 *
 * Que NO se mide
 * --------------
 * Nada de esto dice como se comporta el sistema en produccion. Corre contra un
 * portatil con PostgreSQL en WSL2, 200 pacientes y una base de 384 KB. Los
 * numeros sirven para **comparar entre ejecuciones** -- detectar que un cambio
 * empeoro algo -- no para prometerle capacidad a una clinica.
 *
 * Uso
 * ---
 *   k6 run -e URL_API=http://127.0.0.1:8000/api/v1 \
 *          -e CLINICA_ID=<uuid> reservas.js
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const API = __ENV.URL_API || 'http://127.0.0.1:8000/api/v1';
const CLINICA_ID = __ENV.CLINICA_ID;
const CONTRASENA = __ENV.CONTRASENA || 'DesarrolloLocal2026';
const CORREO = __ENV.CORREO || 'rita.recepcion.11@example.invalid';

/**
 * Reservas que el sistema acepto sobre un turno ya ocupado.
 *
 * Es el unico contador que de verdad importa. Cualquier valor distinto de cero
 * significa que la restriccion de exclusion no esta haciendo su trabajo, y eso
 * es dos pacientes citados a la misma hora.
 */
const duplicadas = new Counter('reservas_duplicadas');

/** Colisiones resueltas correctamente: el 409 esperado. */
const colisiones = new Counter('colisiones_resueltas');

const errores_inesperados = new Rate('errores_inesperados');
const latencia_disponibilidad = new Trend('latencia_disponibilidad', true);
const latencia_reserva = new Trend('latencia_reserva', true);

export const options = {
  scenarios: {
    // Fase 1: lectura de disponibilidad, que es lo que mas se pide en una
    // recepcion real -- se consulta muchas veces por cada reserva.
    consulta: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '20s', target: 10 },
        { duration: '30s', target: 10 },
        { duration: '10s', target: 0 },
      ],
      exec: 'consultarDisponibilidad',
    },
    // Fase 2: varios usuarios peleando por los mismos turnos. Es el escenario
    // que busca el fallo, no el que busca el rendimiento.
    contienda: {
      executor: 'constant-vus',
      vus: 8,
      duration: '30s',
      startTime: '60s',
      exec: 'reservarEnContienda',
    },
  },
  thresholds: {
    /**
     * Sin trafico, todos los demas umbrales pasan trivialmente.
     *
     * La primera corrida de esta prueba fallo al conectar y k6 reporto
     * `reservas_duplicadas: 0` en verde. Un informe que dice «cero duplicados»
     * cuando no se intento ni una reserva es peor que un fallo: se archiva como
     * evidencia de algo que nunca se comprobo.
     */
    http_reqs: ['count > 100'],
    // El umbral que no se negocia.
    reservas_duplicadas: ['count == 0'],
    errores_inesperados: ['rate < 0.01'],
    // Latencia: objetivos de este equipo, no promesas de produccion.
    latencia_disponibilidad: ['p(95) < 1500'],
    latencia_reserva: ['p(95) < 2000'],
  },
};

function acceder() {
  const respuesta = http.post(
    `${API}/autenticacion/sesion`,
    JSON.stringify({ correo: CORREO, contrasena: CONTRASENA, clinica_id: CLINICA_ID }),
    { headers: { 'Content-Type': 'application/json' }, tags: { nombre: 'acceso' } },
  );
  if (respuesta.status !== 200) {
    // El limitador de tasa frena el acceso a los 10 por minuto. En una corrida
    // de carga hay que subirlo, igual que en las pruebas de extremo a extremo.
    throw new Error(
      `No se pudo iniciar sesion (${respuesta.status}). ` +
        'Arranque la API con LIMITE_LOGIN_POR_MINUTO alto para la corrida.',
    );
  }
  return respuesta.json('token_acceso');
}

export function setup() {
  if (!CLINICA_ID) {
    throw new Error('Falta CLINICA_ID.');
  }
  const token = acceder();
  const cabeceras = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const servicios = http.get(`${API}/catalogo/servicios`, { headers: cabeceras }).json();
  const profesionales = http.get(`${API}/catalogo/profesionales`, { headers: cabeceras }).json();
  const sedes = http.get(`${API}/catalogo/sedes`, { headers: cabeceras }).json();
  const pacientes = http.get(`${API}/pacientes/?limite=5`, { headers: cabeceras }).json('elementos');

  return {
    token,
    servicio_id: servicios[0].id,
    profesional_id: profesionales[0].id,
    sede_id: sedes[0].id,
    paciente_id: pacientes[0].id,
  };
}

function cabecerasDe(datos) {
  return { Authorization: `Bearer ${datos.token}`, 'Content-Type': 'application/json' };
}

function ventana(dias) {
  const desde = new Date(Date.now() + dias * 86400000);
  desde.setUTCHours(12, 0, 0, 0);
  const hasta = new Date(desde.getTime() + 86400000);
  return { desde: desde.toISOString(), hasta: hasta.toISOString() };
}

export function consultarDisponibilidad(datos) {
  const { desde, hasta } = ventana(3 + (__VU % 5));
  const url =
    `${API}/agenda/disponibilidad?profesional_id=${datos.profesional_id}` +
    `&servicio_id=${datos.servicio_id}&sede_id=${datos.sede_id}` +
    `&desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}`;

  const respuesta = http.get(url, { headers: cabecerasDe(datos), tags: { nombre: 'disponibilidad' } });
  latencia_disponibilidad.add(respuesta.timings.duration);
  errores_inesperados.add(respuesta.status >= 500);
  check(respuesta, { 'disponibilidad responde 200': (r) => r.status === 200 });
  sleep(1);
}

export function reservarEnContienda(datos) {
  // Todos los usuarios virtuales apuntan a la MISMA ventana estrecha, para que
  // choquen de verdad. Repartirlos daria una prueba de rendimiento que no
  // ejercita la garantia.
  const { desde, hasta } = ventana(10);
  const url =
    `${API}/agenda/disponibilidad?profesional_id=${datos.profesional_id}` +
    `&servicio_id=${datos.servicio_id}&sede_id=${datos.sede_id}` +
    `&desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}`;

  const disponibilidad = http.get(url, { headers: cabecerasDe(datos) });
  if (disponibilidad.status !== 200) {
    errores_inesperados.add(disponibilidad.status >= 500);
    return;
  }
  const turnos = disponibilidad.json('turnos') || [];
  if (turnos.length === 0) {
    return;
  }

  // Todos eligen el primero: es el punto de colision.
  const cuerpo = JSON.stringify({
    paciente_id: datos.paciente_id,
    profesional_id: datos.profesional_id,
    servicio_id: datos.servicio_id,
    sede_id: datos.sede_id,
    inicio: turnos[0].inicio,
  });

  const respuesta = http.post(`${API}/agenda/citas`, cuerpo, {
    headers: {
      ...cabecerasDe(datos),
      // Clave distinta por intento: sin ella la idempotencia devolveria la
      // misma cita y la prueba no ejerceria la contienda.
      'Idempotency-Key': `carga-${__VU}-${__ITER}-${Date.now()}`,
    },
    tags: { nombre: 'reserva' },
  });
  latencia_reserva.add(respuesta.timings.duration);

  if (respuesta.status === 201) {
    // Una creacion es legitima solo si el turno estaba libre. Se comprueba
    // despues, en la verificacion final del recuento.
    return;
  }
  if (respuesta.status === 409) {
    colisiones.add(1);
    return;
  }
  errores_inesperados.add(respuesta.status >= 400);
  sleep(0.5);
}

/**
 * Comprobacion final: ninguna cita solapa con otra del mismo profesional.
 *
 * Es la unica forma de afirmar que la garantia se sostuvo bajo carga. Contar
 * los 409 no basta: diria que el sistema rechazo cosas, no que no acepto dos.
 */
export function teardown(datos) {
  const { desde, hasta } = ventana(10);
  const url =
    `${API}/agenda/citas?profesional_id=${datos.profesional_id}` +
    `&desde=${encodeURIComponent(desde)}&hasta=${encodeURIComponent(hasta)}&limite=500`;
  const respuesta = http.get(url, { headers: cabecerasDe(datos) });
  if (respuesta.status !== 200) {
    return;
  }

  const citas = (respuesta.json('elementos') || []).filter((c) =>
    ['HELD', 'CONFIRMED', 'RESCHEDULED'].includes(c.estado),
  );
  const porInicio = {};
  for (const cita of citas) {
    porInicio[cita.inicio] = (porInicio[cita.inicio] || 0) + 1;
  }
  for (const [inicio, cuantas] of Object.entries(porInicio)) {
    if (cuantas > 1) {
      duplicadas.add(cuantas - 1);
      console.error(`DUPLICADO: ${cuantas} citas activas en ${inicio}`);
    }
  }
}
