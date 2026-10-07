import { randomUUID } from 'node:crypto';
import type { APIRequestContext } from '@playwright/test';
import { expect, test } from '../apoyo/prueba';
import { acceder, CODIGOS_ROL, irA } from '../apoyo/sesion';
import { seleccionarCitaEnAgenda } from '../apoyo/agenda';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const fecha = (iso: string) => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(iso));

async function prepararAgenda(request: APIRequestContext) {
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, {
    data: { codigo_rol: CODIGOS_ROL.recepcion },
  });
  expect(acceso.ok()).toBeTruthy();
  const headers = { Authorization: `Bearer ${(await acceso.json()).token_acceso}` };
  const leer = async (ruta: string) => {
    const respuesta = await request.get(API + ruta, { headers });
    expect(respuesta.ok(), `${ruta}: ${respuesta.status()}`).toBeTruthy();
    return respuesta.json();
  };
  const sede = (await leer('/catalogo/sedes'))[0];
  const servicio = (await leer('/catalogo/servicios'))[0];
  const profesional = (await leer(
    `/catalogo/profesionales?sede_id=${sede.id}&especialidad_id=${servicio.especialidad_id}`,
  ))[0];
  const pacientes = (await leer('/pacientes/?limite=100')).elementos;
  // El resto de la suite deja citas sintéticas activas en la base local. Busca
  // un turno dentro del máximo permitido por la API para no depender de que
  // quede libre precisamente en una semana concreta.
  const desde = new Date(Date.now() + 14 * 86400000).toISOString();
  const hasta = new Date(Date.now() + 60 * 86400000).toISOString();
  const params = new URLSearchParams({
    sede_id: sede.id, profesional_id: profesional.id, servicio_id: servicio.id, desde, hasta,
  });
  const disponibilidad = await leer(`/agenda/disponibilidad?${params}`);
  expect(disponibilidad.turnos.length).toBeGreaterThan(1);
  const turno = disponibilidad.turnos[0];
  const turnoPrevio = disponibilidad.turnos.find(
    (opcion: { inicio: string }) => Date.parse(opcion.inicio) > Date.parse(turno.inicio),
  );
  expect(turnoPrevio, 'se necesita un segundo turno libre para probar el reagendamiento').toBeTruthy();
  const dia = fecha(turno.inicio);
  const inicioDia = new Date(`${dia}T00:00:00-05:00`);
  const agendaVentana = await leer(
    `/agenda/citas?desde=${encodeURIComponent(inicioDia.toISOString())}` +
      `&hasta=${encodeURIComponent(new Date(inicioDia.getTime() + 3 * 86400000).toISOString())}&limite=200`,
  );
  const ocupados = new Set(agendaVentana.elementos.map((cita: { paciente_id: string }) => cita.paciente_id));
  const paciente = pacientes.find((p: { id: string; nivel_verificacion: string }) =>
    !ocupados.has(p.id) && p.nivel_verificacion === 'PRESENCIAL',
  ) ?? pacientes.find((p: { id: string }) => !ocupados.has(p.id));
  if (!paciente) throw new Error('No hay paciente sintético libre para el turno de prueba.');
  const cuerpo = {
    sede_id: sede.id, profesional_id: profesional.id, servicio_id: servicio.id,
    paciente_id: paciente.id, inicio: turno.inicio,
  };
  return { headers, sede, servicio, profesional, paciente, turno, turnoPrevio, cuerpo, leer };
}

