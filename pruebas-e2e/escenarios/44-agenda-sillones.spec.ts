import { randomUUID } from 'node:crypto';
import type { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { apiE2e } from '../apoyo/api-e2e';
import { acceder, irA } from '../apoyo/sesion';

const API = apiE2e();
const horaLocal = (instante: string) => new Intl.DateTimeFormat('en-GB', {
  timeZone: 'America/Guayaquil', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}).format(new Date(instante));
const fechaLocal = (instante: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(instante));

async function iniciarApi(request: APIRequestContext, codigo_rol: string) {
  const respuesta = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol } });
  expect(respuesta.ok(), `sesión ${codigo_rol}`).toBe(true);
  return { Authorization: `Bearer ${(await respuesta.json()).token_acceso}` };
}

async function prepararReserva(request: APIRequestContext) {
  const headers = await iniciarApi(request, 'administrador_clinica');
  const leer = async (ruta: string) => {
    const respuesta = await request.get(`${API}${ruta}`, { headers });
    expect(respuesta.ok(), ruta).toBe(true);
    return respuesta.json();
  };
  const yo = await leer('/autenticacion/yo');
  const servicios = await leer('/catalogo/servicios');
  const profesionales = await leer('/catalogo/profesionales');
  const sedes = yo.ambito.sedes as string[];
  const desde = new Date(Date.now() + 2 * 86_400_000).toISOString();
  const hasta = new Date(Date.now() + 45 * 86_400_000).toISOString();

  for (const sedeId of sedes) {
    const salas = await leer(`/catalogo/consultorios?sede_id=${encodeURIComponent(sedeId)}`);
    const activas = salas.filter((sala: { activo?: boolean }) => sala.activo !== false);
    for (const servicio of servicios) {
      for (const profesional of profesionales.filter((item: { especialidad_id: string }) => item.especialidad_id === servicio.especialidad_id)) {
        for (const sala of activas) {
          const parametros = new URLSearchParams({
            sede_id: sedeId,
            servicio_id: servicio.id,
            profesional_id: profesional.id,
            consultorio_id: sala.id,
            desde,
            hasta,
          });
          const disponibilidad = await request.get(`${API}/agenda/disponibilidad?${parametros}`, { headers });
          if (!disponibilidad.ok()) continue;
          const turnos = (await disponibilidad.json()).turnos as { inicio: string }[];
          const turno = turnos.find((item) => Date.parse(item.inicio) > Date.now());
          if (turno) return { sedeId, sala, servicio, profesional, turno, salas: activas };
        }
      }
    }
  }
  throw new Error('No hay un turno futuro sintético disponible en un consultorio activo.');
}

async function comprobarSinScroll(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(() =>
    document.documentElement.scrollHeight - document.documentElement.clientHeight,
  )).toBeLessThanOrEqual(1);
}

