/** Auditoría automatizada de accesibilidad en pantallas principales. */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { acceder, irA } from '../apoyo/sesion';
import { expect, test } from '../apoyo/prueba';

const ETIQUETAS_WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const RUTAS_MENU = [
  '/panel', '/plataforma/clinicas', '/usuarios', '/agenda', '/pacientes', '/lista-espera',
  '/historia-clinica', '/medicamentos', '/conocimiento', '/delegaciones', '/equipo',
  '/promociones', '/catalogo', '/pagos', '/gastos', '/conversaciones', '/agente-demo', '/seguridad',
  '/asistente', '/automatizaciones', '/configuracion', '/ayuda',
].sort();
const rutasAuditadas = new Set<string>();

async function exigirSinIncidencias(page: Page): Promise<void> {
  // Las entradas con Motion duran menos de un segundo: se audita la pantalla
  // asentada, no un fotograma a media opacidad. Los bucles infinitos de los
  // gráficos decorativos no cuentan.
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every((animacion) => animacion.effect?.getTiming().iterations === Infinity || animacion.playState !== 'running'),
  );
  const resultado = await new AxeBuilder({ page })
    .withTags(ETIQUETAS_WCAG)
    .analyze();

  const incidencias = resultado.violations.map((incidencia) => ({
    regla: incidencia.id,
    impacto: incidencia.impact,
    ayuda: incidencia.help,
    elementos: incidencia.nodes.map((nodo) => ({
      selector: nodo.target,
      resumen: nodo.failureSummary,
    })),
  }));

  expect(incidencias, `${page.url()}\n${JSON.stringify(incidencias, null, 2)}`).toEqual([]);
}

test.describe('Accesibilidad WCAG 2.2 AA', () => {
  test('pantalla de acceso', async ({ page }) => {
    await page.goto('/acceso');
    await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
    await exigirSinIncidencias(page);
  });

  test('panel de seguimiento y agenda para recepción', async ({ page }) => {
    await acceder(page, 'recepcion');
    await expect(page.getByRole('heading', { name: 'Panel de seguimiento' })).toBeVisible();
    await exigirSinIncidencias(page);

    await irA(page, /^Agenda/);
    await expect(page.getByRole('heading').first()).toBeVisible();
    await exigirSinIncidencias(page);
  });

  test('historia clínica para profesional', async ({ page }) => {
    await acceder(page, 'profesional');
    await irA(page, 'Historia clínica');
    await expect(page.getByRole('heading', { name: 'Historia clínica' })).toBeVisible();
    await exigirSinIncidencias(page);
  });

  test('administración de clínica', async ({ page }) => {
    await acceder(page, 'administradora');
    await irA(page, 'Configuración');
    await expect(page.getByRole('heading', { name: 'Administración de la clínica' })).toBeVisible();
    await exigirSinIncidencias(page);
  });

  for (const rol of [
    'recepcion',
    'asistente',
    'profesional',
    'administradora',
    'auditor',
    'superadministrador',
  ] as const) {
    test(`todas las secciones visibles para ${rol}`, async ({ page }) => {
      // Administración recorre más de veinte pantallas y cada una se audita ya
      // asentada (tras sus animaciones de entrada): 30 s no alcanzan.
      test.setTimeout(120_000);
      await acceder(page, rol);
      const enlaces = page.getByRole('navigation', { name: 'Secciones' }).getByRole('link');

      for (const enlace of await enlaces.all()) {
        const destino = await enlace.getAttribute('href');
        expect(destino, 'Cada sección visible debe tener una ruta').toBeTruthy();
        rutasAuditadas.add(destino!);
        await enlace.click();
        await expect(page).toHaveURL(new RegExp(`${destino?.replaceAll('/', '\\/')}$`));
        await expect(page.locator('main h1').first()).toBeVisible();
        await exigirSinIncidencias(page);
      }
    });
  }

  test.afterAll(() => {
    expect([...rutasAuditadas].sort(), 'La auditoría debe cubrir todas las rutas del menú').toEqual(RUTAS_MENU);
  });
});
