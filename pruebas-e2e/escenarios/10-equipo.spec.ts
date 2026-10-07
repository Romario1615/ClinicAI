/** Gestión de perfiles profesionales desde la interfaz conectada. */
import { expect, test } from '../apoyo/prueba';

import { acceder } from '../apoyo/sesion';

test('administración crea, edita y desactiva un perfil profesional', async ({ page }) => {
  await acceder(page, 'administradora');
  await page.getByRole('navigation', { name: 'Secciones' })
    .getByRole('link', { name: 'Equipo clínico' }).click();
  await expect(page.getByRole('heading', { name: 'Equipo clínico' })).toBeVisible();

  const sufijo = Date.now().toString();
  const nombre = `Profesional E2E ${sufijo}`;
  await page.getByLabel('Nombres').fill(nombre);
  await page.getByLabel('Apellidos').fill('Pruebas');
  await page.getByLabel('Especialidad').selectOption({ index: 1 });
  await page.getByLabel('Teléfono de contacto').fill('0990001234');

  const sede = page.locator('.sede-opcion input').first();
  await expect(sede).toBeVisible();
  await sede.check();
  await page.getByLabel('Sede principal').selectOption({ index: 1 });
  await page.getByRole('button', { name: 'Crear perfil' }).click();
  await expect(page.getByRole('status')).toContainText('Profesional agregado al equipo.');

  const equipo = page.getByRole('region', { name: 'Equipo' });
  const perfil = equipo.getByRole('article').filter({ hasText: nombre });
  await expect(perfil).toContainText('Disponible');
  await perfil.getByRole('button', { name: 'Editar' }).click();
  await expect(page.getByLabel('Teléfono de contacto')).toHaveValue('0990001234');

  // El perfil clínico y las credenciales son registros distintos. El
  // administrador los vincula desde Usuarios y roles.
  await page.getByRole('navigation', { name: 'Secciones' })
    .getByRole('link', { name: 'Usuarios y roles' }).click();
  await expect(page.getByRole('heading', { name: 'Usuarios y roles' })).toBeVisible();
  await page.getByRole('button', { name: 'Dar acceso a una persona' }).click();
  await page.getByLabel('Nombre', { exact: true }).fill(`Cuenta ${sufijo}`);
  await page.getByLabel('Apellido', { exact: true }).fill('Profesional');
  await page.getByLabel('Correo', { exact: true }).fill(`profesional-${sufijo}@example.invalid`);
  await page.getByLabel('Contraseña inicial').fill('Inicial!Segura123');
  await page.locator('.opciones .opcion').filter({ hasText: /^Profesional/ }).locator('input').check();
  await page.getByLabel('Perfil profesional').selectOption({ label: `${nombre} Pruebas` });
  await page.getByRole('button', { name: 'Crear cuenta y dar acceso' }).click();
  await expect(page.locator('.exito[role="status"]')).toContainText('Cuenta creada y acceso concedido.');
  const cuenta = page.locator('tbody tr').filter({ hasText: `profesional-${sufijo}@example.invalid` });
  await expect(cuenta).toContainText('Profesional');

  await page.getByRole('navigation', { name: 'Secciones' })
    .getByRole('link', { name: 'Equipo clínico' }).click();
  await expect(page.getByRole('heading', { name: 'Equipo clínico' })).toBeVisible();
  const perfilActualizado = equipo.getByRole('article').filter({ hasText: nombre });
  await perfilActualizado.getByRole('button', { name: 'Editar' }).click();
  await page.getByLabel('Perfil activo').uncheck();
  await page.getByRole('button', { name: 'Guardar cambios' }).click();

  await expect(page.getByRole('status')).toContainText('Perfil profesional actualizado.');
  await expect(perfil).toContainText('Inactivo');
});
