/** Bandeja de mensajes derivados: navegación protegida y vista disponible. */
import { expect, test } from '../apoyo/prueba';

import { acceder, irA } from '../apoyo/sesion';

test('el profesional abre la bandeja segura de atención de mensajes', async ({ page }) => {
  await acceder(page, 'profesional');
  await irA(page, /atención de mensajes/i);

  await expect(page).toHaveURL(/\/conversaciones$/);
  await expect(page.getByRole('heading', { name: 'Atención de mensajes' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Conversaciones pendientes' })).toBeVisible();
});
