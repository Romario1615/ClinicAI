import { expect, test } from '../apoyo/prueba';

import { pacienteConVersionAnterior } from '../apoyo/datos';
import { acceder, irA } from '../apoyo/sesion';

const PNG_MINIMO =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNQdE79DwADGwHJJzVbHwAAAABJRU5ErkJggg==';

test('el profesional carga y vuelve a ver una imagen cifrada del paciente', async ({ page, request }) => {
  const paciente = await pacienteConVersionAnterior(request);
  await acceder(page, 'profesional');
  await irA(page, /pacientes/i);

  const busqueda = page.getByRole('region', { name: 'Buscar pacientes' });
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
  const descripcion = `Control visual E2E ${Date.now()}`;
  await galeria.getByLabel('Piezas FDI (opcional)').fill('36');
  await galeria.getByLabel('Descripción (opcional)').fill(descripcion);
  await galeria.getByLabel(/Archivo JPEG, PNG o WebP/i).setInputFiles({
    name: 'control.png',
    mimeType: 'image/png',
    buffer: Buffer.from(PNG_MINIMO, 'base64'),
  });
  await galeria.getByRole('button', { name: 'Guardar imagen' }).click();

  await expect(galeria.locator('.galeria__exito')).toContainText(/Imagen cargada y cifrada/i);
  const tarjeta = galeria.locator('.galeria__tarjeta').filter({ hasText: descripcion });
  await expect(tarjeta.locator('img')).toBeVisible();
  await expect(tarjeta).toContainText('Fotografía intraoral');
  await expect(tarjeta).toContainText('Pieza(s) 36');
});
