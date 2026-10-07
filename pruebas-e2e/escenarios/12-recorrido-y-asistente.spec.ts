/**
 * Recorrido del paciente dentro de la clínica, asistente del equipo y
 * configuración de la IA.
 *
 * Comprueba que las piezas encajan: lo que el profesional pide en la agenda
 * (más tiempo, derivar) llega a la API y queda en el recorrido del paciente;
 * el asistente responde desde la interfaz; y la administración ve dónde se
 * configura JEV y el modelo de respuestas.
 */
import { randomUUID } from 'node:crypto';
import type { APIRequestContext, Page } from '@playwright/test';

import { expect, test } from '../apoyo/prueba';
import { acceder, CODIGOS_ROL, irA, type Rol } from '../apoyo/sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const fecha = (iso: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(iso));

/** La cita en la vista de lista o en el calendario por horas, la que esté visible. */
async function seleccionarCitaEnAgenda(page: Page, nombre: string): Promise<void> {
  const fila = page.locator('.fila-dia').filter({ hasText: nombre }).first();
  const bloque = page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).first();
  const objetivo = (await fila.count()) > 0 ? fila : bloque;
  await expect(objetivo, `la agenda debe mostrar la cita de ${nombre}`).toBeVisible({ timeout: 6_000 });
  await objetivo.click();
}

async function cabeceras(request: APIRequestContext, rol: Rol) {
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, {
    data: { codigo_rol: CODIGOS_ROL[rol] },
  });
  expect(acceso.ok()).toBeTruthy();
  return { Authorization: `Bearer ${(await acceso.json()).token_acceso}` };
}

/** Cita del profesional de la sesión local, con llegada y atención iniciada. */
async function citaEnAtencion(request: APIRequestContext) {
  const recepcion = await cabeceras(request, 'recepcion');
  const profesional = await cabeceras(request, 'profesional');
  const leer = async (ruta: string, headers = recepcion) => {
    const r = await request.get(API + ruta, { headers });
    expect(r.ok(), `${ruta}: ${r.status()}`).toBeTruthy();
    return r.json();
  };
  const yo = await leer('/autenticacion/yo', profesional);
  expect(yo.profesional_id, 'la sesión local de profesional debe tener ficha profesional').toBeTruthy();
  const ficha = await leer(`/catalogo/profesionales/${yo.profesional_id}`);
  const servicios = (await leer('/catalogo/servicios'))
    .filter((s: { especialidad_id: string }) => s.especialidad_id === ficha.especialidad_id);

  // No todo servicio de la especialidad se ofrece en cada sede: se prueba
  // cada combinación hasta dar con un hueco (404 = combinación inexistente).
  const desde = new Date(Date.now() + 14 * 86400000).toISOString();
  const hasta = new Date(Date.now() + 60 * 86400000).toISOString();
  let turno: { inicio: string } | undefined;
  let sedeId = '';
  let servicio: { id: string; especialidad_id: string } | undefined;
  busqueda: for (const candidato of servicios) {
    for (const sede of yo.ambito.sedes as string[]) {
      const params = new URLSearchParams({ sede_id: sede, profesional_id: yo.profesional_id, servicio_id: candidato.id, desde, hasta });
      const r = await request.get(`${API}/agenda/disponibilidad?${params}`, { headers: recepcion });
      const turnos = r.ok() ? (await r.json()).turnos : [];
      if (turnos.length > 0) {
        [turno, sedeId, servicio] = [turnos[0], sede, candidato];
        break busqueda;
      }
    }
  }
  if (!turno || !servicio) throw new Error('El profesional de la sesión local no tiene huecos en sus sedes.');

  const inicioDia = new Date(`${fecha(turno.inicio)}T00:00:00-05:00`);
  const ventana = await leer(`/agenda/citas?desde=${encodeURIComponent(inicioDia.toISOString())}&hasta=${encodeURIComponent(new Date(inicioDia.getTime() + 86400000).toISOString())}&limite=200`);
  const ocupados = new Set(ventana.elementos.map((c: { paciente_id: string }) => c.paciente_id));
  const paciente = (await leer('/pacientes/?limite=100')).elementos
    .find((p: { id: string }) => !ocupados.has(p.id));
  if (!paciente) throw new Error('No hay un paciente sintético libre ese día.');

  const creada = await request.post(`${API}/agenda/citas`, {
    data: { sede_id: sedeId, profesional_id: yo.profesional_id, servicio_id: servicio.id, paciente_id: paciente.id, inicio: turno.inicio },
    headers: { ...recepcion, 'Idempotency-Key': randomUUID() },
  });
  expect(creada.ok(), `crear cita: ${creada.status()}`).toBeTruthy();
  const cita = await creada.json();
  for (const [ruta, headers] of [['llegada', recepcion], ['inicio-atencion', profesional]] as const) {
    const r = await request.post(`${API}/agenda/citas/${cita.id}/${ruta}`, { headers });
    expect(r.ok(), `${ruta}: ${r.status()}`).toBeTruthy();
  }
  return { cita, paciente, servicio, ficha, sedeId, profesional, leer };
}

