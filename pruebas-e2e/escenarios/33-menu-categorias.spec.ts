/** Categorías del menú con permisos reales, teclado y cajón móvil. */
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '../apoyo/prueba';
import { acceder, irA, type Rol } from '../apoyo/sesion';

const ROLES: readonly Rol[] = ['recepcion', 'asistente', 'profesional', 'administradora', 'auditor', 'superadministrador'];

for (const rol of ROLES) {
  test(`las categorías de ${rol} conservan todas sus secciones sin duplicados ni grupos vacíos`, async ({ page }) => {
    await acceder(page, rol);
    const nav = page.locator('#navegacion-principal');
    const destinos = await nav.locator('a').evaluateAll(enlaces => enlaces.map(enlace => enlace.getAttribute('href')));
    expect(new Set(destinos).size).toBe(destinos.length);
    expect(destinos).toContain('/ayuda');
    if (rol !== 'superadministrador') expect(destinos).not.toContain('/plataforma/clinicas');
    if (['recepcion', 'asistente', 'profesional'].includes(rol)) expect(destinos).not.toContain('/usuarios');
    await expect(nav.locator('.navegacion__desplegar[aria-expanded="true"]')).toHaveCount(1);
    expect(await nav.getByRole('link').count()).toBeLessThan(destinos.length);

    const visitados = new Set(['/ayuda']);
    for (const grupo of await nav.locator('.navegacion__categoria').all()) {
      const boton = grupo.locator('.navegacion__desplegar');
      const enlacesDelGrupo = grupo.locator('a');
      expect(await enlacesDelGrupo.count()).toBeGreaterThan(0);
      if (await boton.getAttribute('aria-expanded') === 'false') await boton.click();
      await expect(nav.locator('.navegacion__desplegar[aria-expanded="true"]')).toHaveCount(1);
      const enlaces = grupo.getByRole('link');
      await expect(enlaces).not.toHaveCount(0);
      for (const enlace of await enlaces.all()) {
        await expect(enlace).toBeVisible();
        visitados.add((await enlace.getAttribute('href'))!);
      }
      await boton.click();
      await expect(grupo.getByRole('link')).toHaveCount(0);
      await expect(nav.getByRole('link', { name: 'Ayuda', exact: true })).toBeVisible();
    }
    expect([...visitados].sort()).toEqual(destinos.sort());
  });
}

test('teclado y Atrás revelan la sección actual y conservan el foco visible', async ({ page }) => {
  await acceder(page, 'administradora');
  const nav = page.locator('#navegacion-principal');
  const clinica = nav.locator('#categoria-clinica');
  await clinica.focus();
  if (await clinica.getAttribute('aria-expanded') !== 'false') await page.keyboard.press('Space');
  await expect(clinica).toHaveAttribute('aria-expanded', 'false');
  await expect(clinica).toBeFocused();
  await page.keyboard.press('Space');
  await expect(clinica).toHaveAttribute('aria-expanded', 'true');
  await expect(clinica).toBeFocused();
  await page.keyboard.press('Tab');
  const agenda = nav.getByRole('link', { name: 'Agenda', exact: true });
  await expect(agenda).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/agenda$/);
  await expect(agenda).toHaveAttribute('aria-current', 'page');
  await irA(page, 'Pagos');
  await expect(page).toHaveURL(/\/pagos$/);
  await expect(nav.locator('#categoria-finanzas')).toHaveAttribute('aria-expanded', 'true');
  await page.goBack();
  await expect(page).toHaveURL(/\/agenda$/);
  await expect(clinica).toHaveAttribute('aria-expanded', 'true');
  await expect(clinica).toBeFocused();
  await expect(nav.locator('#categoria-finanzas')).toHaveAttribute('aria-expanded', 'false');
  await expect(agenda).toHaveAttribute('aria-current', 'page');
});

test('la redirección de ingreso abre la categoría de un destino con parámetros', async ({ page }) => {
  await page.goto('/pagos?origen=navegacion-sintetica');
  await expect(page).toHaveURL(/\/acceso\?destino=/);
  await page.getByRole('button', { name: /administración de clínica/i }).click();
  await expect(page).toHaveURL(/\/pagos\?origen=navegacion-sintetica$/);
  await expect(page.locator('#categoria-finanzas')).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('#secciones-finanzas').getByRole('link', { name: 'Pagos', exact: true })).toHaveAttribute('aria-current', 'page');
});

test('el menú respeta el espacio disponible, el teclado y el contraste en escritorio y móvil', async ({ page }) => {
  test.setTimeout(120_000);
  await acceder(page, 'administradora');
  const nav = page.locator('#navegacion-principal');
  const menu = page.getByRole('button', { name: 'Alternar navegación' });
  for (const dimensiones of [
    { width: 1366, height: 768 }, { width: 1024, height: 768 },
    { width: 821, height: 600 }, { width: 390, height: 844 }, { width: 320, height: 568 },
  ]) {
    await page.setViewportSize(dimensiones);
    if (dimensiones.width <= 820) await menu.click();
    await expect(nav).toBeVisible();
    if (dimensiones.width === 1366) {
      await nav.screenshot({ path: test.info().outputPath('menu-categorias.png') });
    }
    for (const boton of await nav.locator('.navegacion__desplegar').all()) {
      if (await boton.getAttribute('aria-expanded') === 'false') await boton.click();
      await boton.scrollIntoViewIfNeeded();
      const geometria = await nav.evaluate(elemento => {
        const caja = elemento.getBoundingClientRect();
        const listas = elemento.querySelector('.navegacion__categorias')!;
        return {
          dentro: caja.left >= 0 && caja.top >= 0 && caja.right <= innerWidth + 1 && caja.bottom <= innerHeight + 1,
          sinDesborde: listas.scrollWidth <= listas.clientWidth + 1,
          paginaX: document.documentElement.scrollWidth <= innerWidth + 1,
        };
      });
      expect(geometria, JSON.stringify(dimensiones)).toEqual({ dentro: true, sinDesborde: true, paginaX: true });
    }
    await nav.evaluate(elemento => Promise.all(elemento.getAnimations({ subtree: true })
      .filter(animacion => animacion.effect?.getTiming().iterations !== Infinity)
      .map(animacion => animacion.finished.catch(() => undefined))));
    const resultado = await new AxeBuilder({ page }).include('#navegacion-principal')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(resultado.violations).toEqual([]);
    if (dimensiones.width <= 820) {
      await nav.locator('#categoria-ia').focus();
      await page.keyboard.press('Escape');
      await expect(nav).toBeHidden();
      await expect(menu).toBeFocused();
      await expect(page.locator('main#contenido')).not.toHaveAttribute('inert');
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await irA(page, 'Asistente');
  await expect(page).toHaveURL(/\/asistente$/);
  await expect(nav).toBeHidden();
  await menu.click();
  await expect(nav.locator('#categoria-ia')).toHaveAttribute('aria-expanded', 'true');
  await irA(page, 'Ayuda');
  await expect(page).toHaveURL(/\/ayuda$/);
  await expect(nav).toBeHidden();
});
