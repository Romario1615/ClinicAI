/** Extremos de presentación de avisos; no sustituyen cálculos ni permisos. */
import { test, expect } from '../apoyo/prueba';
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { acceder } from '../apoyo/sesion';
import { esperaDeConsultas, solapesVisibles } from '../apoyo/espacio';

async function cantidades(page: Page, cantidad: number): Promise<void> {
  await page.route('**/api/v1/**/cuenta', async route => {
    const camino = new URL(route.request().url()).pathname;
    if (!['/conversaciones/pendientes/cuenta', '/conversaciones/avisos-tratamiento/cuenta',
      '/historia/avisos-acceso-emergencia/cuenta'].some(p => camino.endsWith(p))) {
      await route.fallback(); return;
    }
    await route.fulfill({ json: { cantidad } });
  });
  await page.route('**/api/v1/pagos/cargos/**', async route => {
    if (new URL(route.request().url()).searchParams.get('vencidos') !== 'true') {
      await route.fallback(); return;
    }
    await route.fulfill({ json: { elementos: [], total: cantidad, limite: 1, desplazamiento: 0 } });
  });
}

for (const movimiento of ['reduce', 'no-preference'] as const) {
  test(movimiento === 'reduce'
    ? 'los avisos permanecen dentro de la pantalla y solo desplazan su lista'
    : 'los avisos permanecen dentro de la pantalla con movimiento normal y solo desplazan su lista', async ({ page }, info) => {
    test.setTimeout(120_000);
    const erroresNavegador: string[] = [];
    page.on('pageerror', e => erroresNavegador.push(e.message));
    const esperar = esperaDeConsultas(page);
    await page.emulateMedia({ reducedMotion: movimiento });
    await cantidades(page, 12345);
    await acceder(page, 'administradora');
    await esperar();
    const incidencias: unknown[] = [];
    for (const tamano of [{ width: 1440, height: 900 }, { width: 1024, height: 768 },
      { width: 821, height: 600 }, { width: 820, height: 600 }, { width: 768, height: 1024 },
      { width: 390, height: 844 }, { width: 320, height: 568 }, { width: 844, height: 390 }]) {
      await page.setViewportSize(tamano);
      const campana = page.getByRole('button', { name: 'Notificaciones de seguimiento' });
      await campana.click();
      const panel = page.getByRole('dialog', { name: 'Seguimiento de hoy' });
      await expect(panel).toBeVisible();
      await esperar();
      await expect(campana).toHaveAccessibleDescription('49380 avisos pendientes');
      await expect(page.locator('.campana__cuenta')).toHaveText('99+');
      const limites = await panel.evaluate(e => {
        const r = e.getBoundingClientRect();
        return { izquierda: r.left, derecha: r.right, arriba: r.top, abajo: r.bottom,
          ancho: innerWidth, alto: innerHeight };
      });
      if (limites.izquierda < 0 || limites.derecha > tamano.width + 1
        || limites.arriba < 0 || limites.abajo > tamano.height + 1) incidencias.push({ tamano, limites });
      const cabecera = await panel.locator('header').boundingBox();
      const pie = await panel.locator('.notificaciones__todo').boundingBox();
      const lista = panel.locator('.notificaciones__contenido');
      if (tamano.height === 390) {
        expect(await lista.evaluate(e => e.scrollHeight > e.clientHeight)).toBe(true);
      }
      for (const enlace of await lista.getByRole('link').all()) {
        await enlace.scrollIntoViewIfNeeded();
        expect(await enlace.evaluate(e => {
          const r = e.getBoundingClientRect(), padre = e.parentElement!.getBoundingClientRect();
          return r.left >= 0 && r.right <= innerWidth + 1 && r.top >= padre.top - 1
            && r.bottom <= padre.bottom + 1 && r.height >= 44;
        }), await enlace.textContent()).toBe(true);
        const errores = await solapesVisibles(page, '#panel-notificaciones');
        if (errores.length) incidencias.push({ tamano, errores });
      }
      expect(await panel.locator('header').boundingBox()).toEqual(cabecera);
      expect(await panel.locator('.notificaciones__todo').boundingBox()).toEqual(pie);
      expect((await new AxeBuilder({ page }).include('#panel-notificaciones')
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([]);
      await page.screenshot({ path: info.outputPath(`avisos-${tamano.width}-${tamano.height}.png`) });
      await panel.getByRole('button', { name: 'Cerrar notificaciones' }).click();
      await expect(campana).toBeFocused();
      await expect(panel).not.toBeVisible();
    }
    await info.attach('limites-avisos', { body: JSON.stringify(incidencias, null, 2), contentType: 'application/json' });
    expect(incidencias).toEqual([]);
    expect(erroresNavegador).toEqual([]);
  });
}

test('la carga y el vacío mantienen el cierre disponible y el foco vuelve a la campana', async ({ page }) => {
  const erroresNavegador: string[] = [];
  page.on('pageerror', e => erroresNavegador.push(e.message));
  const esperar = esperaDeConsultas(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await cantidades(page, 0);
  let resolver!: () => void;
  const liberar = new Promise<void>(r => { resolver = r; });
  let consultas = 0;
  await page.route('**/api/v1/agenda/citas?**', async route => {
    if (route.request().method() !== 'GET') {
      await route.fallback(); return;
    }
    consultas++;
    await liberar;
    await route.fulfill({ json: { elementos: [], total: 0, limite: 200, desplazamiento: 0 } });
  });
  try {
    await acceder(page, 'administradora');
    await expect.poll(() => consultas).toBeGreaterThan(0);
    const campana = page.getByRole('button', { name: 'Notificaciones de seguimiento' });
    await campana.click();
    const panel = page.getByRole('dialog', { name: 'Seguimiento de hoy' });
    await expect(panel).toContainText('Actualizando avisos…');
    await expect(panel.getByRole('button', { name: 'Cerrar notificaciones' })).toBeVisible();
    expect(await solapesVisibles(page, '#panel-notificaciones')).toEqual([]);
    resolver();
    await esperar();
    await expect(panel).toContainText('Todo al día');
    expect(await solapesVisibles(page, '#panel-notificaciones')).toEqual([]);
    await panel.getByRole('link', { name: 'Ver seguimiento en el panel' }).focus();
    await page.keyboard.press('Escape');
    await expect(panel).not.toBeVisible();
    await expect(campana).toBeFocused();
    await campana.click();
    await page.locator('main').click({ position: { x: 20, y: 480 } });
    await expect(panel).not.toBeVisible();
    expect(erroresNavegador).toEqual([]);
  } finally { resolver(); }
});

test('los accesos de los avisos conservan el destino y cierran el panel', async ({ page }) => {
  test.setTimeout(60_000);
  const esperar = esperaDeConsultas(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await cantidades(page, 5);
  await acceder(page, 'administradora');
  for (const [etiqueta, ruta] of [['Cobros vencidos', '/pagos'], ['Atención de mensajes', '/conversaciones'],
    ['Revisión clínica', '/conversaciones'], ['Seguridad clínica', '/seguridad']]) {
    await esperar();
    await page.getByRole('button', { name: 'Notificaciones de seguimiento' }).click();
    const panel = page.getByRole('dialog', { name: 'Seguimiento de hoy' });
    await panel.getByRole('link', { name: new RegExp(etiqueta) }).click();
    await expect(page).toHaveURL(new RegExp(`${ruta}$`));
    await expect(panel).not.toBeVisible();
  }
});
