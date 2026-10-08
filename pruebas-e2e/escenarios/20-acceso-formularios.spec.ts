/** Fondo original y formularios dentro del alto real de la ventana. */
import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';

const TAMANOS = [
  { width: 1440, height: 900 }, { width: 1280, height: 600 },
  { width: 900, height: 500 }, { width: 844, height: 390 },
  { width: 390, height: 844 }, { width: 320, height: 568 },
];

async function medir(page: Page, dialogo: Locator, formulario: string) {
  await expect(dialogo).toBeVisible();
  for (const tamano of TAMANOS) {
    await page.setViewportSize(tamano);
    await dialogo.evaluate(d => Promise.all(d.getAnimations({ subtree: true })
      .filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined))));
    const resultado = await dialogo.evaluate((d, id) => {
      const ventana = d.querySelector('.ventana')!.getBoundingClientRect();
      const cuerpo = d.querySelector<HTMLElement>('.ventana__cuerpo')!;
      const pie = d.querySelector<HTMLElement>('.ventana__pie')!;
      const botones = [...pie.querySelectorAll<HTMLButtonElement>('button')];
      const rect = pie.getBoundingClientRect();
      return {
        ventanaDentro: ventana.top >= -1 && ventana.bottom <= innerHeight + 1 && ventana.left >= -1 && ventana.right <= innerWidth + 1,
        pieDentro: rect.top >= -1 && rect.bottom <= innerHeight + 1 && rect.width > 0,
        botonesDentro: botones.every(b => { const r=b.getBoundingClientRect();return r.left>=-1 && r.right<=innerWidth+1 && r.top>=-1 && r.bottom<=innerHeight+1; }),
        campos: cuerpo.querySelectorAll('input,select,textarea').length,
        scroll: getComputedStyle(cuerpo).overflowY,
        submitVinculado: botones.some(b => b.type === 'submit' && b.form?.id === id),
        horizontal: document.documentElement.scrollWidth > innerWidth + 1,
      };
    }, formulario);
    expect(resultado, `${formulario} a ${tamano.width}×${tamano.height}`).toMatchObject({
      ventanaDentro: true, pieDentro: true, botonesDentro: true, scroll: 'auto', submitVinculado: true, horizontal: false,
    });
    expect(resultado.campos).toBeGreaterThan(0);
    const pieAntes = await dialogo.locator('.ventana__pie').boundingBox();
    await dialogo.locator('.ventana__cuerpo').evaluate(c => { c.scrollTop = c.scrollHeight; });
    const pieDespues = await dialogo.locator('.ventana__pie').boundingBox();
    expect(pieDespues!.y).toBeCloseTo(pieAntes!.y, 0);
  }
  await page.setViewportSize(TAMANOS[0]);
}

test('conserva y carga la imagen original de acceso en seis tamaños', async ({ page, request }) => {
  await page.goto('/acceso');
  await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
  const fondo = page.locator('.acceso__marca');
  expect(await fondo.evaluate(e => getComputedStyle(e).backgroundImage)).toContain('/images/acceso-equipo.png');
  const imagen = await request.get('/images/acceso-equipo.png');
  expect(imagen.ok()).toBeTruthy();expect(imagen.headers()['content-type']).toContain('image/png');
  expect(await page.evaluate(async () => {
    const img = new Image();img.src='/images/acceso-equipo.png';await img.decode();return img.naturalWidth>0 && img.naturalHeight>0;
  })).toBe(true);
  for (const tamano of TAMANOS) {
    await page.setViewportSize(tamano);await expect(fondo).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  }
  await page.setViewportSize(TAMANOS[0]);
  const axe = await new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(axe.violations).toEqual([]);
  await page.screenshot({ path: '../tmp/qa-20261007/acceso-fondo-conservado.png' });
});

test('pacientes y gastos tienen acciones fijas en móvil y escritorio', async ({ page }) => {
  test.setTimeout(60_000);await acceder(page,'administradora');
  await irA(page,'Pacientes');await page.getByRole('button',{name:'Registrar paciente',exact:true}).click();
  await medir(page,page.getByRole('dialog',{name:'Registrar paciente',exact:true}),'formulario-editor-paciente');
  await page.getByRole('button',{name:'Cancelar',exact:true}).click();
  await irA(page,'Gastos y caja');await page.getByRole('button',{name:'Registrar gasto',exact:true}).click();
  await medir(page,page.getByRole('dialog',{name:'Registrar gasto',exact:true}),'formulario-gasto');
});

