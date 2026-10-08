/** CRUD y documentos reales en la base sintética aislada, sin proveedores externos. */
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas, pacienteConTomas } from '../apoyo/datos';

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
  await page.getByRole('tablist', { name: 'Secciones de la ficha' }).getByRole('tab', { name: 'Documentos y PDF', exact: true }).click();
  await expect(page.getByLabel('Cita de referencia')).toHaveValue(origen.id);
  await expect(page.getByRole('heading', { name: 'Presupuestos, cotizaciones y recetas' })).toBeVisible();
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
  await archivo.saveAs('../tmp/qa-20261007/presupuesto-verificado.pdf');
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

test('faciograma en la ficha conserva la cita, versiona zonas y descarga PDF en escritorio y móvil', async ({ page, request }) => {
  test.setTimeout(60_000);
  const accesos = await (await request.get(`${API}/autenticacion/accesos-locales`)).json();
  const estetica = accesos.especialidades_profesionales.find((e: { nombre: string }) => /dermatolog/i.test(e.nombre));
  expect(estetica).toBeTruthy();
  const profesional = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'profesional', especialidad_id: estetica.id } });
  expect(profesional.ok()).toBeTruthy();
  const cabeceras = { Authorization: `Bearer ${(await profesional.json()).token_acceso}` };
  const disponibles = await (await request.get(`${API}/historia/especialidades`, { headers: cabeceras })).json();
  const propia = disponibles.find((e: { propia: boolean }) => e.propia);
  expect(propia.id).toBe(estetica.id);
  const listado = await (await request.get(`${API}/pacientes/?limite=100`, { headers: cabeceras })).json();
  let encontrada: {id:string; numero_documento:string} | null = null;
  for (const persona of listado.elementos) {
    const acceso = await (await request.get(`${API}/pacientes/${persona.id}/acceso-clinico`, { headers: cabeceras })).json();
    if (!acceso.acceso_clinico) continue;
    const contextos = await (await request.get(`${API}/pacientes/${persona.id}/contextos-atencion`, { headers: cabeceras })).json();
    if (contextos.some((c: { especialidad_id:string }) => c.especialidad_id===propia.id)) { encontrada=persona;break; }
  }
  if (!encontrada) throw new Error('Prepare un paciente sintético con una cita de Dermatología.');
  const paciente = encontrada;
  await page.goto('/acceso');
  await page.getByRole('combobox', { name:'Especialidad del profesional' }).selectOption(estetica.id);
  await page.getByRole('button', { name:/profesional de salud/i }).click();
  await page.waitForURL(/\/(panel|agenda)/);
  await irA(page, 'Pacientes');
  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(paciente.numero_documento!);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Ver ficha' }).click();
  const pestañasFicha = page.getByRole('tablist', { name: 'Secciones de la ficha' });
  await pestañasFicha.getByRole('tab', { name: 'Faciograma', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Faciograma', exact: true })).toBeVisible();
  const contextos = await (await request.get(`${API}/pacientes/${paciente.id}/contextos-atencion`, { headers: cabeceras })).json();
  const origen = contextos.find((c: { especialidad_id: string }) => c.especialidad_id === propia.id);
  expect(origen).toBeTruthy();
  await page.getByLabel('Cita de referencia').selectOption(origen.id);
  await pestañasFicha.getByRole('tab', { name: 'Documentos y PDF', exact: true }).click();
  await expect(page.getByLabel('Cita de referencia')).toHaveValue(origen.id);
  await expect(page.getByRole('heading', { name: 'Presupuestos, cotizaciones y recetas' })).toBeVisible();
  await pestañasFicha.getByRole('tab', { name: 'Faciograma', exact: true }).click();
  await expect(page.getByLabel('Cita de referencia')).toHaveValue(origen.id);
  await page.getByRole('button', { name: 'Nuevo registro facial' }).click();
  let ventana = page.getByRole('dialog', { name: 'Editar registro facial' });
  const zona = ventana.getByRole('button', { name: 'Mentón: SIN_REGISTRO' });
  await zona.focus(); await page.keyboard.press('Enter');
  await ventana.getByLabel('Observación de la zona').fill('Seguimiento estético sintético');
  await ventana.getByLabel('Estado de la zona', { exact: true }).selectOption('PLANIFICADO');
  await ventana.getByRole('button', { name: 'Actualizar zona', exact: true }).click();
  const titulo = `Faciograma E2E ${randomUUID().slice(0, 8)}`;
  await ventana.getByLabel('Título', { exact: true }).fill(titulo);
  const sede = ventana.getByLabel('Sede del registro', { exact: true }); if (!(await sede.inputValue())) await sede.selectOption({ index: 1 });
  await ventana.getByRole('button', { name: 'Guardar versión' }).click();
  await expect(ventana).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Mentón: PLANIFICADO' })).toBeVisible();
  const tarjeta = page.locator('article.registro').filter({ hasText: titulo });
  await tarjeta.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar registro facial' });
  await ventana.getByRole('button', { name: 'Mentón: PLANIFICADO' }).click();
  await ventana.getByLabel('Estado de la zona', { exact: true }).selectOption('REALIZADO');
  await ventana.getByRole('button', { name: 'Actualizar zona', exact: true }).click();
  await ventana.getByLabel('Motivo del registro o modificación').fill('Actualización estética sintética');
  await ventana.getByRole('button', { name: 'Guardar versión' }).click();
  await expect(tarjeta).toContainText('v2');
  await expect(page.getByRole('button', { name: 'Mentón: REALIZADO' })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()).violations).toEqual([]);
  const descarga = page.waitForEvent('download');
  await tarjeta.getByRole('button', { name: 'Descargar PDF' }).click();
  const archivo = await descarga;
  expect((await readFile((await archivo.path())!)).subarray(0, 5).toString()).toBe('%PDF-');
  await archivo.saveAs('../tmp/qa-20261007/faciograma-verificado.pdf');
  for (const ancho of [1440, 768, 390]) {
    await page.setViewportSize({ width: ancho, height: 900 });
    const desborde = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    expect(desborde, `desborde a ${ancho}px`).toBe(false);
    await page.locator('app-mapa-facial').getByRole('button', { name: 'Mentón: REALIZADO' }).scrollIntoViewIfNeeded();
    await expect(page.locator('app-mapa-facial')).toBeInViewport();
    await page.screenshot({ path: `../tmp/qa-20261007/faciograma-${ancho}.png`, fullPage: true });
  }
  await tarjeta.getByRole('button', { name: 'Anular', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Anular registro' });
  await ventana.getByLabel('Motivo de anulación').fill('Cierre del registro facial sintético');
  await ventana.getByRole('button', { name: 'Anular registro', exact: true }).click();
  await expect(tarjeta).toContainText('Anulado');
  await page.getByRole('button', { name: 'Ver historial', exact: true }).click();
  await expect(page.locator('article.registro').filter({ hasText: titulo })).toHaveCount(3);
});

test('cotización y receta confirmada generan PDF y entrega WhatsApp sandbox desde la ficha', async ({ page, request }) => {
  const paciente = await pacienteConTomas(request);
  const profesional = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'profesional' } });
  const headers = { Authorization: `Bearer ${(await profesional.json()).token_acceso}` };
  const recetas = await (await request.get(`${API}/historia/pacientes/${paciente.id}/recetas`, { headers })).json();
  const receta = recetas.find((r: { estado: string }) => r.estado === 'CONFIRMADA');
  expect(receta).toBeTruthy();
  const admin = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  const cabeceras = { Authorization: `Bearer ${(await admin.json()).token_acceso}` };
  const textos = await (await request.get(`${API}/pacientes/consentimientos/textos`, { headers: cabeceras })).json();
  const texto = textos.find((t: { tipo: string }) => t.tipo === 'DOCUMENTOS_WHATSAPP');
  const consentimiento = await request.post(`${API}/pacientes/${paciente.id}/consentimientos`, { headers: cabeceras, data: { tipo: texto.tipo, version_texto: texto.version, confirmo_lectura: true, canal: 'PRESENCIAL' } });
  expect([201, 409]).toContain(consentimiento.status());
  await acceder(page, 'profesional');
  await irA(page, 'Pacientes');
  const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
  await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(paciente.numero_documento!);
  await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
  await page.getByRole('row').filter({ hasText: paciente.numero_documento! }).getByRole('button', { name: 'Ver ficha' }).click();
  await page.getByRole('tablist', { name: 'Secciones de la ficha' }).getByRole('tab', { name: 'Documentos y PDF', exact: true }).click();
  for (const tipo of ['COTIZACION', 'RECETA']) {
    await page.getByRole('button', { name: 'Crear documento', exact: true }).click();
    let ventana = page.getByRole('dialog', { name: 'Preparar documento', exact: true });
    const titulo = `${tipo} E2E ${randomUUID().slice(0, 8)}`;
    await ventana.getByLabel('Título', { exact: true }).fill(titulo);
    const sede = ventana.getByLabel('Sede del registro', { exact: true });
    if (!(await sede.inputValue())) await sede.selectOption({ index: 1 });
    // El selector ofrece Receta únicamente cuando terminó de cargar las confirmadas.
    await expect(ventana.getByLabel('Tipo de documento').locator('option[value="RECETA"]')).toHaveCount(1);
    await ventana.getByLabel('Tipo de documento').selectOption(tipo);
    if (tipo === 'RECETA') {
      await ventana.getByLabel('Receta confirmada', { exact: true }).selectOption(receta.id);
    } else {
      await ventana.getByLabel('Concepto 1', { exact: true }).fill('Servicio de prueba sintético');
      await ventana.getByLabel('Precio unitario 1').fill('15.50');
      await ventana.getByLabel('Válido hasta').fill(new Date(Date.now() + 60 * 86_400_000).toISOString().slice(0, 10));
      await ventana.getByLabel('Observaciones generales').fill('Condiciones de la cotización sintética');
    }
    const guardado = page.waitForResponse(r => r.request().method() === 'POST' && /\/registros$/.test(r.url()));
    await ventana.getByRole('button', { name: 'Guardar versión' }).click();
    const respuesta = await guardado;
    expect(respuesta.status(), await respuesta.text()).toBe(201);
    const registro = await respuesta.json();
    expect(registro.tipo).toBe(tipo);
    if (tipo === 'RECETA') {
      expect(registro.contenido.receta_id).toBe(receta.id);
      expect(registro.contenido.medicamentos.length).toBe(receta.medicamentos.length);
      expect(registro.contenido.medicamentos[0].dosis).toBe(receta.medicamentos[0].dosis);
    }
    const tarjeta = page.locator('article.registro').filter({ hasText: titulo });
    await expect(tarjeta).toBeVisible();
    const descarga = page.waitForEvent('download');
    await tarjeta.getByRole('button', { name: 'Descargar PDF' }).click();
    const archivo = await descarga;
    expect((await readFile((await archivo.path())!)).subarray(0, 5).toString()).toBe('%PDF-');
    await archivo.saveAs(`../tmp/qa-20261007/${tipo === 'RECETA' ? 'receta' : 'cotizacion'}-verificada.pdf`);
    await tarjeta.getByRole('button', { name: 'Enviar por WhatsApp' }).click();
    ventana = page.getByRole('dialog', { name: 'Enviar documento por WhatsApp', exact: true });
    await ventana.getByRole('checkbox').check();
    const envio = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/whatsapp'));
    await ventana.getByRole('button', { name: 'Solicitar envío' }).click();
    const entrega = await envio;
    expect(entrega.status(), await entrega.text()).toBe(200);
    expect((await entrega.json()).modo).toBe('sandbox');
    await expect(ventana).not.toBeVisible();
  }
});
