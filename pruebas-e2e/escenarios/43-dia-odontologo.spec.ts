import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { APIRequestContext, Page } from '@playwright/test';
import { expect, test } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const carpetaCapturas = resolve(process.cwd(), 'test-results/dia-odontologo');
test.use({ actionTimeout: 15_000 });
const fechaLocal = (fecha: Date) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(fecha);

async function prepararDia(request: APIRequestContext) {
  const iniciarSesion = async (codigo_rol: string) => {
    const respuesta = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol } });
    expect(respuesta.ok(), `Inicio de sesión local: ${codigo_rol}`).toBe(true);
    return { Authorization: `Bearer ${(await respuesta.json()).token_acceso}` };
  };
  const headersProfesional = await iniciarSesion('profesional');
  const headersAdmin = await iniciarSesion('administrador_clinica');
  const yoRespuesta = await request.get(`${API}/autenticacion/yo`, { headers: headersProfesional });
  expect(yoRespuesta.ok()).toBe(true);
  const yo = await yoRespuesta.json();
  const profesionalRespuesta = await request.get(`${API}/catalogo/profesionales/${yo.profesional_id}`, { headers: headersProfesional });
  expect(profesionalRespuesta.ok()).toBe(true);
  const profesional = await profesionalRespuesta.json();
  const serviciosRespuesta = await request.get(`${API}/catalogo/servicios`, { headers: headersProfesional });
  expect(serviciosRespuesta.ok()).toBe(true);
  const servicios = (await serviciosRespuesta.json()).filter((s: { especialidad_id: string }) => s.especialidad_id === profesional.especialidad_id);

  const ahora = new Date();
  const desde = new Date(ahora.getTime() + 60_000);
  const hasta = new Date(ahora.getTime() + 48 * 60 * 60_000);
  let turno: { inicio: string; sede_id: string; servicio_id: string } | null = null;
  busqueda: for (const servicio of servicios) {
    for (const sede_id of yo.ambito.sedes as string[]) {
      const params = new URLSearchParams({ sede_id, profesional_id: profesional.id, servicio_id: servicio.id,
        desde: desde.toISOString(), hasta: hasta.toISOString() });
      const respuesta = await request.get(`${API}/agenda/disponibilidad?${params}`, { headers: headersProfesional });
      if (!respuesta.ok()) continue;
      const turnos = (await respuesta.json()).turnos;
      const candidato = turnos.find((t: { inicio: string }) => new Date(t.inicio).getTime() > Date.now());
      if (candidato) {
        turno = { inicio: candidato.inicio, sede_id, servicio_id: servicio.id };
        break busqueda;
      }
    }
  }
  expect(turno, 'Debe haber un horario sintético hoy o mañana para el profesional local').not.toBeNull();

  const documento = `E2E${Date.now()}`;
  const pacienteRespuesta = await request.post(`${API}/pacientes/`, {
    headers: { ...headersAdmin, 'Idempotency-Key': randomUUID() },
    data: { nombre: 'Consulta', apellido: `Odontológica sintética ${randomUUID().slice(0, 8)}`,
      tipo_documento: 'PASAPORTE', numero_documento: documento },
  });
  expect(pacienteRespuesta.status()).toBe(201);
  const paciente = await pacienteRespuesta.json();
  const citaRespuesta = await request.post(`${API}/agenda/citas`, {
    headers: { ...headersAdmin, 'Idempotency-Key': randomUUID() },
    data: { ...turno, profesional_id: profesional.id, paciente_id: paciente.id },
  });
  expect(citaRespuesta.status()).toBe(201);
  const cita = await citaRespuesta.json();
  // Preparación del escenario: la paciente sintética ya hizo check-in y espera
  // al profesional; la transición de inicio ocurre durante el recorrido UI.
  const llegada = await request.post(`${API}/agenda/citas/${cita.id}/llegada`, { headers: headersAdmin });
  expect(llegada.status()).toBe(200);
  return { paciente, cita, profesional, documento };
}

async function captura(page: Page, numero: number) {
  await page.evaluate(() => Promise.all(
    document.getAnimations({ subtree: true })
      .filter(animacion => animacion.effect?.getTiming().iterations !== Infinity)
      .map(animacion => animacion.finished.catch(() => undefined)),
  ));
  await page.screenshot({ path: resolve(carpetaCapturas, `${String(numero).padStart(2, '0')}-paso.png`), fullPage: false });
}