test('recepción anota, ofrece y resuelve un turno de la lista de espera', async ({ page, request }) => {
  const agenda = await prepararAgenda(request);
  const sufijo = randomUUID().slice(0, 10);
  const altaPaciente = await request.post(`${API}/pacientes/`, {
    headers: { ...agenda.headers, 'Idempotency-Key': randomUUID() },
    data: {
      nombre: 'Paciente', apellido: `Espera ${sufijo}`,
      tipo_documento: 'SIN_DOCUMENTO', numero_documento: null,
    },
  });
  expect(altaPaciente.status()).toBe(201, await altaPaciente.text());
  const paciente = await altaPaciente.json();

  const altaCitaPrevia = await request.post(`${API}/agenda/citas`, {
    headers: { ...agenda.headers, 'Idempotency-Key': randomUUID() },
    data: { ...agenda.cuerpo, paciente_id: paciente.id, inicio: agenda.turnoPrevio.inicio },
  });
  expect(altaCitaPrevia.status()).toBe(201, await altaCitaPrevia.text());
  const citaPrevia = await altaCitaPrevia.json();

  const altaCita = await request.post(`${API}/agenda/citas`, {
    headers: { ...agenda.headers, 'Idempotency-Key': randomUUID() },
    data: agenda.cuerpo,
  });
  expect(altaCita.status()).toBe(201, await altaCita.text());
  const cita = await altaCita.json();
  let citaResultanteId = '';
  let entradaId = '';
  let entradaSiguienteId = '';

  try {
    await acceder(page, 'recepcion');
    await irA(page, 'Lista de espera');
    await page.getByRole('button', { name: 'Anotar a un paciente' }).click();
    const selector = page.locator('app-selector-paciente');
    await selector.getByLabel('Buscar paciente').fill(`Espera ${sufijo}`);
    await selector.getByRole('button', { name: 'Buscar', exact: true }).click();
    await selector.getByRole('combobox', { name: 'Paciente', exact: true }).selectOption(paciente.id);
    await expect(page.getByRole('dialog', { name: 'Anotar a un paciente' })).toBeVisible({ timeout: 4_000 });
    await expect(page.getByRole('combobox', { name: /^Sede/ })).toBeVisible({ timeout: 4_000 });
    await page.getByRole('combobox', { name: /^Sede/ }).selectOption(agenda.sede.id);
    await page.getByRole('combobox', { name: /^Servicio/ }).selectOption(agenda.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional (opcional)', exact: true }).selectOption(agenda.profesional.id);
    const citaPreviaSelector = page.getByRole('combobox', { name: 'Cita actual que desea cambiar (opcional)' });
    await expect(citaPreviaSelector).toBeVisible();
    await citaPreviaSelector.selectOption(citaPrevia.id);
    const diaDisponible = fecha(agenda.turno.inicio);
    await page.getByLabel('Disponible desde (opcional)').fill(diaDisponible);
    await page.getByLabel('Disponible hasta (opcional)').fill(diaDisponible);
    const diaIngles = new Intl.DateTimeFormat('en-US', {
      weekday: 'long', timeZone: 'America/Guayaquil',
    }).format(new Date(agenda.turno.inicio));
    const diasIngles = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    const indiceDia = diasIngles.indexOf(diaIngles);
    expect(indiceDia).toBeGreaterThanOrEqual(0);
    const diasEspanol = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
    await page.getByRole('checkbox', { name: diasEspanol[indiceDia], exact: true }).check();
    await page.getByLabel('Desde las').fill('00:00');
    await page.getByLabel('Hasta las').fill('23:59');
    await page.getByRole('button', { name: 'Añadir a la lista' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Lista de espera actualizada' })).toBeVisible();

    const listado = await agenda.leer('/lista-espera/');
    const entrada = listado.elementos.find((fila: { paciente_id: string }) => fila.paciente_id === paciente.id);
    expect(entrada, 'la entrada creada desde la interfaz debe persistir').toBeTruthy();
    entradaId = entrada.id;
    expect(entrada.estado).toBe('ACTIVA');
    expect(entrada.profesional_id).toBe(agenda.profesional.id);
    expect(entrada.disponible_desde).toBe(diaDisponible);
    expect(entrada.disponible_hasta).toBe(diaDisponible);
    expect(entrada.preferencias).toEqual({
      dias_semana: [indiceDia], hora_desde: '00:00:00', hora_hasta: '23:59:00',
    });
    expect(entrada.cita_previa_id).toBe(citaPrevia.id);

    // Un segundo paciente espera detrás. Al aceptar la primera oferta, debe
    // recibir el turno anterior que la aceptación acaba de liberar.
    const altaSiguientePaciente = await request.post(`${API}/pacientes/`, {
      headers: { ...agenda.headers, 'Idempotency-Key': randomUUID() },
      data: {
        nombre: 'Paciente', apellido: `Siguiente ${sufijo}`,
        tipo_documento: 'SIN_DOCUMENTO', numero_documento: null,
      },
    });
    expect(altaSiguientePaciente.status()).toBe(201, await altaSiguientePaciente.text());
    const siguientePaciente = await altaSiguientePaciente.json();
    const altaSiguienteEntrada = await request.post(`${API}/lista-espera/`, {
      headers: { ...agenda.headers, 'Idempotency-Key': randomUUID() },
      data: {
        paciente_id: siguientePaciente.id,
        sede_id: agenda.sede.id,
        servicio_id: agenda.servicio.id,
        especialidad_id: agenda.servicio.especialidad_id,
        profesional_id: agenda.profesional.id,
      },
    });
    expect(altaSiguienteEntrada.status()).toBe(201, await altaSiguienteEntrada.text());
    entradaSiguienteId = (await altaSiguienteEntrada.json()).id;

    await irA(page, 'Agenda');
    await page.getByRole('combobox', { name: 'Sede', exact: true }).selectOption(agenda.sede.id);
    await page.getByRole('combobox', { name: 'Especialidad', exact: true }).selectOption(agenda.servicio.especialidad_id);
    await page.getByRole('combobox', { name: 'Servicio', exact: true }).selectOption(agenda.servicio.id);
    await page.getByRole('combobox', { name: 'Profesional', exact: true }).selectOption(agenda.profesional.id);
    await page.getByLabel('Fecha', { exact: true }).fill(fecha(cita.inicio));
    const nombreCita = `${agenda.paciente.nombre} ${agenda.paciente.apellido}`;
    await seleccionarCitaEnAgenda(page, nombreCita);
    const panel = page.locator('.panel');
    await panel.getByRole('button', { name: 'Cancelar la cita' }).click();
    await page.getByLabel('Motivo de la cancelación').fill('Turno liberado para lista de espera sintetica');
    const cancelacion = page.waitForResponse(
      (respuesta) => respuesta.url().includes(`/agenda/citas/${cita.id}/cancelacion`) &&
        respuesta.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Cancelar la cita', exact: true }).last().click();
    expect((await cancelacion).status()).toBe(200);
    await expect(page.getByRole('status').filter({ hasText: 'Cita cancelada' })).toBeVisible();

    await irA(page, 'Lista de espera');
    const fila = page.getByRole('button').filter({ hasText: `Espera ${sufijo}` });
    await expect(fila).toContainText('Con oferta');
    await fila.click();
    const detalle = page.locator('app-ventana-flotante');
    await expect(detalle).toContainText('Este paciente no sabe nada de la oferta.');
    await expect(detalle).toContainText('No tiene consentimiento para mensajes automáticos.');

    // La recepción confirma que habló con el paciente antes de aceptar en su nombre.
    const aceptacion = page.waitForResponse(
      (respuesta) => respuesta.url().includes(`/lista-espera/${entradaId}/resolver`) &&
        respuesta.request().method() === 'POST',
    );
    await detalle.getByRole('button', { name: 'Aceptar y cambiar la cita' }).click();
    const respuesta = await aceptacion;
    expect(respuesta.status()).toBe(200);
    const completada = await respuesta.json();
    expect(completada.estado).toBe('CUMPLIDA');
    citaResultanteId = completada.cita_resultante_id;
    const citaNueva = await agenda.leer(`/agenda/citas/${citaResultanteId}`);
    expect(citaNueva.estado).toBe('CONFIRMED');
    expect(Date.parse(citaNueva.inicio)).toBe(Date.parse(cita.inicio));
    const citaAnteriorCancelada = await agenda.leer(`/agenda/citas/${citaPrevia.id}`);
    expect(citaAnteriorCancelada.estado).toBe('CANCELLED');
    expect(citaAnteriorCancelada.motivo_cancelacion).toContain('lista de espera');
    const listadoSiguiente = await agenda.leer('/lista-espera/');
    const siguienteEntrada = listadoSiguiente.elementos.find(
      (fila: { id: string }) => fila.id === entradaSiguienteId,
    );
    expect(siguienteEntrada.estado).toBe('OFERTADA');
    expect(Date.parse(siguienteEntrada.oferta_inicio)).toBe(Date.parse(citaPrevia.inicio));
  } finally {
    const huboFallo = test.info().errors.length > 0;
    try {
      for (const id of [entradaId, entradaSiguienteId].filter(Boolean)) {
        const estado = await agenda.leer(`/lista-espera/`).then((pagina: { elementos: { id: string; estado: string }[] }) =>
          pagina.elementos.find((fila) => fila.id === id)?.estado,
        );
        if (estado === 'ACTIVA' || estado === 'OFERTADA') {
          await request.post(`${API}/lista-espera/${id}/resolver`, {
            headers: { ...agenda.headers, 'Idempotency-Key': randomUUID() },
            data: { accion: 'cancelar' },
          });
        }
      }
      for (const id of [citaResultanteId, cita.id, citaPrevia.id].filter(Boolean)) {
        const actual = await agenda.leer(`/agenda/citas/${id}`);
        if (!['CANCELLED', 'COMPLETED', 'NO_SHOW'].includes(actual.estado)) {
          await request.post(`${API}/agenda/citas/${id}/cancelacion`, {
            headers: agenda.headers,
            data: { motivo: 'Cierre de prueba sintetica de lista de espera' },
          });
        }
      }
    } catch (fallo) {
      if (!huboFallo) throw fallo;
    }
  }
});
