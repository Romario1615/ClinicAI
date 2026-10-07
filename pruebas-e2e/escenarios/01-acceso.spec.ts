/** Acceso local por rol y navegación protegida. */
import AxeBuilder from '@axe-core/playwright';
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

  test('la pantalla de acceso conserva landmarks válidos y permite saltar al contenido con teclado', async ({ page }) => {
    await page.goto('/acceso');
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.getByRole('group', { name: 'Ingresar como un rol' })).toBeVisible();

    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Saltar al contenido' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('#contenido')).toBeFocused();
  });

  test('recepción entra y ve la navegación de su rol', async ({ page }) => {
    await acceder(page, 'recepcion');
    const navegacion = page.getByRole('navigation', { name: 'Secciones' });
    await expect(navegacion.getByRole('link', { name: /agenda/i })).toBeVisible();
    await expect(navegacion.getByRole('link', { name: /pacientes/i })).toBeVisible();
  });

  test('anuncia la sección actual en la navegación', async ({ page }) => {
    await acceder(page, 'recepcion');
    const navegacion = page.getByRole('navigation', { name: 'Secciones' });
    const agenda = navegacion.getByRole('link', { name: /agenda/i });
    await agenda.click();
    await expect(agenda).toHaveAttribute('aria-current', 'page');
  });

  test('administración de clínica entra en el entorno local', async ({ page }) => {
    await acceder(page, 'administradora');
    await expect(page.getByRole('navigation', { name: 'Secciones' })).toBeVisible();
    await expect(page.locator('h1').first()).toContainText(/panel/i);
  });

  test('el menú móvil se despliega encima del contenido y cierra con Escape o al tocar fuera', async ({ page }) => {
    await acceder(page, 'recepcion');

    const alternar = page.getByRole('button', { name: 'Alternar navegación' });
    const navegacion = page.getByRole('navigation', { name: 'Secciones' });
    for (const ancho of [320, 390]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      await expect(alternar).toHaveAttribute('aria-expanded', 'false');
      await alternar.click();
      await expect(alternar).toHaveAttribute('aria-expanded', 'true');
      await expect(navegacion).toBeVisible();
      await expect(navegacion).toHaveCSS('position', 'fixed');
      await expect(page.getByRole('button', { name: 'Cerrar menú de navegación' })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(ancho);
      const accesibilidad = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze();
      expect(accesibilidad.violations.map(({ id }) => id)).toEqual([]);

      await page.keyboard.press('Escape');
      await expect(navegacion).toBeHidden();
      await alternar.click();
      // Pulsa la franja visible junto al panel flotante; el centro del fondo
      // queda cubierto por la propia navegación y no recibe el clic.
      await page.getByRole('button', { name: 'Cerrar menú de navegación' }).click({ position: { x: ancho - 12, y: 12 } });
      await expect(navegacion).toBeHidden();
    }
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
    await page.getByRole('button', { name: 'Registrar clínica' }).first().click();
    const registro = page.getByRole('dialog', { name: 'Registrar clínica' });
    await expect(registro).toBeVisible();
    await registro.getByLabel('Nombre de la clínica').fill(nombre);
    await registro.getByLabel('Identificación fiscal').fill(`E2E-${sufijo}`);
    await registro.getByLabel('Nombre', { exact: true }).fill('Admin');
    await registro.getByLabel('Apellido', { exact: true }).fill('Pruebas');
    await registro.getByLabel('Correo de acceso').fill(`admin-${sufijo}@example.invalid`);
    await registro.getByLabel('Contraseña temporal').fill('Temporal!Seguro1234');
    await registro.getByRole('button', { name: 'Crear clínica y administrador' }).click();
    await expect(page.getByRole('status').filter({ hasText: `Clínica ${nombre} creada` })).toBeVisible();
    await expect(page.getByRole('strong').filter({ hasText: nombre })).toBeVisible();

    const organizacion = page.getByRole('article').filter({ hasText: nombre }).first();
    await organizacion.getByRole('button', { name: 'Gestionar sedes' }).click();
    const sedes = page.locator('section').filter({ has: page.getByRole('heading', { name: `Sedes de ${nombre}` }) });
    await expect(sedes.getByRole('article').filter({ hasText: 'Sede principal' })).toBeVisible();
    await sedes.getByRole('button', { name: 'Agregar sucursal' }).click();
    const altaSede = page.getByRole('dialog', { name: 'Agregar sede' });
    await altaSede.getByLabel('Nombre de la sede').fill(`Sucursal E2E ${sufijo}`);
    await altaSede.getByLabel('Dirección').fill('Av. Pruebas 456');
    await altaSede.getByRole('button', { name: 'Crear sede' }).click();
    await expect(sedes.getByRole('status')).toContainText(`Sede Sucursal E2E ${sufijo} creada`);
    await expect(sedes.getByRole('article').filter({ hasText: `Sucursal E2E ${sufijo}` })).toBeVisible();

    await page.getByRole('button', { name: 'Dar acceso a una persona' }).click();
    const asignacion = page.getByRole('dialog', { name: 'Dar acceso a una persona' });
    await expect(asignacion).toBeVisible();
    await asignacion.locator('select[name="clinicaNuevaUsuario"]').selectOption({ label: nombre });
    const todasLasSedes = asignacion.getByRole('checkbox', { name: /Acceso a todas las sedes/ });
    await expect(todasLasSedes).toBeChecked();
    await todasLasSedes.uncheck();
    await asignacion.getByRole('checkbox', { name: `Sucursal E2E ${sufijo}` }).check();
    await asignacion.locator('input[name="nombreUsuario"]').fill('Recepción');
    await asignacion.locator('input[name="apellidoUsuario"]').fill('E2E');
    await asignacion.locator('input[name="correoUsuario"]').fill(`recepcion-${sufijo}@example.invalid`);
    await asignacion.locator('input[name="contrasenaUsuario"]').fill('Temporal!Seguro1234');
    await asignacion.getByRole('checkbox', { name: /recepci[oó]n/i }).check();
    await asignacion.getByRole('button', { name: 'Crear cuenta y asignar módulos' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Cuenta creada y vinculada' }))
      .toContainText(`Cuenta creada y vinculada a ${nombre}`);
    const cuentaCreada = page.getByRole('article').filter({ hasText: `recepcion-${sufijo}@example.invalid` });
    await expect(cuentaCreada).toContainText('Acceso limitado a 1 sede');
  });
});
