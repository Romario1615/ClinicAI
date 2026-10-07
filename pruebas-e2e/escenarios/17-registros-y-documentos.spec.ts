/** CRUD y documentos reales en la base sintética aislada, sin proveedores externos. */
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

test('superadministración edita clínica y cuenta, desactiva y reactiva', async ({ page, request }) => {
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'superadministrador' } });
  expect(acceso.ok()).toBeTruthy();
  const headers = { Authorization: `Bearer ${(await acceso.json()).token_acceso}` };
  const sufijo = Date.now();
  const nombre = `Clínica CRUD sintética ${sufijo}`;
  const alta = await request.post(`${API}/plataforma/clinicas`, { headers, data: {
    nombre, zona_horaria: 'America/Guayaquil', moneda: 'USD', idioma: 'es', sede_nombre: 'Sede sintética',
    administrador_nombre: 'Cuenta CRUD', administrador_apellido: `${sufijo}`, administrador_correo: `crud-${sufijo}@example.invalid`, contrasena_inicial: 'Temporal!Sintetica2026',
  } });
  expect(alta.status()).toBe(201);
  await acceder(page, 'superadministrador');
  await irA(page, 'Clínicas');
  let fila = page.locator('article.fila').filter({ hasText: nombre }).filter({ has: page.getByRole('button', { name: 'Editar clínica', exact: true }) });
  await fila.getByRole('button', { name: 'Editar clínica' }).click();
  let ventana = page.getByRole('dialog', { name: `Editar ${nombre}` });
  await ventana.getByLabel('Nombre', { exact: true }).fill(`${nombre} editada`);
  await ventana.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(ventana).not.toBeVisible();
  fila = page.locator('article.fila').filter({ hasText: `${nombre} editada` }).filter({ has: page.getByRole('button', { name: 'Editar clínica', exact: true }) });
  for (const accion of ['Desactivar', 'Reactivar']) {
    await fila.getByRole('button', { name: `${accion} clínica` }).click();
    ventana = page.getByRole('dialog', { name: `${accion} ${nombre} editada` });
    await ventana.getByLabel('Motivo').fill('Cambio administrativo sintético');
    await ventana.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(ventana).not.toBeVisible();
    await expect(fila).toContainText(accion === 'Desactivar' ? 'Inactiva' : 'Activa');
  }
  const cuenta = page.locator('article.fila').filter({ hasText: `crud-${sufijo}@example.invalid` });
  await cuenta.getByRole('button', { name: 'Editar usuario' }).click();
  ventana = page.getByRole('dialog', { name: 'Editar Cuenta CRUD' });
  await ventana.getByLabel('Nombre', { exact: true }).fill('Cuenta actualizada');
  await ventana.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(cuenta).toContainText('Cuenta actualizada');
  for (const accion of ['Desactivar', 'Reactivar']) {
    await cuenta.getByRole('button', { name: `${accion} usuario` }).click();
    ventana = page.getByRole('dialog', { name: `${accion} Cuenta actualizada` });
    await ventana.getByLabel('Motivo').fill('Cambio de cuenta sintético');
    await ventana.getByRole('button', { name: 'Guardar cambios' }).click();
    await expect(ventana).not.toBeVisible();
  }
});

test('ficha por cita, presupuesto PDF, versiones y entrega privada sandbox', async ({ page, request }) => {
  const paciente = await pacienteConNotas(request);
  const admin = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  const headers = { Authorization: `Bearer ${(await admin.json()).token_acceso}` };
  const textos = await (await request.get(`${API}/pacientes/consentimientos/textos`, { headers })).json();
  const texto = textos.find((t: { tipo: string }) => t.tipo === 'DOCUMENTOS_WHATSAPP');
  const consentimiento = await request.post(`${API}/pacientes/${paciente.id}/consentimientos`, { headers, data: { tipo: texto.tipo, version_texto: texto.version, confirmo_lectura: true, canal: 'PRESENCIAL' } });
  expect([201, 409]).toContain(consentimiento.status());
  await acceder(page, 'profesional');
  await irA(page, 'Pacientes');
  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(paciente.numero_documento!);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Ver ficha' }).click();
  await page.getByRole('tab', { name: 'Atención y documentos', exact: true }).click();
  const cita = page.getByLabel('Cita de referencia');
  await expect(cita.locator('option')).not.toHaveCount(1);
  const profesional = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'profesional' } });
  const cabeceras = { Authorization: `Bearer ${(await profesional.json()).token_acceso}` };
  const disponibles = await (await request.get(`${API}/historia/especialidades`, { headers: cabeceras })).json();
  const contextos = await (await request.get(`${API}/pacientes/${paciente.id}/contextos-atencion`, { headers: cabeceras })).json();
  const origen = contextos.find((c: { especialidad_id: string }) => disponibles.some((e: { id: string }) => e.id === c.especialidad_id));
  expect(origen).toBeTruthy(); await cita.selectOption(origen.id);
  await page.getByRole('tab', { name: 'Documentos', exact: true }).click();
  await page.getByRole('button', { name: 'Crear documento' }).click();
  let ventana = page.getByRole('dialog', { name: 'Preparar documento' });
  const titulo = `Presupuesto E2E ${Date.now()}`;
  await ventana.getByLabel('Título', { exact: true }).fill(titulo);
  await ventana.getByLabel('Concepto 1', { exact: true }).fill('Consulta sintética');
  await ventana.getByLabel('Cantidad 1', { exact: true }).fill('2');
  await ventana.getByLabel('Precio unitario 1').fill('12.35');
  const guardado = page.waitForResponse(r => r.request().method() === 'POST' && /\/registros$/.test(r.url()));
  await ventana.getByRole('button', { name: 'Guardar versión' }).click();
  const respuesta = await guardado;
  expect(respuesta.status()).toBe(201);
  const registro = await respuesta.json();
  expect(registro.cita_id).toBe(await cita.inputValue());
  const tarjeta = page.locator('article.registro').filter({ hasText: titulo });
  await expect(tarjeta).toContainText(/24[.,]70/);
  const descarga = page.waitForEvent('download');
  await tarjeta.getByRole('button', { name: 'Descargar PDF' }).click();
  const archivo = await descarga;
  expect((await readFile((await archivo.path())!)).subarray(0, 5).toString()).toBe('%PDF-');
  await tarjeta.getByRole('button', { name: 'Enviar por WhatsApp' }).click();
  ventana = page.getByRole('dialog', { name: 'Enviar documento por WhatsApp' });
  await ventana.getByRole('checkbox').check();
  const envio = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/whatsapp'));
  await ventana.getByRole('button', { name: 'Solicitar envío' }).click();
  const entrega = await (await envio).json();
  expect(entrega.modo).toBe('sandbox');
  await expect(page.getByRole('status').filter({ hasText: 'WhatsApp sandbox' })).toBeVisible();
  await tarjeta.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Preparar documento' });
  await ventana.getByLabel('Motivo del registro o modificación').fill('Corrección de presupuesto sintético');
  await ventana.getByRole('button', { name: 'Guardar versión' }).click();
  await expect(tarjeta).toContainText('v2');
  const token = entrega.enlace.split('/').pop();
  const invalidado = await request.post(`${API}/publico/documentos/${token}/acceso`, { data: { fecha_nacimiento: '1990-01-01' } });
  expect(invalidado.status()).toBe(404);
  await tarjeta.getByRole('button', { name: 'Anular', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Anular registro' });
  await ventana.getByLabel('Motivo de anulación').fill('Cierre sintético de prueba');
  await ventana.getByRole('button', { name: 'Anular registro', exact: true }).click();
  await expect(tarjeta).toContainText('Anulado');
  await page.getByRole('button', { name: 'Ver historial', exact: true }).click();
  await expect(page.locator('article.registro').filter({ hasText: titulo })).toHaveCount(3);
});

