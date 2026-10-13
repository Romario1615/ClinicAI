/**
 * Prueba de uso real de un día de recepción.
 *
 * Recorre la interfaz como lo haría una recepcionista: entrar, registrar un
 * paciente sintético, agendar, confirmar, marcar llegada, buscar, cobrar un
 * abono, anotar en lista de espera, reprogramar y cancelar. No es una prueba
 * de dominio: cada paso anota en `test.info().annotations` (tipo `hallazgo`)
 * lo que se aparta de lo esperable en un software dental, y continúa.
 *
 * Datos exclusivamente sintéticos: nombres con «[SINTETICO]», cédulas 99…,
 * teléfonos +59399… y correos @example.invalid.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import type { APIRequestContext, Locator, Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, CODIGOS_ROL, irA } from '../apoyo/sesion';
import { apiE2e } from '../apoyo/api-e2e';

// Las acciones de Playwright no tienen límite por defecto: sin esto, un campo
// que no aparece deja el recorrido colgado en lugar de anotar un hallazgo.
test.use({ viewport: { width: 1440, height: 900 }, actionTimeout: 15_000 });

const API = apiE2e();
const CARPETA = resolve(process.cwd(), '..', 'tmp', 'e2e-anexo-f', 'dia-recepcion');
/** Etiqueta con o sin asterisco de obligatorio ("Nombres *"). */
const etiqueta = (texto: string) => new RegExp('^' + texto + '(\\s*\\*)?$');
const TS = Date.now();
const SUFIJO = String(TS).slice(-6);

const NOMBRE_1 = '[SINTETICO] Recepcion';
const APELLIDO_1 = `Dia ${SUFIJO}`;
const CEDULA_1 = `99${String(TS).slice(-8)}`;
const TELEFONO_1 = `+59399${String(TS).slice(-7)}`;
const CORREO_1 = `recepcion.${SUFIJO}@example.invalid`;

const NOMBRE_2 = '[SINTETICO] Espera';
const APELLIDO_2 = `Lista ${SUFIJO}`;
const CEDULA_2 = `99${String(TS + 1).slice(-8)}`;

type Severidad = 'alta' | 'media' | 'baja';
interface Hallazgo { paso: string; severidad: Severidad; descripcion: string; captura: string; }
const hallazgos: Hallazgo[] = [];
const consola: string[] = [];

function anotar(paso: string, severidad: Severidad, descripcion: string, captura = ''): void {
  hallazgos.push({ paso, severidad, descripcion, captura });
  test.info().annotations.push({ type: 'hallazgo', description: `[${severidad}] ${paso}: ${descripcion}` });
}

function dato(descripcion: string): void {
  test.info().annotations.push({ type: 'dato', description: descripcion });
}

const fecha = (iso: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(iso));

async function sesionApi(request: APIRequestContext, codigo: string, especialidad_id?: string) {
  const respuesta = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: codigo, ...(especialidad_id ? { especialidad_id } : {}) } });
  expect(respuesta.ok()).toBe(true);
  return { Authorization: `Bearer ${(await respuesta.json()).token_acceso}` };
}

/** Primera combinación del profesional de prueba con horarios para el recorrido. */
async function buscarDisponibilidad(request: APIRequestContext, headers: Record<string, string>) {
  const yoRecepcion = await (await request.get(`${API}/autenticacion/yo`, { headers })).json();
  const profesionales = await (await request.get(`${API}/catalogo/profesionales`, { headers })).json();
  const servicios = await (await request.get(`${API}/catalogo/servicios`, { headers })).json();
  for (const servicio of servicios) {
    const headersProfesional = await sesionApi(request, CODIGOS_ROL.profesional, servicio.especialidad_id);
    const identidadProfesional = await (await request.get(`${API}/autenticacion/yo`, { headers: headersProfesional })).json();
    const profesional = profesionales.find((item: { id: string }) => item.id === identidadProfesional.profesional_id);
    if (!profesional) continue;
    for (const sede_id of yoRecepcion.ambito.sedes) {
      const params = new URLSearchParams({
        sede_id, profesional_id: profesional.id, servicio_id: servicio.id,
        desde: new Date(Date.now() + 60_000).toISOString(),
        hasta: new Date(Date.now() + 60 * 86_400_000).toISOString(),
      });
      const respuesta = await request.get(`${API}/agenda/disponibilidad?${params}`, { headers: headersProfesional });
      if (!respuesta.ok()) continue;
      const turnos = (await respuesta.json()).turnos as { inicio: string }[];
      if (turnos.length >= 3) return { sede_id, profesional, servicio, turnos, headersProfesional };
    }
  }
  throw new Error('No hay tres turnos futuros sintéticos del profesional de prueba');
}

