/** Regresión del ancho disponible al mantener abierto el agente de una ficha. */
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

test('el agente conserva los datos personales largos dentro de su tarjeta', async ({ page, request }) => {
  const paciente = await pacienteConNotas(request);
  // Solo altera la respuesta visual de esta ficha sintética, sin escribir en BD.
  await page.route(`**/api/v1/pacientes/${paciente.id}`, async route => {
    const url = route.request().url().replace('http://127.0.0.1:8000/api/v1', API);
    const respuesta = await route.fetch({ url });
    expect(respuesta.ok()).toBeTruthy();
    await route.fulfill({ response: respuesta, json: {
      ...await respuesta.json(), correo: `contacto.${'x'.repeat(100)}@example.invalid`,
    } });
  });
  await acceder(page, 'profesional');
  await irA(page, 'Pacientes');
  const buscar = page.getByRole('form', { name: 'Buscar pacientes' });
  await buscar.getByRole('textbox', { name: /buscar por nombre/i }).fill(paciente.numero_documento!);
  await buscar.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Ver ficha' }).click();
  await page.getByRole('button', { name: 'Agente del paciente', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Agente del paciente' })).toContainText('Funciones locales');
  const datos = page.locator('.ficha__datos dd');
  await expect(datos.filter({ hasText: '@example.invalid' })).toHaveCount(1);
  for (const ancho of [1440, 1280, 1024, 821, 768, 390]) {
    await page.setViewportSize({ width: ancho, height: 900 });
    const mediciones = await datos.evaluateAll(elementos => elementos.map(elemento => {
      const campo = elemento.getBoundingClientRect();
      const tarjeta = elemento.closest('.ficha__bloque')!.getBoundingClientRect();
      return { dentro: campo.left >= tarjeta.left && campo.right <= tarjeta.right + 1,
        textoContenido: elemento.scrollWidth <= elemento.clientWidth + 1 };
    }));
    expect(mediciones.length).toBeGreaterThan(0);
    expect(mediciones.every(m => m.dentro && m.textoContenido), `Datos fuera de la tarjeta a ${ancho}px`).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: '../tmp/qa-20261007/agente-datos-personales.png' });
});
