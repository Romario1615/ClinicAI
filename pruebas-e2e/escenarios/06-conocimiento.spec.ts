import { expect, test } from '../apoyo/prueba';

import { acceder, irA } from '../apoyo/sesion';

test('el personal consulta desde la interfaz una fuente aprobada', async ({ page }) => {
  await acceder(page, 'profesional');
  await irA(page, /conocimiento/i);

  await page.getByRole('textbox', { name: /qué necesita consultar/i }).fill(
    'seguro carne vigente antes de la consulta',
  );
  await page
    .getByRole('region', { name: /buscar en la base de conocimiento/i })
    .getByRole('button', { name: /^buscar$/i })
    .click();

  const resultado = page.getByRole('region', { name: 'Resultado de la búsqueda' });
  await expect(resultado).toContainText('documento(s) aprobado(s)');
  await expect(resultado).toContainText('Si tiene cobertura de seguro, presente el carne vigente');
  await expect(resultado).not.toContainText(/borrador de preguntas frecuentes/i);
});

test('la interfaz explica cuando la consulta no tiene una fuente aprobada', async ({ page }) => {
  await acceder(page, 'profesional');
  await irA(page, /conocimiento/i);

  await page.getByRole('textbox', { name: /qué necesita consultar/i }).fill(
    'xylophor glabrata dispositivo quasar ZXQ-1937',
  );
  await page
    .getByRole('region', { name: /buscar en la base de conocimiento/i })
    .getByRole('button', { name: /^buscar$/i })
    .click();

  const resultado = page.getByRole('region', { name: 'Resultado de la búsqueda' });
  await expect(resultado).toContainText('No hay información aprobada sobre esto');
  await expect(resultado).toContainText('Derive la consulta a un profesional');
  await expect(resultado.locator('article.fragmento')).toHaveCount(0);
});
