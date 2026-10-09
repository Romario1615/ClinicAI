/** API real para el recorrido; datos agregados sintéticos para extremos visuales. */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';

async function abrir(page: Page): Promise<void> {
  await acceder(page, 'administradora');
  await irA(page, 'Analítica IA');
  await expect(page.locator('.analitica__kpi').first()).toBeVisible();
}

async function medir(page: Page, escritorio: boolean): Promise<void> {
  const medidas = await page.evaluate(() => {
    const principal = document.querySelector('app-analitica')!;
    const hermanos = ['.analitica__hero', '.analitica__filtros', '.analitica__filtros-movil', '.analitica__tabs', '.analitica__resultados']
      .map(selector => document.querySelector(selector)!.getBoundingClientRect()).filter(r => r.height > 0);
    const tarjetas = [...document.querySelectorAll('.analitica__kpi, .analitica__recomendacion')];
    const errores = tarjetas.flatMap((tarjeta, indice) => {
      const rect = tarjeta.getBoundingClientRect();
      const piezas = [...tarjeta.children].map(e => e.getBoundingClientRect());
      return piezas.flatMap((p, i) => [
        ...(p.left < rect.left - 1 || p.right > rect.right + 1 ? [`Tarjeta ${indice}: desborde horizontal`] : []),
        ...(i && p.top < piezas[i - 1].bottom - 1 ? [`Tarjeta ${indice}: objetos solapados`] : []),
      ]);
    });
    return {
      ancho: document.documentElement.scrollWidth - innerWidth,
      alto: document.documentElement.scrollHeight - innerHeight,
      altoHost: principal.scrollHeight - principal.clientHeight,
      separados: hermanos.every((r, i) => !i || r.top >= hermanos[i - 1].bottom + 4),
      lista: document.querySelector('.analitica__contenido')!.clientHeight,
      errores,
    };
  });
  expect(medidas.ancho, 'El documento debe caber en el ancho').toBeLessThanOrEqual(1);
  if (escritorio) {
    expect(medidas.alto, 'Solo la lista debe desplazarse').toBeLessThanOrEqual(1);
    expect(medidas.altoHost).toBeLessThanOrEqual(1);
    expect(medidas.lista, 'La lista conserva espacio utilizable').toBeGreaterThan(90);
  }
  expect(medidas.separados, 'Cabecera, filtros, pestañas y resultados conservan separación').toBe(true);
  expect(medidas.errores).toEqual([]);
}

for (const [nombre, tamanos] of [
  ['escritorio', [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 821, height: 600 }]],
  ['móvil y tableta', [{ width: 768, height: 1024 }, { width: 390, height: 844 }, { width: 320, height: 740 }]],
] as const) {
  test(`analítica: separación de elementos y tres vistas en ${nombre}`, async ({ page }) => {
    test.setTimeout(120_000);
    await abrir(page);
    for (const tamano of tamanos) {
      await page.setViewportSize(tamano);
      for (const etiqueta of ['Descriptivo · qué pasó', 'Predictivo · qué puede pasar', 'Prescriptivo · qué revisar']) {
        await page.getByRole('button', { name: etiqueta, exact: true }).click();
        await medir(page, tamano.width >= 821);
      }
    }
    await page.setViewportSize(nombre === 'escritorio' ? { width: 1440, height: 900 } : { width: 390, height: 844 });
    await page.getByRole('button', { name: 'Descriptivo · qué pasó', exact: true }).click();
    await page.screenshot({ path: `../tmp/qa-20261007/analitica-${nombre === 'escritorio' ? 'compacta' : 'movil'}-20261009.png` });
  });
}

test('analítica: búsqueda, áreas, detalles con teclado y límites accesibles', async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await abrir(page);
  const cantidad = await page.locator('.analitica__kpi').count();
  expect(cantidad).toBeGreaterThan(1);
  await page.getByRole('searchbox', { name: 'Buscar indicador' }).fill('inasistencias');
  expect(await page.locator('.analitica__kpi').count()).toBeLessThan(cantidad);
  await page.getByRole('searchbox', { name: 'Buscar indicador' }).fill('indicador inexistente sintetico');
  await expect(page.getByRole('heading', { name: 'Sin coincidencias' })).toBeVisible();
  await page.getByRole('button', { name: 'Mostrar todos' }).click();
  await expect(page.locator('.analitica__kpi')).toHaveCount(cantidad);
  await page.getByRole('combobox', { name: 'Área de los indicadores' }).selectOption('finanzas');
  const nombres = await page.locator('.analitica__kpi h3').allTextContents();
  expect(nombres.length).toBeGreaterThan(0);
  await expect(page.locator('.analitica__categoria').first()).toContainText('Finanzas');
  await page.getByRole('button', { name: 'Predictivo · qué puede pasar' }).click();
  const boton = page.locator('.analitica__ver-detalle').first();
  const titulo = await page.locator('.analitica__kpi h3').first().innerText();
  await boton.focus();
  await page.keyboard.press('Enter');
  const detalle = page.getByRole('dialog', { name: titulo, exact: true });
  await expect(detalle).toBeVisible();
  await expect(detalle.getByRole('region', { name: 'Evaluación del modelo' })).toBeVisible();
  await expect(detalle.getByRole('table').first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(detalle).not.toBeVisible();
  await expect(boton).toBeFocused();
  await page.getByRole('button', { name: 'Alcance del análisis' }).click();
  const limites = page.getByRole('dialog', { name: 'Alcance y límites del análisis' });
  await expect(limites).toContainText('sin API externa');
  await limites.getByRole('button', { name: 'Volver al análisis' }).click();
  await page.locator('.analitica__contenido').evaluate(n => n.scrollTop = 0);
  await page.screenshot({ path: '../tmp/qa-20261007/analitica-finanzas-predictiva-20261009.png' });
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()).violations).toEqual([]);
});