test('agenda por sillón: muestra consultorios y reserva en la columna elegida', async ({ page, request }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const seleccion = await prepararReserva(request);
  const administracion = await iniciarApi(request, 'administrador_clinica');
  const dia = fechaLocal(seleccion.turno.inicio);
  const desdeDia = new Date(`${dia}T00:00:00-05:00`).toISOString();
  const hastaDia = new Date(`${dia}T00:00:00-05:00`);
  hastaDia.setUTCDate(hastaDia.getUTCDate() + 1);
  const filtroCitas = new URLSearchParams({
    sede_id: seleccion.sedeId,
    profesional_id: seleccion.profesional.id,
    desde: desdeDia,
    hasta: hastaDia.toISOString(),
    limite: '200',
  });
  const citasDelDia = await request.get(`${API}/agenda/citas?${filtroCitas}`, { headers: administracion });
  expect(citasDelDia.ok()).toBe(true);
  const filasDia = (await citasDelDia.json()).elementos as { estado: string; consultorio_id: string | null }[];
  const hayCitaSinSillon = filasDia.some((cita) => cita.estado !== 'CANCELLED' && cita.consultorio_id === null);
  const sufijo = randomUUID().slice(0, 8);
  const numeroDocumento = `${Date.now()}`;
  const altaPaciente = await request.post(`${API}/pacientes/`, {
    headers: { ...administracion, 'Idempotency-Key': randomUUID() },
    data: {
      nombre: '[SINTETICO] Agenda sillones',
      apellido: `Prueba ${sufijo}`,
      tipo_documento: 'PASAPORTE',
      numero_documento: numeroDocumento,
    },
  });
  expect(altaPaciente.status()).toBe(201);
  const paciente = await altaPaciente.json();

  await acceder(page, 'recepcion');
  await irA(page, 'Agenda');
  await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(seleccion.sedeId);
  await page.getByLabel('Fecha', { exact: true }).fill(fechaLocal(seleccion.turno.inicio));
  await page.getByRole('group', { name: 'Organizar columnas del día' }).getByRole('button', { name: 'Sillón', exact: true }).click();
  const filtros = page.getByRole('region', { name: 'Filtros de la agenda' });
  await expect(filtros.getByRole('combobox', { name: 'Servicio', exact: true })).toHaveValue('');
  await expect(filtros.getByRole('combobox', { name: 'Profesional', exact: true })).toHaveValue('');

  const cabeceras = page.locator('app-calendario-agenda .tiempo__titulo .tiempo__nombre strong');
  await expect(cabeceras).toHaveCount(seleccion.salas.length + (hayCitaSinSillon ? 1 : 0), { timeout: 15_000 });
  for (const [indice, sala] of seleccion.salas.entries()) {
    await expect(cabeceras.nth(indice)).toHaveText(sala.nombre);
  }
  const indiceSala = seleccion.salas.findIndex((sala: { id: string }) => sala.id === seleccion.sala.id);
  expect(indiceSala).toBeGreaterThanOrEqual(0);
  const huecosSala = page.locator('app-calendario-agenda .tiempo__columna').nth(indiceSala).locator('.bloque.estado--LIBRE');
  await expect(huecosSala.first()).toBeVisible({ timeout: 15_000 });
  const horaObjetivo = horaLocal(seleccion.turno.inicio);
  const indiceHueco = await huecosSala.evaluateAll((bloques, objetivo) => bloques.findIndex((bloque) => {
    const rango = bloque.querySelector('.bloque__hora')?.textContent?.trim() ?? '';
    const [inicio, fin] = rango.split('–').map((parte) => parte.trim());
    return Boolean(inicio && (fin ? inicio <= objetivo && objetivo < fin : inicio === objetivo));
  }), horaObjetivo);
  expect(indiceHueco, `debe haber un hueco de horario que contenga las ${horaObjetivo}`).toBeGreaterThanOrEqual(0);
  await comprobarSinScroll(page);

  await huecosSala.nth(indiceHueco).click();
  const reserva = page.getByRole('dialog', { name: 'Reservar cita', exact: true });
  await expect(reserva).toBeVisible();
  const selectorSala = reserva.locator('fieldset.selector-sala').filter({ hasText: seleccion.sala.nombre });
  await expect(selectorSala.getByRole('button', { name: new RegExp(seleccion.sala.nombre) })).toHaveAttribute('aria-pressed', 'true');
  const servicioReserva = reserva.getByRole('combobox', { name: 'Servicio *', exact: true });
  const profesionalReserva = reserva.getByRole('combobox', { name: 'Profesional *', exact: true });
  await servicioReserva.selectOption(seleccion.servicio.id);
  const respuestaDisponibilidad = page.waitForResponse((respuesta) => {
    const url = new URL(respuesta.url());
    return url.pathname.endsWith('/agenda/disponibilidad')
      && url.searchParams.get('consultorio_id') === seleccion.sala.id
      && url.searchParams.get('servicio_id') === seleccion.servicio.id
      && url.searchParams.get('profesional_id') === seleccion.profesional.id;
  });
  await profesionalReserva.selectOption(seleccion.profesional.id);
  expect((await respuestaDisponibilidad).ok()).toBe(true);
  const horaElegida = reserva.getByRole('button', { name: horaObjetivo, exact: true });
  await expect(horaElegida).toBeVisible();
  await horaElegida.click();
  await expect(selectorSala.getByRole('button', { name: new RegExp(seleccion.sala.nombre) })).toHaveAttribute('aria-pressed', 'true');

  const selectorPaciente = reserva.locator('app-selector-paciente');
  const buscadorPaciente = selectorPaciente.getByRole('combobox', { name: 'Paciente', exact: true });
  await buscadorPaciente.fill(paciente.apellido);
  await selectorPaciente.getByRole('option', { name: new RegExp(paciente.apellido) }).click();
  const guardado = page.waitForResponse((respuesta) =>
    respuesta.request().method() === 'POST' && /\/agenda\/citas\/?$/.test(new URL(respuesta.url()).pathname),
  );
  await reserva.getByRole('button', { name: 'Confirmar cita', exact: true }).click();
  const respuesta = await guardado;
  expect(respuesta.status()).toBe(201);
  const cita = await respuesta.json();
  expect(cita.consultorio_id).toBe(seleccion.sala.id);

  const columnaElegida = page.locator('app-calendario-agenda .tiempo__columna').nth(indiceSala);
  await expect(columnaElegida.locator('.bloque').filter({ hasText: `${paciente.nombre} ${paciente.apellido}` })).toBeVisible({ timeout: 15_000 });
  await comprobarSinScroll(page);
});
