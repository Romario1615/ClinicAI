import { randomUUID } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import type { APIRequestContext, Locator, Page } from '@playwright/test';
import { expect, test } from '../apoyo/prueba';
import { acceder, CODIGOS_ROL, irA } from '../apoyo/sesion';
import { huecosVisiblesEnAgenda, seleccionarCitaEnAgenda } from '../apoyo/agenda';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const fecha = (iso: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(iso));
const horaLocal = (iso: string) => new Intl.DateTimeFormat('en-GB', {
  timeZone: 'America/Guayaquil', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}).format(new Date(iso));

function fechaSemanal(iso: string, semanas: number): string {
  const [anio, mes, dia] = fecha(iso).split('-').map(Number);
  return new Date(Date.UTC(anio, mes - 1, dia + semanas * 7)).toISOString().slice(0, 10);
}

async function preparar(request: APIRequestContext) {
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, {
    data: { codigo_rol: CODIGOS_ROL.recepcion },
  });
  expect(acceso.ok()).toBeTruthy();
  const headers = { Authorization: `Bearer ${(await acceso.json()).token_acceso}` };
  const leer = async (ruta: string) => {
    const r = await request.get(API + ruta, { headers });
    expect(r.ok(), `${ruta}: ${r.status()}`).toBeTruthy();
    return r.json();
  };
  const sede = (await leer('/catalogo/sedes'))[0];
  const servicio = (await leer('/catalogo/servicios'))[0];
  const profesional = (await leer(`/catalogo/profesionales?sede_id=${sede.id}&especialidad_id=${servicio.especialidad_id}`))[0];
  const pacientes = (await leer('/pacientes/?limite=100')).elementos;
  // La base de desarrollo conserva citas sintéticas de ejecuciones previas.
  // Buscar hasta el horizonte permitido evita que una semana ya ocupada haga
  // fallar todos los recorridos operativos antes de probar la interfaz.
  const desde = new Date(Date.now() + 14 * 86400000).toISOString();
  const hasta = new Date(Date.now() + 60 * 86400000).toISOString();
  const params = new URLSearchParams({ sede_id: sede.id, profesional_id: profesional.id, servicio_id: servicio.id, desde, hasta });
  const disponibilidad = await leer(`/agenda/disponibilidad?${params}`);
  expect(disponibilidad.turnos.length).toBeGreaterThan(0);
  const turno = disponibilidad.turnos[0];
  // Evita que la pantalla elija por error una cita anterior del mismo paciente
  // al filtrar las filas del día; también deja libre el día de reprogramación.
  const diaLocal = fecha(turno.inicio);
  const inicioDia = new Date(`${diaLocal}T00:00:00-05:00`);
  const agendaVentana = await leer(`/agenda/citas?desde=${encodeURIComponent(inicioDia.toISOString())}&hasta=${encodeURIComponent(new Date(inicioDia.getTime() + 3 * 86400000).toISOString())}&limite=200`);
  const ocupados = new Set(agendaVentana.elementos.map((cita: { paciente_id: string }) => cita.paciente_id));
  const paciente = pacientes.find((p: { id: string; nivel_verificacion: string }) =>
    !ocupados.has(p.id) && p.nivel_verificacion === 'PRESENCIAL',
  ) ?? pacientes.find((p: { id: string }) => !ocupados.has(p.id));
  if (!paciente) throw new Error('No hay un paciente sintetico libre para la ventana de prueba.');
  const cuerpo = { sede_id: sede.id, profesional_id: profesional.id, servicio_id: servicio.id, paciente_id: paciente.id, inicio: turno.inicio };
  return { headers, sede, servicio, profesional, paciente, turno, cuerpo, leer };
}

async function encontrarTurnoParaSerie(datos: Awaited<ReturnType<typeof preparar>>) {
  const desde = new Date(Date.now() + 14 * 86400000).toISOString();
  const hasta = new Date(Date.now() + 60 * 86400000).toISOString();
  const parametros = new URLSearchParams({
    sede_id: datos.sede.id,
    profesional_id: datos.profesional.id,
    servicio_id: datos.servicio.id,
    desde,
    hasta,
  });
  const candidatos = await datos.leer(`/agenda/disponibilidad?${parametros}`);

  for (const candidato of candidatos.turnos.slice(0, 120)) {
    const hora = horaLocal(candidato.inicio);
    let todasDisponibles = true;
    for (const semana of [1, 2]) {
      const dia = fechaSemanal(candidato.inicio, semana);
      const diaDesde = new Date(`${dia}T00:00:00-05:00`).toISOString();
      const diaHasta = new Date(Date.parse(diaDesde) + 86400000).toISOString();
      const parametrosDia = new URLSearchParams({
        sede_id: datos.sede.id,
        profesional_id: datos.profesional.id,
        servicio_id: datos.servicio.id,
        desde: diaDesde,
        hasta: diaHasta,
      });
      const disponibilidad = await datos.leer(`/agenda/disponibilidad?${parametrosDia}`);
      if (!disponibilidad.turnos.some((turno: { inicio: string }) => horaLocal(turno.inicio) === hora)) {
        todasDisponibles = false;
        break;
      }
    }
    if (todasDisponibles) return candidato;
  }

  throw new Error('No se encontró un horario libre para crear una serie semanal de dos citas.');
}

