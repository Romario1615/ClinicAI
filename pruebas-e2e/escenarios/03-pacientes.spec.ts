/**
 * Pacientes: busqueda, ficha y el vacio que se confunde.
 *
 * El escenario que importa es el tercero. «No se busco» y «no hay
 * coincidencias» son cosas distintas, y confundirlas hace que quien atiende
 * concluya que un paciente no esta registrado y le cree una ficha duplicada.
 * Una ficha duplicada parte la historia clinica entre dos registros.
 */
import { expect, test } from '../apoyo/prueba';

import { acceder, irA } from '../apoyo/sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

test.describe('Pacientes', () => {
  test.beforeEach(async ({ page }) => {
    await acceder(page, 'recepcion');
    await irA(page, /pacientes/i);
    await expect(page.getByRole('heading', { name: /pacientes/i })).toBeVisible();
  });

  test('el listado muestra pacientes con su nivel de verificacion', async ({ page }) => {
    await expect(page.locator('table tbody tr').first()).toBeVisible();

    // El nivel de verificacion no es decorativo: un telefono sin verificar no
    // basta para dar informacion por WhatsApp, y quien atiende tiene que verlo
    // en la fila, antes de hablar.
    await expect(page.locator('.verificacion').first()).toBeVisible();
  });

  test('el recuento muestra el total del ambito que devuelve la API', async ({ page, request }) => {
    const recuento = await page.locator('.recuento').textContent();
    expect(recuento).toMatch(/de\s+\d+\s+pacientes/i);
    const total = Number(/de\s+(\d+)\s+pacientes/i.exec(recuento ?? '')?.[1] ?? '0');
    expect(total).toBeGreaterThan(0);
    // El personal tiene el comodín de pacientes de SU clínica: el ámbito recorta
    // por clínica (cubierto en pruebas de API: test_paciente_ajeno_no_se_edita,
    // test_nombres_pacientes_api). Antes se comparaba con un 200 fijo, que
    // dejaba de valer en cuanto las corridas E2E añadían pacientes.
    const sesion = await request.post(`${API}/autenticacion/sesion-local`, { data: { codigo_rol: 'recepcion' } });
    expect(sesion.ok()).toBe(true);
    const listado = await request.get(`${API}/pacientes/?limite=1`, {
      headers: { Authorization: `Bearer ${(await sesion.json()).token_acceso}` },
    });
    expect(listado.ok()).toBe(true);
    expect(total).toBe((await listado.json()).total);
  });

  test('un termino demasiado corto dice que NO se busco', async ({ page }) => {
    const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
    await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill('a');
    await busqueda.getByRole('button', { name: /^buscar$/i }).click();

    // Lo que NO debe decir: que no hay coincidencias, ni que el ambito esta
    // vacio. Las tres cosas significan algo distinto.
    await expect(page.locator('body')).toContainText(/no lleg[oó] a hacerse/i);
    await expect(page.locator('body')).not.toContainText(/sin coincidencias/i);
    await expect(page.locator('body')).not.toContainText(/no hay pacientes en su [aá]mbito/i);
  });

  test('un termino sin resultados dice que no hay coincidencias', async ({ page }) => {
    const busqueda = page.getByRole('form', { name: 'Buscar pacientes' });
    await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill('zzzzzzzz');
    await busqueda.getByRole('button', { name: /^buscar$/i }).click();

    await expect(page.locator('body')).toContainText(/sin coincidencias/i);
    await expect(page.locator('body')).not.toContainText(/no lleg[oó] a hacerse/i);
  });

  test('la ficha distingue datos personales y ofrece el historial en consulta', async ({ page }) => {
    await page.getByRole('button', { name: /ver ficha/i }).first().click();

    await expect(page.locator('.ficha')).toBeVisible();
    await page.getByRole('tab', { name: 'Resumen', exact: true }).click();
    // La ficha actual reúne historial y herramientas, también para recepción.
    // El resumen administrativo no se debe presentar como historia vacía.
    await expect(page.locator('.ficha')).toContainText('Datos personales');
    await expect(page.locator('.ficha')).toContainText('Solo consulta');
    await expect(page.getByRole('tab', { name: 'Historia y recetas', exact: true })).toBeVisible();
    await expect(page.locator('.ficha')).toContainText('Cada lectura de datos clínicos queda registrada');
  });

  test('el buscador global carga la ficha al seleccionar un resultado', async ({ page }) => {
    const nombrePaciente = await page
      .locator('table tbody tr')
      .first()
      .locator('td')
      .first()
      .innerText();
    const apellido = nombrePaciente.split(',')[0].trim();
    const buscador = page.getByRole('search');
    await buscador.getByRole('searchbox').fill(apellido);
    await buscador.getByRole('button', { name: 'Buscar', exact: true }).click();

    const resultados = page.getByRole('region', { name: 'Resultados de la búsqueda' });
    const primerResultado = resultados.locator('.buscador__opcion').first();
    await expect(primerResultado).toBeVisible();
    await primerResultado.click();

    const ficha = page.getByRole('dialog');
    await expect(ficha).toBeVisible();
    await expect(ficha.locator('app-ficha-paciente')).toBeVisible();
  });
});
