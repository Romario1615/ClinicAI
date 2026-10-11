/** Búsqueda local de módulos autorizados y navegación con teclado. */
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '../apoyo/prueba';
import { acceder, irA, type Rol } from '../apoyo/sesion';

const ROLES: readonly Rol[] = ['recepcion', 'asistente', 'profesional', 'administradora', 'auditor', 'superadministrador'];

for (const rol of ROLES) {
  test(`el buscador de ${rol} ofrece exactamente las secciones de su menú`, async ({ page }) => {
    await acceder(page, rol);
    const destinos = await page.locator('#navegacion-principal a').evaluateAll(enlaces =>
      enlaces.map(enlace => enlace.getAttribute('href')));
    await page.getByRole('button', { name: 'Buscar sección', exact: true }).click();
    const ventana = page.getByRole('dialog', { name: 'Buscar sección', exact: true });
    const consulta = ventana.getByRole('searchbox', { name: 'Nombre de la sección o categoría' });
    await expect(consulta).toBeFocused();
    const resultados = await ventana.locator('a').evaluateAll(enlaces => enlaces.map(enlace => enlace.getAttribute('href')));
    expect(resultados.sort()).toEqual(destinos.sort());
    expect(new Set(resultados).size).toBe(resultados.length);
    await consulta.fill('usuarios');
    const autorizado = destinos.includes('/usuarios');
    await expect(ventana.getByRole('link', { name: 'Usuarios y roles', exact: true })).toHaveCount(autorizado ? 1 : 0);
    await consulta.fill('clinicas');
    await expect(ventana.getByRole('link', { name: 'Clínicas', exact: true })).toHaveCount(rol === 'superadministrador' ? 1 : 0);
    await consulta.fill('ayuda');
    await expect(ventana.getByRole('link', { name: 'Ayuda', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(ventana).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Buscar sección', exact: true })).toBeFocused();
  });
}

test('buscar por nombre y categoría funciona con teclado y permite elegir la sección actual', async ({ page }) => {
  await acceder(page, 'administradora');
  const abrir = page.getByRole('button', { name: 'Buscar sección', exact: true });
  await abrir.focus();
  await page.keyboard.press('Enter');
  const ventana = page.getByRole('dialog', { name: 'Buscar sección', exact: true });
  const consulta = ventana.getByRole('searchbox');
  await expect(consulta).toBeFocused();
  await consulta.fill('  IA ANALITICA ');
  await expect(ventana.getByRole('link')).toHaveCount(1);
  await expect(ventana.getByRole('status')).toHaveText('1 sección disponible');
  await page.keyboard.press('Tab');
  await expect(ventana.getByRole('link', { name: 'Analítica IA', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/analitica$/);
  await expect(ventana).toHaveCount(0);
  await expect(page.locator('main#contenido')).toBeFocused();
  await abrir.click();
  await expect(consulta).toHaveValue('');
  await consulta.fill('resumen analitica');
  await ventana.getByRole('link', { name: 'Analítica IA', exact: true }).click();
  await expect(ventana).toHaveCount(0);
  await expect(page.locator('main#contenido')).toBeFocused();
  await abrir.click();
  await consulta.fill('sin coincidencia sintética');
  await expect(ventana.getByRole('status')).toHaveText('0 secciones disponibles');
  await expect(ventana.getByRole('link')).toHaveCount(0);
  await expect(ventana).toContainText('No se encontraron secciones');
  await consulta.fill('finanzas');
  await expect(ventana.getByRole('link', { name: 'Pagos', exact: true })).toBeVisible();
  await expect(ventana.getByRole('link', { name: 'Gastos y caja', exact: true })).toBeVisible();
});

test('búsqueda y cajón conservan espacio, contraste y foco en cinco tamaños', async ({ page }) => {
  test.setTimeout(120_000);
  await acceder(page, 'superadministrador');
  const menu = page.getByRole('button', { name: 'Alternar navegación' });
  const nav = page.locator('#navegacion-principal');
  const abrir = page.getByRole('button', { name: 'Buscar sección', exact: true });
  const ventana = page.getByRole('dialog', { name: 'Buscar sección', exact: true });
  for (const dimensiones of [
    { width: 1366, height: 768 }, { width: 1024, height: 768 },
    { width: 821, height: 600 }, { width: 390, height: 844 }, { width: 320, height: 568 },
  ]) {
    await page.setViewportSize(dimensiones);
    if (dimensiones.width <= 820) {
      await menu.click();
      await expect(abrir).toBeFocused();
    }
    await abrir.click();
    await expect(ventana.getByRole('searchbox')).toBeFocused();
    const geometria = await ventana.locator('.ventana').evaluate(elemento => {
      const caja = elemento.getBoundingClientRect();
      return {
        dentro: caja.left >= 0 && caja.top >= 0 && caja.right <= innerWidth + 1 && caja.bottom <= innerHeight + 1,
        sinDesborde: elemento.scrollWidth <= elemento.clientWidth + 1,
        paginaX: document.documentElement.scrollWidth <= innerWidth + 1,
      };
    });
    expect(geometria, JSON.stringify(dimensiones)).toEqual({ dentro: true, sinDesborde: true, paginaX: true });
    await ventana.evaluate(elemento => Promise.all(elemento.getAnimations({ subtree: true })
      .filter(animacion => animacion.effect?.getTiming().iterations !== Infinity)
      .map(animacion => animacion.finished.catch(() => undefined))));
    const resultado = await new AxeBuilder({ page }).include('dialog[open]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(resultado.violations).toEqual([]);
    if (dimensiones.width === 1366) await ventana.locator('.ventana').screenshot({ path: test.info().outputPath('buscador-secciones.png') });
    await page.keyboard.press('Escape');
    await expect(ventana).toHaveCount(0);
    await expect(abrir).toBeFocused();
    await expect(nav).toBeVisible();
    if (dimensiones.width <= 820) {
      await page.keyboard.press('Escape');
      await expect(nav).toBeHidden();
      await expect(menu).toBeFocused();
    }
  }
  await menu.click();
  await abrir.click();
  await ventana.getByRole('searchbox').fill('comunicacion asistente');
  await ventana.getByRole('link', { name: 'Asistente', exact: true }).click();
  await expect(page).toHaveURL(/\/asistente$/);
  await expect(nav).toBeHidden();
  await expect(page.locator('main#contenido')).toBeFocused();
  await expect(page.locator('main#contenido')).not.toHaveAttribute('inert');
});

test('los enlaces del cajón móvil enfocan el contenido incluso al repetir el destino', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await acceder(page, 'administradora');
  const nav = page.locator('#navegacion-principal');
  const menu = page.getByRole('button', { name: 'Alternar navegación' });
  for (let repeticion = 0; repeticion < 2; repeticion++) {
    await irA(page, 'Agenda');
    await expect(page).toHaveURL(/\/agenda$/);
    await expect(nav).toBeHidden();
    await expect(page.locator('main#contenido')).toBeFocused();
    await expect(page.locator('main#contenido')).not.toHaveAttribute('inert');
  }
  await menu.click();
  await expect(page.getByRole('button', { name: 'Buscar sección', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
});
