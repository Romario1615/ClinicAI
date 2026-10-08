/** Regresión de las pantallas y pestañas incorporadas desde GitHub. */
import type { Locator, Page } from '@playwright/test';
import { pacienteConVersionAnterior } from '../apoyo/datos';
import { expect, test } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';

async function dentroDePantalla(elemento: Locator): Promise<void> {
  await expect(elemento).toBeVisible();
  expect(await elemento.evaluate((nodo) => {
    const caja = nodo.getBoundingClientRect();
    return caja.top >= 0 && caja.bottom <= innerHeight + 1;
  }), 'La acción debe permanecer dentro del alto visible').toBeTruthy();
}

async function sinDesbordamiento(page: Page, escritorio: boolean): Promise<void> {
  await expect.poll(() => page.evaluate(() => ({
    ancho: document.documentElement.scrollWidth <= innerWidth + 1,
    alto: document.documentElement.scrollHeight <= innerHeight + 1,
  }))).toMatchObject(escritorio ? { ancho: true, alto: true } : { ancho: true });
}

test('agenda y pacientes conservan sus acciones al desplazar el contenido en escritorio y caben en móvil', async ({ page }) => {
  test.setTimeout(60_000);
  await acceder(page, 'recepcion');
  for (const dimensiones of [
    { width: 1280, height: 720 },
    { width: 821, height: 600 },
    { width: 390, height: 844 },
    { width: 320, height: 844 },
  ]) {
    await page.setViewportSize(dimensiones);
    // La barra lateral está disponible en escritorio; la navegación directa
    // conserva la sesión en memoria y evita abrir el menú móvil para cada ruta.
    if (dimensiones.width < 821) {
      await page.getByRole('button', { name: 'Alternar navegación', exact: true }).click();
    }
    await irA(page, 'Agenda');
    await expect(page.getByRole('button', { name: 'Nueva cita', exact: true })).toBeVisible();
    for (const vista of ['Día', 'Semana', 'Mes', 'Lista']) {
      await page.getByRole('group', { name: 'Vista de la agenda' }).getByRole('button', { name: vista, exact: true }).click();
      await sinDesbordamiento(page, dimensiones.width >= 821);
    }
    if (dimensiones.width >= 821) {
      await dentroDePantalla(page.getByRole('button', { name: 'Nueva cita', exact: true }));
      await dentroDePantalla(page.getByLabel('Fecha', { exact: true }));
    } else {
      await page.getByRole('button', { name: 'Alternar navegación', exact: true }).click();
    }
    await irA(page, 'Pacientes');
    await expect(page.getByRole('table')).toBeVisible();
    await sinDesbordamiento(page, dimensiones.width >= 821);
    if (dimensiones.width >= 821) {
      const lista = page.locator('app-pacientes .tabla-envoltorio');
      expect(await lista.evaluate((nodo) => nodo.scrollHeight > nodo.clientHeight)).toBeTruthy();
      await lista.evaluate((nodo) => { nodo.scrollTop = nodo.scrollHeight; });
      await dentroDePantalla(page.getByRole('form', { name: 'Buscar pacientes' }));
      await dentroDePantalla(page.getByRole('navigation', { name: 'Paginación de pacientes' }));
      await sinDesbordamiento(page, true);
    }
  }
});

