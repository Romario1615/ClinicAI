/** Manuales separados, controles de lectura y WebP de las pantallas interiores. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA, CODIGOS_ROL, type Rol } from '../apoyo/sesion';
import type { Manual } from '../../frontend/src/app/paginas/ayuda/ayuda.service';

test('los quince recursos interiores son WebP reales y conservan los originales', async ({ page }) => {
  const png = ['notificaciones-vacias','agenda-turnos','pagos-administrativos','catalogo-clinica','medicacion-seguimiento','busqueda-pacientes','lista-espera','integraciones-clinicai-banner','bandeja-sin-pendientes'];
  const jpg = ['campanas-pacientes','equipo-clinica-colaboracion','sedes-red-clinicas','usuarios-roles-acceso','conocimiento-evidencia','historia-clinica-integral'];
  await page.goto('/acceso');
  let originales = 0; let webp = 0;
  for (const nombre of [...png,...jpg]) {
    const convertido = await page.request.get(`/images/${nombre}.webp`);
    const original = await page.request.get(`/images/${nombre}.${png.includes(nombre) ? 'png' : 'jpg'}`);
    expect(convertido.status(),nombre).toBe(200); expect(original.status(),nombre).toBe(200);
    expect(convertido.headers()['content-type']).toContain('image/webp');
    const contenido = await convertido.body();
    expect(contenido.toString('ascii',0,4)).toBe('RIFF'); expect(contenido.toString('ascii',8,12)).toBe('WEBP');
    webp += contenido.length; originales += (await original.body()).length;
    expect(await page.evaluate(async ({nombre,extension}) => {
      const img = new Image(); img.src=`/images/${nombre}.webp`; await img.decode();
      const fuente = new Image(); fuente.src=`/images/${nombre}.${extension}`; await fuente.decode();
      const alfa = (imagen: HTMLImageElement) => { const c=document.createElement('canvas');c.width=imagen.naturalWidth;c.height=imagen.naturalHeight;const ctx=c.getContext('2d')!;ctx.drawImage(imagen,0,0);return ctx.getImageData(0,0,1,1).data[3]; };
      return img.naturalWidth > 0 && img.naturalHeight > 0 && img.naturalWidth <= fuente.naturalWidth &&
        Math.abs(img.naturalHeight - fuente.naturalHeight * img.naturalWidth / fuente.naturalWidth) <= .5 && (alfa(fuente) !== 0 || alfa(img) === 0);
    },{nombre,extension:png.includes(nombre)?'png':'jpg'}),nombre).toBe(true);
  }
  expect(originales).toBe(8531109); expect(webp).toBe(499754);
});

for (const rol of ['recepcion','asistente','profesional','administradora','auditor','superadministrador'] as Rol[]) {
  test(`Ayuda de ${rol} presenta únicamente su manual autorizado`, async ({page}) => {
    await acceder(page,rol);
    const respuesta = page.waitForResponse(r => r.url().endsWith('/ayuda/manuales') && r.status()===200);
    await irA(page,'Ayuda');
    const datos = await (await respuesta).json() as {manuales:Manual[]};
    expect(datos.manuales.map(m=>m.rol_codigo)).toEqual([CODIGOS_ROL[rol]]);
    await expect(page.getByRole('heading',{name:'Su manual de trabajo'})).toBeVisible();
    await expect(page.locator('.ayuda__intro h2')).toHaveText(datos.manuales[0].titulo);
    await expect(page.getByRole('tablist')).toHaveCount(0);
    await expect(page.locator('.ayuda__tarea')).toHaveCount(datos.manuales[0].secciones.length);
    await expect(page.getByRole('status')).toContainText(`Mostrando ${datos.manuales[0].secciones.length} de`);
    await page.locator('.ayuda__identidad img').evaluate(img=>(img as HTMLImageElement).decode());
    if (datos.manuales[0].secciones.length) await expect(page.locator('details[open]')).toHaveCount(1);
  });
}

test('expandir, contraer, filtrar, limpiar y seguir la tarea operan en el manual', async ({page}) => {
  await acceder(page,'recepcion'); await irA(page,'Ayuda');
  const tareas = page.locator('.ayuda__tarea'); await expect(tareas.first()).toBeVisible();
  const total = await tareas.count(); expect(total).toBeGreaterThan(1);
  await page.getByRole('button',{name:'Expandir todas',exact:true}).click(); await expect(page.locator('details[open]')).toHaveCount(total);
  await page.getByRole('button',{name:'Contraer todas',exact:true}).click(); await expect(page.locator('details[open]')).toHaveCount(0);
  const titulo = await tareas.first().locator('summary strong').innerText();
  const busqueda = page.getByRole('searchbox',{name:'Buscar en el manual'}); await busqueda.fill(titulo.toUpperCase());
  await expect(tareas).toHaveCount(1); await expect(page.locator('details[open]')).toHaveCount(1);
  await page.getByRole('button',{name:'Limpiar búsqueda',exact:true}).click(); await expect(busqueda).toBeFocused(); await expect(busqueda).toHaveValue('');
  await expect(tareas).toHaveCount(total);
  const primera = tareas.first(); const enlace = primera.getByRole('link'); const ruta = await enlace.getAttribute('href');
  await enlace.click(); await expect(page).toHaveURL(new RegExp(`${ruta!.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}$`));
});

test('los controles y listas de Ayuda respetan el espacio en seis tamaños', async ({page},info) => {
  test.setTimeout(60_000); await page.emulateMedia({reducedMotion:'reduce'});
  await acceder(page,'administradora'); await irA(page,'Ayuda');
  for (const tamano of [{width:1366,height:768},{width:1024,height:768},{width:821,height:600},{width:844,height:390},{width:390,height:844},{width:320,height:568}]) {
    await page.setViewportSize(tamano);
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
    if (tamano.width>=821 && tamano.height>=600) await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollHeight <= innerHeight+1)).toBe(true);
    const buscar = page.getByRole('searchbox',{name:'Buscar en el manual'}); await buscar.scrollIntoViewIfNeeded();
    expect(await buscar.evaluate(e=>e.getBoundingClientRect().right<=innerWidth+1)).toBe(true);
    await expect(page.getByRole('button',{name:'Expandir todas',exact:true})).toBeVisible();
    expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()).violations).toEqual([]);
    if (tamano.width===1366 || tamano.width===390) await page.screenshot({path:info.outputPath(`ayuda-${tamano.width}.png`)});
  }
});

test('varios manuales mantienen filtros y aperturas independientes con teclado', async ({page}) => {
  // Contrato visual sintético de múltiples roles; no concede permisos al usuario real.
  const manual = (codigo:string,nombre:string): Manual => ({rol_codigo:codigo,rol_nombre:nombre,tipo:'PERSONALIZADO',titulo:`Manual de ${nombre}`,introduccion:'Guía sintética de consulta.',responsabilidades:['Consultar el contenido permitido.'],limites:['No modificar registros clínicos.'],secciones:[{clave:`${codigo}.uno`,titulo:'Primera tarea',ruta:null,proposito:'Consultar información.',pasos:['Abra la sección autorizada.'],limites:[],permisos:[]},{clave:`${codigo}.dos`,titulo:'Segunda tarea',ruta:null,proposito:'Consultar otra sección.',pasos:['Revise los datos disponibles.'],limites:[],permisos:[]}]});
  await page.route('**/ayuda/manuales', r=>r.fulfill({json:{manuales:[manual('qa_uno','Consulta uno'),manual('qa_dos','Consulta dos')]}}));
  await acceder(page,'recepcion'); await irA(page,'Ayuda');
  const busqueda = page.getByRole('searchbox',{name:'Buscar en el manual'});
  await busqueda.fill('Segunda'); await expect(page.locator('.ayuda__tarea')).toHaveCount(1);
  await page.getByRole('tab',{name:'Consulta uno',exact:true}).focus(); await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab',{name:'Consulta dos',exact:true})).toBeFocused();
  await expect(page.getByRole('tabpanel',{name:'Consulta dos',exact:true})).toBeVisible();
  await expect(busqueda).toHaveValue(''); await expect(page.locator('details[open]')).toHaveCount(1);
  await page.keyboard.press('Home'); await expect(page.getByRole('tabpanel',{name:'Consulta uno',exact:true})).toBeVisible();
  await expect(page.locator('.ayuda__tarea')).toHaveCount(2);
});
