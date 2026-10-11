import { test as base, expect } from '@playwright/test';
import { apiE2e } from './api-e2e';

// Verifica al importar la suite, antes de que cualquier escenario pueda
// sembrar o modificar datos. La omisión de URL_API nunca usa desarrollo.
const apiAislada = apiE2e();

/** Dirige el navegador a la API real elegida para la ejecucion aislada. */
export const test = base.extend({
  page: async ({ page }, use) => {
    const origen = 'http://127.0.0.1:8000/api/v1';
    if (apiAislada !== origen) {
      await page.route(`${origen}/**`, route => route.continue({
        url: route.request().url().replace(origen, apiAislada),
      }));
    }
    await use(page);
  },
});
export { expect };
