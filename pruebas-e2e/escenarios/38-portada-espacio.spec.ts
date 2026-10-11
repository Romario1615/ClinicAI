/** La ilustración debe respetar el espacio del mensaje y del acceso. */
import { test, expect } from '../apoyo/prueba';
import { esperaDeConsultas, solapesVisibles } from '../apoyo/espacio';

const tamanos = [
  { width: 1920, height: 1080 }, { width: 1440, height: 900 },
  { width: 1366, height: 768 }, { width: 1280, height: 720 },
  { width: 1200, height: 800 }, { width: 1101, height: 700 },
  { width: 1024, height: 768 }, { width: 821, height: 600 },
  { width: 900, height: 500 }, { width: 844, height: 390 },
  { width: 820, height: 600 }, { width: 768, height: 1024 },
  { width: 390, height: 844 }, { width: 320, height: 568 },
];

for (const movimiento of ['reduce', 'no-preference'] as const) {
  test(`la portada separa texto, ilustración y tarjetas con movimiento ${movimiento}`, async ({ page }, info) => {
    test.setTimeout(120_000);
    const esperar = esperaDeConsultas(page);
    await page.emulateMedia({ reducedMotion: movimiento });
    await page.goto('/acceso');
    await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
    await esperar();
    const incidencias: unknown[] = [];
    for (const tamano of tamanos) {
      await page.setViewportSize(tamano);
      await expect(page.locator('.acceso')).toHaveCSS('height', `${tamano.height}px`);
      await page.locator('.acceso__tarjeta').evaluate(e => { e.scrollTop = 0; });
      await esperar();
      const errores = await solapesVisibles(page);
      const ilustracion = await page.locator('.acceso__grafico svg').evaluate(svg => {
        if (!svg.checkVisibility({ checkVisibilityCSS: true })) return [];
        const r = svg.getBoundingClientRect();
        return ['.acceso__mensaje', '.acceso__pie-marca', '.acceso__agente'].filter(selector => {
          const e = document.querySelector(selector)!;
          if (!e.checkVisibility({ checkVisibilityCSS: true })) return false;
          const b = e.getBoundingClientRect();
          return Math.min(r.right, b.right) - Math.max(r.left, b.left) > 2
            && Math.min(r.bottom, b.bottom) - Math.max(r.top, b.top) > 2;
        });
      });
      if (errores.length || ilustracion.length) incidencias.push({ tamano, errores, ilustracion });
      await page.screenshot({ path: info.outputPath(`portada-${tamano.width}-${tamano.height}.png`) });
    }
    await info.attach('portada-geometria', {
      body: JSON.stringify({ movimiento, tamanos, incidencias }, null, 2),
      contentType: 'application/json',
    });
    expect(incidencias).toEqual([]);
  });
}
