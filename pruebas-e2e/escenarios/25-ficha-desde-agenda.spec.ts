import { randomUUID } from 'node:crypto';
import type { APIRequestContext } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const fecha = (iso: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(iso));

async function prepararCita(request: APIRequestContext, rol: 'profesional' | 'recepcion') {
  const login = async (codigo_rol: string) => {
    const respuesta = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol } });
    expect(respuesta.ok()).toBe(true);
    return { Authorization: `Bearer ${(await respuesta.json()).token_acceso}` };
  };
  const recepcion = await login('recepcion');
  const profesional = await login('profesional');
  const administracion = await login('administrador_clinica');
  const leer = async (ruta: string, headers = recepcion) => {
    const respuesta = await request.get(API + ruta, { headers });
    expect(respuesta.ok(), ruta).toBe(true);
    return respuesta.json();
  };
  const headers = rol === 'profesional' ? profesional : recepcion;
  const yo = await leer('/autenticacion/yo', headers);
  // Recepción solo ve profesionales de sus sedes; su cita debe respetar ese
  // ámbito. La sesión profesional prueba únicamente al responsable propio.
  const fichaProfesional = rol === 'profesional'
    ? await leer(`/catalogo/profesionales/${yo.profesional_id}`, headers)
    : (await leer('/catalogo/profesionales', headers))[0];
  const servicios = (await leer('/catalogo/servicios')).filter((s: { especialidad_id: string }) => s.especialidad_id === fichaProfesional.especialidad_id);
  let seleccion: { inicio: string; sede_id: string; servicio_id: string } | null = null;
  busqueda: for (const servicio of servicios) {
    for (const sede_id of yo.ambito.sedes) {
      const params = new URLSearchParams({ sede_id, profesional_id: fichaProfesional.id, servicio_id: servicio.id,
        desde: new Date(Date.now() + 14 * 86_400_000).toISOString(), hasta: new Date(Date.now() + 60 * 86_400_000).toISOString() });
      const respuesta = await request.get(`${API}/agenda/disponibilidad?${params}`, { headers });
      const turnos = respuesta.ok() ? (await respuesta.json()).turnos : [];
      if (turnos.length) {
        seleccion = { inicio: turnos[0].inicio, sede_id, servicio_id: servicio.id };
        break busqueda;
      }
    }
  }
  expect(seleccion, 'Debe haber un horario sintético del profesional local').not.toBeNull();
  const alta = await request.post(`${API}/pacientes/`, {
    headers: { ...administracion, 'Idempotency-Key': randomUUID() },
    data: { nombre: 'Ficha de agenda', apellido: `Sintética ${randomUUID().slice(0, 8)}`, tipo_documento: 'PASAPORTE', numero_documento: String(Date.now()) },
  });
  expect(alta.status()).toBe(201);
  const paciente = await alta.json();
  const reserva = await request.post(`${API}/agenda/citas`, {
    headers: { ...administracion, 'Idempotency-Key': randomUUID() },
    data: { ...seleccion, profesional_id: fichaProfesional.id, paciente_id: paciente.id },
  });
  expect(reserva.status()).toBe(201);
  const cita = await reserva.json();
  return { paciente, cita, fichaProfesional, administracion };
}

for (const rol of ['profesional', 'recepcion'] as const) {
  test(`agenda abre ficha y herramientas con su cita, consulta y registro según rol: ${rol}`, async ({ page, request }) => {
    test.setTimeout(120_000);
    const datos = await prepararCita(request, rol);
    if (rol === 'profesional') {
      const llegada = await request.post(`${API}/agenda/citas/${datos.cita.id}/llegada`, { headers: datos.administracion });
      expect(llegada.status()).toBe(200);
    }
    const nombre = `${datos.paciente.nombre} ${datos.paciente.apellido}`;
    await page.setViewportSize({ width: 1366, height: 768 });
    await acceder(page, rol);
    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.cita.sede_id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.fichaProfesional.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.cita.servicio_id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.fichaProfesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(datos.cita.inicio));
    await page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).click();
    const detalle = page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') });
    const ficha = page.locator('app-ventana-flotante').filter({ has: page.locator('app-ficha-paciente') });
    const menu = page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true });
    if (rol === 'profesional') {
      // El inicio explícito desde la agenda habilita el vínculo asistencial
      // del profesional, también cuando es la primera cita de este paciente.
      const inicio = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/agenda/citas/${datos.cita.id}/inicio-atencion`));
      await detalle.getByRole('button', { name: 'Iniciar atención', exact: true }).click();
      expect((await inicio).status()).toBe(200);
      await expect(detalle).toHaveCount(0);
      await page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).click();
    }
    for (const acceso of ['normal', 'directo', 'movil'] as const) {
      if (acceso === 'movil') await page.setViewportSize({ width: 390, height: 844 });
      await detalle.getByRole('button', { name: acceso === 'normal' ? 'Ver ficha del paciente' : 'Elegir qué registrar', exact: true }).click();
      await expect(page.locator('app-ficha-paciente')).toBeVisible();
      if (acceso === 'normal') {
        await expect(menu).toHaveCount(0);
        await ficha.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
      }
      await expect(menu).toBeVisible();
      await expect(menu.getByRole('button', { name: /^Periodontograma e índice/ })).toBeEnabled();
      await expect(menu.getByRole('button', { name: /^Faciograma Mapa/ })).toBeEnabled();
      await expect(menu.getByRole('button', { name: 'Comenzar atención sin cita', exact: true })).toHaveCount(0);
      await menu.getByRole('button', { name: /^Evolución y antecedentes/ }).click();
      await expect(page.locator('#historia-panel-evolucion')).toBeFocused();
      await expect(page.getByLabel('Cita de referencia')).toHaveValue(datos.cita.id);
      await expect(page.locator('#historia-panel-evolucion')).toBeInViewport();
      if (rol === 'recepcion') {
        await expect(page.getByRole('button', { name: 'Nueva nota', exact: true })).toHaveCount(0);
        await expect(page.getByRole('button', { name: 'Nueva receta', exact: true })).toHaveCount(0);
      } else if (acceso === 'normal') {
        await page.getByRole('button', { name: 'Nueva nota', exact: true }).click();
        const editor = page.getByRole('dialog', { name: 'Nueva nota de evolución', exact: true });
        await editor.getByLabel('Motivo de consulta', { exact: true }).fill('Control sintético de apertura desde agenda');
        await editor.getByLabel('Subjetivo (lo que refiere el paciente)', { exact: true }).fill('Registro sintético para verificar el contexto de la cita.');
        const guardado = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/historia/notas'));
        await editor.getByRole('button', { name: 'Guardar nota', exact: true }).click();
        const respuesta = await guardado;
        expect(respuesta.status()).toBe(201);
        const nota = await respuesta.json();
        expect(nota.paciente_id).toBe(datos.paciente.id);
        expect(nota.cita_id).toBe(datos.cita.id);
        await expect(editor).not.toBeVisible();
      }
      await ficha.getByRole('button', { name: `Cerrar ${nombre}`, exact: true }).click();
      await expect(page.locator('app-ficha-paciente')).toHaveCount(0);
      await expect(detalle.getByRole('button', { name: 'Ver ficha del paciente', exact: true })).toBeVisible();
      await expect(page.getByLabel('Fecha', { exact: true })).toHaveValue(fecha(datos.cita.inicio));
    }
  });
}
