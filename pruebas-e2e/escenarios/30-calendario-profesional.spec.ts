/** Ventana de calendario propio contra la API real aislada; Google permanece en sandbox. */
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import AxeBuilder from '@axe-core/playwright';

for (const ancho of [1366, 1024, 390]) {
  test(`calendario propio: ventana, validación y error de configuración a ${ancho}px`, async ({ page }) => {
    await page.setViewportSize({ width: ancho, height: ancho === 390 ? 844 : 768 });
    await acceder(page, 'profesional');
    if (ancho < 821) await page.getByRole('button', { name: 'Alternar navegación', exact: true }).click();
    await irA(page, 'Agenda');
    const boton = page.getByRole('button', { name: 'Mi Google Calendar', exact: true });
    await boton.click();
    const ventana = page.getByRole('dialog', { name: 'Mi Google Calendar', exact: true });
    await expect(ventana).toBeVisible();
    await expect(ventana.getByText('No tienes calendarios conectados.')).toBeVisible();
    const calendario = ventana.getByRole('textbox', { name: /^Calendario de Google(?:\s*\*)?$/ });
    await calendario.fill(' ');
    await expect(ventana.getByRole('button', { name: 'Autorizar en Google', exact: true })).toBeDisabled();
    await calendario.fill('primary');
    const respuesta = page.waitForResponse(r => r.url().endsWith('/calendario/oauth/inicio') && r.request().method() === 'POST');
    await ventana.getByRole('button', { name: 'Autorizar en Google', exact: true }).click();
    expect((await respuesta).status()).toBe(503);
    await expect(ventana.getByRole('alert')).toContainText(/sandbox|Integraciones/);
    await expect(calendario).toHaveValue('primary');
    await expect(ventana.getByRole('button', { name: 'Autorizar en Google', exact: true })).toBeEnabled();
    const medidas = await ventana.evaluate(e => {
      const r = e.getBoundingClientRect();
      return { izquierda: r.left, derecha: r.right, arriba: r.top, abajo: r.bottom, ancho: innerWidth, alto: innerHeight };
    });
    expect(medidas.izquierda).toBeGreaterThanOrEqual(0);
    expect(medidas.derecha).toBeLessThanOrEqual(medidas.ancho + 1);
    expect(medidas.arriba).toBeGreaterThanOrEqual(0);
    expect(medidas.abajo).toBeLessThanOrEqual(medidas.alto + 1);
    // Esperar la animación de entrada antes de medir contraste.
    await ventana.evaluate(async e => { await Promise.all(e.getAnimations({ subtree: true }).filter(a => a.effect?.getComputedTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined))); });
    const accesibilidad = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(accesibilidad.violations).toEqual([]);
    await page.screenshot({ path: `../tmp/qa-20261010-calendario/calendario-${ancho}.png` });
    await page.keyboard.press('Escape');
    await expect(ventana).not.toBeVisible();
    await expect(boton).toBeFocused();
  });
}

test('recepción no tiene acceso al calendario profesional', async ({ page }) => {
  await acceder(page, 'recepcion'); await irA(page, 'Agenda');
  await expect(page.getByRole('button', { name: 'Mi Google Calendar', exact: true })).toHaveCount(0);
});