test('las pestañas clínicas cambian con flechas, Inicio y Fin y conservan su panel asociado', async ({ page, request }) => {
  const paciente = await pacienteConVersionAnterior(request);
  await acceder(page, 'profesional');
  await irA(page, 'Historia clínica');
  const buscador = page.getByRole('region', { name: /buscar paciente/i });
  await buscador.getByRole('textbox', { name: /buscar paciente/i }).fill(paciente.numero_documento ?? '');
  await buscador.getByRole('button', { name: /^buscar$/i }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento ?? '' })
    .getByRole('button', { name: /abrir historia/i }).click();
  const odontologia = page.locator('app-selector-especialidad [role="group"] button').filter({ hasText: /odontolog/i });
  if (await odontologia.count()) await odontologia.first().click();

  const evolucion = page.getByRole('tab', { name: 'Evolución', exact: true });
  await evolucion.focus();
  await page.keyboard.press('ArrowRight');
  // La cantidad de borradores puede llegar después de abrir la historia.
  const recetas = page.getByRole('tab', { name: /^Recetas(?: \d+)?$/ });
  await expect(recetas).toBeFocused();
  await expect(recetas).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel', { name: /^Recetas(?: \d+)?$/ })).toBeVisible();
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Planes', exact: true })).toBeFocused();
  await expect(page.getByRole('tabpanel', { name: 'Planes', exact: true })).toBeVisible();
  await page.keyboard.press('Home');
  await expect(evolucion).toBeFocused();
  await expect(evolucion).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel', { name: 'Evolución', exact: true }).locator('.nota').first()).toBeVisible();
});

/**
 * Medición de la regla «pantalla de trabajo» en todas las secciones del menú.
 *
 * En escritorio ninguna sección desplaza la página ni su propio anfitrión:
 * lo que no cabe desplaza dentro de su tarjeta (`.desplazable`). En móvil la
 * página puede desplazar en vertical, pero nunca en horizontal.
 */
async function medirSecciones(page: Page): Promise<string[]> {
  const rutas = await page.locator('nav.navegacion a[href^="/"]').evaluateAll((enlaces) =>
    [...new Set(enlaces.map((enlace) => enlace.getAttribute('href') ?? ''))].filter(Boolean),
  );
  expect(rutas.length).toBeGreaterThan(0);
  const fallos: string[] = [];
  const tamanos = [
    { width: 1366, height: 768, escritorio: true },
    { width: 1024, height: 768, escritorio: true },
    { width: 390, height: 844, escritorio: false },
  ];
  for (const { escritorio, ...dimensiones } of tamanos) {
    await page.setViewportSize(dimensiones);
    for (const ruta of rutas) {
      // Clic programático: en móvil el enlace está dentro del cajón cerrado y
      // el router lo atiende igual sin recargar (la sesión vive en memoria).
      await page.evaluate((href) => document.querySelector<HTMLElement>(`nav.navegacion a[href="${href}"]`)?.click(), ruta);
      await page.waitForURL((url) => url.pathname.startsWith(ruta));
      await page.waitForLoadState('networkidle');
      // La coreografía de entrada desplaza las tarjetas unos píxeles mientras
      // dura; se mide con la pantalla ya quieta.
      await page.evaluate(() => Promise.all(document.getAnimations()
        .filter((animacion) => animacion.effect?.getTiming().iterations !== Infinity)
        .map((animacion) => animacion.finished.catch(() => undefined))));
      const medida = await page.evaluate(() => {
        const raiz = document.scrollingElement!;
        const anfitrion = document.querySelector('router-outlet')?.nextElementSibling as HTMLElement | null;
        return {
          paginaY: raiz.scrollHeight - raiz.clientHeight,
          paginaX: raiz.scrollWidth - raiz.clientWidth,
          anfitrionY: anfitrion ? anfitrion.scrollHeight - anfitrion.clientHeight : 0,
        };
      });
      const etiqueta = `${ruta} a ${dimensiones.width}×${dimensiones.height}`;
      if (medida.paginaX > 1) fallos.push(`${etiqueta}: desborda ${medida.paginaX} px en horizontal`);
      if (escritorio && medida.paginaY > 1) fallos.push(`${etiqueta}: la página desplaza ${medida.paginaY} px`);
      if (escritorio && medida.anfitrionY > 1) fallos.push(`${etiqueta}: la sección desplaza ${medida.anfitrionY} px`);
    }
  }
  return fallos;
}

test('ninguna sección desplaza la página en escritorio ni desborda en móvil', async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1366, height: 768 });
  await acceder(page, 'administradora');
  expect(await medirSecciones(page)).toEqual([]);
});

test('la consola de plataforma cabe en escritorio y no desborda en móvil', async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1366, height: 768 });
  await acceder(page, 'superadministrador');
  expect(await medirSecciones(page)).toEqual([]);
});