const evidencia = {
  estado: 'insuficiente', motivo: 'Faltan observaciones sintéticas para evaluar el modelo.',
  algoritmo: null, observaciones: 0, dias_historia: 0, dias_seleccion: 7, dias_evaluacion: 7,
  mae: null, mae_base: null, mejora_porcentaje: null, entrenado_hasta: null,
  evaluacion_desde: null, evaluacion_hasta: null, banda: 'Error empírico, sin probabilidad calibrada.',
};
const extremos = {
  generado_en: '2026-10-09T01:00:00Z', zona_horaria: 'America/Guayaquil',
  desde: '2026-04-01', hasta: '2026-10-08', horizonte: 14,
  kpis: ['citas', 'cobros', 'estado.adherencia.alertas_abiertas', 'estado.conocimiento.en_revision'].map((clave, i) => ({
    clave, nombre: `Indicador sintético de nombre extenso para evaluar legibilidad y separación ${i}`,
    unidad: i === 1 ? 'USD/atención' : 'registros', total: i ? 1234567890123.45 : null,
    agregacion: 'captura actual', definicion: 'Serie agregada sintética sin pacientes. Los días sin observaciones conservan su valor desconocido y no se sustituyen por cero.',
    historia: [{ fecha: '2026-10-08', valor: i ? 0 : null, muestras: i ? 1 : 0 }],
    prediccion: [], evidencia,
  })),
  recomendaciones: [], limites: ['Aprendizaje local, sin API externa.'],
};

test('analítica: cifras extensas, nombres largos, series vacías y ventanas en pantalla pequeña', async ({ page }) => {
  await page.route('**/dashboard/analitica**', route => route.fulfill({ json: extremos }));
  await abrir(page);
  for (const tamano of [{ width: 821, height: 600 }, { width: 390, height: 844 }, { width: 320, height: 740 }]) {
    await page.setViewportSize(tamano);
    await page.getByRole('button', { name: 'Predictivo · qué puede pasar' }).click();
    await medir(page, tamano.width >= 821);
    await page.locator('.analitica__ver-detalle').first().click();
    const ventana = page.getByRole('dialog');
    await expect(ventana).toBeVisible();
    const geometria = await ventana.evaluate(n => {
      const r = n.getBoundingClientRect();
      return { ancho: r.width <= innerWidth + 1, alto: r.height <= innerHeight + 1, desborde: n.scrollWidth - n.clientWidth };
    });
    expect(geometria).toEqual({ ancho: true, alto: true, desborde: 0 });
    await ventana.getByRole('button', { name: 'Cerrar detalle', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Ajustar análisis' }).click();
  const filtros = page.getByRole('dialog', { name: 'Filtros del análisis' });
  await filtros.getByRole('combobox', { name: 'Horizonte' }).selectOption({ label: '7 días' });
  const consulta = page.waitForRequest(r => r.url().includes('/dashboard/analitica') && r.url().includes('horizonte=7'));
  await filtros.getByRole('button', { name: 'Actualizar análisis', exact: true }).click();
  await consulta;
  await expect(filtros).not.toBeVisible();
  await expect(page.locator('.analitica__kpi')).toHaveCount(4);
  await page.screenshot({ path: '../tmp/qa-20261007/analitica-extremos-movil-20261009.png' });
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()).violations).toEqual([]);
});

test('analítica: explica el fallo y actualiza las cifras al reintentar', async ({ page }) => {
  let peticiones = 0;
  await page.route('**/dashboard/analitica**', route => {
    peticiones++;
    return peticiones === 1
      ? route.fulfill({ status: 503, json: { codigo: 'PRUEBA_VISUAL', mensaje: 'Servicio sintético temporalmente no disponible' } })
      : route.fulfill({ json: extremos });
  });
  await acceder(page, 'administradora'); await irA(page, 'Analítica IA');
  await expect(page.getByRole('alert')).toContainText('Servicio sintético temporalmente no disponible');
  await expect(page.locator('.analitica__kpi')).toHaveCount(0);
  await page.getByRole('button', { name: 'Reintentar', exact: true }).click();
  await expect(page.locator('.analitica__kpi')).toHaveCount(4);
  await page.getByRole('button', { name: 'Prescriptivo · qué revisar' }).click();
  await expect(page.getByRole('heading', { name: 'Sin propuestas para revisar' })).toBeVisible();
});
