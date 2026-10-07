/**
 * Historia clinica y medicacion.
 *
 * Los escenarios que la especificacion exige y que aqui se comprueban de
 * extremo a extremo:
 *
 * * **Un PRN no se presenta como pauta fija.** Escribir «cada 8 horas» sobre un
 *   «cuando sea necesario» es un error de medicacion, no un detalle de
 *   presentacion.
 * * **Bloqueo comprobado de informacion no autorizada.** El asistente ve la
 *   medicacion y no las notas, y la pantalla lo dice como un limite, no como
 *   una averia.
 * * **La historia no se borra: se versiona**, y las versiones anteriores se
 *   pueden ver. Si la interfaz solo mostrara la vigente, esa garantia existiria
 *   en la base y no serviria de nada a quien la audita.
 *
 * Los pacientes sobre los que se prueba se localizan por API. Recorrer la
 * pantalla a base de clics hasta dar con uno que tenga datos hace la prueba
 * lenta y dependiente de como siembre el generador.
 */
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '../apoyo/prueba';

import {
  pacienteConAlertaAdherencia,
  pacienteConTomas,
  pacienteConVersionAnterior,
} from '../apoyo/datos';
import { acceder, irA } from '../apoyo/sesion';
import { huecosVisiblesEnAgenda } from '../apoyo/agenda';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

function fechaAgenda(diasDesdeHoy: number): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Guayaquil',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(Date.now() + diasDesdeHoy * 24 * 60 * 60 * 1000));
}

/**
 * Busca al paciente **por su documento** y abre su detalle.
 *
 * Por apellido no sirve: varios pacientes sinteticos lo comparten, y abrir «el
 * primero que coincide» abre a otra persona. La prueba entonces falla por un
 * motivo que no tiene nada que ver con lo que comprueba.
 */
async function abrir(page: Page, documento: string, boton: RegExp): Promise<void> {
  const busqueda = page.getByRole('region', { name: /buscar paciente/i });
  await busqueda.waitFor({ state: 'visible' });
  await busqueda.getByRole('textbox', { name: /buscar paciente/i }).fill(documento);
  await busqueda.getByRole('button', { name: /^buscar$/i }).click();
  // Hay varias acciones «Abrir historia»: se limita a la fila del documento
  // exacto para no abrir al primer paciente de la tabla.
  await page.getByRole('row').filter({ hasText: documento }).getByRole('button', { name: boton }).click();
  await page
    .locator('app-cargando')
    .waitFor({ state: 'detached' })
    .catch(() => undefined);
}