test('el profesional pide más tiempo, abre la derivación y el recorrido lo registra', async ({ page, request }) => {
  const datos = await citaEnAtencion(request);
  try {
    await acceder(page, 'profesional');
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.sedeId);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.ficha.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(datos.cita.inicio));
    await seleccionarCitaEnAgenda(page, `${datos.paciente.nombre} ${datos.paciente.apellido}`);

    const nombre = `${datos.paciente.nombre} ${datos.paciente.apellido}`;
    const recorrido = page.getByRole('group', { name: 'El paciente en la clínica' });
    await recorrido.getByRole('button', { name: 'Pedir más tiempo' }).click();
    // La agenda muestra el resultado arriba y recarga, cerrando el panel.
    await expect(page.getByRole('status').filter({ hasText: /Atención alargada|Más tiempo pedido/ })).toBeVisible();

    await seleccionarCitaEnAgenda(page, nombre);
    await recorrido.getByRole('button', { name: 'Derivar a otra área' }).click();
    const ventana = page.getByRole('dialog', { name: /¿A qué área lo envía\?/ });
    await expect(ventana).toBeVisible();
    await expect(ventana).not.toContainText('Buscando quién puede atenderle');
    await ventana.getByRole('button', { name: /cerrar/i }).first().click();

    const pasos = await datos.leer(`/agenda/pacientes/${datos.paciente.id}/recorrido`, datos.profesional);
    const tipos = JSON.stringify(pasos);
    expect(tipos).toContain('LLEGADA');
    expect(tipos).toMatch(/PROLONG/);
  } finally {
    // La atención iniciada no se cancela: se cierra como atendida.
    await request.post(`${API}/agenda/citas/${datos.cita.id}/completado`, { headers: datos.profesional });
  }
});

test('el asistente del equipo responde desde la interfaz', async ({ page }) => {
  await acceder(page, 'profesional');
  await irA(page, 'Asistente');
  await expect(page.getByRole('heading', { name: 'Asistente', level: 1 })).toBeVisible();

  const chat = page.getByRole('region', { name: 'Conversación con el asistente' });
  await chat.getByLabel('Mensaje').fill('¿Quién sigue?');
  await chat.getByRole('button', { name: 'Enviar' }).click();

  const mensajes = chat.getByRole('log').locator('article.mensaje');
  await expect(mensajes).toHaveCount(2, { timeout: 15_000 });
  await expect(mensajes.last()).not.toHaveText('');
  await expect(chat.getByRole('alert')).toHaveCount(0);
});

test('administración ve dónde configurar JEV y el modelo de respuestas', async ({ page }) => {
  await acceder(page, 'administradora');
  await irA(page, 'Configuración');
  await page.getByRole('button', { name: 'Integraciones', exact: true }).click();

  const jev = page.getByRole('region', { name: 'JEV · TypeSafe' });
  await expect(jev).toBeVisible();
  await expect(jev.getByRole('button', { name: /probar conexión/i })).toBeVisible();
  const respuestas = page.getByRole('region', { name: 'Respuestas del asistente' });
  await expect(respuestas).toBeVisible();
  await respuestas.getByRole('button', { name: 'Configurar respuestas' }).click();
  const editor = page.getByRole('dialog', { name: 'Configurar respuestas del asistente' });
  await expect(editor).toBeVisible();
  await expect(editor.getByRole('radio')).toHaveCount(3);
  await page.keyboard.press('Escape');
  await expect(editor).toHaveCount(0);
});