/** La limpieza no debe reemplazar el fallo que Playwright ya está reportando. */
async function limpiarCitaDePrueba(
  request: APIRequestContext,
  datos: Awaited<ReturnType<typeof preparar>>,
  citaId: string,
  huboFallo: boolean,
) {
  try {
    const cita = await datos.leer(`/agenda/citas/${citaId}`);
    if (cita.estado !== 'CANCELLED') {
      const respuesta = await request.post(`${API}/agenda/citas/${citaId}/cancelacion`, {
        headers: datos.headers,
        data: { motivo: 'Cierre de prueba sintetica E2E' },
      });
      expect(respuesta.ok(), `limpieza de cita: ${respuesta.status()}`).toBeTruthy();
    }
  } catch (fallo) {
    if (!huboFallo) throw fallo;
  }
}

async function seleccionarPaciente(contenedor: Page | Locator, paciente: { id: string; apellido: string }) {
  const selector = contenedor.locator('app-selector-paciente');
  await selector.getByLabel('Buscar paciente', { exact: true }).fill(paciente.apellido);
  await selector.getByRole('button', { name: 'Buscar', exact: true }).click();
  const pacientes = selector.getByRole('combobox', { name: 'Paciente', exact: true });
  await pacientes.selectOption(paciente.id);
}

test('recepción exporta el resumen de agenda sin datos de pacientes', async ({ page }) => {
  await acceder(page, 'recepcion');
  await irA(page, 'Agenda');

  const respuesta = page.waitForResponse(
    (r) => new URL(r.url()).pathname.endsWith('/agenda/resumen.csv'),
  );
  const descarga = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar resumen CSV' }).click();
  const http = await respuesta;
  const cuerpo = await http.text();
  expect(http.status(), cuerpo).toBe(200);
  const archivo = await descarga;
  const csv = cuerpo.replace(/^\uFEFF/, '');

  expect(archivo.suggestedFilename()).toMatch(/^resumen-agenda-\d{4}-\d{2}-\d{2}\.csv$/);
  const filas = csv.trim().split(/\r?\n/);
  expect(filas[0]).toBe('Fecha local;Estado;Citas');
  for (const fila of filas.slice(1)) {
    const [fecha, estado, cantidad, ...extra] = fila.split(';');
    expect(fecha).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(estado).toMatch(/^(PENDING|HELD|CONFIRMED|RESCHEDULED|CANCELLED|COMPLETED|NO_SHOW)$/);
    expect(cantidad).toMatch(/^\d+$/);
    expect(extra).toHaveLength(0);
  }
});