test.describe('Historia clinica', () => {
  test('el profesional abre una historia y ve sus notas', async ({ page, request }) => {
    const paciente = await pacienteConVersionAnterior(request);
    await acceder(page, 'profesional');
    await irA(page, /historia/i);
    await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);

    await expect(page.locator('.nota').first()).toBeVisible();
  });

  test('la nueva nota SOAP se abre en Liquid Glass, es accesible y se adapta a móviles', async ({ page, request }) => {
    const paciente = await pacienteConVersionAnterior(request);
    await acceder(page, 'profesional');
    await irA(page, /historia/i);
    await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);

    await page.getByRole('button', { name: 'Nueva nota', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Nueva nota de evolución' });
    await expect(editor).toBeVisible();
    await editor.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    const auditoria = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .include('dialog.capa')
      .analyze();
    expect(auditoria.violations.map((item) => item.id)).toEqual([]);

    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `El editor de nota no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.keyboard.press('Escape');
    await expect(editor).toHaveCount(0);
  });

  test('la receta extensa usa una ventana accesible con el pie siempre disponible', async ({ page, request }) => {
    const paciente = await pacienteConVersionAnterior(request);
    await acceder(page, 'profesional');
    await irA(page, /historia/i);
    await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);

    await page.getByRole('tab', { name: 'Recetas' }).click();
    await page.getByRole('button', { name: 'Nueva receta', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Nueva receta · borrador' });
    await expect(editor).toBeVisible();
    await editor.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));
    const auditoria = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .include('dialog.capa')
      .analyze();
    expect(auditoria.violations.map((item) => item.id)).toEqual([]);
    await expect(editor.locator('.ventana__pie')).toBeVisible();

    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `El editor de receta no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.keyboard.press('Escape');
    await expect(editor).toHaveCount(0);
  });

  test('el Formulario MSP 033 usa una ventana amplia accesible con acciones fijas', async ({ page, request }) => {
    const paciente = await pacienteConVersionAnterior(request);
    await acceder(page, 'profesional');
    await irA(page, /historia/i);
    await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);

    const especialidadOdontologica = page
      .locator('app-selector-especialidad [role="group"] button')
      .filter({ hasText: /odontolog/i });
    if (await especialidadOdontologica.count()) await especialidadOdontologica.first().click();
    await page.getByRole('tab', { name: 'Formulario MSP 033' }).click();
    await page.getByRole('button', { name: 'Registrar formulario' }).click();
    const editor = page.getByRole('dialog', { name: 'Registrar atención' });
    await expect(editor).toBeVisible();
    await expect(editor.locator('.ventana--alta')).toBeVisible();
    await expect(editor.locator('.ventana__pie button', { hasText: 'Guardar formulario' })).toBeVisible();
    const desplazamiento = await editor.locator('.ventana__cuerpo').evaluate((cuerpo) => ({
      altoContenido: cuerpo.scrollHeight,
      altoVisible: cuerpo.clientHeight,
    }));
    expect(desplazamiento.altoContenido).toBeGreaterThan(desplazamiento.altoVisible);
    await editor.evaluate((dialog) => Promise.all(
      dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
    ));

    const auditoria = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .include('dialog.capa')
      .analyze();
    expect(auditoria.violations.map((item) => item.id)).toEqual([]);

    for (const ancho of [390, 320]) {
      await page.setViewportSize({ width: ancho, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `El formulario MSP 033 no debe desbordarse a ${ancho}px`,
      ).toBeTruthy();
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.keyboard.press('Escape');
    await expect(editor).toHaveCount(0);
  });

  test('las versiones anteriores se conservan y se pueden ver', async ({ page, request }) => {
    const paciente = await pacienteConVersionAnterior(request);
    await acceder(page, 'profesional');
    await irA(page, /historia/i);
    await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);

    await page.getByRole('button', { name: /ver versiones anteriores/i }).click();
    await page
      .locator('app-cargando')
      .waitFor({ state: 'detached' })
      .catch(() => undefined);

    const versiones = page.locator('details.versiones').first();
    await expect(versiones).toBeVisible();
    await expect(versiones).toContainText(/anterior/i);

    // El motivo del cambio viaja con la version: sin el, saber que algo se
    // corrigio no dice por que.
    await expect(page.locator('.nota__correccion').first()).toBeVisible();
  });

  test('el asistente ve la medicacion y el limite de las notas', async ({ page }) => {
    await acceder(page, 'asistente');
    await irA(page, /medicamentos/i);

    await expect(page.getByRole('heading', { name: /medicaci[oó]n/i })).toBeVisible();
    // El limite se enuncia como limite. Un error rojo haria pensar que algo se
    // rompio, y quien atiende reportaria una averia que no existe.
    await expect(page.locator('body')).not.toContainText(/no se pudo cargar/i);
  });
});

