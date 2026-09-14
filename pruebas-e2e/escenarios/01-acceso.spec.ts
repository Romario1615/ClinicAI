/**
 * Acceso y segundo factor.
 *
 * Lo que solo se puede comprobar aqui
 * -----------------------------------
 * Que el formulario, el interceptor de token, el guardia de navegacion y lo que
 * el backend exige **encajan entre si**. Cada pieza tiene sus pruebas; que
 * encajen no lo prueba ninguna.
 */
import { expect, test } from '@playwright/test';

import { CONTRASENA, CUENTAS, obtenerClinicaId } from '../apoyo/sesion';

test.describe('Acceso', () => {
  test('una ruta protegida redirige al acceso y vuelve al destino', async ({ page }) => {
    await page.goto('/pacientes');

    // El guardia no protege datos -- eso lo hace el backend -- pero si evita
    // que alguien vea una pantalla que va a fallar en cada peticion.
    await expect(page).toHaveURL(/\/acceso/);
    await expect(page).toHaveURL(/destino/);
  });

  test('las credenciales incorrectas no entran y lo dicen', async ({ page }) => {
    const clinicaId = await obtenerClinicaId(page);
    await page.goto('/acceso');
    await page.locator('input[name="clinica"]').fill(clinicaId);
    await page.locator('input[name="correo"]').fill(CUENTAS.recepcion);
    await page.locator('input[name="contrasena"]').fill('contrasena-que-no-es');
    await page.getByRole('button', { name: /entrar/i }).click();

    await expect(page).toHaveURL(/\/acceso/);
    await expect(page.locator('body')).toContainText(/credencial|incorrect|no.*v[aá]lid/i);
  });

  test('recepcion entra y ve la navegacion de su rol', async ({ page }) => {
    const clinicaId = await obtenerClinicaId(page);
    await page.goto('/acceso');
    await page.locator('input[name="clinica"]').fill(clinicaId);
    await page.locator('input[name="correo"]').fill(CUENTAS.recepcion);
    await page.locator('input[name="contrasena"]').fill(CONTRASENA);
    await page.getByRole('button', { name: /entrar/i }).click();

    await page.waitForURL(/\/(panel|agenda)/);
    // Se acota a la barra de navegacion: el panel tambien enlaza a la agenda,
    // y un selector que coja los dos falla por ambiguo sin que nada este mal.
    const navegacion = page.locator('nav');
    await expect(navegacion.getByRole('link', { name: /agenda/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /pacientes/i })).toBeVisible();
  });

  test('un rol que exige segundo factor no entra, y no es un fallo', async ({ page }) => {
    const clinicaId = await obtenerClinicaId(page);
    await page.goto('/acceso');
    await page.locator('input[name="clinica"]').fill(clinicaId);
    await page.locator('input[name="correo"]').fill(CUENTAS.administradora);
    await page.locator('input[name="contrasena"]').fill(CONTRASENA);
    await page.getByRole('button', { name: /entrar/i }).click();

    // El rol `administrador_clinica` exige TOTP y esta cuenta sintetica no lo
    // tiene configurado. Es el control funcionando: no se queda en el panel
    // con todas las acciones fallando.
    await expect(page).not.toHaveURL(/\/(panel|agenda)$/);
    await expect(page.locator('body')).toContainText(/segundo factor|verificaci|c[oó]digo/i);
  });
});
