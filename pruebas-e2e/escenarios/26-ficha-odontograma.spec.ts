import { randomUUID } from 'node:crypto';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConVersionAnterior } from '../apoyo/datos';
import type { APIRequestContext, Page } from '@playwright/test';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
test.use({ actionTimeout: 15_000 });

async function crearPaciente(request: APIRequestContext) {
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  expect(acceso.ok()).toBe(true);
  const documento = String(Date.now());
  const alta = await request.post(`${API}/pacientes/`, {
    headers: { Authorization: `Bearer ${(await acceso.json()).token_acceso}`, 'Idempotency-Key': randomUUID() },
    data: { nombre: 'Odontograma funcional', apellido: 'Sintético', tipo_documento: 'PASAPORTE', numero_documento: documento },
  });
  expect(alta.status()).toBe(201);
  return { ...(await alta.json()), documento } as { id: string; documento: string };
}

async function abrirFicha(page: Page, documento: string) {
  await irA(page, 'Pacientes');
  await expect(page).toHaveURL(/\/pacientes$/);
  await expect(page.getByRole('heading', { name: 'Pacientes de su ámbito', exact: true })).toBeVisible();
  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(documento);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: documento }).getByRole('button', { name: 'Ver ficha', exact: true }).click();
}

async function abrirOdontograma(page: Page) {
  await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
  await page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true }).getByRole('button', { name: /^Odontograma Piezas/ }).click();
  await expect(page.locator('app-odontograma').getByRole('heading', { name: 'Odontograma', exact: true })).toBeVisible();
}

test('odontograma de Historia conserva piezas legibles y controles accesibles', async ({ page, request }) => {
  test.setTimeout(90_000);
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  expect(acceso.ok()).toBe(true);
  const documento = String(Date.now());
  const alta = await request.post(`${API}/pacientes/`, {
    headers: { Authorization: `Bearer ${(await acceso.json()).token_acceso}`, 'Idempotency-Key': randomUUID() },
    data: { nombre: 'Odontograma visible', apellido: 'Sintético', tipo_documento: 'PASAPORTE', numero_documento: documento },
  });
  expect(alta.status()).toBe(201);
  await page.setViewportSize({ width: 1366, height: 768 });
  await acceder(page, 'profesional');
  await irA(page, 'Historia clínica');
  const busqueda = page.getByRole('region', { name: 'Buscar paciente', exact: true });
  await busqueda.getByRole('textbox').fill(documento);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: documento }).getByRole('button', { name: 'Abrir historia', exact: true }).click();
  await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
  await page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true }).getByRole('button', { name: /^Odontograma Piezas/ }).click();
  const odontograma = page.locator('app-odontograma');
  await expect(odontograma.getByRole('heading', { name: 'Odontograma', exact: true })).toBeVisible();
  await expect(odontograma.getByText('Propuesta por edad; puede cambiarla')).toBeVisible();
  const dimensiones = await odontograma.locator('.diente__svg').first().boundingBox();
  await page.screenshot({ path: test.info().outputPath('odontograma-escritorio.png') });
  expect(dimensiones!.width, 'las piezas deben conservar al menos 44 px en escritorio').toBeGreaterThanOrEqual(44);
  await expect(odontograma.locator('.diente')).toHaveCount(32);
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 2)).toBe(true);
});

test('la ficha abre el Odontograma cuando el profesional tiene acceso clínico', async ({ page, request }) => {
  test.setTimeout(90_000);
  const paciente = await pacienteConVersionAnterior(request);
  await acceder(page, 'profesional');
  await abrirFicha(page, paciente.numero_documento ?? '');
  const pestaña = page.getByRole('tab', { name: 'Odontograma', exact: true });
  await expect(pestaña).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('app-ficha-paciente app-odontograma')).toBeVisible();
});

