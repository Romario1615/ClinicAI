/** Una respuesta retrasada no debe cambiar las cifras del filtro vigente. */
import { test, expect } from '../apoyo/prueba';
import { acceder } from '../apoyo/sesion';

test('el Panel conserva las cifras reales del periodo vigente aunque fallen después consultas anteriores', async ({ page }) => {
  await acceder(page, 'administradora');
  await page.getByRole('tab', { name: 'Cifras del periodo', exact: true }).click();
  const tarjeta = page.locator('article.tarjeta').filter({ has: page.getByText('Citas del periodo', { exact: true }) });
  await expect(tarjeta).toBeVisible();

  const origen = 'http://127.0.0.1:8000/api/v1';
  const api = process.env.URL_API ?? origen;
  const anteriores: string[] = [];
  const liberar: (() => Promise<void>)[] = [];
  let numero = 0;
  let totalVigente: number | undefined;
  await page.route(/\/api\/v1\/dashboard\/\?/, async ruta => {
    const turno = ++numero;
    if (turno <= 2) {
      anteriores.push(ruta.request().url());
      let continuar!: () => void;
      const bloqueo = new Promise<void>(resolve => { continuar = resolve; });
      liberar.push(async () => {
        try {
          await ruta.fulfill({ status: 503, headers: {
            'Access-Control-Allow-Origin': new URL(process.env.URL_BASE ?? 'http://localhost:4200').origin,
          }, json: {
            codigo: 'QA_ANTERIOR', mensaje: 'Respuesta anterior sintética descartada', detalles: {},
          } });
        } finally { continuar(); }
      });
      await bloqueo;
      return;
    }
    const respuesta = await ruta.fetch({ url: ruta.request().url().replace(origen, api) });
    expect(respuesta.ok()).toBeTruthy();
    if (turno === 3) totalVigente = (await respuesta.json()).total_citas;
    await ruta.fulfill({ response: respuesta });
  });
  try {
    await page.getByRole('button', { name: '7 días', exact: true }).click();
    await expect.poll(() => anteriores.length).toBe(2);
    await page.getByRole('button', { name: '30 días', exact: true }).click();
    await expect.poll(() => totalVigente !== undefined).toBe(true);
    await expect(tarjeta.locator('.cifra')).toHaveText(String(totalVigente));
    const respuestas = Promise.all(anteriores.map(url => page.waitForResponse(r => r.url() === url && r.status() === 503)));
    await Promise.all(liberar.splice(0).map(salir => salir()));
    await Promise.all((await respuestas).map(r => r.finished()));
    // Ceder dos ciclos de renderizado después de recibir los cuerpos HTTP.
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(tarjeta).toBeVisible();
    await expect(tarjeta.locator('.cifra')).toHaveText(String(totalVigente));
    await expect(page.locator('.aviso-error')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '30 días', exact: true })).toHaveAttribute('aria-pressed', 'true');
  } finally {
    await Promise.all(liberar.splice(0).map(salir => salir()));
  }
});
