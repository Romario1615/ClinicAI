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
  test('recepcion no ve las secciones clinicas', async ({ page }) => {
    await acceder(page, 'recepcion');
    const navegacion = page.locator('nav');

    await expect(navegacion.getByRole('link', { name: /agenda/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /pacientes/i })).toBeVisible();
    // Recepcion no tiene ningun permiso clinico: ni historia ni recetas.
    await expect(navegacion.getByRole('link', { name: /historia/i })).toHaveCount(0);
    await expect(navegacion.getByRole('link', { name: /medicamentos/i })).toHaveCount(0);
  });

  test('el asistente si ve medicamentos, porque tiene receta.leer', async ({ page }) => {
    await acceder(page, 'asistente');
    const navegacion = page.locator('nav');

    // Los permisos clinicos no van juntos: el asistente sigue la medicacion
    // sin poder leer las notas.
    await expect(navegacion.getByRole('link', { name: /medicamentos/i })).toBeVisible();
  });

  test('el profesional ve las secciones clinicas', async ({ page }) => {
    await acceder(page, 'profesional');
    const navegacion = page.locator('nav');

    await expect(navegacion.getByRole('link', { name: /historia/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /medicamentos/i })).toBeVisible();
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
