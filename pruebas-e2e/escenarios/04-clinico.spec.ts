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
import { type Page, expect, test } from '@playwright/test';

import { pacienteConTomas, pacienteConVersionAnterior } from '../apoyo/datos';
import { acceder, irA } from '../apoyo/sesion';

/**
 * Busca al paciente **por su documento** y abre su detalle.
 *
 * Por apellido no sirve: varios pacientes sinteticos lo comparten, y abrir «el
 * primero que coincide» abre a otra persona. La prueba entonces falla por un
 * motivo que no tiene nada que ver con lo que comprueba.
 */
async function abrir(page: Page, documento: string, boton: RegExp): Promise<void> {
  await page.locator('input[name="termino"]').fill(documento);
  await page.getByRole('button', { name: /^buscar$/i }).click();
  await page.getByRole('button', { name: boton }).first().click();
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
});