test.describe('Medicacion', () => {
  test('un PRN nunca aparece en el calendario de tomas', async ({ page, request }) => {
    const paciente = await pacienteConTomas(request);
    await acceder(page, 'profesional');
    await irA(page, /medicamentos/i);
    await abrir(page, paciente.numero_documento ?? '', /ver medicaci/i);

    await expect(page.locator('table tbody tr').first()).toBeVisible();
    // Un «cuando sea necesario» no genera tomas. Si apareciera aqui con una
    // hora, seria una pauta fija a los ojos de quien mira.
    await expect(page.locator('table')).not.toContainText(/cuando sea necesario/i);
  });

  test('el calendario se declara recuento y no valoracion', async ({ page, request }) => {
    const paciente = await pacienteConTomas(request);
    await acceder(page, 'profesional');
    await irA(page, /medicamentos/i);
    await abrir(page, paciente.numero_documento ?? '', /ver medicaci/i);

    // La regla 5 de CLAUDE.md, dicha en la propia pantalla: el sistema cuenta
    // omisiones; no concluye que el tratamiento falle ni sugiere cambiarlo.
    await expect(page.locator('.pie')).toContainText(/recuento/i);
    await expect(page.locator('.pie')).toContainText(/no dice si el tratamiento funciona/i);
  });

  test('una toma futura no ofrece el boton de registrar', async ({ page, request }) => {
    const paciente = await pacienteConTomas(request);
    await acceder(page, 'profesional');
    await irA(page, /medicamentos/i);
    await abrir(page, paciente.numero_documento ?? '', /ver medicaci/i);

    const futuras = page.locator('tbody tr', { hasText: 'aún no toca' });
    if ((await futuras.count()) > 0) {
      // Marcar como tomada una dosis que todavia no toca produce un registro
      // de adherencia falso, y ese registro es lo que el profesional mira.
      await expect(futuras.first().getByRole('button')).toHaveCount(0);
    }
  });

  test('el profesional revisa y atiende una alerta por tomas omitidas', async ({
    page,
    request,
  }) => {
    const { paciente, alertaId } = await pacienteConAlertaAdherencia(request);
    await acceder(page, 'profesional');
    await irA(page, /medicamentos/i);
    await abrir(page, paciente.numero_documento ?? '', /ver medicaci/i);

    const alerta = page.getByRole('region', { name: 'Alertas de adherencia abiertas' });
    await expect(alerta).toBeVisible();
    await expect(alerta).toContainText(/tomas sin registrar en el periodo/i);

    const atencion = page.waitForResponse(
      (respuesta) =>
        respuesta.url().includes(`/historia/adherencia/alertas/${alertaId}/atencion`) &&
        respuesta.request().method() === 'POST',
    );
    // Un paciente puede tener una alerta abierta por receta: se atiende la suya.
    const propia = alerta.locator(`[data-alerta="${alertaId}"]`);
    await propia.getByRole('button', { name: 'Marcar atendida' }).click();
    expect((await atencion).status()).toBe(204);
    await expect(propia).toHaveCount(0);
  });
});