test('la ficha registra hallazgos y notas por pieza, versiona y permite consulta sin edición', async ({ page, request }) => {
  test.setTimeout(120_000);
  const paciente = await crearPaciente(request);
  await acceder(page, 'profesional');
  await abrirFicha(page, paciente.documento);
  await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
  const herramientas = page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true });
  const inicio = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/atencion-profesional'));
  await herramientas.getByRole('button', { name: 'Comenzar atención sin cita', exact: true }).click();
  expect((await inicio).status()).toBe(204);
  await abrirOdontograma(page);
  const odontograma = page.locator('app-odontograma');
  await odontograma.getByRole('button', { name: 'Caries', exact: true }).click();
  await odontograma.locator('[data-pieza="16"] [data-region="centro"]').click();
  await odontograma.getByRole('button', { name: 'Seleccionar', exact: true }).click();
  await odontograma.locator('[data-pieza="16"] .diente__numero').click();
  const pieza = page.getByRole('dialog', { name: 'Pieza FDI 16', exact: true });
  await expect(pieza).toBeVisible();
  await pieza.getByLabel('Nota clínica de esta pieza').fill('Hallazgo sintético registrado desde la ficha.');
  await pieza.getByRole('button', { name: 'Listo', exact: true }).click();
  await odontograma.getByRole('button', { name: 'Guardar odontograma', exact: true }).click();
  const revision = page.getByRole('dialog', { name: 'Guardar odontograma', exact: true });
  await expect(revision).toBeVisible();
  const alta = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/pacientes/${paciente.id}/odontograma`));
  await revision.getByRole('button', { name: 'Guardar odontograma', exact: true }).click();
  const respuesta = await alta;
  expect(respuesta.status()).toBe(201);
  const primera = await respuesta.json();
  expect(primera.piezas['16'].caras.O).toBe('CARIES');
  expect(primera.piezas['16'].nota).toContain('sintético');
  await expect(revision).not.toBeVisible();
  await expect(odontograma).toContainText('Versión 1');
  await odontograma.getByRole('button', { name: 'Obturación de resina', exact: true }).click();
  await odontograma.locator('[data-pieza="16"] [data-region="centro"]').click();
  await odontograma.getByRole('button', { name: 'Guardar nueva versión', exact: true }).click();
  await revision.getByRole('button', { name: 'Guardar odontograma', exact: true }).click();
  await expect(revision.getByRole('alert')).toContainText('mínimo 8');
  await revision.getByRole('textbox', { name: /Motivo de la versión nueva/ }).fill('Control sintético de la pieza dieciséis');
  const cambio = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/odontograma/versiones'));
  await revision.getByRole('button', { name: 'Guardar odontograma', exact: true }).click();
  expect((await cambio).status()).toBe(201);
  await expect(revision).not.toBeVisible();
  await odontograma.getByLabel('Versión del odontograma', { exact: true }).selectOption('1');
  await expect(odontograma).toContainText('Solo lectura');
  await expect(odontograma.getByRole('button', { name: 'Guardar nueva versión', exact: true })).toHaveCount(0);
  await expect(odontograma.locator('[data-pieza="16"] [data-region="centro"]')).toHaveAttribute('class', /cara--caries/);
  await odontograma.getByLabel('Versión del odontograma', { exact: true }).selectOption('2');
  await expect(odontograma.locator('[data-pieza="16"] [data-region="centro"]')).toHaveAttribute('class', /cara--obturacion_resina/);

  await acceder(page, 'recepcion');
  await abrirFicha(page, paciente.documento);
  await abrirOdontograma(page);
  await expect(odontograma).toContainText('Versión 2');
  await expect(odontograma.getByRole('toolbar')).toHaveCount(0);
  await expect(odontograma.getByRole('button', { name: /Guardar|Crear odontograma/ })).toHaveCount(0);
  await odontograma.locator('[data-pieza="16"] .diente__numero').click();
  await expect(pieza.getByLabel('Nota clínica de esta pieza')).toHaveValue('Hallazgo sintético registrado desde la ficha.');
  await expect(pieza.getByLabel('Nota clínica de esta pieza')).toBeDisabled();
});

test('odontograma de la ficha mantiene tamaño y desplazamiento interno en escritorio y móvil', async ({ page, request }) => {
  test.setTimeout(90_000);
  const paciente = await crearPaciente(request);
  await acceder(page, 'profesional');
  await abrirFicha(page, paciente.documento);
  await abrirOdontograma(page);
  const odontograma = page.locator('app-odontograma');
  for (const dimensiones of [{ width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(dimensiones);
    await expect(odontograma.locator('.diente')).toHaveCount(32);
    const pieza = odontograma.locator('[data-pieza="16"] .diente__svg');
    // Tras cambiar el tamaño, Angular repinta el diente: reintentar si se desconecta.
    await expect(async () => { await pieza.scrollIntoViewIfNeeded({ timeout: 2_000 }); }).toPass({ timeout: 10_000 });
    expect((await pieza.boundingBox())!.width).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
    if (dimensiones.width >= 821) expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 2)).toBe(true);
    await odontograma.locator('[data-pieza="16"] .diente__numero').click();
    await expect(page.getByRole('dialog', { name: 'Pieza FDI 16', exact: true })).toBeVisible();
    await page.getByRole('dialog', { name: 'Pieza FDI 16', exact: true }).getByRole('button', { name: 'Listo', exact: true }).click();
    for (const codigo of [18, 28, 38, 48]) {
      const extremo = odontograma.locator(`[data-pieza="${codigo}"] .diente__numero`);
      await extremo.click();
      const detalle = page.getByRole('dialog', { name: `Pieza FDI ${codigo}`, exact: true });
      await expect(detalle).toBeVisible();
      await detalle.getByRole('button', { name: 'Listo', exact: true }).click();
    }
    await page.screenshot({ path: test.info().outputPath(`ficha-odontograma-${dimensiones.width}.png`) });
  }
});

test('los accesos a pagos y agenda conservan el paciente de la ficha', async ({ page, request }) => {
  const paciente = await crearPaciente(request);
  await acceder(page, 'administradora');
  await abrirFicha(page, paciente.documento);
  await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
  const herramientas = page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true });
  const pagos = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/pagos/') && new URL(r.url()).searchParams.get('paciente_id') === paciente.id);
  const cargos = page.waitForResponse(r => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/pagos/cargos/') && new URL(r.url()).searchParams.get('paciente_id') === paciente.id);
  await herramientas.getByRole('button', { name: 'Pagos del paciente', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/pagos\\?paciente=${paciente.id}`));
  for (const respuesta of [await pagos, await cargos]) {
    expect(respuesta.status()).toBe(200);
    expect((await respuesta.json()).total).toBe(0);
  }
  await page.getByRole('button', { name: 'Registrar un abono', exact: true }).click();
  const formulario = page.getByRole('dialog', { name: 'Registrar un abono', exact: true });
  await expect(formulario).toContainText('Odontograma funcional Sintético');
  await expect(formulario.locator('app-selector-paciente')).toHaveCount(0);
  await formulario.getByRole('button', { name: 'Cerrar Registrar un abono', exact: true }).click();
  await abrirFicha(page, paciente.documento);
  await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
  await herramientas.getByRole('button', { name: 'Gestionar citas', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/agenda\\?paciente=${paciente.id}`));
  await expect(page.locator('app-agenda')).toContainText('Agendando para');
  await expect(page.locator('app-agenda')).toContainText('Odontograma funcional');
});