test('recepción reserva desde un hueco de la agenda y la API conserva la cita', async ({ page, request }) => {
  const datos = await preparar(request);
  let citaId = '';
  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(datos.turno.inicio));
    await page.getByRole('button', { name: 'Lista', exact: true }).click();

    const huecos = huecosVisiblesEnAgenda(page);
    await expect(huecos.first()).toBeVisible();
    await huecos.first().click();
    const dialogo = page.getByRole('dialog', { name: 'Reservar cita' });
    await expect(dialogo.getByRole('heading', { name: 'Reservar cita' })).toBeVisible();
    await dialogo.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    const auditoria = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(auditoria.violations.map((violacion) => violacion.id)).toEqual([]);
    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `La reserva Liquid Glass no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await seleccionarPaciente(dialogo, datos.paciente);
    const respuesta = page.waitForResponse(r =>
      r.url().endsWith('/agenda/citas') && r.request().method() === 'POST',
    );
    await dialogo.getByRole('button', { name: 'Confirmar cita', exact: true }).click();
    const creada = await respuesta;
    expect(creada.status()).toBe(201);
    const cuerpo = await creada.json();
    citaId = cuerpo.id;
    expect(cuerpo.paciente_id).toBe(datos.paciente.id);
    expect(cuerpo.estado).toBe('CONFIRMED');
    await expect(page.locator('.exito[role="status"]')).toContainText('Cita creada para');
    expect((await datos.leer(`/agenda/citas/${citaId}`)).estado).toBe('CONFIRMED');
  } finally {
    if (citaId) await limpiarCitaDePrueba(request, datos, citaId, false);
  }
});

test('recepción crea dos citas recurrentes desde el formulario Liquid Glass', async ({ page, request }) => {
  const datos = await preparar(request);
  const turno = await encontrarTurnoParaSerie(datos);
  const citasCreadas: string[] = [];
  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(turno.inicio));
    await page.getByRole('button', { name: 'Lista', exact: true }).click();

    const hueco = huecosVisiblesEnAgenda(page).filter({ hasText: horaLocal(turno.inicio) }).first();
    await expect(hueco).toBeVisible();
    await hueco.click();
    const dialogo = page.getByRole('dialog', { name: 'Reservar cita' });
    await dialogo.getByRole('checkbox', { name: /Repetir esta cita/ }).check();
    await dialogo.getByLabel('Frecuencia').selectOption('SEMANAL');
    await dialogo.getByLabel('Cantidad de citas').fill('2');
    await seleccionarPaciente(dialogo, datos.paciente);

    const respuesta = page.waitForResponse((r) =>
      r.url().endsWith('/agenda/citas/series') && r.request().method() === 'POST',
    );
    await dialogo.getByRole('button', { name: 'Crear serie de 2 citas', exact: true }).click();
    const creada = await respuesta;
    expect(creada.status()).toBe(201);
    const cuerpo = await creada.json();
    expect(cuerpo.citas).toHaveLength(2);
    expect(cuerpo.frecuencia).toBe('SEMANAL');
    expect(cuerpo.citas.map((cita: { inicio: string }) => horaLocal(cita.inicio))).toEqual([
      horaLocal(turno.inicio),
      horaLocal(turno.inicio),
    ]);
    citasCreadas.push(...cuerpo.citas.map((cita: { id: string }) => cita.id));
    await expect(page.getByRole('status').filter({ hasText: 'Serie de 2 citas creada' })).toBeVisible();
  } finally {
    for (const citaId of citasCreadas) await limpiarCitaDePrueba(request, datos, citaId, false);
  }
});

test('el simulador reserva, confirma y muestra la cita real', async ({ page, request }, info) => {
  const datos = await preparar(request);
  let citaId = '';
  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Agente demo');
    await page.getByRole('button', { name: 'Preparar conversación', exact: true }).click();
    await seleccionarPaciente(page, datos.paciente);
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
    await page.getByLabel('Buscar desde').fill(fecha(datos.turno.inicio));
    await page.getByRole('button', { name: 'Iniciar simulación' }).click();
    await page.getByRole('button', { name: 'Buscar horarios', exact: true }).click();
    await page.getByRole('button', { name: /^Elegir 1/ }).click();
    // Elegir un turno ejecuta hold_slot. Esperar a que aparezca la acción de
    // confirmar evita asociar la respuesta de reserva a la petición siguiente.
    await page.getByRole('button', { name: 'Confirmar cita', exact: true }).waitFor();
    const respuesta = page.waitForResponse(r => r.url().endsWith('/mensajes') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Confirmar cita', exact: true }).click();
    const confirmada = await (await respuesta).json();
    expect(confirmada.herramientas).toContain('confirm_appointment');
    citaId = confirmada.datos.cita_id;
    const cita = await datos.leer(`/agenda/citas/${citaId}`);
    expect(cita.estado).toBe('CONFIRMED');
    await page.getByRole('button', { name: 'Mis citas', exact: true }).click();
    await expect(page.locator('.cita-demo').first()).toBeVisible();
    await page.screenshot({ path: info.outputPath('agente-demo.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole('button', { name: 'Enviar', exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await page.getByRole('button', { name: 'Hablar con una persona' }).click();
    await expect(page.getByText('Atención del personal requerida')).toBeVisible();
  } finally {
    if (citaId) await request.post(`${API}/agenda/citas/${citaId}/cancelacion`, {
      headers: datos.headers, data: { motivo: 'Cierre de prueba sintetica E2E' },
    });
  }
});

test('la agenda permite reprogramar y cancelar una cita', async ({ page, request }, info) => {
  const datos = await preparar(request);
  const creada = await request.post(`${API}/agenda/citas`, { data: datos.cuerpo,
    headers: { ...datos.headers, 'Idempotency-Key': randomUUID() } });
  expect(creada.ok()).toBeTruthy();
  const cita = await creada.json();
  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Agenda');
    // `getByLabel` con `exact` no sirve aqui y no es cosa del rediseno: la
    // etiqueta envuelve al `select`, asi que su textContent incluye el texto de
    // la opcion elegida («SedeSede Norte [SINTETICO]») y nunca vale «Sede». El
    // nombre accesible que si vale es el del rol, que es lo que usa la otra
    // prueba de este mismo archivo.
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page
      .getByRole('combobox', { name: 'Especialidad', exact: true })
      .selectOption(datos.servicio.especialidad_id);
    await page
      .getByRole('combobox', { name: 'Servicio', exact: true })
      .selectOption(datos.servicio.id);
    await page
      .getByRole('combobox', { name: 'Profesional', exact: true })
      .selectOption(datos.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(cita.inicio));
    // Las acciones de la cita se abren en una ventana lateral con el nombre
    // del paciente; se selecciona por su nombre accesible.
    const nombre = `${datos.paciente.nombre} ${datos.paciente.apellido}`;
    const panel = page.getByRole('dialog', { name: nombre, exact: true });
    await seleccionarCitaEnAgenda(page, nombre);
    await expect(panel).toContainText(nombre);
    await panel.getByRole('button', { name: 'Reprogramar' }).click();
    const dialogo = page.getByRole('dialog', { name: 'Reprogramar cita', exact: true });
    const horario = dialogo.getByRole('combobox', { name: 'Nuevo horario' });
    // El profesional puede no atender al día siguiente. Recorre fechas desde
    // la disponibilidad real de la interfaz hasta encontrar un turno libre.
    for (let dias = 1; dias <= 14; dias += 1) {
      const fechaNueva = fecha(new Date(Date.parse(cita.inicio) + dias * 24 * 60 * 60 * 1000).toISOString());
      await dialogo.getByLabel('Nueva fecha').fill(fechaNueva);
      await dialogo.getByText('Buscando horarios…').waitFor({ state: 'hidden' }).catch(() => undefined);
      if (await horario.locator('option').count() > 1) break;
    }
    await expect(horario.locator('option')).not.toHaveCount(1);
    const nuevoInicio = await horario.locator('option').evaluateAll((opciones, actual) => {
      const elegible = opciones.find((opcion) => {
        const valor = (opcion as HTMLOptionElement).value;
        return valor && valor !== actual;
      }) as HTMLOptionElement | undefined;
      return elegible?.value ?? '';
    }, cita.inicio);
    expect(nuevoInicio, 'debe existir un horario distinto para reprogramar').toBeTruthy();
    await horario.selectOption(nuevoInicio);
    await dialogo.getByLabel('Motivo del cambio').fill('Cambio administrativo sintetico');
    const respuesta = page.waitForResponse(r => r.url().includes('/reprogramacion'));
    await dialogo.getByRole('button', { name: 'Guardar cambio' }).click();
    const respuestaReprogramacion = await respuesta;
    expect(respuestaReprogramacion.status()).toBe(200);
    await expect(page.getByRole('status').filter({ hasText: 'Cita reprogramada' })).toBeVisible();
    const cambiada = await datos.leer(`/agenda/citas/${cita.id}`);
    expect(cambiada.inicio).not.toBe(cita.inicio);
    expect(cambiada.estado).toBe('RESCHEDULED');
    await page.screenshot({ path: info.outputPath('agenda.png'), fullPage: true });
    // La cita se movió al día siguiente: actualizar el filtro antes de volver
    // a elegir la fila evita cancelar otra cita del mismo paciente.
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(cambiada.inicio));
    await seleccionarCitaEnAgenda(page, nombre);
    await panel.getByRole('button', { name: 'Cancelar la cita' }).click();
    const confirmacion = page.getByRole('dialog');
    await confirmacion.getByLabel('Motivo de la cancelación').fill('Cierre de prueba sintetica E2E');
    await confirmacion.getByRole('button', { name: 'Cancelar la cita' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cita cancelada' })).toBeVisible();
    expect((await datos.leer(`/agenda/citas/${cita.id}`)).estado).toBe('CANCELLED');
  } finally {
    await limpiarCitaDePrueba(request, datos, cita.id, test.info().errors.length > 0);
  }
});

test('recepción registra la llegada y asistencia clínica mide la espera y cierra la atención', async ({ page, request }) => {
  const datos = await preparar(request);
  const creada = await request.post(`${API}/agenda/citas`, {
    data: datos.cuerpo,
    headers: { ...datos.headers, 'Idempotency-Key': randomUUID() },
  });
  expect(creada.ok()).toBeTruthy();
  const cita = await creada.json();
  let estadoFinal = cita.estado;
  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(cita.inicio));
    const nombre = `${datos.paciente.nombre} ${datos.paciente.apellido}`;
    await seleccionarCitaEnAgenda(page, nombre);
    const panel = page.getByRole('dialog', { name: nombre, exact: true });
    await panel.getByRole('button', { name: 'Registrar llegada' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Llegada registrada' })).toBeVisible();
    const llegada = await datos.leer(`/agenda/citas/${cita.id}`);
    expect(llegada.llegada_en).toBeTruthy();
    estadoFinal = llegada.estado;
    const hoy = fecha(new Date().toISOString());
    const inicioDia = new Date(`${hoy}T00:00:00-05:00`);
    const finDia = new Date(`${hoy}T00:00:00-05:00`);
    finDia.setDate(finDia.getDate() + 1);
    const resumenPanel = await datos.leer(
      `/dashboard/?desde=${encodeURIComponent(inicioDia.toISOString())}&hasta=${encodeURIComponent(finDia.toISOString())}`,
    );
    expect(resumenPanel.espera.personas_en_espera).toBeGreaterThan(0);
    expect(resumenPanel.ocupacion_agenda.minutos_disponibles).toBeGreaterThan(0);
    expect(resumenPanel.ocupacion_agenda.porcentaje).not.toBeNull();
    await irA(page, 'Panel');
    await expect(page.locator('.rejilla .tarjeta').filter({ hasText: 'Sala de espera' }))
      .toContainText('paciente(s) esperando en el periodo');
    // Las métricas de ocupación están en la pestaña del periodo del nuevo Panel.
    await page.getByRole('tab', { name: 'Cifras del periodo', exact: true }).click();
    const ocupacion = page.locator('.tarjeta').filter({
      has: page.getByText('Ocupación de agenda', { exact: true }),
    });
    await expect(ocupacion).toBeVisible();
    await expect(ocupacion).toContainText(`${resumenPanel.ocupacion_agenda.porcentaje}%`);
    await expect(ocupacion.locator('progress')).toHaveAttribute(
      'aria-label',
      `Ocupación de agenda: ${resumenPanel.ocupacion_agenda.porcentaje} por ciento`,
    );

    await acceder(page, 'asistente');
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(cita.inicio));
    await seleccionarCitaEnAgenda(page, nombre);
    await expect(panel).toContainText('Espera registrada');
    await panel.getByRole('button', { name: 'Iniciar atención' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Atención iniciada' })).toBeVisible();
    const iniciada = await datos.leer(`/agenda/citas/${cita.id}`);
    expect(iniciada.atencion_iniciada_en).toBeTruthy();

    // La agenda cierra el panel al recargar después de guardar una transición.
    await seleccionarCitaEnAgenda(page, nombre);
    await panel.getByRole('button', { name: 'Marcar como atendida' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cita marcada como atendida' })).toBeVisible();
    const completada = await datos.leer(`/agenda/citas/${cita.id}`);
    expect(completada.completada_en).toBeTruthy();
    estadoFinal = completada.estado;
  } finally {
    if (estadoFinal !== 'COMPLETED' && estadoFinal !== 'CANCELLED') {
      await limpiarCitaDePrueba(request, datos, cita.id, test.info().errors.length > 0);
    }
  }
});

test('un pago registrado en la pantalla aparece en la API', async ({ page, request }) => {
  const datos = await preparar(request);
  const creada = await request.post(`${API}/agenda/citas`, { data: datos.cuerpo,
    headers: { ...datos.headers, 'Idempotency-Key': randomUUID() } });
  expect(creada.ok()).toBeTruthy();
  const cita = await creada.json();
  await acceder(page, 'recepcion');
  await irA(page, 'Pagos');
  await page.getByRole('button', { name: 'Registrar un abono', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Registrar un abono' })).toBeVisible();
  await seleccionarPaciente(page, datos.paciente);
  await page.getByRole('combobox', { name: 'Cita', exact: true }).selectOption(cita.id);
  await page.getByLabel('Total pactado (USD)').fill('100');
  await page.getByLabel('Importe (USD)').fill('25.50');
  const referencia = `Prueba sintetica ${randomUUID().slice(0, 8)}`;
  await page.getByLabel('Referencia del comprobante (opcional)').fill(referencia);
  await page.getByRole('button', { name: 'Registrar abono pendiente' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Abono registrado como pendiente de confirmación.' })).toBeVisible();
  await expect(page.getByRole('row').filter({ hasText: referencia })).toBeVisible();
  const pagos = await datos.leer('/pagos/?limite=100');
  const pago = pagos.elementos.find((p: { cita_id: string }) => p.cita_id === cita.id);
  expect(pago.importe).toBe('25.50');
  expect(pago.estado).toBe('PENDING');
});
