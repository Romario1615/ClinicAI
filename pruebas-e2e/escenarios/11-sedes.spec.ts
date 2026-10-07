/** Administración local de información operativa de sedes. */
import { expect, test } from '../apoyo/prueba';
import { acceder } from '../apoyo/sesion';

test('administración edita y conserva los datos de la sede en Configuración', async ({ page }) => {
  await acceder(page, 'administradora');
  await page.getByRole('navigation', { name: 'Secciones' })
    .getByRole('link', { name: 'Configuración' }).click();
  await page.getByRole('button', { name: 'Sedes' }).click();
  await expect(page.getByRole('heading', { name: 'Sedes y datos de reserva' })).toBeVisible();

  const tarjeta = page.locator('article.sede').first();
  await expect(tarjeta).toBeVisible();
  const telefonoAnterior = await tarjeta.locator('dl div').nth(1).locator('dd').innerText();
  const valorAnterior = telefonoAnterior === 'Sin teléfono registrado' ? '' : telefonoAnterior;
  const telefonoTemporal = '0990000001';

  await tarjeta.getByRole('button', { name: 'Editar sede' }).click();
  const editor = page.getByRole('dialog', { name: /^Editar sede · / });
  await editor.getByLabel('Teléfono').fill(telefonoTemporal);
  await editor.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByRole('status')).toContainText('La información de la sede se actualizó.');
  await expect(tarjeta.locator('dl div').nth(1).locator('dd')).toHaveText(telefonoTemporal);

  // Restaurar el valor previo para que este escenario no altere la base local.
  await tarjeta.getByRole('button', { name: 'Editar sede' }).click();
  await editor.getByLabel('Teléfono').fill(valorAnterior);
  await editor.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(tarjeta.locator('dl div').nth(1).locator('dd')).toHaveText(telefonoAnterior);
});
