import { randomUUID } from 'node:crypto';
import type { APIRequestContext, Page } from '@playwright/test';
import { expect, test } from '../apoyo/prueba';
import { acceder, CODIGOS_ROL, irA } from '../apoyo/sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const fecha = (iso: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(iso));

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

async function seleccionarPaciente(page: Page, paciente: { id: string; apellido: string }) {
  const selector = page.locator('app-selector-paciente');
  await selector.getByLabel('Buscar paciente', { exact: true }).fill(paciente.apellido);
  await selector.getByRole('button', { name: 'Buscar', exact: true }).click();
  const pacientes = selector.getByRole('combobox', { name: 'Paciente', exact: true });
  await pacientes.selectOption(paciente.id);
}

test('el simulador reserva, confirma y muestra la cita real', async ({ page, request }, info) => {
  const datos = await preparar(request);
  let citaId = '';
  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Agente demo');
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
    await expect(page.getByRole('button', { name: 'Enviar mensaje' })).toBeVisible();
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
    // La agenda ya no es una tabla con botones por fila: se pulsa la fila del
    // dia y las acciones aparecen en el panel de la derecha.
    const nombre = `${datos.paciente.nombre} ${datos.paciente.apellido}`;
    const panel = page.locator('.panel');
    await page.locator('.fila-dia').filter({ hasText: nombre }).first().click();
    await expect(panel).toContainText(nombre);
    await panel.getByRole('button', { name: 'Reprogramar' }).click();
    const dialogo = page.getByRole('dialog');
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
    await expect(page.locator('.fila-dia').filter({ hasText: nombre }).first()).toBeVisible();
    await page.locator('.fila-dia').filter({ hasText: nombre }).first().click();
    await panel.getByRole('button', { name: 'Cancelar la cita' }).click();
    const confirmacion = page.getByRole('dialog');
    await confirmacion.getByLabel('Motivo de la cancelación').fill('Cierre de prueba sintetica E2E');
    await confirmacion.getByRole('button', { name: 'Cancelar la cita' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cita cancelada' })).toBeVisible();
    expect((await datos.leer(`/agenda/citas/${cita.id}`)).estado).toBe('CANCELLED');
  } finally {
    if ((await datos.leer(`/agenda/citas/${cita.id}`)).estado !== 'CANCELLED') {
      await request.post(`${API}/agenda/citas/${cita.id}/cancelacion`, {
        headers: datos.headers, data: { motivo: 'Cierre de prueba sintetica E2E' },
      });
    }
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
    await page.locator('.fila-dia').filter({ hasText: nombre }).first().click();
    const panel = page.locator('.panel');
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
    await irA(page, 'Panel');
    await expect(page.locator('.rejilla .tarjeta').filter({ hasText: 'Sala de espera' }))
      .toContainText('paciente(s) esperando en el periodo');

    await acceder(page, 'asistente');
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sede.id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(cita.inicio));
    await page.locator('.fila-dia').filter({ hasText: nombre }).first().click();
    await expect(page.locator('.panel')).toContainText('Espera registrada');
    await page.locator('.panel').getByRole('button', { name: 'Iniciar atención' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Atención iniciada' })).toBeVisible();
    const iniciada = await datos.leer(`/agenda/citas/${cita.id}`);
    expect(iniciada.atencion_iniciada_en).toBeTruthy();

    // La agenda cierra el panel al recargar después de guardar una transición.
    await page.locator('.fila-dia').filter({ hasText: nombre }).first().click();
    await page.locator('.panel').getByRole('button', { name: 'Marcar como atendida' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cita marcada como atendida' })).toBeVisible();
    const completada = await datos.leer(`/agenda/citas/${cita.id}`);
    expect(completada.completada_en).toBeTruthy();
    estadoFinal = completada.estado;
  } finally {
    if (estadoFinal !== 'COMPLETED' && estadoFinal !== 'CANCELLED') {
      await request.post(`${API}/agenda/citas/${cita.id}/cancelacion`, {
        headers: datos.headers,
        data: { motivo: 'Cierre de prueba sintetica E2E' },
      });
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
  await seleccionarPaciente(page, datos.paciente);
  await page.getByRole('combobox', { name: 'Cita', exact: true }).selectOption(cita.id);
  await page.getByLabel('Importe (USD)').fill('25.50');
  const referencia = `Prueba sintetica ${randomUUID().slice(0, 8)}`;
  await page.getByLabel('Referencia del comprobante (opcional)').fill(referencia);
  await page.getByRole('button', { name: 'Registrar pago pendiente' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Pago guardado' })).toBeVisible();
  await expect(page.getByRole('article').filter({ hasText: referencia })).toBeVisible();
  const pagos = await datos.leer('/pagos/?limite=100');
  const pago = pagos.elementos.find((p: { cita_id: string }) => p.cita_id === cita.id);
  expect(pago.importe).toBe('25.50');
  expect(pago.estado).toBe('PENDING');
});
