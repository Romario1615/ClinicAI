/** Carga, envío y error sintéticos: comprueba presentación, no credenciales. */
import { test, expect } from '../apoyo/prueba';
import { esperaDeConsultas, solapesVisibles } from '../apoyo/espacio';

test('la portada conserva sus espacios durante la carga, el envío y un error largo', async ({ page }, info) => {
  test.setTimeout(120_000);
  const esperar = esperaDeConsultas(page);
  const erroresNavegador: string[] = [];
  page.on('pageerror', e => erroresNavegador.push(e.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  let liberarAccesos!: () => void, liberarIngreso!: () => void;
  const accesos = new Promise<void>(r => { liberarAccesos = r; });
  const ingreso = new Promise<void>(r => { liberarIngreso = r; });
  let intentos = 0;
  await page.route('**/autenticacion/accesos-locales', async route => {
    await accesos;
    await route.fallback();
  });
  await page.route('**/autenticacion/sesion-local', async route => {
    intentos++;
    await ingreso;
    await route.fulfill({ status: 503, json: { codigo: 'NO_DISPONIBLE',
      mensaje: 'Servicio temporalmente no disponible. '.repeat(5),
      correlacion_id: 'referencia-sintetica-'.repeat(15) } });
  });
  const tamanos = [{ width: 1440, height: 900 }, { width: 1024, height: 768 },
    { width: 821, height: 600 }, { width: 820, height: 600 }, { width: 768, height: 1024 },
    { width: 390, height: 844 }, { width: 320, height: 568 }, { width: 844, height: 390 }];
  const incidencias: unknown[] = [];
  const medir = async (estado: string) => {
    for (const tamano of tamanos) {
      await page.setViewportSize(tamano);
      await expect(page.locator('.acceso')).toHaveCSS('height', `${tamano.height}px`);
      await page.evaluate(() => document.fonts.ready);
      for (const posicion of [0, 0.5, 1]) {
        await page.locator('.acceso__tarjeta').evaluate((e, posicion) => {
          e.scrollTop = (e.scrollHeight - e.clientHeight) * posicion;
        }, posicion);
        const errores = await solapesVisibles(page);
        const dentro = await page.locator('.acceso__tarjeta').evaluate(e => {
          const r = e.getBoundingClientRect();
          return r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1
            && document.documentElement.scrollWidth <= innerWidth + 1
            && document.documentElement.scrollHeight <= innerHeight + 1;
        });
        if (errores.length || !dentro) incidencias.push({ estado, tamano, posicion, errores, dentro });
      }
      await expect(page.locator('.acceso__foto').first()).toHaveCSS('opacity', '1');
      if (tamano.width === 390) await page.screenshot({ path: info.outputPath(`acceso-${estado}.png`) });
    }
  };
  try {
    await page.goto('/acceso');
    await expect(page.getByRole('heading', { name: 'Preparando acceso' })).toBeVisible();
    await medir('carga');
    liberarAccesos();
    await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
    await esperar();
    await page.getByRole('button', { name: /profesional de salud/i }).click();
    await expect(page.getByRole('status')).toHaveCount(6);
    for (const boton of await page.locator('.acceso__rol').all()) await expect(boton).toBeDisabled();
    await medir('envio');
    liberarIngreso();
    await expect(page.getByRole('alert')).toContainText('Servicio temporalmente no disponible.');
    await esperar();
    for (const boton of await page.locator('.acceso__rol').all()) await expect(boton).toBeEnabled();
    await medir('error');
    await page.getByRole('button', { name: /profesional de salud/i }).click();
    await expect.poll(() => intentos).toBe(2);
    await expect(page.getByRole('alert')).toBeVisible();
    expect(erroresNavegador).toEqual([]);
    await info.attach('estados-portada', { body: JSON.stringify({ tamanos, incidencias }, null, 2), contentType: 'application/json' });
    expect(incidencias).toEqual([]);
  } finally { liberarAccesos(); liberarIngreso(); }
});