async function medirScroll(page: Page, paso: string): Promise<number> {
  const exceso = await page.evaluate(() => {
    const e = document.documentElement;
    return e.scrollHeight - e.clientHeight;
  });
  if (exceso > 1) anotar(paso, 'baja', `La página tiene scroll vertical de ${exceso}px a 1440x900.`);
  return exceso;
}

async function ventanaCierraSiAbierta(page: Page): Promise<void> {
  const cierres = page.locator('app-ventana-flotante button.ventana__cerrar');
  for (let indice = await cierres.count() - 1; indice >= 0; indice--) {
    const boton = cierres.nth(indice);
    if (await boton.isVisible().catch(() => false)) await boton.click();
  }
}

/** Ejecuta un paso, lo captura y mide el scroll. Un fallo se anota y no detiene el recorrido. */
async function paso(page: Page, nn: string, nombre: string, accion: () => Promise<void>): Promise<void> {
  console.log(`[dia] ${new Date().toISOString()} inicio ${nn} ${nombre}`);
  const inicioHallazgos = hallazgos.length;
  test.info().annotations.push({ type: 'paso', description: `${nn} ${nombre}` });
  try {
    await accion();
  } catch (error) {
    const fallo = error as Error;
    const mensaje = [fallo.message.split('\n')[0], ...(fallo.stack?.split('\n').slice(1, 3) ?? [])].join(' ').trim();
    anotar(`${nn} ${nombre}`, 'alta', `No completable en la interfaz: ${mensaje}`);
  }
  mkdirSync(CARPETA, { recursive: true });
  const captura = `${CARPETA}/${nn}-${nombre}.png`;
  try {
    await page.screenshot({ path: captura });
    for (const hallazgo of hallazgos.slice(inicioHallazgos)) hallazgo.captura = captura;
  } catch (error) {
    anotar(`${nn} ${nombre}`, 'baja', `No se pudo capturar pantalla: ${String((error as Error).message).split('\n')[0]}`);
  }
  await medirScroll(page, `${nn} ${nombre}`).catch(() => undefined);
}

/** Busca un paciente con el selector reutilizable y lo elige por id. */
async function elegirPacienteEnSelector(contenedor: Locator, cedula: string): Promise<void> {
  const buscador = contenedor.getByRole('combobox', { name: /^Paciente/ });
  await buscador.fill(cedula);
  await contenedor.getByRole('option', { name: new RegExp(cedula) }).click();
  await expect(buscador).toHaveValue(/.+/);
}

