/** OCR real de un PDF imagen sintético; ingesta y consulta sobre la API aislada. */
import { resolve } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';

for (const ancho of [1366, 1024, 390]) {
  test(`escaneo, revisión y borrador en ventana a ${ancho}px`, async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: ancho, height: ancho === 390 ? 844 : 768 });
    await acceder(page, 'administradora');
    if (ancho < 821) await page.getByRole('button', { name: 'Alternar navegación', exact: true }).click();
    await irA(page, /conocimiento/i);
    await page.getByRole('button', { name: 'Cargar documento', exact: true }).click();
    const ventana = page.getByRole('dialog', { name: 'Cargar documento', exact: true });
    await expect(ventana).toBeVisible();
    let altas = 0;
    page.on('request', r => { if (r.method() === 'POST' && r.url().endsWith('/conocimiento/documentos')) altas++; });
    if (ancho === 1366) {
      await ventana.locator('input[type="file"]').first().setInputFiles({ name: 'no-valido.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\narchivo sintético inválido') });
      await ventana.getByRole('button', { name: 'Reconocer texto del escaneo', exact: true }).click();
      await expect(ventana.getByRole('alert')).toContainText(/dañado|procesar/);
      expect(altas).toBe(0);
    }
    await ventana.locator('input[type="file"]').first().setInputFiles(resolve('fixtures/horario-escaneado-sintetico.pdf'));
    const reconocimiento = page.waitForResponse(r => r.url().endsWith('/conocimiento/extraer-escaneo') && r.request().method() === 'POST');
    await ventana.getByRole('button', { name: 'Reconocer texto del escaneo', exact: true }).click();
    expect((await reconocimiento).status()).toBe(200);
    await expect(ventana.getByText('Revise el texto reconocido', { exact: true })).toBeVisible();
    await expect(ventana.getByText(/Sin texto reconocido en las páginas 2/)).toBeVisible();
    expect(altas).toBe(0);
    const guardar = ventana.getByRole('button', { name: 'Cargar documento', exact: true });
    await expect(guardar).toBeDisabled();
    const contenido = ventana.getByRole('textbox', { name: 'Contenido', exact: true });
    await expect(contenido).toHaveValue(/HORARIO SINTETICO/);
    await contenido.fill(`Horario administrativo sintético OCR ${ancho}. Lunes a viernes de 08:00 a 17:00. No contiene datos clínicos.`);
    const titulo = `Horario OCR sintético ${ancho} ${Date.now()}`;
    await ventana.getByRole('textbox', { name: /^Título(?:\s*\*)?$/ }).fill(titulo);
    const revisar = ventana.getByRole('checkbox', { name: 'He comparado y corregido el texto con el documento original.', exact: true });
    await revisar.check();
    await expect(guardar).toBeEnabled();
    await contenido.fill(`Horario administrativo sintético OCR ${ancho}. Lunes a viernes de 08:00 a 17:00. Documento revisado.`);
    await expect(revisar).not.toBeChecked();
    await expect(guardar).toBeDisabled();
    await revisar.check();
    await ventana.evaluate(async e => { await Promise.all(e.getAnimations({ subtree: true }).filter(a => a.effect?.getComputedTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined))); });
    const accesibilidad = await new AxeBuilder({ page }).include('dialog').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(accesibilidad.violations).toEqual([]);
    const medidas = await ventana.evaluate(e => { const r = e.getBoundingClientRect(); return { izquierda: r.left, derecha: r.right, arriba: r.top, abajo: r.bottom, ancho: innerWidth, alto: innerHeight, paginaAncho: document.documentElement.scrollWidth }; });
    expect(medidas.izquierda).toBeGreaterThanOrEqual(0);
    expect(medidas.arriba).toBeGreaterThanOrEqual(0);
    expect(medidas.derecha).toBeLessThanOrEqual(medidas.ancho + 1);
    expect(medidas.abajo).toBeLessThanOrEqual(medidas.alto + 1);
    expect(medidas.paginaAncho).toBeLessThanOrEqual(medidas.ancho + 1);
    const marco = await ventana.locator('.ventana').evaluate(e => {
      const cabecera = e.querySelector('.ventana__cabecera')!.getBoundingClientRect();
      const pie = e.querySelector('.ventana__pie')!.getBoundingClientRect();
      return { cabecera: cabecera.top, pie: pie.bottom, alto: innerHeight,
        desplazamiento: e.scrollTop, capa: e.closest('dialog')!.scrollTop };
    });
    expect(marco.cabecera).toBeGreaterThanOrEqual(0);
    expect(marco.pie).toBeLessThanOrEqual(marco.alto + 1);
    expect(marco.desplazamiento).toBe(0);
    expect(marco.capa).toBe(0);
    await page.screenshot({ path: `../tmp/qa-20261010-ocr/ocr-${ancho}.png` });
    const alta = page.waitForResponse(r => r.url().endsWith('/conocimiento/documentos') && r.request().method() === 'POST');
    await guardar.click();
    const respuesta = await alta;
    expect(respuesta.status()).toBe(201);
    expect((await respuesta.json()).status).toBe('DRAFT');
    await expect(ventana.getByText('Versión 1 cargada', { exact: false })).toBeVisible();
    expect(altas).toBe(1);
    await ventana.getByRole('button', { name: 'Listo', exact: true }).click();
    await expect(ventana).not.toBeVisible();
  });
}

test('auditoría consulta conocimiento sin cargar ni reconocer documentos', async ({ page }) => {
  await acceder(page, 'auditor'); await irA(page, /conocimiento/i);
  await expect(page.getByRole('button', { name: 'Cargar documento', exact: true })).toHaveCount(0);
});