test('recorrido de un día de clínica como odontólogo: agenda, ficha, registros, cierre y radiografía', async ({ page, request }) => {
  test.setTimeout(180_000);
  mkdirSync(carpetaCapturas, { recursive: true });
  const datos = await prepararDia(request);
  const erroresConsola: string[] = [];
  page.on('console', mensaje => { if (mensaje.type() === 'error') erroresConsola.push(mensaje.text()); });
  page.on('pageerror', error => erroresConsola.push(error.message));
  const hallazgos: string[] = [];
  const nombre = `${datos.paciente.nombre} ${datos.paciente.apellido}`;
  await page.setViewportSize({ width: 1440, height: 900 });

  // 1. Acceso local y agenda propia.
  await acceder(page, 'profesional');
  await irA(page, 'Agenda');
  await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.cita.sede_id);
  await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.profesional.especialidad_id);
  await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.cita.servicio_id);
  await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
  await page.getByLabel('Fecha', { exact: true }).fill(fechaLocal(new Date(datos.cita.inicio)));
  await expect(page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre })).toBeVisible();
  await captura(page, 1);

  // 2. Abrir la cita y su ficha; registrar la diferencia entre contexto de cita y odontograma.
  await page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).click();
  const detalle = page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') });
  const ficha = page.locator('app-ventana-flotante').filter({ has: page.locator('app-ficha-paciente') });
  const seccionesFicha = ficha.getByRole('tablist', { name: 'Secciones de la ficha', exact: true });
  const llegada = detalle.getByRole('button', { name: 'Registrar llegada', exact: true });
  if (await llegada.isVisible().catch(() => false)) await llegada.click();
  const botonInicio = detalle.getByRole('button', { name: 'Iniciar atención', exact: true });
  await expect(botonInicio, 'La cita propia con check-in debe ofrecer el inicio profesional').toBeVisible();
  const inicioAtencion = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/agenda/citas/${datos.cita.id}/inicio-atencion`));
  await botonInicio.click();
  expect((await inicioAtencion).status()).toBe(200);
  await expect(detalle).toHaveCount(0);
  await page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).click();
  await detalle.getByRole('button', { name: 'Ver ficha del paciente', exact: true }).click();
  await expect(page.locator('app-ficha-paciente')).toBeVisible();
  const pestanaOdontograma = seccionesFicha.getByRole('tab', { name: 'Odontograma', exact: true });
  if (await pestanaOdontograma.getAttribute('aria-selected') !== 'true') {
    hallazgos.push('La ficha abierta desde una cita no entra directamente al Odontograma: prioriza Atención y documentos; hace falta cambiar de pestaña.');
  }
  await captura(page, 2);

  // 3. Hallazgos FDI y obturación en dos piezas y guardado de una versión.
  await seccionesFicha.getByRole('tab', { name: 'Odontograma', exact: true }).click();
  const odonto = ficha.locator('app-odontograma');
  await expect(odonto.getByRole('heading', { name: 'Odontograma', exact: true })).toBeVisible();
  await odonto.getByRole('button', { name: 'Caries', exact: true }).click();
  await odonto.locator('[data-pieza="16"] [data-region="centro"]').click();
  await odonto.getByRole('button', { name: 'Obturación de resina', exact: true }).click();
  await odonto.locator('[data-pieza="26"] [data-region="centro"]').click();
  await odonto.getByRole('button', { name: 'Crear odontograma', exact: true }).click();
  const revision = page.getByRole('dialog', { name: 'Guardar odontograma', exact: true });
  await expect(revision).toBeVisible();
  await revision.getByRole('button', { name: 'Guardar odontograma', exact: true }).click();
  await expect(odonto).toContainText('Versión 1');
  await captura(page, 3);
  if (await odonto.getByRole('button', { name: 'Guardar nueva versión', exact: true }).count()) {
    hallazgos.push('El primer guardado se denomina «Crear odontograma»; el verbo no comunica que se está firmando/guardando una versión clínica.');
  }

  // 4. Índice de placa como control periodontal.
  await seccionesFicha.getByRole('tab', { name: 'Periodoncia', exact: true }).click();
  const perio = ficha.locator('app-periodontograma');
  await expect(perio.getByRole('heading', { name: 'Periodontograma', exact: true })).toBeVisible();
  await perio.getByRole('button', { name: 'Índice de placa', exact: true }).click();
  const placa = perio.locator('app-indice-placa');
  await placa.getByRole('button', { name: 'Marcar todas presentes', exact: true }).click();
  await placa.getByRole('button', { name: 'Pieza 16, Vestibular', exact: true }).click();
  await placa.getByLabel('Observación (opcional)').fill('Control sintético de placa en una superficie.');
  await placa.getByRole('button', { name: 'Registrar control', exact: true }).click();
  await expect(placa.getByRole('status')).toContainText(/guardad|registrad|control/i);
  await captura(page, 4);

  // 5. Nota SOAP de evolución vinculada a la cita.
  await seccionesFicha.getByRole('tab', { name: 'Historia y recetas', exact: true }).click();
  if (!(await ficha.getByRole('button', { name: 'Nueva nota', exact: true }).count())) {
    hallazgos.push('La pestaña Historia y recetas de la ficha no permite crear una nota; obliga a abrir la historia completa y salir de la ficha/cita.');
    await ficha.getByRole('button', { name: 'Abrir historia completa', exact: true }).click();
    await expect(page).toHaveURL(/\/historia-clinica/);
  }
  await page.getByRole('button', { name: 'Nueva nota', exact: true }).click();
  const editorNota = page.getByRole('dialog', { name: 'Nueva nota de evolución', exact: true });
  await editorNota.getByLabel('Motivo de consulta').fill('Evaluación odontológica sintética');
  await editorNota.getByLabel('Subjetivo (lo que refiere el paciente)').fill('Paciente sintético acude a control programado.');
  await editorNota.getByLabel('Objetivo (exploración)').fill('Caries oclusal FDI 16; obturación de resina FDI 26.');
  await editorNota.getByLabel('Análisis').fill('Hallazgos registrados en odontograma para revisión clínica.');
  await editorNota.getByLabel('Plan').fill('Presentar propuesta por fases y revisar con el paciente.');
  await captura(page, 5);
  const respuestaNota = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/historia/notas'));
  await editorNota.getByRole('button', { name: 'Guardar nota', exact: true }).click();
  const guardadoNota = await respuestaNota;
  expect(guardadoNota.status()).toBe(201);
  const nota = await guardadoNota.json();
  if (nota.cita_id !== datos.cita.id) {
    hallazgos.push(`La nota SOAP se guardó sin vincularse a la cita (cita_id=${nota.cita_id ?? 'vacío'}); abrir la historia completa perdió el contexto de la atención.`);
  }

  // La historia completa abandona la ficha superpuesta; volver a Agenda añade
  // pasos y obliga a reabrir al paciente antes de preparar el plan.
  await irA(page, 'Agenda');
  await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.cita.sede_id);
  await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.profesional.especialidad_id);
  await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.cita.servicio_id);
  await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
  await page.getByLabel('Fecha', { exact: true }).fill(fechaLocal(new Date(datos.cita.inicio)));
  await page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre }).click();
  await page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') })
    .getByRole('button', { name: 'Ver ficha del paciente', exact: true }).click();
  await expect(page.locator('app-ficha-paciente')).toBeVisible();

  // 6. Borrador de plan con procedimientos, piezas FDI, fase y presupuesto estimado.
  await seccionesFicha.getByRole('tab', { name: 'Plan de tratamiento', exact: true }).click();
  const planes = ficha.locator('app-planes-tratamiento');
  await planes.getByRole('button', { name: 'Crear borrador', exact: true }).click();
  const editorPlan = page.getByRole('dialog', { name: 'Crear borrador de tratamiento', exact: true });
  await editorPlan.getByLabel('Título del plan').fill('Plan odontológico sintético');
  await editorPlan.getByLabel('Descripción').fill('Restauración de caries oclusal');
  await editorPlan.getByLabel('Fase').fill('1');
  await editorPlan.getByLabel('Pieza FDI (opcional)').fill('16');
  await editorPlan.getByLabel('Caras FDI').fill('O');
  await editorPlan.getByLabel('Precio (USD)').fill('85');
  await editorPlan.getByRole('button', { name: 'Añadir al plan', exact: true }).click();
  await editorPlan.getByLabel('Descripción').fill('Revisión de obturación existente');
  await editorPlan.getByLabel('Fase').fill('2');
  await editorPlan.getByLabel('Pieza FDI (opcional)').fill('26');
  await editorPlan.getByLabel('Caras FDI').fill('O');
  await editorPlan.getByLabel('Precio (USD)').fill('0');
  await editorPlan.getByRole('button', { name: 'Añadir al plan', exact: true }).click();
  await captura(page, 6);
  await editorPlan.getByRole('button', { name: 'Guardar borrador', exact: true }).click();
  await expect(planes).toContainText('Plan odontológico sintético');
  if (!(await planes.getByRole('button', { name: /presupuesto/i }).count())) {
    hallazgos.push('El plan queda como borrador y no ofrece presupuesto/cotización hasta pasos posteriores de propuesta/aceptación; el total no se entrega directamente a recepción.');
  }
  hallazgos.push('No hay acción para convertir directamente los hallazgos del odontograma en procedimientos del plan; pieza y caras se vuelven a capturar manualmente.');

  // 7. Cerrar la cita desde Agenda tras completar los registros.
  await ficha.getByRole('button', { name: `Cerrar ${nombre}`, exact: true }).click();
  await expect(page.locator('app-ficha-paciente')).toHaveCount(0);
  await expect(detalle).toBeVisible();
  await captura(page, 7);
  const completar = detalle.getByRole('button', { name: 'Marcar como atendida', exact: true });
  if (await completar.isVisible().catch(() => false)) {
    page.once('dialog', dialog => dialog.accept());
    await completar.click();
    await expect(page.getByRole('status').filter({ hasText: 'Cita marcada como atendida' })).toBeVisible();
  } else {
    hallazgos.push('Al volver a la cita no se ofrece «Marcar como atendida»; no se pudo cerrar la atención desde el contexto abierto.');
    test.info().annotations.push({ type: 'hallazgo', description: 'Paso 7: la acción para marcar la cita atendida no estuvo disponible en el detalle.' });
  }

  // 8. Verificar si el cargo quedó pendiente para recepción, sin registrar un pago.
  const pagosRespuesta = await request.get(`${API}/pagos/cargos/?limite=100&paciente_id=${datos.paciente.id}`, {
    headers: { Authorization: `Bearer ${(await (await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'recepcion' } })).json()).token_acceso}` },
  });
  expect(pagosRespuesta.ok()).toBe(true);
  const cargos = (await pagosRespuesta.json()).elementos as Array<{ cita_id: string; total_acordado: string | null }>;
  const cargo = cargos.find(item => item.cita_id === datos.cita.id);
  await captura(page, 8);
  if (!cargo) {
    hallazgos.push('La cita atendida no genera ni deja un cargo pendiente asociado: recepción no tiene importe/estado que cobrar; el borrador del plan tampoco crea el cargo.');
    test.info().annotations.push({ type: 'hallazgo', description: 'Paso 8: no se encontró cargo de la cita para recepción; se documenta como brecha del recorrido.' });
  }

  // 9. Cargar una radiografía sintética generada por canvas, nunca datos reales.
  if (!(await page.locator('app-ficha-paciente').count())) {
    hallazgos.push('Al marcar la cita como atendida se cierra la ficha; para adjuntar la radiografía hay que volver a Pacientes y buscar de nuevo al paciente.');
    await irA(page, 'Pacientes');
    const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
    await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill(datos.documento);
    await busqueda.getByRole('button', { name: 'Buscar', exact: true }).click();
    if (await page.getByRole('row').filter({ hasText: datos.documento }).count()) {
      await page.getByRole('row').filter({ hasText: datos.documento }).getByRole('button', { name: 'Ver ficha', exact: true }).click();
    } else {
      hallazgos.push('Tras el cierre, el paciente sintético deja de aparecer en la búsqueda del ámbito del profesional, aunque tiene una cita atendida hoy/mañana.');
      await irA(page, 'Agenda');
      await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(datos.cita.sede_id);
      await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(datos.profesional.especialidad_id);
      await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(datos.cita.servicio_id);
      await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(datos.profesional.id);
      await page.getByLabel('Fecha', { exact: true }).fill(fechaLocal(new Date(datos.cita.inicio)));
      const bloque = page.locator('app-calendario-agenda button.bloque').filter({ hasText: nombre });
      await bloque.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => undefined);
      if (await bloque.isVisible()) {
        await bloque.click();
        const detalleCita = page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') });
        const verFicha = detalleCita.getByRole('button', { name: 'Ver ficha del paciente', exact: true });
        await verFicha.waitFor({ state: 'visible', timeout: 8_000 }).catch(() => undefined);
        if (await verFicha.isVisible()) await verFicha.click();
      }
    }
    await page.locator('app-ficha-paciente').waitFor({ state: 'visible', timeout: 8_000 }).catch(() => undefined);
    if (!(await page.locator('app-ficha-paciente').count())) {
      hallazgos.push('No fue posible volver a abrir la ficha por Pacientes ni desde la cita completada; la carga de radiografía quedó bloqueada en este recorrido.');
      test.info().annotations.push({ type: 'fixme', description: 'Paso 9 no alcanzable en la interfaz: no hay acceso a la ficha tras completar la cita; evidencia en 09-paso.png.' });
      await captura(page, 9);
      test.info().annotations.push({ type: 'hallazgos', description: hallazgos.join('\n') });
      return;
    }
  }
  await seccionesFicha.getByRole('tab', { name: 'Imágenes', exact: true }).click();
  const galeria = ficha.locator('section[aria-label="Imágenes clínicas del paciente"]');
  await galeria.getByRole('button', { name: 'Cargar imagen clínica', exact: true }).click();
  const carga = page.getByRole('dialog', { name: 'Cargar imagen clínica', exact: true });
  const pngBase64 = await page.evaluate(async () => {
    const canvas = document.createElement('canvas'); canvas.width = 360; canvas.height = 240;
    const ctx = canvas.getContext('2d')!;
    const fondo = ctx.createLinearGradient(0, 0, 360, 240); fondo.addColorStop(0, '#171a20'); fondo.addColorStop(1, '#b6bac0');
    ctx.fillStyle = fondo; ctx.fillRect(0, 0, 360, 240);
    ctx.fillStyle = 'rgba(240,240,240,.78)';
    for (let i = 0; i < 8; i++) { const x = 42 + i * 39; ctx.beginPath(); ctx.ellipse(x, 124 + Math.sin(i / 7 * Math.PI) * 28, 17, 54, (i - 3.5) * .035, 0, Math.PI * 2); ctx.fill(); }
    ctx.strokeStyle = 'rgba(20,20,20,.65)'; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(26, 177); ctx.quadraticCurveTo(178, 245, 334, 177); ctx.stroke();
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await carga.getByLabel('Tipo').selectOption('RADIOGRAFIA_PERIAPICAL');
  await carga.getByLabel('Piezas FDI (opcional)').fill('16');
  await carga.getByLabel('Descripción (opcional)').fill('Radiografía sintética generada para recorrido E2E');
  await carga.getByLabel(/Archivo JPEG, PNG o WebP/i).setInputFiles({
    name: 'radiografia-sintetica.png', mimeType: 'image/png', buffer: Buffer.from(pngBase64, 'base64'),
  });
  await carga.getByRole('button', { name: 'Guardar imagen', exact: true }).click();
  await expect(galeria.locator('.galeria__exito')).toContainText(/Imagen cargada/i);
  const tarjetaRadiografia = galeria.locator('.galeria__tarjeta').filter({ hasText: 'Radiografía sintética generada para recorrido E2E' });
  await expect(tarjetaRadiografia.locator('img')).toBeVisible();
  await captura(page, 9);

  const medidas = await page.evaluate(() => ({ ancho: document.documentElement.scrollWidth, alto: document.documentElement.scrollHeight,
    viewportAncho: innerWidth, viewportAlto: innerHeight }));
  if (medidas.ancho > medidas.viewportAncho + 2 || medidas.alto > medidas.viewportAlto + 2) {
    hallazgos.push(`Desplazamiento de página en escritorio después del recorrido: documento ${medidas.ancho}×${medidas.alto}, viewport ${medidas.viewportAncho}×${medidas.viewportAlto}.`);
  }
  if (erroresConsola.length) hallazgos.push(`Errores de consola durante el recorrido: ${erroresConsola.join(' | ')}`);
  test.info().annotations.push({ type: 'hallazgos', description: hallazgos.length ? hallazgos.join('\n') : 'No se detectaron incoherencias capturadas por las comprobaciones del escenario.' });
});
