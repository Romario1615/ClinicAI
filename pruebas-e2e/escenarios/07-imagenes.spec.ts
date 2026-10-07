import { expect, test } from '../apoyo/prueba';
import AxeBuilder from '@axe-core/playwright';

import { pacienteConVersionAnterior } from '../apoyo/datos';
import { acceder, irA } from '../apoyo/sesion';

const PNG_MINIMO =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNQdE79DwADGwHJJzVbHwAAAABJRU5ErkJggg==';

test('el profesional carga y vuelve a ver una imagen cifrada del paciente', async ({ page, request }) => {
  const paciente = await pacienteConVersionAnterior(request);
  await acceder(page, 'profesional');
  await irA(page, /pacientes/i);

  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(
    paciente.numero_documento ?? '',
  );
  await busqueda.getByRole('button', { name: /^buscar$/i }).click();
  await page
    .getByRole('row')
    .filter({ hasText: paciente.numero_documento ?? '' })
    .getByRole('button', { name: /ver ficha/i })
    .click();

  const ficha = page.locator('.ficha');
  await ficha.getByRole('tab', { name: 'Imágenes' }).click();
  const galeria = ficha.locator('section[aria-label="Imágenes clínicas del paciente"]');
  await galeria.getByRole('button', { name: 'Cargar imagen clínica', exact: true }).click();
  const carga = page.getByRole('dialog', { name: 'Cargar imagen clínica', exact: true });
  await expect(carga).toBeVisible();
  await carga.evaluate((dialogo) => Promise.all(
    dialogo.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
  ));
  const accesibilidad = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(accesibilidad.violations.map((incidencia) => incidencia.id)).toEqual([]);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  const descripcion = `Control visual E2E ${Date.now()}`;
  await carga.getByLabel('Piezas FDI (opcional)').fill('36');
  await carga.getByLabel('Descripción (opcional)').fill(descripcion);
  await carga.getByLabel(/Archivo JPEG, PNG o WebP/i).setInputFiles({
    name: 'control.png',
    mimeType: 'image/png',
    buffer: Buffer.from(PNG_MINIMO, 'base64'),
  });
  await carga.getByRole('button', { name: 'Guardar imagen', exact: true }).click();
  await expect(carga).toHaveCount(0);

  await expect(galeria.locator('.galeria__exito')).toContainText(/Imagen cargada y cifrada/i);
  const tarjeta = galeria.locator('.galeria__tarjeta').filter({ hasText: descripcion });
  await expect(tarjeta.locator('img')).toBeVisible();
  await expect(tarjeta).toContainText('Fotografía intraoral');
  await expect(tarjeta).toContainText('Pieza(s) 36');
});
