/** PDF privado y errores reales; únicamente una base sintética de QA. */
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

async function preparar(request: Parameters<typeof pacienteConNotas>[0], observaciones: string) {
  const paciente = await pacienteConNotas(request);
  const sesion = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'profesional' } });
  expect(sesion.ok()).toBeTruthy();
  const headers = { Authorization: `Bearer ${(await sesion.json()).token_acceso}` };
  const contextos = await (await request.get(`${API}/pacientes/${paciente.id}/contextos-atencion`, { headers })).json();
  expect(contextos.length).toBeGreaterThan(0);
  const origen = contextos[0];
  const titulo = `Documento sintético ${randomUUID().slice(0, 8)}`;
  const alta = await request.post(`${API}/historia/pacientes/${paciente.id}/registros`, { headers, data: {
    clave_idempotencia: randomUUID(), tipo: 'PRESUPUESTO', titulo, especialidad_id: origen.especialidad_id,
    sede_id: origen.sede_id, cita_id: origen.id, motivo: 'Verificación sintética del PDF', observaciones,
    partidas: [{ descripcion: 'Concepto sintético', cantidad: '2', precio_unitario: '12.35' }],
  } });
  expect(alta.status()).toBe(201);
  return { paciente, headers, registro: await alta.json(), titulo };
}

test('un PDF no representable muestra la explicación del servidor y libera el botón', async ({ page, request }) => {
  const datos = await preparar(request, 'Texto de prueba 😀');
  await acceder(page, 'profesional');
  await irA(page, 'Pacientes');
  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(datos.paciente.numero_documento!);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: datos.paciente.numero_documento! }).getByRole('button', { name: 'Ver ficha' }).click();
  await page.getByRole('tablist', { name: 'Secciones de la ficha' }).getByRole('tab', { name: 'Documentos y PDF', exact: true }).click();
  const tarjeta = page.locator('article.registro').filter({ hasText: datos.titulo });
  const descarga = tarjeta.getByRole('button', { name: 'Descargar PDF' });
  const respuesta = page.waitForResponse(r => r.url().endsWith(`/${datos.registro.id}/pdf`));
  await descarga.click();
  expect((await respuesta).status()).toBe(422);
  await expect(page.getByRole('alert').filter({ hasText: 'U+1F600' })).toBeVisible();
  await expect(descarga).toBeEnabled();
});

test('la página pública verifica identidad y descarga el documento Unicode en móvil', async ({ page, request }) => {
  const datos = await preparar(request, 'Unidades sintéticas: μg / µg ≤ 5 ≥ 2 °C cm²\nSegundo párrafo');
  const admin = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  const headers = { Authorization: `Bearer ${(await admin.json()).token_acceso}` };
  const identidad = await (await request.get(`${API}/pacientes/${datos.paciente.id}`, { headers })).json();
  const textos = await (await request.get(`${API}/pacientes/consentimientos/textos`, { headers })).json();
  const texto = textos.find((t: { tipo: string }) => t.tipo === 'DOCUMENTOS_WHATSAPP');
  const consentimiento = await request.post(`${API}/pacientes/${datos.paciente.id}/consentimientos`, { headers, data: { tipo: texto.tipo, version_texto: texto.version, confirmo_lectura: true, canal: 'PRESENCIAL' } });
  expect([201, 409]).toContain(consentimiento.status());
  const entrega = await request.post(`${API}/historia/pacientes/${datos.paciente.id}/registros/${datos.registro.id}/whatsapp`, { headers: datos.headers, data: { clave_idempotencia: randomUUID(), identidad_destinatario_confirmada: true } });
  expect(entrega.status()).toBe(200);
  const token = (await entrega.json()).enlace.split('/').pop();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/documentos/${token}`);
  await page.getByLabel('Fecha de nacimiento').fill('1900-01-01');
  await page.getByRole('button', { name: 'Descargar PDF', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Los datos no coinciden');
  if (identidad.fecha_nacimiento) {
    await page.getByLabel('Fecha de nacimiento').fill(identidad.fecha_nacimiento);
  } else {
    await page.getByRole('button', { name: 'La clínica no tiene mi fecha de nacimiento' }).click();
    await page.getByLabel('Últimos 4 caracteres de su documento').fill(identidad.numero_documento.slice(-4));
  }
  const descarga = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Descargar PDF', exact: true }).click();
  const archivo = await descarga;
  expect((await readFile((await archivo.path())!)).subarray(0, 5).toString()).toBe('%PDF-');
  await archivo.saveAs('../tmp/qa-20261010-documentos-e2e/publico-unicode.pdf');
  await expect(page.getByRole('status')).toContainText('Documento descargado');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([]);
});