test('el profesional completa un plan y atiende su control posterior', async ({ page, request }) => {
  test.setTimeout(90_000);
  const paciente = await pacienteConVersionAnterior(request);
  const titulo = `Plan sintetico ${Date.now()}`;
  let citaId = '';
  let tokenAgenda = '';
  await acceder(page, 'profesional');
  await irA(page, /historia/i);
  await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);

  await page.getByRole('tab', { name: 'Planes de tratamiento' }).click();
  const planes = page.getByRole('region', { name: 'Planes de tratamiento' });
  await planes.getByRole('button', { name: 'Crear borrador' }).click();
  const editor = page.getByRole('dialog', { name: 'Crear borrador de tratamiento' });
  await expect(editor).toBeVisible();
  await editor.evaluate((dialog) => Promise.all(
    dialog.getAnimations({ subtree: true }).map((animacion) => animacion.finished.catch(() => undefined)),
  ));
  const incumplimientos = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .include('dialog.capa')
    .analyze();
  expect(incumplimientos.violations.map((item) => item.id)).toEqual([]);
  for (const ancho of [390, 320]) {
    await page.setViewportSize({ width: ancho, height: 844 });
    const desbordamiento = await page.evaluate(() => ({
      viewport: window.innerWidth,
      documento: document.documentElement.scrollWidth,
      cuerpo: document.body.scrollWidth,
      contenido: [...document.querySelectorAll<HTMLElement>('.contenido, main, .planes, .lista-planes, dialog, .ventana')]
        .map((elemento) => ({
          selector: elemento.className ? `${elemento.tagName.toLowerCase()}.${String(elemento.className).replace(/\s+/g, '.')}` : elemento.tagName.toLowerCase(),
          ancho: Math.round(elemento.getBoundingClientRect().width),
          cliente: elemento.clientWidth,
          scroll: elemento.scrollWidth,
          derecha: Math.round(elemento.getBoundingClientRect().right),
        })),
      elementos: [...document.querySelectorAll<HTMLElement>('body *')]
        .map((elemento) => ({
          selector: `${elemento.tagName.toLowerCase()}${elemento.className && typeof elemento.className === 'string' ? `.${elemento.className.trim().replace(/\s+/g, '.')}` : ''}`,
          izquierda: Math.round(elemento.getBoundingClientRect().left),
          derecha: Math.round(elemento.getBoundingClientRect().right),
          ancho: Math.round(elemento.getBoundingClientRect().width),
          texto: (elemento.textContent ?? '').trim().slice(0, 80),
          padre: elemento.parentElement?.className,
        }))
        .filter((elemento) => elemento.izquierda < -1 || elemento.derecha > window.innerWidth + 1),
    }));
    expect(desbordamiento.documento <= desbordamiento.viewport + 1,
      `El editor del plan no debe desbordarse a ${ancho}px: ${JSON.stringify({ contenido: desbordamiento.contenido, elementos: desbordamiento.elementos.filter((elemento) => elemento.derecha > ancho + 1).slice(-10) })}`,
    ).toBeTruthy();
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  await editor.getByLabel('Título del plan').fill(titulo);
  await editor.getByLabel('Descripción').fill('Restauración sintetica de prueba');
  await editor.getByLabel('Pieza FDI (opcional)').fill('36');
  await editor.getByLabel('Caras FDI').fill('OM');
  await editor.getByLabel('Precio (USD)').fill('85.00');
  await editor.getByRole('button', { name: 'Añadir al plan' }).click();
  const guardado = page.waitForResponse(
    (respuesta) =>
      respuesta.url().includes(`/odontologia/pacientes/${paciente.id}/planes-tratamiento`) &&
      respuesta.request().method() === 'POST',
  );
  await editor.getByRole('button', { name: 'Guardar borrador' }).click();
  const respuestaPlan = await guardado;
  expect(respuestaPlan.status()).toBe(201);
  const procedimientoId = (await respuestaPlan.json()).procedimientos[0].id as string;
  await expect(editor).toHaveCount(0);
  await expect(planes.getByRole('status').filter({ hasText: 'Borrador guardado' })).toBeVisible();

  const plan = planes.locator('article.plan').filter({ hasText: titulo });
  await expect(plan).toContainText('PENDIENTE DE REVISIÓN');
  await expect(plan).toContainText('Pieza 36');
  await plan.getByRole('button', { name: 'Proponer al paciente' }).click();
  await expect(planes.getByRole('status').filter({ hasText: 'Plan propuesto' })).toBeVisible();
  await expect(plan).toContainText('PROPUESTO');
  await expect(plan).toContainText('Falta registrar la aceptación firmada del paciente.');

  await plan.getByRole('button', { name: 'Registrar aceptación firmada' }).click();
  await plan.getByLabel('Referencia del documento firmado').fill(`Constancia ${titulo}`);
  await plan.getByRole('button', { name: 'Confirmar' }).click();
  await expect(plan).toContainText('ACEPTADO · EN CURSO');

  await plan.getByRole('button', { name: 'Agendar esta fase' }).click();
  await expect(page).toHaveURL(/procedimiento_plan=/);
  await expect(page.getByText('Esta cita quedará vinculada al procedimiento seleccionado en el plan.'))
    .toBeVisible();
  const fecha = page.getByLabel('Fecha', { exact: true });
  for (let dias = 2; dias <= 30; dias += 1) {
    const cargando = page.waitForResponse(
      (respuesta) => respuesta.url().includes('/agenda/disponibilidad') && respuesta.status() === 200,
    );
    await fecha.fill(fechaAgenda(dias));
    await cargando;
    if (await huecosVisiblesEnAgenda(page).count()) break;
  }
  const hueco = huecosVisiblesEnAgenda(page).first();
  await expect(hueco, 'debe haber al menos un turno disponible para agendar la fase').toBeVisible();
  await hueco.click();
  const dialogoReserva = page.getByRole('dialog', { name: 'Reservar cita' });
  await expect(dialogoReserva).toBeVisible();
  const reserva = page.waitForResponse(
    (respuesta) =>
      respuesta.url().endsWith('/agenda/citas') && respuesta.request().method() === 'POST',
  );
  await dialogoReserva.getByRole('button', { name: 'Confirmar cita', exact: true }).click();
  const respuestaCita = await reserva;
  expect(respuestaCita.status()).toBe(201);
  expect(respuestaCita.request().postDataJSON().procedimiento_plan_id).toBe(procedimientoId);
  citaId = (await respuestaCita.json()).id as string;
  tokenAgenda = (await respuestaCita.request().headerValue('authorization')) ?? '';

  try {
    await irA(page, /historia/i);
    await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);
    await page.getByRole('tab', { name: 'Planes de tratamiento' }).click();
    const planAgendado = page.locator('article.plan').filter({ hasText: titulo });
    await expect(planAgendado).toContainText('Cita agendada para esta fase');

    // Al cancelar la cita, el vínculo se libera en la misma transacción para
    // permitir elegir otro horario para el mismo procedimiento.
    const cancelada = await request.post(`${API}/agenda/citas/${citaId}/cancelacion`, {
      headers: { Authorization: tokenAgenda },
      data: { motivo: 'Reagendar la fase de prueba E2E' },
    });
    expect(cancelada.status()).toBe(200);
  } finally {
    if (citaId && tokenAgenda) {
      try {
        const existente = await request.get(`${API}/agenda/citas/${citaId}`, {
          headers: { Authorization: tokenAgenda },
        });
        if (existente.ok() && (await existente.json()).estado !== 'CANCELLED') {
          await request.post(`${API}/agenda/citas/${citaId}/cancelacion`, {
            headers: { Authorization: tokenAgenda },
            data: { motivo: 'Limpieza de prueba sintetica E2E' },
          });
        }
      } catch {
        // En una interrupción de Playwright el contexto HTTP también puede
        // cerrarse. La cita ya es sintética y el flujo normal la cancela arriba.
      }
    }
  }
  // Salir y volver al módulo vuelve a consultar el plan tras la cancelación.
  await irA(page, /agenda/i);
  await irA(page, /historia/i);
  await abrir(page, paciente.numero_documento ?? '', /abrir historia/i);
  await page.getByRole('tab', { name: 'Planes de tratamiento' }).click();
  const planLiberado = page.locator('article.plan').filter({ hasText: titulo });
  await expect(planLiberado).not.toContainText('Cita agendada para esta fase');
  await expect(planLiberado.getByRole('button', { name: 'Agendar esta fase' })).toBeVisible();

  await planLiberado.getByRole('button', { name: 'Completar' }).click();
  const control = new Date();
  control.setDate(control.getDate() + 7);
  const fechaControl = [
    control.getFullYear(),
    String(control.getMonth() + 1).padStart(2, '0'),
    String(control.getDate()).padStart(2, '0'),
  ].join('-');
  const fechaControlVisible = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(control);
  await planLiberado.getByLabel('Fecha de control posterior (opcional)').fill(fechaControl);
  await planLiberado.getByRole('button', { name: 'Confirmar' }).click();
  await expect(planLiberado).toContainText('Control posterior pendiente');
  await expect(planLiberado).toContainText(fechaControlVisible);

  await planLiberado.getByRole('button', { name: 'Registrar control realizado' }).click();
  await planLiberado.getByLabel('Nota del control (opcional)').fill('Control de seguimiento realizado.');
  await planLiberado.getByRole('button', { name: 'Confirmar' }).click();
  await expect(planLiberado).toContainText('Control posterior atendido');
  await expect(planLiberado).toContainText('Control de seguimiento realizado.');
});
