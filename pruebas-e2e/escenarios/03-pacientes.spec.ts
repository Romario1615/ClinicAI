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

  test('el ambito recorta: no se ven los 200 pacientes de la base', async ({ page }) => {
    const recuento = await page.locator('.recuento').textContent();
    expect(recuento).toMatch(/de\s+\d+\s+pacientes/i);

    const total = Number(/de\s+(\d+)\s+pacientes/i.exec(recuento ?? '')?.[1] ?? '0');
    expect(total).toBeGreaterThan(0);
    expect(total).toBeLessThan(200);
  });

  test('un termino demasiado corto dice que NO se busco', async ({ page }) => {
    const busqueda = page.getByRole('region', { name: 'Buscar pacientes' });
    await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill('a');
    await busqueda.getByRole('button', { name: /^buscar$/i }).click();

    // Lo que NO debe decir: que no hay coincidencias, ni que el ambito esta
    // vacio. Las tres cosas significan algo distinto.
    await expect(page.locator('body')).toContainText(/no lleg[oó] a hacerse/i);
    await expect(page.locator('body')).not.toContainText(/sin coincidencias/i);
    await expect(page.locator('body')).not.toContainText(/no hay pacientes en su [aá]mbito/i);
  });

  test('un termino sin resultados dice que no hay coincidencias', async ({ page }) => {
    const busqueda = page.getByRole('region', { name: 'Buscar pacientes' });
    await busqueda.getByRole('textbox', { name: /buscar por nombre/i }).fill('zzzzzzzz');
    await busqueda.getByRole('button', { name: /^buscar$/i }).click();

    await expect(page.locator('body')).toContainText(/sin coincidencias/i);
    await expect(page.locator('body')).not.toContainText(/no lleg[oó] a hacerse/i);
  });

  test('la ficha declara que no es la historia clinica', async ({ page }) => {
    await page.getByRole('button', { name: /ver ficha/i }).first().click();

    await expect(page.locator('.ficha')).toBeVisible();
    // Quien la usa tiene que saber que esta ficha es administrativa: si creyera
    // que es la historia, concluiria que el paciente no tiene antecedentes.
    await expect(page.locator('.ficha')).toContainText(/esta ficha muestra lo administrativo/i);
    await expect(page.locator('.ficha')).toContainText(/historial.*no est[aá]n aqu[ií]|datos cl[ií]nicos/i);
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
