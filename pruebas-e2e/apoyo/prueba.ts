import { test as base, expect } from '@playwright/test';

/** Dirige el navegador a la API real elegida para la ejecucion aislada. */
export const test = base.extend({
  page: async ({ page }, use) => {
    const api = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
    const origen = 'http://127.0.0.1:8000/api/v1';
    if (api !== origen) {
      await page.route(`${origen}/**`, route => route.continue({
        url: route.request().url().replace(origen, api),
      }));
    }
    await use(page);
  },
});
export { expect };
