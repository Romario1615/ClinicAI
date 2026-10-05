/** Acceso local por rol y navegación protegida. */
import { expect, test } from '../apoyo/prueba';

import { acceder } from '../apoyo/sesion';

test.describe('Acceso local por roles', () => {
  test('una ruta protegida redirige al acceso y vuelve al destino', async ({ page }) => {
    await page.goto('/pacientes');
    await expect(page).toHaveURL(/\/acceso/);
    await expect(page).toHaveURL(/destino/);
  });

  test('muestra botones de rol y oculta el formulario de contraseña', async ({ page }) => {
    await page.goto('/acceso');
    await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
    await expect(page.locator('.acceso__rol')).toHaveCount(6);
    await expect(page.locator('input[name="contrasena"]')).toHaveCount(0);
  });

  test('recepción entra y ve la navegación de su rol', async ({ page }) => {
    await acceder(page, 'recepcion');
    const navegacion = page.getByRole('navigation', { name: 'Secciones' });
    await expect(navegacion.getByRole('link', { name: /agenda/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /pacientes/i })).toBeVisible();
  });

  test('administración de clínica entra en el entorno local', async ({ page }) => {
    await acceder(page, 'administradora');
    await expect(page.getByRole('navigation', { name: 'Secciones' })).toBeVisible();
    await expect(page.locator('h1').first()).toContainText(/panel/i);
  });

  test('auditoría entra en el entorno local', async ({ page }) => {
    await acceder(page, 'auditor');
    await expect(page.getByRole('navigation', { name: 'Secciones' })).toBeVisible();
  });

  test('superadministración abre el portal global de clínicas', async ({ page }) => {
    await acceder(page, 'superadministrador');
    await expect(page.getByRole('navigation', { name: 'Secciones' }).getByRole('link', { name: 'Clínicas' })).toBeVisible();
    await page.getByRole('link', { name: 'Clínicas' }).click();
    await expect(page.getByRole('heading', { name: 'Clínicas', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Organizaciones registradas' })).toBeVisible();
  });

  test('superadministración registra clínica y administrador inicial', async ({ page }) => {
    await acceder(page, 'superadministrador');
    await page.getByRole('link', { name: 'Clínicas' }).click();
    const sufijo = Date.now().toString();
    const nombre = `Clínica E2E [SINTETICO] ${sufijo}`;
    const registro = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Registrar una clínica' }) });
    await registro.getByLabel('Nombre de la clínica').fill(nombre);
    await registro.getByLabel('Identificación fiscal').fill(`E2E-${sufijo}`);
    await registro.getByLabel('Nombre', { exact: true }).fill('Admin');
    await registro.getByLabel('Apellido', { exact: true }).fill('Pruebas');
    await registro.getByLabel('Correo de acceso').fill(`admin-${sufijo}@example.invalid`);
    await registro.getByLabel('Contraseña temporal').fill('Temporal!Seguro1234');
    await registro.getByRole('button', { name: 'Crear clínica y administrador' }).click();
    await expect(page.getByRole('status')).toContainText(`Clínica ${nombre} creada`);
    await expect(page.getByRole('strong').filter({ hasText: nombre })).toBeVisible();

    const asignacion = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Dar acceso a una persona' }) });
    await asignacion.locator('select[name="clinicaNuevaUsuario"]').selectOption({ label: nombre });
    await asignacion.locator('input[name="nombreUsuario"]').fill('Recepción');
    await asignacion.locator('input[name="apellidoUsuario"]').fill('E2E');
    await asignacion.locator('input[name="correoUsuario"]').fill(`recepcion-${sufijo}@example.invalid`);
    await asignacion.locator('input[name="contrasenaUsuario"]').fill('Temporal!Seguro1234');
    await asignacion.getByRole('checkbox', { name: /recepci[oó]n/i }).check();
    await asignacion.getByRole('button', { name: 'Crear cuenta y asignar módulos' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cuenta creada y vinculada' }))
      .toContainText(`Cuenta creada y vinculada a ${nombre}`);
    await expect(page.getByRole('article').filter({ hasText: `recepcion-${sufijo}@example.invalid` }))
      .toBeVisible();
  });
});
