/** Auditoría automatizada de accesibilidad en pantallas principales. */
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

import { acceder, irA } from '../apoyo/sesion';
import { expect, test } from '../apoyo/prueba';

const ETIQUETAS_WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
const RUTAS_MENU = [
  '/panel', '/analitica', '/plataforma/clinicas', '/usuarios', '/agenda', '/pacientes', '/lista-espera',
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
    // Cuatro auditorías axe y ventanas a varios tamaños dentro de este recorrido.
    test.setTimeout(60_000);
    await acceder(page, 'recepcion');
    await expect(page.getByRole('heading', { name: 'Panel de seguimiento' })).toBeVisible();
    await exigirSinIncidencias(page);

    await page.getByRole('tab', { name: 'Cifras del periodo', exact: true }).click();
    await page.getByRole('button', { name: /Ajustar filtros/ }).click();
    const filtros = page.getByRole('dialog', { name: 'Filtros del dashboard' });
    await expect(filtros).toBeVisible();
    // axe calcula contraste sobre los píxeles actuales: esperar a que termine
    // la entrada evita medir la opacidad intermedia de la animación del vidrio.
    await filtros.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await page.keyboard.press('Escape');
    await expect(filtros).toHaveCount(0);

    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      await page.getByRole('button', { name: /Ajustar filtros/ }).click();
      await expect(filtros).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `La ventana de filtros no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
      await page.keyboard.press('Escape');
      await expect(filtros).toHaveCount(0);
    }
    await page.setViewportSize({ width: 1280, height: 800 });

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
    // Varias ventanas de configuración: cada una conserva su auditoría completa.
    test.setTimeout(60_000);
    await acceder(page, 'administradora');
    await irA(page, 'Configuración');
    await expect(page.getByRole('heading', { name: 'Administración de la clínica' })).toBeVisible();
    await exigirSinIncidencias(page);

    await page.getByRole('button', { name: 'Editar información' }).click();
    const perfil = page.getByRole('dialog', { name: 'Editar información de la clínica' });
    await expect(perfil).toBeVisible();
    const nombreClinica = perfil.getByLabel('Nombre de la clínica');
    const nombreGuardado = await nombreClinica.inputValue();
    await nombreClinica.fill('Cambio sintético sin guardar');
    await perfil.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await page.keyboard.press('Escape');
    await expect(perfil).toHaveCount(0);
    await page.getByRole('button', { name: 'Editar información' }).click();
    await expect(perfil.getByLabel('Nombre de la clínica')).toHaveValue(nombreGuardado);
    await page.keyboard.press('Escape');
    await expect(perfil).toHaveCount(0);

    await page.getByRole('button', { name: 'Integraciones' }).click();
    await expect(page.getByRole('heading', { name: 'Los servicios de tu clínica, en un solo lugar' })).toBeVisible();
    await page.getByRole('button', { name: 'Configurar Anthropic' }).click();
    const anthropic = page.getByRole('dialog', { name: 'Configurar Anthropic' });
    await expect(anthropic).toBeVisible();
    await expect(anthropic.getByLabel('Clave API')).toHaveValue('');
    await anthropic.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await anthropic.getByLabel('Clave API').fill('clave-sintetica-sin-enviar');
    await page.mouse.click(1200, 760);
    await expect(anthropic).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(anthropic).toHaveCount(0);

    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      await page.getByRole('button', { name: 'Configurar Anthropic' }).click();
      await expect(anthropic).toBeVisible();
      await expect(anthropic.getByLabel('Clave API')).toHaveValue('');
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `La ventana de Anthropic no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
      await page.keyboard.press('Escape');
      await expect(anthropic).toHaveCount(0);
    }
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.getByRole('button', { name: 'Agenda y feriados' }).click();
    await expect(page.getByRole('heading', { name: 'Horarios y feriados' })).toBeVisible();
    await page.getByRole('button', { name: 'Nuevo horario' }).click();
    const horario = page.getByRole('dialog', { name: 'Agregar horario' });
    await expect(horario).toBeVisible();
    await horario.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await page.keyboard.press('Escape');
    await expect(horario).toHaveCount(0);

    await page.getByRole('button', { name: 'Nuevo cierre' }).click();
    const cierre = page.getByRole('dialog', { name: 'Agregar cierre' });
    await expect(cierre).toBeVisible();
    await cierre.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await page.keyboard.press('Escape');
    await expect(cierre).toHaveCount(0);

    await page.getByRole('button', { name: 'Disponibilidad del equipo' }).click();
    await page.getByRole('button', { name: 'Nueva franja' }).click();
    const franja = page.getByRole('dialog', { name: 'Nueva franja' });
    await expect(franja).toBeVisible();
    await franja.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await page.keyboard.press('Escape');
    await expect(franja).toHaveCount(0);

    await page.getByRole('button', { name: 'Bloqueos', exact: true }).click();
    await page.getByRole('button', { name: 'Nuevo bloqueo' }).click();
    const bloqueo = page.getByRole('dialog', { name: 'Nuevo bloqueo' });
    await expect(bloqueo).toBeVisible();
    await bloqueo.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    await page.keyboard.press('Escape');
    await expect(bloqueo).toHaveCount(0);

    await irA(page, 'Configuración');
    await page.getByRole('button', { name: 'Anamnesis', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Plantillas de anamnesis' })).toBeVisible();
    await page.getByRole('button', { name: 'Nueva plantilla' }).click();
    const anamnesis = page.getByRole('dialog', { name: 'Crear plantilla de anamnesis' });
    await expect(anamnesis).toBeVisible();
    await anamnesis.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `El diseñador de anamnesis no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.keyboard.press('Escape');
    await expect(anamnesis).toHaveCount(0);

    await irA(page, 'Promociones');
    await page.getByRole('button', { name: 'Nueva campaña' }).click();
    const campana = page.getByRole('dialog', { name: 'Nueva campaña' });
    await expect(campana).toBeVisible();
    await campana.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    await exigirSinIncidencias(page);
    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `El formulario de campaña no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.keyboard.press('Escape');
    await expect(campana).toHaveCount(0);
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
        if (destino === '/delegaciones') {
          const nueva = page.getByRole('button', { name: 'Nueva delegación', exact: true });
          if (await nueva.count()) {
            await nueva.click();
            const delegacion = page.getByRole('dialog', { name: 'Nueva delegación de firma' });
            await expect(delegacion).toBeVisible();
            await delegacion.evaluate((dialog) => Promise.all(
              dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
            ));
            await exigirSinIncidencias(page);
            for (const ancho of [390, 320]) {
              await page.setViewportSize({ width: ancho, height: 844 });
              expect(
                await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
                `El formulario de delegación no debe desbordarse a ${ancho}px`,
              ).toBeTruthy();
            }
            await page.setViewportSize({ width: 1280, height: 800 });
            await page.keyboard.press('Escape');
            await expect(delegacion).toHaveCount(0);
          }
        }
        if (destino === '/equipo') {
          await page.getByRole('button', { name: 'Agregar profesional', exact: true }).click();
          const alta = page.getByRole('dialog', { name: 'Agregar profesional' });
          await expect(alta).toBeVisible();
          await alta.evaluate((dialog) => Promise.all(
            dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
          ));
          await exigirSinIncidencias(page);
          await page.keyboard.press('Escape');
          await expect(alta).toHaveCount(0);
        }
        if (destino === '/catalogo') {
          const nuevaEspecialidad = page.getByRole('button', { name: 'Nueva especialidad', exact: true });
          if (await nuevaEspecialidad.count()) {
            await nuevaEspecialidad.click();
            const especialidad = page.getByRole('dialog', { name: 'Nueva especialidad' });
            await expect(especialidad).toBeVisible();
            await especialidad.evaluate((dialog) => Promise.all(
              dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
            ));
            await exigirSinIncidencias(page);
            await page.keyboard.press('Escape');
            await expect(especialidad).toHaveCount(0);
          }
        }
        if (destino === '/pagos') {
          const abrirAbono = page.getByRole('button', { name: 'Registrar un abono', exact: true });
          if (await abrirAbono.count()) {
            await abrirAbono.click();
            const abono = page.getByRole('dialog', { name: 'Registrar un abono' });
            await expect(abono).toBeVisible();
            await abono.evaluate((dialog) => Promise.all(
              dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
            ));
            await exigirSinIncidencias(page);
            for (const ancho of [390, 320]) {
              await page.setViewportSize({ width: ancho, height: 844 });
              expect(
                await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
                `El formulario de abono no debe desbordarse a ${ancho}px`,
              ).toBeTruthy();
            }
            await page.setViewportSize({ width: 1280, height: 800 });
            await page.keyboard.press('Escape');
            await expect(abono).toHaveCount(0);
          }
        }
      }
    });
  }

  test.afterAll(() => {
    if (rutasAuditadas.size > 0) {
      expect([...rutasAuditadas].sort(), 'La auditoría debe cubrir todas las rutas del menú').toEqual(RUTAS_MENU);
    }
  });
});