test('conocimiento, cuentas y roles conservan su formulario desplazable', async ({ page }) => {
  test.setTimeout(60_000);await acceder(page,'administradora');
  await irA(page,'Conocimiento');await page.getByRole('button',{name:'Cargar documento',exact:true}).click();
  const carga=page.getByRole('dialog',{name:'Cargar documento',exact:true});
  await carga.getByRole('radio',{name:'Pegar texto'}).click();
  await medir(page,carga,'formulario-cargar-documento');
  await page.getByRole('button',{name:'Cancelar',exact:true}).click();
  await irA(page,'Usuarios y roles');await page.getByRole('button',{name:'Dar acceso a una persona',exact:true}).click();
  await medir(page,page.getByRole('dialog',{name:'Dar acceso a una persona',exact:true}),'form-alta');
  await page.getByRole('button',{name:'Cancelar',exact:true}).click();
  await page.getByRole('button',{name:'Crear rol',exact:true}).click();
  await medir(page,page.getByRole('dialog',{name:'Crear un rol para la clínica',exact:true}),'form-rol');
});

test('clínicas y accesos de plataforma contienen los formularios largos', async ({ page }) => {
  test.setTimeout(60_000);await acceder(page,'superadministrador');
  await irA(page,'Clínicas');await page.getByRole('button',{name:'Registrar clínica',exact:true}).click();
  await medir(page,page.getByRole('dialog',{name:'Registrar clínica',exact:true}),'formulario-clinica-plataforma');
});

test('la búsqueda del agente flota sobre la ficha y conserva el historial al cancelar', async ({ page, request }) => {
  const paciente=await pacienteConNotas(request);await acceder(page,'profesional');await irA(page,'Pacientes');
  const buscar=page.getByRole('form',{name:'Buscar pacientes'});
  await buscar.getByRole('textbox',{name:/buscar por nombre/i}).fill(paciente.numero_documento!);
  await buscar.getByRole('button',{name:'Buscar',exact:true}).click();
  await page.getByRole('row').filter({hasText:paciente.numero_documento!}).getByRole('button',{name:'Ver ficha'}).click();
  await page.getByRole('button',{name:'Agente del paciente',exact:true}).click();
  await expect(page.getByRole('region',{name:'Agente del paciente'})).toContainText('Funciones locales');
  await page.getByText('Más gestiones',{exact:true}).click();
  await page.getByRole('button',{name:'Configurar búsqueda',exact:true}).click();
  const dialogo=page.getByRole('dialog',{name:'Configurar búsqueda de citas',exact:true});
  await medir(page,dialogo,'formulario-contexto-agente');
  await dialogo.getByRole('button',{name:'Cancelar',exact:true}).click();
  await expect(dialogo).toHaveCount(0);await expect(page.getByRole('region',{name:'Agente del paciente'})).toContainText('Funciones locales');
});

test('el periodontograma conserva las acciones mientras se editan sus seis sitios', async ({ page, request }) => {
  test.setTimeout(60_000);const paciente=await pacienteConNotas(request);
  await acceder(page,'profesional');await irA(page,'Pacientes');
  const buscar=page.getByRole('form',{name:'Buscar pacientes'});
  await buscar.getByRole('textbox',{name:/buscar por nombre/i}).fill(paciente.numero_documento!);
  await buscar.getByRole('button',{name:'Buscar',exact:true}).click();
  await page.getByRole('row').filter({hasText:paciente.numero_documento!}).getByRole('button',{name:'Ver ficha'}).click();
  await page.getByRole('tab',{name:'Periodoncia',exact:true}).click();
  await page.getByRole('button',{name:'Nuevo examen',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Registrar examen periodontal',exact:true});
  await editor.getByRole('button',{name:'Editar pieza 16',exact:true}).click();
  await expect(editor.locator('fieldset.perio__sitio')).toHaveCount(6);
  await medir(page,editor,'formulario-periodontograma');
  await expect(editor.getByRole('button',{name:'Guardar examen',exact:true})).toBeDisabled();
  await page.screenshot({path:'../tmp/qa-20261007/periodontograma-ventana-formulario.png'});
});