test('faciograma accesible guarda una zona y descarga su PDF en escritorio y móvil', async ({ page, request }) => {
  const paciente = await pacienteConNotas(request);
  const admin = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  const headers = { Authorization: `Bearer ${(await admin.json()).token_acceso}` };
  const catalogo = await (await request.get(`${API}/catalogo/especialidades/modulos-historia`, { headers })).json();
  const profesional = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'profesional' } });
  const cabeceras = { Authorization: `Bearer ${(await profesional.json()).token_acceso}` };
  const disponibles = await (await request.get(`${API}/historia/especialidades`, { headers: cabeceras })).json();
  const propia = disponibles.find((e: { propia: boolean }) => e.propia);
  const configurada = catalogo.especialidades.find((e: { id: string }) => e.id === propia.id);
  const activar = await request.put(`${API}/catalogo/especialidades/${propia.id}/modulos-historia`, { headers, data: { modulos: [...new Set([...configurada.modulos, 'faciograma'])], motivo: 'Habilitación sintética E2E' } });
  expect(activar.ok(), await activar.text()).toBeTruthy();
  await acceder(page, 'profesional');
  await irA(page, 'Historia clínica');
  await page.getByPlaceholder(/nombre.*apellido.*documento/i).fill(paciente.numero_documento!);
  await page.getByRole('region', { name: 'Buscar paciente', exact: true }).getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Abrir historia' }).click();
  const especialidad = page.locator('app-selector-especialidad').getByRole('button', { name: new RegExp(propia.nombre) });
  if (await especialidad.count()) await especialidad.click();
  await page.getByRole('tab', { name: 'Faciograma', exact: true }).click();
  await page.getByRole('button', { name: 'Nuevo registro facial' }).click();
  const ventana = page.getByRole('dialog', { name: 'Editar registro facial' });
  const zona = ventana.getByRole('button', { name: 'Mentón: SIN_REGISTRO' });
  await zona.focus(); await page.keyboard.press('Enter');
  await ventana.getByLabel('Observación de la zona').fill('Seguimiento estético sintético');
  await ventana.getByLabel('Estado de la zona', { exact: true }).selectOption('PLANIFICADO');
  await ventana.getByRole('button', { name: 'Agregar al registro' }).click();
  await ventana.getByLabel('Título', { exact: true }).fill(`Faciograma E2E ${randomUUID().slice(0, 8)}`);
  const sede = ventana.getByLabel('Sede del registro', { exact: true }); if (!(await sede.inputValue())) await sede.selectOption({ index: 1 });
  await ventana.getByRole('button', { name: 'Guardar versión' }).click();
  await expect(ventana).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Mentón: PLANIFICADO' })).toBeVisible();
  const descarga = page.waitForEvent('download');
  await page.locator('article.registro').first().getByRole('button', { name: 'Descargar PDF' }).click();
  expect((await readFile((await (await descarga).path())!)).subarray(0, 5).toString()).toBe('%PDF-');
  for (const ancho of [1440, 768, 390]) {
    await page.setViewportSize({ width: ancho, height: 900 });
    const desborde = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    expect(desborde, `desborde a ${ancho}px`).toBe(false);
    await page.screenshot({ path: `../tmp/qa-20261007/faciograma-${ancho}.png`, fullPage: true });
  }
});
