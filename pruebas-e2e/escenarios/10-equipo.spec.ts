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
  await page.getByRole('button', { name: 'Agregar profesional' }).click();
  const alta = page.getByRole('dialog', { name: 'Agregar profesional' });
  await expect(alta).toBeVisible();
  await alta.getByLabel('Nombres').fill(nombre);
  await alta.getByLabel('Apellidos').fill('Pruebas');
  await alta.getByLabel('Especialidad').selectOption({ index: 1 });
  await alta.getByLabel('Teléfono de contacto').fill('0990001234');

  const sede = alta.locator('.sede-opcion input').first();
  await expect(sede).toBeVisible();
  await sede.check();
  await alta.getByLabel('Sede principal').selectOption({ index: 1 });
  await alta.getByRole('button', { name: 'Crear perfil' }).click();
  await expect(page.getByRole('status')).toContainText('Profesional agregado al equipo.');

  const equipo = page.getByRole('region', { name: 'Equipo' });
  const perfil = equipo.getByRole('article').filter({ hasText: nombre });
  await expect(perfil).toContainText('Disponible');
  await perfil.getByRole('button', { name: 'Editar' }).click();
  const edicion = page.getByRole('dialog', { name: 'Editar perfil profesional' });
  await expect(edicion.getByLabel('Teléfono de contacto')).toHaveValue('0990001234');
  await edicion.getByRole('button', { name: 'Cancelar' }).click();

  // El perfil clínico y las credenciales son registros distintos. El
  // administrador los vincula desde Usuarios y roles.
  await page.getByRole('navigation', { name: 'Secciones' })
    .getByRole('link', { name: 'Usuarios y roles' }).click();
  await expect(page.getByRole('heading', { name: 'Usuarios y roles' })).toBeVisible();
  await page.getByRole('button', { name: 'Dar acceso a una persona' }).click();
  const altaAcceso = page.getByRole('dialog', { name: 'Dar acceso a una persona' });
  await expect(altaAcceso).toBeVisible();
  await altaAcceso.getByLabel('Nombre', { exact: true }).fill(`Cuenta ${sufijo}`);
  await altaAcceso.getByLabel('Apellido', { exact: true }).fill('Profesional');
  await altaAcceso.getByLabel('Correo', { exact: true }).fill(`profesional-${sufijo}@example.invalid`);
  await altaAcceso.getByLabel('Contraseña inicial').fill('Inicial!Segura123');
  await altaAcceso.locator('.opciones .opcion').filter({ hasText: /^Profesional/ }).locator('input').check();
  await altaAcceso.getByLabel('Perfil profesional').selectOption({ label: `${nombre} Pruebas` });
  await altaAcceso.getByRole('button', { name: 'Crear cuenta y dar acceso' }).click();
  await expect(page.locator('.exito[role="status"]')).toContainText('Cuenta creada y acceso concedido.');
  const cuenta = page.locator('tbody tr').filter({ hasText: `profesional-${sufijo}@example.invalid` });
  await expect(cuenta).toContainText('Profesional');

  await page.getByRole('navigation', { name: 'Secciones' })
    .getByRole('link', { name: 'Equipo clínico' }).click();
  await expect(page.getByRole('heading', { name: 'Equipo clínico' })).toBeVisible();
  const perfilActualizado = equipo.getByRole('article').filter({ hasText: nombre });
  await perfilActualizado.getByRole('button', { name: 'Editar' }).click();
  const editarActualizado = page.getByRole('dialog', { name: 'Editar perfil profesional' });
  await editarActualizado.getByLabel('Perfil activo').uncheck();
  await editarActualizado.getByRole('button', { name: 'Guardar cambios' }).click();

  await expect(page.getByRole('status')).toContainText('Perfil profesional actualizado.');
  await expect(perfil).toContainText('Inactivo');
});