test('recepción: un día completo de trabajo con pacientes sintéticos', async ({ page, request }) => {
  test.setTimeout(900_000);
  mkdirSync(CARPETA, { recursive: true });
  page.on('console', (mensaje) => { if (mensaje.type() === 'error') consola.push(`console.error: ${mensaje.text()}`); });
  page.on('pageerror', (error) => consola.push(`pageerror: ${error.message}`));

  const headers = await sesionApi(request, CODIGOS_ROL.recepcion);
  let paciente1 = '';
  let paciente2 = '';
  let citaUI = '';
  let horaCita = '';
  let disponibilidad: Awaited<ReturnType<typeof buscarDisponibilidad>> | null = null;

  // 01. Entrar como recepción: debe abrir en Agenda con todo el equipo.
  await paso(page, '01', 'entrar', async () => {
    await acceder(page, 'recepcion');
    const ruta = new URL(page.url()).pathname;
    dato(`Ruta tras entrar como recepción: ${ruta}`);
    if (!ruta.startsWith('/agenda')) {
      anotar('01 entrar', 'media', `Al entrar como recepción la app abre en ${ruta}, no en Agenda.`);
      await irA(page, 'Agenda');
    }
    const profesional = page.getByRole('combobox', { name: 'Profesional', exact: true });
    await expect(profesional).toBeVisible();
    const valor = await profesional.evaluate((s) => (s as HTMLSelectElement).selectedOptions[0]?.textContent?.trim() ?? '');
    const opciones = await profesional.locator('option').allTextContents();
    dato(`Profesional por defecto: "${valor}". Opciones: ${opciones.length}`);
    if (!/todos|todo el equipo/i.test(valor)) {
      anotar('01 entrar', 'media', `El filtro Profesional no abre con todo el equipo; valor inicial «${valor}».`);
    }
  });

  // 02. Registrar un paciente nuevo.
  await paso(page, '02', 'registrar-paciente', async () => {
    console.log('[dia] s2 a irA');
    await irA(page, 'Pacientes');
    console.log('[dia] s2 b click registrar');
    await page.getByRole('button', { name: 'Registrar paciente', exact: true }).click();
    console.log('[dia] s2 c nombres');
    await page.getByLabel(etiqueta('Nombres')).fill(NOMBRE_1);
    console.log('[dia] s2 d apellidos');
    await page.getByLabel(etiqueta('Apellidos')).fill(APELLIDO_1);
    console.log('[dia] s2 e tipo');
    await page.locator('select[name="tipo"]').selectOption('CEDULA', { timeout: 10_000 });
    console.log('[dia] s2 f numero');
    await page.getByLabel(etiqueta('Número de documento')).fill(CEDULA_1);
    console.log('[dia] s2 g whatsapp');
    await page.locator('input[name="telefono"]').fill(TELEFONO_1);
    await expect(page.getByLabel(/^WhatsApp/)).toBeVisible();
    console.log('[dia] s2 h correo');
    await page.locator('input[name="correo"]').fill(CORREO_1);
    await expect(page.getByLabel(/^Correo/)).toBeVisible();
    console.log('[dia] s2 i guardar');
    const guardado = page.waitForResponse((r) => r.request().method() === 'POST' && /\/pacientes\/?$/.test(new URL(r.url()).pathname), { timeout: 30_000 });
    await page.getByRole('button', { name: 'Guardar paciente', exact: true }).click();
    console.log('[dia] s2 j esperando respuesta');
    const respuesta = await guardado;
    console.log('[dia] s2 k respuesta ' + respuesta.status());
    expect(respuesta.status()).toBe(201);
    paciente1 = (await respuesta.json()).id;
    await expect(page.getByRole('button', { name: 'Guardar paciente', exact: true })).toHaveCount(0);
  });

  // 03. Agendar desde «Nueva cita» en el primer hueco libre.
  await paso(page, '03', 'nueva-cita', async () => {
    disponibilidad = await buscarDisponibilidad(request, headers);
    const d = disponibilidad;
    dato(`Día elegido por la API para el primer hueco: ${fecha(d.turnos[0].inicio)}`);
    await irA(page, 'Agenda');
    const filtros = page.getByRole('region', { name: 'Filtros de la agenda' });
    await expect(filtros).toBeVisible({ timeout: 60_000 });
    await expect.poll(() => filtros.locator('select').count(), { timeout: 60_000 }).toBeGreaterThan(3);
    const filtrosSelect = filtros.locator('select');
    await filtrosSelect.nth(0).selectOption(d.sede_id);
    await filtrosSelect.nth(1).selectOption('');
    await filtrosSelect.nth(2).selectOption('');
    await filtrosSelect.nth(3).selectOption('');
    await page.getByLabel(etiqueta('Fecha')).fill(fecha(d.turnos[0].inicio));
    await page.getByRole('button', { name: 'Nueva cita', exact: true }).click();
    const ventana = page.locator('app-ventana-flotante').filter({ hasText: 'Reservar cita' });
    await expect(ventana).toBeVisible();
    await ventana.locator('select[name="servicio-reserva"]').selectOption(d.servicio.id);
    await ventana.locator('select[name="profesional-reserva"]').selectOption(d.profesional.id);
    await expect(ventana).toBeVisible();
    const horas = ventana.locator('.arranques__lista button');
    await expect.poll(() => horas.count()).toBeGreaterThan(0);
    const primera = (await horas.first().textContent())?.trim() ?? '';
    dato(`Primera hora libre ofrecida en Reservar cita: ${primera}`);
    await horas.first().click();
    await elegirPacienteEnSelector(ventana.locator('app-selector-paciente'), CEDULA_1);
    const guardado = page.waitForResponse((r) => r.request().method() === 'POST' && /\/agenda\/citas\/?$/.test(new URL(r.url()).pathname), { timeout: 30_000 });
    await ventana.getByRole('button', { name: 'Confirmar cita', exact: true }).click();
    const respuesta = await guardado;
    expect(respuesta.status()).toBe(201);
    const creada = await respuesta.json();
    citaUI = creada.id;
    horaCita = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/Guayaquil', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(creada.inicio));
  });

  // 04. Confirmar la cita y marcar la llegada del paciente.
  await paso(page, '04', 'confirmar-y-llegada', async () => {
    const bloque = page.locator('app-calendario-agenda button.bloque')
      .filter({ hasText: `${NOMBRE_1} ${APELLIDO_1}` }).filter({ hasText: horaCita }).first();
    await expect(bloque).toBeVisible();
    await expect(bloque).toContainText(`${NOMBRE_1} ${APELLIDO_1}`);
    await bloque.click();
    const detalle = page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') });
    const confirmar = detalle.getByRole('button', { name: 'Confirmar cita', exact: true });
    if (await confirmar.count()) {
      const confirmada = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/agenda/citas/${citaUI}/confirmacion`), { timeout: 30_000 });
      await confirmar.click();
      expect((await confirmada).status()).toBe(200);
    } else {
      // La reserva desde este formulario ya crea la cita confirmada. No se
      // repite una transición que la interfaz correctamente no ofrece.
      await expect(detalle).toContainText('Confirmada');
      dato('La cita quedó confirmada al reservar; se comprueba el estado y se continúa con la llegada.');
    }
    const llegada = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/agenda/citas/${citaUI}/llegada`), { timeout: 30_000 });
    await detalle.getByRole('button', { name: 'Registrar llegada', exact: true }).click();
    expect((await llegada).status()).toBe(200);

    // La caja recibe el cargo que deja la atención. La identidad profesional
    // de prueba coincide con quien atiende la cita; solo se prepara el estado
    // de atención por API para mantener este recorrido centrado en recepción.
    const inicio = await request.post(`${API}/agenda/citas/${citaUI}/inicio-atencion`, { headers: disponibilidad!.headersProfesional });
    expect(inicio.status()).toBe(200, await inicio.text());
    const completado = await request.post(`${API}/agenda/citas/${citaUI}/completado`, { headers: disponibilidad!.headersProfesional });
    expect(completado.status()).toBe(200, await completado.text());
    const cargo = await request.get(`${API}/pagos/cargos/?cita_id=${citaUI}&limite=1`, { headers });
    expect(cargo.ok()).toBe(true, await cargo.text());
    expect((await cargo.json()).elementos).toHaveLength(1);
  });

  // 05. Buscar al paciente desde el buscador superior y abrir su ficha.
  await paso(page, '05', 'buscador-y-ficha', async () => {
    const buscador = page.getByRole('searchbox', { name: /buscar paciente por nombre, apellido o documento/i });
    await buscador.fill(CEDULA_1);
    await page.locator('app-buscador-global').getByRole('button', { name: 'Buscar', exact: true }).click();
    const resultado = page.locator('app-buscador-global').getByText(CEDULA_1).first();
    await expect(resultado).toBeVisible({ timeout: 10_000 });
    await resultado.click();
    const ficha = page.locator('app-ficha-paciente');
    await expect(ficha).toBeVisible();
    const clinicos = ['Nueva nota', 'Nueva receta'];
    for (const etiqueta of clinicos) {
      const n = await page.getByRole('button', { name: etiqueta, exact: true }).count();
      if (n > 0) anotar('05 buscador-y-ficha', 'alta', `Recepción ve el botón «${etiqueta}» en la ficha clínica.`);
    }
    const editar = await page.getByRole('button', { name: /editar/i }).count();
    dato(`Botones «editar» visibles en la ficha para recepción: ${editar}`);
    await page.locator('app-ventana-flotante').filter({ has: ficha }).locator('button.ventana__cerrar').click();
    await expect(ficha).toHaveCount(0);
  });

  // 06. Registrar el cobro de la cita desde Pagos.
  await paso(page, '06', 'pagos-abono', async () => {
    await irA(page, 'Pagos');
    await page.getByRole('button', { name: 'Registrar un abono', exact: true }).click();
    const ventana = page.locator('app-ventana-flotante').filter({ hasText: 'Registrar un abono' });
    await expect(ventana).toBeVisible();
    await elegirPacienteEnSelector(ventana.locator('app-selector-paciente'), CEDULA_1);
    await expect.poll(async () => ventana.locator('select[name="cita"] option').count()).toBeGreaterThan(1);
    const cargoCita = page.waitForResponse((r) => r.request().method() === 'GET' && new URL(r.url()).pathname.endsWith('/pagos/cargos/') && new URL(r.url()).searchParams.get('cita_id') === citaUI, { timeout: 30_000 });
    await ventana.locator('select[name="cita"]').selectOption(citaUI);
    const respuestaCargo = await cargoCita;
    expect(respuestaCargo.ok()).toBe(true);
    const cargo = (await respuestaCargo.json()).elementos[0] as { total_acordado: string; saldo_no_asignado: string };
    const total = ventana.locator('input[name="total-acordado"]');
    await expect(total).toHaveValue(String(Number(cargo.total_acordado)));
    await expect(ventana.locator('input[name="importe"]')).toHaveValue(String(Number(cargo.saldo_no_asignado)));
    const guardado = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/pagos'), { timeout: 30_000 });
    await ventana.getByRole('button', { name: 'Registrar abono pendiente', exact: true }).click();
    const respuesta = await guardado;
    dato(`Respuesta del abono: ${respuesta.status()}`);
    if (!respuesta.ok()) anotar('06 pagos-abono', 'alta', `El abono devolvió ${respuesta.status()}.`);
    await ventanaCierraSiAbierta(page);
  });

  // 07. Lista de espera: añadir otro paciente sintético.
  await paso(page, '07', 'lista-espera', async () => {
    const alta = await request.post(`${API}/pacientes/`, {
      headers: { ...headers, 'Idempotency-Key': randomUUID() },
      data: { nombre: NOMBRE_2, apellido: APELLIDO_2, tipo_documento: 'CEDULA', numero_documento: CEDULA_2 },
    });
    expect(alta.status()).toBe(201, await alta.text());
    paciente2 = (await alta.json()).id;
    await ventanaCierraSiAbierta(page);
    await irA(page, 'Lista de espera');
    await page.getByRole('button', { name: 'Anotar a un paciente', exact: true }).click();
    const ventana = page.locator('app-ventana-flotante').filter({ hasText: 'Anotar a un paciente' });
    await expect(ventana).toBeVisible();
    await expect(ventana.locator('app-selector-paciente [role="combobox"]')).toBeVisible();
    const selector = ventana.locator('app-selector-paciente');
    const buscador = selector.getByRole('combobox', { name: /^Paciente/ });
    await buscador.fill(CEDULA_2);
    await selector.getByRole('option', { name: new RegExp(CEDULA_2) }).click();
    await ventana.locator('select[name="sede"]').selectOption(disponibilidad!.sede_id);
    const servicioEspera = ventana.locator('select[name="servicio"]');
    await expect.poll(async () => servicioEspera.locator('option').count()).toBeGreaterThan(1);
    await servicioEspera.selectOption({ index: 1 });
    const guardado = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/lista-espera'), { timeout: 30_000 });
    await ventana.getByRole('button', { name: 'Añadir a la lista', exact: true }).click();
    expect((await guardado).ok()).toBe(true);
  });

  // 08. Reprogramar una cita y cancelar otra con motivo.
  await paso(page, '08', 'reprogramar-y-cancelar', async () => {
    await ventanaCierraSiAbierta(page);
    const d = disponibilidad!;
    const dias = [...new Set(d.turnos.map((t) => fecha(t.inicio)))];
    const diaA = dias[1] ?? dias[0];
    const diaB = dias[2] ?? dias[0];
    const horaA = d.turnos.find((t) => fecha(t.inicio) === diaA)!;
    const horaB = d.turnos.find((t) => fecha(t.inicio) === diaB && t.inicio !== horaA.inicio) ?? d.turnos[2];
    for (const [cuando, paciente] of [[horaA, 'reprogramar'], [horaB, 'cancelar']] as const) {
      const alta = await request.post(`${API}/agenda/citas`, {
        headers: { ...headers, 'Idempotency-Key': randomUUID() },
        data: { sede_id: d.sede_id, profesional_id: d.profesional.id, servicio_id: d.servicio.id, paciente_id: paciente2, inicio: cuando.inicio },
      });
      dato(`Cita sembrada por API para ${paciente}: ${alta.status()}`);
    }
    await irA(page, 'Agenda');
    const filtrosAgenda = page.getByRole('region', { name: 'Filtros de la agenda' }).locator('select');
    await expect.poll(() => filtrosAgenda.count(), { timeout: 60_000 }).toBeGreaterThan(3);
    await filtrosAgenda.nth(0).selectOption(d.sede_id);
    await filtrosAgenda.nth(1).selectOption(d.profesional.especialidad_id);
    await filtrosAgenda.nth(2).selectOption(d.servicio.id);
    await filtrosAgenda.nth(3).selectOption(d.profesional.id);
    await page.getByLabel(etiqueta('Fecha')).fill(diaA);
    const bloqueA = page.locator('app-calendario-agenda button.bloque, .fila-dia').filter({ hasText: NOMBRE_2 }).first();
    await bloqueA.click();
    const detalle = page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') });
    await detalle.getByRole('button', { name: 'Reprogramar', exact: true }).click();
    const reprogramacion = page.locator('#formulario-reprogramacion');
    await expect(reprogramacion).toBeVisible();
    await reprogramacion.locator('textarea[name="motivoCambio"]').fill('Cambio sintetico de prueba de recepcion');
    const nuevoHorario = reprogramacion.locator('select[name="turnoNuevo"] option');
    // En la suite completa otros escenarios llenan ese día: como haría
    // recepción, si no quedan horarios se prueba otra fecha con turnos.
    for (const otroDia of [diaA, ...dias.filter((dia) => dia !== diaA)]) {
      if (otroDia !== diaA) await reprogramacion.locator('input[name="fechaNueva"]').fill(otroDia);
      await expect(reprogramacion.getByText('Buscando horarios…')).toHaveCount(0);
      if (await nuevoHorario.count() > 1) break;
    }
    await expect.poll(async () => nuevoHorario.count()).toBeGreaterThan(1);
    await reprogramacion.locator('select[name="turnoNuevo"]').selectOption({ index: 1 });
    const reprogramada = page.waitForResponse((r) => r.request().method() !== 'GET' && r.url().includes('/agenda/citas/'), { timeout: 30_000 });
    await page.locator('button[form="formulario-reprogramacion"]').click();
    expect((await reprogramada).ok()).toBe(true);

    await page.getByLabel(etiqueta('Fecha')).fill(diaB);
    const bloqueB = page.locator('app-calendario-agenda button.bloque, .fila-dia').filter({ hasText: NOMBRE_2 }).first();
    await bloqueB.click();
    const detalleB = page.locator('app-ventana-flotante').filter({ has: page.locator('.detalle-cita') });
    await detalleB.getByRole('button', { name: 'Solicitar cancelación', exact: true }).click();
    const ventanaCancelar = page.locator('app-ventana-flotante').filter({ hasText: 'Cancelar cita' });
    await expect(ventanaCancelar).toBeVisible();
    const confirmar = ventanaCancelar.getByRole('button', { name: 'Confirmar cancelación', exact: true });
    if (await confirmar.isEnabled()) anotar('08 reprogramar-y-cancelar', 'alta', 'Confirmar cancelación está activo sin motivo.');
    await ventanaCancelar.locator('textarea[name="motivo"]').fill('Motivo sintetico de prueba');
    const cancelada = page.waitForResponse((r) => r.request().method() !== 'GET' && r.url().includes('/agenda/citas/'), { timeout: 30_000 });
    await confirmar.click();
    expect((await cancelada).ok()).toBe(true);
  });

  // Consola: errores registrados durante el recorrido.
  if (consola.length) {
    for (const linea of [...new Set(consola)]) anotar('transversal consola', 'media', linea.slice(0, 300));
  } else {
    dato('Sin errores de consola durante el recorrido.');
  }

  writeFileSync(`${CARPETA}/hallazgos.json`, JSON.stringify(hallazgos, null, 2), 'utf8');
  expect(hallazgos.filter((hallazgo) => hallazgo.severidad === 'alta'), 'El recorrido debe completar todos los pasos sin hallazgos bloqueantes').toEqual([]);
});
