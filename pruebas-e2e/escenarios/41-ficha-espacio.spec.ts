/** Contención visual de ficha, agente y selector sobre datos QA reales. */
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';
import { esperaDeConsultas, solapesVisibles } from '../apoyo/espacio';

for (const rol of ['profesional', 'recepcion'] as const) {
  test(`ficha, agente y herramientas conservan sus espacios para ${rol}`, async ({ page, request }, info) => {
    test.setTimeout(120_000);
    const esperar = esperaDeConsultas(page);
    const paciente = await pacienteConNotas(request);
    const erroresNavegador: string[] = [];
    page.on('pageerror', e => erroresNavegador.push(e.message));
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1440, height: 900 });
    await acceder(page, rol);
    await irA(page, 'Pacientes');
    const buscar = page.getByRole('form', { name: 'Buscar pacientes' });
    await buscar.getByRole('textbox', { name: /buscar por nombre/i }).fill(paciente.numero_documento!);
    await buscar.getByRole('button', { name: 'Buscar', exact: true }).click();
    await page.getByRole('row').filter({ hasText: paciente.numero_documento! })
      .getByRole('button', { name: 'Ver ficha', exact: true }).click();
    await esperar();
    const tamanos = [{ width: 1440, height: 900 }, { width: 1024, height: 768 },
      { width: 821, height: 600 }, { width: 768, height: 1024 }, { width: 390, height: 844 },
      { width: 320, height: 568 }, { width: 844, height: 390 }];
    const incidencias: unknown[] = [];
    let mediciones = 0;
    const medir = async (estado: string) => {
      for (const tamano of tamanos) {
        await page.setViewportSize(tamano);
        await esperar();
        const ventana = page.locator('dialog[open]').last();
        const marco = ventana.locator('.ventana');
        expect(await marco.evaluate(e => {
          const r = e.getBoundingClientRect();
          return r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1;
        }), `${estado} ${JSON.stringify(tamano)}`).toBe(true);
        for (const posicion of [0, .5, 1]) {
          await ventana.locator('.ventana__cuerpo,.ficha,.ficha__lado,.ficha__cuerpo,.ficha__agente')
            .evaluateAll((elementos, posicion) => {
              for (const e of elementos) e.scrollTop = (e.scrollHeight - e.clientHeight) * posicion;
            }, posicion);
          await esperar();
          const errores = await solapesVisibles(page);
          mediciones++;
          if (errores.length) {
            incidencias.push({ estado, tamano, posicion, errores });
            await page.screenshot({ path: info.outputPath(`${estado}-${tamano.width}-${posicion}.png`) });
          }
        }
      }
    };
    await medir('ficha');
    await page.getByRole('button', { name: 'Agente del paciente', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Agente del paciente' })).toBeVisible();
    await medir('agente');
    await page.getByRole('button', { name: 'Elegir qué registrar', exact: true }).click();
    const herramientas = page.getByRole('dialog', { name: 'Herramientas del paciente', exact: true });
    await expect(herramientas).toBeVisible();
    await expect(herramientas.locator('.herramienta')).toHaveCount(10);
    if (rol === 'recepcion') {
      await expect(herramientas).not.toContainText('Consultar y registrar');
      await expect(herramientas.getByRole('button', { name: 'Comenzar atención sin cita', exact: true })).toHaveCount(0);
    }
    await medir('herramientas');
    await page.setViewportSize({ width: 390, height: 844 });
    await herramientas.getByRole('button', { name: 'Cerrar', exact: true }).click();
    await page.getByRole('tab', { name: 'Contacto y consentimientos', exact: true }).click();
    await esperar();
    await page.screenshot({ path: info.outputPath(`ficha-${rol}-movil.png`) });
    expect(erroresNavegador).toEqual([]);
    await info.attach('ficha-geometria', { body: JSON.stringify({ rol, mediciones, incidencias }, null, 2), contentType: 'application/json' });
    expect(incidencias).toEqual([]);
  });
}
