import { randomUUID } from 'node:crypto';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const herramientas = [
  { nombre: /^Evolución y antecedentes/, panel: 'evolucion', titulo: 'Notas de evolución' },
  { nombre: /^Recetas Prescripciones/, panel: 'recetas', titulo: 'Recetas' },
  { nombre: /^Indicaciones Orientaciones/, panel: 'indicaciones', titulo: 'Indicaciones para el paciente' },
  { nombre: /^Documentos y PDF/, panel: 'documentos', titulo: 'Presupuestos, cotizaciones y recetas' },
  { nombre: /^Odontograma Piezas/, panel: 'odontograma', titulo: 'Odontograma' },
  { nombre: /^Periodontograma e índice/, panel: 'periodoncia', titulo: 'Periodontograma' },
  { nombre: /^Formulario 033/, panel: 'formulario033', titulo: 'Formulario odontológico' },
  { nombre: /^Planes de tratamiento/, panel: 'planes', titulo: 'Planes de tratamiento' },
  { nombre: /^Faciograma Mapa/, panel: 'faciograma', titulo: 'Faciograma' },
  { nombre: /^Fotos y radiografías/, panel: 'imagenes', titulo: 'Imágenes clínicas' },
] as const;

for (const rol of ['profesional', 'recepcion'] as const) {
  test(`cada opción del menú de la ficha abre su herramienta visible y con foco: ${rol}`, async ({ page, request }) => {
    test.setTimeout(120_000);
    const acceso = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
    expect(acceso.ok()).toBe(true);
    const documento = String(Date.now());
    const alta = await request.post(`${API}/pacientes/`, {
      headers: { Authorization: `Bearer ${(await acceso.json()).token_acceso}`, 'Idempotency-Key': randomUUID() },
      data: { nombre: 'Menú de herramientas', apellido: 'Sintético', tipo_documento: 'PASAPORTE', numero_documento: documento },
    });
    expect(alta.status()).toBe(201);
    await page.setViewportSize({ width: 1366, height: 768 });
    await acceder(page, rol);
    await irA(page, 'Pacientes');
    const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
    await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(documento);
    await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
    await page.getByRole('row').filter({ hasText: documento }).getByRole('button', { name: 'Ver ficha', exact: true }).click();
    const menu = page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true });
    for (const herramienta of herramientas) {
      await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
      await expect(menu).toBeVisible();
      const boton = menu.getByRole('button', { name: herramienta.nombre });
      if (herramienta.panel === 'formulario033' && rol === 'recepcion') {
        await expect(boton).toBeDisabled();
        await menu.getByRole('button', { name: 'Cerrar', exact: true }).click();
        continue;
      }
      await expect(boton).toBeEnabled();
      await boton.click();
      await expect(menu).not.toBeVisible();
      const panel = page.locator(`#historia-panel-${herramienta.panel}`);
      await expect(panel).toBeFocused();
      await expect(panel.getByRole('heading', { name: herramienta.titulo, exact: typeof herramienta.titulo === 'string' }).first()).toBeInViewport();
      if (rol === 'recepcion') {
        await expect(panel.getByRole('button', { name: /^(Nueva nota|Nueva receta|Nuevo examen|Nuevo plan|Guardar|Cargar imagen)$/ })).toHaveCount(0);
      }
    }
    // Volver a elegir el mismo módulo después de usar otra pestaña debe abrirlo otra vez.
    for (const movil of [false, true]) {
      if (movil) await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
      await menu.getByRole('button', { name: /^Evolución y antecedentes/ }).click();
      await expect(page.locator('#historia-panel-evolucion')).toBeFocused();
      await page.getByRole('tab', { name: 'Recetas', exact: true }).click();
      await expect(page.locator('#historia-panel-recetas')).toBeVisible();
      await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
      await menu.getByRole('button', { name: /^Evolución y antecedentes/ }).click();
      await expect(page.locator('#historia-panel-evolucion')).toBeFocused();
      await expect(page.getByRole('heading', { name: 'Notas de evolución', exact: true })).toBeInViewport();
    }
  });
}

test('el menú también abre la herramienta visible en Historia clínica', async ({ page, request }) => {
  const paciente = await pacienteConNotas(request);
  await acceder(page, 'profesional');
  await irA(page, 'Historia clínica');
  const busqueda = page.getByRole('region', { name: 'Buscar paciente', exact: true });
  await busqueda.getByRole('textbox').fill(paciente.numero_documento!);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Abrir historia', exact: true }).click();
  const menu = page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true });
  for (const herramienta of [herramientas[1], herramientas[8], herramientas[1]]) {
    await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
    await menu.getByRole('button', { name: herramienta.nombre }).click();
    const panel = page.locator(`#historia-panel-${herramienta.panel}`);
    await expect(panel).toBeFocused();
    await expect(panel.getByRole('heading', { name: herramienta.titulo, exact: true })).toBeInViewport();
    await page.getByRole('tab', { name: 'Evolución', exact: true }).click();
  }
});

test('el menú conserva la cita elegida al cambiar de herramienta en la ficha', async ({ page, request }) => {
  const paciente = await pacienteConNotas(request);
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'profesional' } });
  expect(acceso.ok()).toBe(true);
  const headers = { Authorization: `Bearer ${(await acceso.json()).token_acceso}` };
  const contextos = await request.get(`${API}/pacientes/${paciente.id}/contextos-atencion`, { headers });
  expect(contextos.ok()).toBe(true);
  const citas = await contextos.json();
  expect(citas.length).toBeGreaterThan(0);
  await acceder(page, 'profesional');
  await irA(page, 'Pacientes');
  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(paciente.numero_documento!);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Ver ficha', exact: true }).click();
  await page.getByRole('tab', { name: 'Atención y documentos', exact: true }).click();
  await page.getByLabel('Cita de referencia').selectOption(citas[0].id);
  for (const herramienta of [herramientas[1], herramientas[5], herramientas[1]]) {
    await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
    await page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true }).getByRole('button', { name: herramienta.nombre }).click();
    await expect(page.locator(`#historia-panel-${herramienta.panel}`)).toBeFocused();
    await expect(page.getByLabel('Cita de referencia')).toHaveValue(citas[0].id);
  }
});
