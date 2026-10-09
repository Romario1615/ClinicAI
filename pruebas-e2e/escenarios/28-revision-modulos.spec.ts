/** Formularios administrativos: botones, validación y persistencia en API aislada. */
import { randomUUID } from 'node:crypto';
import type { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
async function cabeceras(request: APIRequestContext) {
  const r = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'administrador_clinica' } });
  expect(r.ok()).toBeTruthy();
  return { Authorization: `Bearer ${(await r.json()).token_acceso}` };
}
function escritura(page: Page, final: string, metodo = 'POST') {
  return page.waitForResponse(r => r.url().split('?')[0].endsWith(final) && r.request().method() === metodo);
}

test('catálogo: crear, editar, desactivar y reactivar; los servicios protegen su especialidad', async ({ page, request }) => {
  test.setTimeout(120_000);
  const headers = await cabeceras(request), sufijo = randomUUID().slice(0, 8);
  const especialidad = `Área sintética ${sufijo}`, servicio = `Servicio sintético ${sufijo}`, sala = `Sala sintética ${sufijo}`;
  const panelEspecialidades = page.locator('#catalogo-panel-especialidades');
  const panelServicios = page.locator('#catalogo-panel-servicios');
  const panelSedes = page.locator('#catalogo-panel-sedes');
  await acceder(page, 'administradora'); await irA(page, 'Catálogo');
  await page.getByRole('tab', { name: /^Especialidades/ }).click();
  await page.getByRole('button', { name: 'Nueva especialidad', exact: true }).click();
  let ventana = page.getByRole('dialog', { name: 'Nueva especialidad', exact: true });
  await ventana.getByLabel('Nombre', { exact: true }).fill(especialidad);
  await ventana.getByLabel('Código', { exact: true }).fill(`QA${sufijo}`);
  let respuesta = escritura(page, '/catalogo/especialidades');
  await ventana.getByRole('button', { name: 'Crear especialidad', exact: true }).click();
  const creada = await respuesta; expect(creada.status()).toBe(201); const esp = await creada.json();
  await expect(ventana).not.toBeVisible();
  let fila = panelEspecialidades.getByRole('row').filter({ hasText: especialidad });
  await fila.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar especialidad', exact: true });
  await ventana.getByLabel('Descripción', { exact: true }).fill('Descripción administrativa verificada');
  respuesta = escritura(page, `/catalogo/especialidades/${esp.id}`, 'PUT');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  expect((await respuesta).status()).toBe(200); await expect(ventana).not.toBeVisible();
  await expect(fila).toContainText('Descripción administrativa verificada');

  await page.getByRole('tab', { name: /^Servicios/ }).click();
  await page.getByRole('button', { name: 'Nuevo servicio', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Nuevo servicio', exact: true });
  await ventana.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(esp.id);
  await ventana.getByLabel('Nombre', { exact: true }).fill(servicio);
  await ventana.getByLabel('Duración (min)', { exact: true }).fill('45');
  await ventana.getByLabel('Preparación (min)', { exact: true }).fill('10');
  await ventana.getByLabel('Precio', { exact: true }).fill('125.50');
  await ventana.getByLabel('Moneda', { exact: true }).fill('USD');
  respuesta = escritura(page, '/catalogo/servicios');
  await ventana.getByRole('button', { name: 'Crear servicio', exact: true }).click();
  const altaServicio = await respuesta; expect(altaServicio.status()).toBe(201); const srv = await altaServicio.json();
  expect(Number(srv.precio)).toBe(125.5); expect(srv.especialidad_id).toBe(esp.id);
  await expect(ventana).not.toBeVisible();
  fila = panelServicios.getByRole('row').filter({ hasText: servicio });
  await fila.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar servicio', exact: true });
  await expect(ventana.getByRole('combobox', { name: 'Especialidad', exact: true })).toBeDisabled();
  await ventana.getByLabel('Precio', { exact: true }).fill('80.25');
  respuesta = escritura(page, `/catalogo/servicios/${srv.id}`, 'PUT');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  expect(Number((await (await respuesta).json()).precio)).toBe(80.25); await expect(ventana).not.toBeVisible();
  await page.getByRole('tab', { name: /^Especialidades/ }).click();
  fila = panelEspecialidades.getByRole('row').filter({ hasText: especialidad });
  respuesta = escritura(page, `/catalogo/especialidades/${esp.id}/estado`, 'PATCH');
  await fila.getByRole('button', { name: 'Desactivar', exact: true }).click();
  expect((await respuesta).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText(/servicios/i);
  await expect(fila.getByRole('button', { name: 'Desactivar', exact: true })).toBeVisible();
  await page.getByRole('tab', { name: /^Servicios/ }).click();
  fila = panelServicios.getByRole('row').filter({ hasText: servicio });
  await fila.getByRole('button', { name: 'Desactivar', exact: true }).click();
  await expect(fila.getByRole('button', { name: 'Activar', exact: true })).toBeVisible();
  await page.getByRole('tab', { name: /^Especialidades/ }).click();
  fila = panelEspecialidades.getByRole('row').filter({ hasText: especialidad });
  await fila.getByRole('button', { name: 'Desactivar', exact: true }).click();
  await expect(fila.getByRole('button', { name: 'Activar', exact: true })).toBeVisible();
  await fila.getByRole('button', { name: 'Activar', exact: true }).click();
  await expect(fila.getByRole('button', { name: 'Desactivar', exact: true })).toBeVisible();
  await page.getByRole('tab', { name: /^Servicios/ }).click();
  fila = panelServicios.getByRole('row').filter({ hasText: servicio });
  await fila.getByRole('button', { name: 'Activar', exact: true }).click();
  await expect(fila.getByRole('button', { name: 'Desactivar', exact: true })).toBeVisible();

  await page.getByRole('tab', { name: /^Sedes y consultorios/ }).click();
  const seleccionSede = page.getByRole('combobox', { name: 'Sede', exact: true });
  if (!(await seleccionSede.inputValue())) await seleccionSede.selectOption({ index: 1 });
  await page.getByRole('button', { name: 'Nuevo consultorio', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Nuevo consultorio', exact: true });
  await ventana.getByLabel('Nombre', { exact: true }).fill(sala);
  await ventana.getByLabel('Capacidad', { exact: true }).fill('2');
  respuesta = escritura(page, '/catalogo/consultorios');
  await ventana.getByRole('button', { name: 'Crear consultorio', exact: true }).click();
  const altaSala = await respuesta; expect(altaSala.status()).toBe(201); const consultorio = await altaSala.json();
  await expect(ventana).not.toBeVisible();
  fila = panelSedes.getByRole('row').filter({ hasText: sala });
  await fila.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar consultorio', exact: true });
  await ventana.getByLabel('Capacidad', { exact: true }).fill('3');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(ventana).not.toBeVisible();
  for (const accion of ['Desactivar', 'Activar']) {
    await fila.getByRole('button', { name: accion, exact: true }).click();
    await expect(fila.getByRole('button', { name: accion === 'Activar' ? 'Desactivar' : 'Activar', exact: true })).toBeVisible();
  }
  const consulta = await request.get(`${API}/catalogo/consultorios/gestion?sede_id=${consultorio.sede_id}`, { headers });
  expect(consulta.ok()).toBeTruthy();
  expect((await consulta.json()).find((x: { id: string }) => x.id === consultorio.id)).toMatchObject({ capacidad: 3, activo: true });
});

test('cuentas: validar, crear rol y persona, editar, cambiar permisos, quitar y restaurar acceso', async ({ page, request }) => {
  test.setTimeout(90_000);
  const headers = await cabeceras(request), sufijo = randomUUID().slice(0, 8);
  const nombreRol = `Consulta sintética ${sufijo}`, correo = `qa-modulos-${sufijo}@example.invalid`;
  await acceder(page, 'administradora'); await irA(page, 'Usuarios y roles');
  await page.getByRole('button', { name: 'Crear rol', exact: true }).click();
  let ventana = page.getByRole('dialog', { name: 'Crear un rol para la clínica', exact: true });
  await ventana.getByLabel('Nombre del rol', { exact: true }).fill(nombreRol);
  await ventana.getByRole('button', { name: 'Crear rol', exact: true }).click();
  await expect(ventana.getByRole('alert')).toContainText('al menos un permiso');
  await ventana.locator('label.permiso input').first().check();
  let respuesta = escritura(page, '/usuarios/roles');
  await ventana.getByRole('button', { name: 'Crear rol', exact: true }).click();
  const rolNuevo = await respuesta; expect(rolNuevo.status()).toBe(201); const rol = await rolNuevo.json();
  await expect(ventana).not.toBeVisible();
  await page.getByRole('button', { name: 'Dar acceso a una persona', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Dar acceso a una persona', exact: true });
  await ventana.getByRole('button', { name: 'Crear cuenta y dar acceso', exact: true }).click();
  await expect(ventana.getByRole('alert')).toContainText('Revise los datos');
  await ventana.getByLabel('Nombre', { exact: true }).fill('Cuenta sintética');
  await ventana.getByLabel('Apellido', { exact: true }).fill(sufijo);
  await ventana.getByLabel('Correo', { exact: true }).fill(correo);
  await ventana.getByLabel(/^Contraseña inicial/).fill('Temporal!Sintetica2026');
  await ventana.getByRole('checkbox', { name: new RegExp(nombreRol) }).check();
  respuesta = escritura(page, '/usuarios');
  await ventana.getByRole('button', { name: 'Crear cuenta y dar acceso', exact: true }).click();
  const alta = await respuesta; expect(alta.status()).toBe(201); const usuario = await alta.json();
  await expect(ventana).not.toBeVisible();
  await page.getByRole('tab', { name: /^Personal/ }).click();
  await page.getByRole('searchbox', { name: 'Buscar persona', exact: true }).fill(correo);
  const fila = page.getByRole('row').filter({ hasText: correo });
  await expect(fila).toContainText(nombreRol);
  await fila.getByRole('button', { name: 'Editar datos', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar usuario', exact: true });
  await ventana.getByLabel('Nombre', { exact: true }).fill('Cuenta corregida');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(ventana).not.toBeVisible(); await expect(fila).toContainText('Cuenta corregida');
  await fila.getByRole('button', { name: 'Gestionar accesos', exact: true }).click();
  ventana = page.getByRole('dialog', { name: `Cuenta corregida ${sufijo}`, exact: true });
  await ventana.getByRole('checkbox', { name: new RegExp(nombreRol) }).uncheck();
  await expect(ventana.getByRole('button', { name: 'Guardar accesos', exact: true })).toBeDisabled();
  await ventana.getByRole('checkbox', { name: /Recepción/ }).check();
  await ventana.getByRole('button', { name: 'Guardar accesos', exact: true }).click();
  await expect(ventana).not.toBeVisible(); await expect(fila).toContainText('Recepción');
  await fila.getByRole('button', { name: 'Quitar acceso', exact: true }).click();
  ventana = page.getByRole('dialog').filter({ has: page.getByRole('button', { name: 'Quitar acceso', exact: true }) });
  await ventana.getByRole('button', { name: 'Quitar acceso', exact: true }).click();
  await expect(ventana).not.toBeVisible(); await expect(fila).not.toBeVisible();
  await page.getByRole('checkbox', { name: 'Mostrar cuentas sin acceso', exact: true }).check();
  await expect(fila).toContainText('Sin acceso');
  await fila.getByRole('button', { name: 'Restaurar acceso', exact: true }).click();
  await expect(fila).toContainText('Con acceso');
  const consulta = await request.get(`${API}/usuarios`, { headers }); expect(consulta.ok()).toBeTruthy();
  expect((await consulta.json()).find((u: { id: string }) => u.id === usuario.id)).toMatchObject({ nombre: 'Cuenta corregida', activo: true });
  expect(rol.id).toBeTruthy();
});

test('horarios y cierres: el error queda visible; pausas, edición y eliminación se conservan', async ({ page, request }) => {
  test.setTimeout(90_000);
  const headers = await cabeceras(request), nombre = `Cierre sintético ${randomUUID().slice(0, 8)}`;
  const fecha = `${new Date().getUTCFullYear()}-12-24`;
  await acceder(page, 'administradora'); await irA(page, 'Configuración');
  await page.getByRole('button', { name: 'Agenda y feriados', exact: true }).click();
  const sede = await page.locator('select[name="agenda-sede"]').inputValue();
  let horarioId: string | undefined, cierreId: string | undefined;
  try {
  await page.getByRole('button', { name: 'Nuevo horario', exact: true }).click();
  let ventana = page.getByRole('dialog', { name: 'Agregar horario', exact: true });
  await ventana.getByRole('combobox', { name: 'Día', exact: true }).selectOption({ label: 'Domingo' });
  await ventana.getByLabel('Desde', { exact: true }).fill('05:00');
  await ventana.getByLabel('Hasta', { exact: true }).fill('04:00');
  let respuesta = escritura(page, `/configuracion/agenda/sedes/${sede}/horarios`);
  await ventana.getByRole('button', { name: 'Agregar horario', exact: true }).click();
  expect((await respuesta).status()).toBe(422);
  await expect(ventana.getByRole('alert')).toBeVisible();
  await ventana.getByLabel('Hasta', { exact: true }).fill('07:00');
  await ventana.getByRole('button', { name: 'Agregar pausa', exact: true }).click();
  await ventana.locator('.pausa').first().getByLabel('Desde', { exact: true }).fill('06:00');
  await ventana.locator('.pausa').first().getByLabel('Hasta', { exact: true }).fill('06:15');
  respuesta = escritura(page, `/configuracion/agenda/sedes/${sede}/horarios`);
  await ventana.getByRole('button', { name: 'Agregar horario', exact: true }).click();
  const alta = await respuesta; expect(alta.status()).toBe(201); const horario = await alta.json();
  horarioId = horario.id;
  expect(horario.descansos).toHaveLength(1); await expect(ventana).not.toBeVisible();
  let fila = page.locator('article.fila').filter({ hasText: 'Domingo · 05:00–07:00' });
  await fila.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar franja horaria', exact: true });
  await ventana.getByRole('button', { name: 'Eliminar pausa 1', exact: true }).click();
  await expect(ventana.locator('.pausa')).toHaveCount(0);
  await ventana.getByLabel('Hasta', { exact: true }).fill('06:30');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(ventana).not.toBeVisible();
  fila = page.locator('article.fila').filter({ hasText: 'Domingo · 05:00–06:30' });
  await fila.getByRole('button', { name: 'Eliminar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Eliminar horario', exact: true });
  await ventana.getByRole('button', { name: 'Cancelar', exact: true }).click(); await expect(fila).toBeVisible();
  await fila.getByRole('button', { name: 'Eliminar', exact: true }).click();
  await ventana.getByRole('button', { name: 'Eliminar', exact: true }).click();
  await expect(ventana).not.toBeVisible(); await expect(fila).not.toBeVisible();
  await page.getByRole('button', { name: 'Nuevo cierre', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Agregar cierre', exact: true });
  await ventana.getByLabel('Nombre', { exact: true }).fill(nombre);
  await ventana.getByLabel('Fecha', { exact: true }).fill(fecha);
  respuesta = escritura(page, '/configuracion/agenda/feriados');
  await ventana.getByRole('button', { name: 'Agregar cierre', exact: true }).click();
  const cierre = await respuesta; expect(cierre.status()).toBe(201); const feriado = await cierre.json();
  cierreId = feriado.id;
  await expect(ventana).not.toBeVisible(); fila = page.locator('article.fila').filter({ hasText: nombre });
  await fila.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar cierre', exact: true });
  await ventana.getByLabel('Desde', { exact: true }).fill('10:00'); await ventana.getByLabel('Hasta', { exact: true }).fill('12:00');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  await expect(ventana).not.toBeVisible(); await expect(fila).toContainText('10:00–12:00');
  await fila.getByRole('button', { name: 'Eliminar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Eliminar cierre', exact: true });
  await ventana.getByRole('button', { name: 'Eliminar', exact: true }).click(); await expect(fila).not.toBeVisible();
  const consulta = await request.get(`${API}/configuracion/agenda/feriados?sede_id=${sede}&desde=${fecha}&hasta=${fecha}`, { headers });
  expect(consulta.ok()).toBeTruthy(); expect((await consulta.json()).some((f: { id: string }) => f.id === feriado.id)).toBe(false);
  } finally {
    // IDs creados por este caso: una aserción fallida tampoco deja disponibilidad alterada.
    for (const [recurso, id] of [['horarios', horarioId], ['feriados', cierreId]]) {
      if (id) expect([204, 404]).toContain((await request.delete(`${API}/configuracion/agenda/${recurso}/${id}`, { headers })).status());
    }
  }
});

test('bloqueos: rechaza horas invertidas, crea, edita y elimina sin perder el destino', async ({ page, request }) => {
  test.setTimeout(90_000);
  const headers = await cabeceras(request), motivo = `Bloqueo sintético ${randomUUID().slice(0, 8)}`;
  const fecha = new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10);
  await acceder(page, 'administradora'); await irA(page, 'Configuración');
  await page.getByRole('button', { name: 'Bloqueos', exact: true }).click();
  await page.getByRole('button', { name: 'Nuevo bloqueo', exact: true }).click();
  let ventana = page.getByRole('dialog', { name: 'Nuevo bloqueo', exact: true });
  await ventana.getByLabel('Inicio', { exact: true }).fill(`${fecha}T05:00`);
  await ventana.getByLabel('Fin', { exact: true }).fill(`${fecha}T04:00`);
  await ventana.getByLabel('Motivo (opcional)', { exact: true }).fill(motivo);
  let respuesta = escritura(page, '/agenda/bloqueos');
  await ventana.getByRole('button', { name: 'Crear bloqueo', exact: true }).click();
  expect((await respuesta).status()).toBe(422); await expect(ventana.getByRole('alert')).toBeVisible();
  await ventana.getByLabel('Fin', { exact: true }).fill(`${fecha}T06:00`);
  respuesta = escritura(page, '/agenda/bloqueos');
  await ventana.getByRole('button', { name: 'Crear bloqueo', exact: true }).click();
  const alta = await respuesta; expect(alta.status()).toBe(201); const bloqueo = await alta.json();
  expect(bloqueo.profesional_id).toBeNull(); expect(bloqueo.consultorio_id).toBeNull();
  await expect(ventana).not.toBeVisible(); const fila = page.locator('article.fila').filter({ hasText: motivo });
  await fila.getByRole('button', { name: 'Editar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Editar bloqueo', exact: true });
  await expect(ventana.getByLabel('Inicio', { exact: true })).toHaveValue(`${fecha}T05:00`);
  await ventana.getByLabel('Fin', { exact: true }).fill(`${fecha}T07:00`);
  respuesta = escritura(page, `/agenda/bloqueos/${bloqueo.id}`, 'PUT');
  await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
  expect((await respuesta).status()).toBe(200); await expect(ventana).not.toBeVisible();
  await fila.getByRole('button', { name: 'Eliminar', exact: true }).click();
  ventana = page.getByRole('dialog', { name: 'Eliminar otro', exact: true });
  await ventana.getByRole('button', { name: 'Eliminar bloqueo', exact: true }).click();
  await expect(ventana).not.toBeVisible(); await expect(fila).not.toBeVisible();
  const consulta = await request.get(`${API}/agenda/bloqueos?sede_id=${bloqueo.sede_id}&desde=${fecha}T00:00:00Z&hasta=${fecha}T23:59:59Z`, { headers });
  expect(consulta.ok()).toBeTruthy(); expect((await consulta.json()).some((b: { id: string }) => b.id === bloqueo.id)).toBe(false);
});

test('mensajes sandbox: ventana vencida, toma, respuesta idempotente, devolución y cierre', async ({ page, request }) => {
  test.skip(!process.env.QA_BANDEJA_VIGENTE || !process.env.QA_BANDEJA_VENCIDA,
    'Preparar los dos hilos con apoyo/sembrar-bandeja.py sobre la base exclusiva de QA.');
  test.setTimeout(90_000);
  const headers = await cabeceras(request);
  const vigente = process.env.QA_BANDEJA_VIGENTE!, vencida = process.env.QA_BANDEJA_VENCIDA!;
  const configuraciones = await request.get(`${API}/configuracion/integraciones`, { headers });
  expect(configuraciones.ok()).toBeTruthy();
  const agente = (await configuraciones.json()).find((c: { codigo: string }) => c.codigo === 'agente_whatsapp');
  const configurar = (habilitada: boolean) => request.put(`${API}/configuracion/integraciones/agente_whatsapp`, {
    headers, data: { habilitada, ajustes: {}, secretos: {}, eliminar_secretos: [] },
  });
  expect((await configurar(true)).ok()).toBeTruthy();
  try {
    const detalles = await Promise.all([vigente, vencida].map(async id => {
      const r = await request.get(`${API}/conversaciones/${id}`, { headers }); expect(r.ok()).toBeTruthy(); return r.json();
    }));
    await acceder(page, 'administradora'); await irA(page, /atención de mensajes/i);
    await page.getByRole('button', { name: new RegExp(detalles[1].telefono) }).click();
    await expect(page.getByRole('textbox')).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Enviar', exact: true })).toBeDisabled();
    await expect(page.locator('.ventana--vencida')).toContainText('24 h');
    await page.getByRole('button', { name: new RegExp(detalles[0].telefono) }).click();
    let respuesta = escritura(page, `/conversaciones/${vigente}/toma`);
    await page.getByRole('button', { name: 'Tomar', exact: true }).click(); expect((await respuesta).status()).toBe(204);
    await expect(page.getByRole('button', { name: 'Devolver al agente', exact: true })).toBeVisible();
    const asignada = await request.get(`${API}/conversaciones/${vigente}`, { headers });
    expect((await asignada.json()).asignado_a_usuario_id).toBeTruthy();
    const mensaje = `Respuesta administrativa sintética ${randomUUID().slice(0, 8)}`;
    await page.getByRole('textbox').fill(mensaje);
    respuesta = escritura(page, `/conversaciones/${vigente}/respuestas`);
    await page.getByRole('button', { name: 'Enviar', exact: true }).click();
    const encolada = await respuesta; expect(encolada.status()).toBe(202);
    expect(encolada.request().headers()['idempotency-key']).toBeTruthy();
    await expect(page.getByRole('region', { name: 'Línea de tiempo de WhatsApp', exact: true })).toContainText(mensaje);
    respuesta = escritura(page, `/conversaciones/${vigente}/devolucion`);
    await page.getByRole('button', { name: 'Devolver al agente', exact: true }).click(); expect((await respuesta).status()).toBe(204);
    await page.getByRole('button', { name: new RegExp(detalles[0].telefono) }).click();
    await expect(page.locator('.detalle__cabecera .estado')).toContainText(/agente/i);
    page.once('dialog', dialogo => dialogo.accept());
    respuesta = escritura(page, `/conversaciones/${vigente}/cierre`);
    await page.getByRole('button', { name: 'Cerrar', exact: true }).click(); expect((await respuesta).status()).toBe(204);
    await page.getByRole('button', { name: new RegExp(detalles[0].telefono) }).click();
    await expect(page.getByRole('textbox')).toBeDisabled();
    const cerrada = await request.get(`${API}/conversaciones/${vigente}`, { headers }); expect((await cerrada.json()).estado).toBe('CERRADA');
  } finally {
    expect((await configurar(agente?.habilitada ?? false)).ok()).toBeTruthy();
  }
});

test('disponibilidad del equipo: crear, editar, consultar y eliminar dentro de profesional y sede', async ({ page, request }) => {
  test.setTimeout(60_000);
  const headers = await cabeceras(request);
  await acceder(page, 'administradora'); await irA(page, 'Configuración');
  await page.getByRole('button', { name: 'Disponibilidad del equipo', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Nueva franja', exact: true })).toBeVisible();
  const sede = await page.locator('select[name="agenda-prof-sede"]').inputValue();
  const profesional = await page.locator('select[name="agenda-profesional"]').inputValue();
  const ruta = `/profesionales/${profesional}/agenda`;
  let id: string | undefined;
  try {
    await page.getByRole('button', { name: 'Nueva franja', exact: true }).click();
    let ventana = page.getByRole('dialog', { name: 'Nueva franja', exact: true });
    await ventana.getByRole('combobox', { name: 'Día', exact: true }).selectOption({ label: 'Domingo' });
    await ventana.getByLabel('Inicio', { exact: true }).fill('05:00');
    await ventana.getByLabel('Fin', { exact: true }).fill('07:00');
    let respuesta = escritura(page, ruta);
    await ventana.getByRole('button', { name: 'Agregar franja', exact: true }).click();
    const alta = await respuesta; expect(alta.status()).toBe(201); const creada = await alta.json(); id = creada.id;
    expect(creada).toMatchObject({ profesional_id: profesional, sede_id: sede }); await expect(ventana).not.toBeVisible();
    let fila = page.locator('app-agenda-profesionales article.fila').filter({ hasText: 'Domingo · 05:00–07:00' });
    await fila.getByRole('button', { name: 'Editar', exact: true }).click();
    ventana = page.getByRole('dialog', { name: 'Editar franja', exact: true });
    await ventana.getByLabel('Fin', { exact: true }).fill('06:00');
    respuesta = escritura(page, `${ruta}/${id}`, 'PUT');
    await ventana.getByRole('button', { name: 'Guardar cambios', exact: true }).click();
    expect((await respuesta).status()).toBe(200); await expect(ventana).not.toBeVisible();
    const consulta = await request.get(`${API}${ruta}?sede_id=${sede}`, { headers }); expect(consulta.ok()).toBeTruthy();
    expect((await consulta.json()).find((f: { id: string }) => f.id === id).hora_fin).toBe('06:00:00');
    fila = page.locator('app-agenda-profesionales article.fila').filter({ hasText: 'Domingo · 05:00–06:00' });
    await fila.getByRole('button', { name: 'Eliminar', exact: true }).click();
    ventana = page.getByRole('dialog', { name: 'Eliminar franja', exact: true });
    await ventana.getByRole('button', { name: 'Cancelar', exact: true }).click(); await expect(fila).toBeVisible();
    await fila.getByRole('button', { name: 'Eliminar', exact: true }).click();
    await ventana.getByRole('button', { name: 'Eliminar franja', exact: true }).click();
    await expect(ventana).not.toBeVisible(); await expect(fila).not.toBeVisible();
  } finally {
    if (id) expect([204, 404]).toContain((await request.delete(`${API}${ruta}/${id}?sede_id=${sede}`, { headers })).status());
  }
});
