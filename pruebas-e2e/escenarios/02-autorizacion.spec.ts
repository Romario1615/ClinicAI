/**
 * Autorizacion vista desde el navegador.
 *
 * Lo que solo se puede comprobar aqui
 * -----------------------------------
 * Que **el guardia de navegacion y el permiso que el backend exige coinciden**.
 * Cada uno tiene sus pruebas por separado; que digan lo mismo no lo prueba
 * ninguna de las dos.
 *
 * Una discrepancia se ve de dos formas, y las dos son malas: una seccion
 * visible cuyas peticiones devuelven 403 en bucle, o una seccion oculta a quien
 * si tiene derecho a usarla.
 */
import { expect, test } from '../apoyo/prueba';

import { acceder } from '../apoyo/sesion';

test.describe('Autorizacion por rol', () => {
  test('recepcion ve las secciones clinicas de consulta y conserva los limites administrativos', async ({ page }) => {
    await acceder(page, 'recepcion');
    const navegacion = page.locator('nav');
    const clinica = navegacion.getByRole('button', { name: /^Atención clínica/ });
    if (await clinica.getAttribute('aria-expanded') === 'false') await clinica.click();

    await expect(navegacion.getByRole('link', { name: /agenda/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /pacientes/i })).toBeVisible();
    // La política compartida permite consultar; no concede gestión de cuentas.
    await expect(navegacion.getByRole('link', { name: /historia/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /medicamentos/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /usuarios/i, includeHidden: true })).toHaveCount(0);
  });

  test('el asistente si ve medicamentos, porque tiene receta.leer', async ({ page }) => {
    await acceder(page, 'asistente');
    const navegacion = page.locator('nav');
    const clinica = navegacion.getByRole('button', { name: /^Atención clínica/ });
    if (await clinica.getAttribute('aria-expanded') === 'false') await clinica.click();

    // Asistencia consulta medicación y notas; no registra contenido clínico.
    await expect(navegacion.getByRole('link', { name: /medicamentos/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /historia/i })).toBeVisible();
  });

  test('el profesional ve las secciones clinicas', async ({ page }) => {
    await acceder(page, 'profesional');
    const navegacion = page.locator('nav');
    const clinica = navegacion.getByRole('button', { name: /^Atención clínica/ });
    if (await clinica.getAttribute('aria-expanded') === 'false') await clinica.click();

    await expect(navegacion.getByRole('link', { name: /historia/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /medicamentos/i })).toBeVisible();
    const ia = navegacion.getByRole('button', { name: /^Comunicación e IA/ });
    if (await ia.getAttribute('aria-expanded') === 'false') await ia.click();
    await expect(navegacion.getByRole('link', { name: /conocimiento/i })).toBeVisible();
  });

  test('recargar la pagina cierra la sesion, y eso es lo correcto', async ({ page }) => {
    await acceder(page, 'recepcion');
    await expect(page.locator('nav')).toBeVisible();

    // Escribir una ruta a mano provoca una carga completa. Los tokens viven
    // **solo en memoria** a proposito (ADR-0016): si se guardaran en
    // `localStorage`, un XSS se los llevaria y mantendria la sesion abierta
    // desde fuera indefinidamente. El precio es este, y se paga a gusto.
    await page.goto('/historia-clinica');

    await expect(page).toHaveURL(/\/acceso/);
    await expect(page).toHaveURL(/destino/);
  });

  test('el token no queda guardado en el navegador', async ({ page }) => {
    await acceder(page, 'recepcion');

    // La comprobacion mira el almacenamiento de verdad, no el codigo que lo
    // usa. Es la unica forma de que la afirmacion signifique algo.
    const guardado = await page.evaluate(() => ({
      local: JSON.stringify(Object.entries(localStorage)),
      sesion: JSON.stringify(Object.entries(sessionStorage)),
    }));

    expect(guardado.local).not.toMatch(/eyJ|token_acceso|Bearer/);
    expect(guardado.sesion).not.toMatch(/eyJ|token_acceso|Bearer/);
  });

});
