import { randomUUID } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA, type Rol } from '../apoyo/sesion';
import { esperaDeConsultas } from '../apoyo/espacio';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

test('logo destacado, celeste turquesa y foto original con seis roles alcanzables', async ({ page }, info) => {
  const esperar = esperaDeConsultas(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/acceso');
  await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
  for (const tamano of [{width:1440,height:900},{width:1280,height:600},{width:1024,height:768},{width:768,height:1024},{width:390,height:844},{width:320,height:568}]) {
    await page.setViewportSize(tamano);
    await expect(page.locator('.acceso')).toHaveCSS('height', `${tamano.height}px`);
    await esperar();
    const medidas = await page.locator('.acceso').evaluate(elemento => {
      const nombre = elemento.querySelector('.marca__nombre')!;
      const img = elemento.querySelector<HTMLImageElement>('.marca__simbolo')!;
      return { nombre:parseFloat(getComputedStyle(nombre).fontSize), logo:img.complete && img.naturalWidth > 0,
        sinDesborde:document.documentElement.scrollWidth<=innerWidth+1,
        fondo:elemento.querySelector<HTMLImageElement>('.acceso__foto')!.currentSrc,
        acento:getComputedStyle(document.documentElement).getPropertyValue('--acento').trim()};
    });
    expect(medidas.logo).toBe(true);expect(medidas.nombre).toBeGreaterThanOrEqual(32);
    expect(medidas.sinDesborde).toBe(true);
    expect(medidas.fondo).toMatch(/\/images\/acceso-equipo(?:-900)?\.webp$/);
    expect(medidas.acento).toBe('#086c7f');
    await expect(page.locator('.acceso__foto').first()).toHaveCSS('opacity', '1');
    const roles = page.locator('.acceso__rol');
    await expect(roles).toHaveCount(6);
    // La tarjeta tiene desplazamiento propio: cada rol debe ser alcanzable,
    // con texto e icono contenidos, aunque no quepan los seis a la vez.
    for (const rol of await roles.all()) {
      await rol.scrollIntoViewIfNeeded();
      expect(await rol.evaluate(e => {
        const r = e.getBoundingClientRect();
        const texto = e.querySelector('.acceso__rol-texto')!.getBoundingClientRect();
        const icono = e.querySelector('.acceso__rol-icono')!.getBoundingClientRect();
        return r.top >= -1 && r.bottom <= innerHeight + 1 && r.left >= 0 && r.right <= innerWidth + 1
          && r.width >= 44 && r.height >= 44 && texto.right <= r.right + 1 && texto.bottom <= r.bottom + 1
          && (icono.right <= texto.left + 1 || icono.bottom <= texto.top + 1);
      }), `${JSON.stringify(tamano)}: ${await rol.textContent()}`).toBe(true);
    }
    await page.locator('.acceso__tarjeta').evaluate(e => { e.scrollTop = 0; });
  }
  await page.setViewportSize({width:1440,height:900});
  await esperar();
  expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()).violations).toEqual([]);
  await page.screenshot({path:info.outputPath('portada-clinicai-turquesa.png')});
});

test('todos los roles consultan las herramientas de un paciente recién creado', async ({ page, request }) => {
  test.setTimeout(150_000);
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, {data:{codigo_rol:'administrador_clinica'}});
  expect(acceso.ok()).toBe(true);
  const headers = {Authorization:`Bearer ${(await acceso.json()).token_acceso}`, 'Idempotency-Key':randomUUID()};
  const documento = String(Date.now());
  const alta = await request.post(`${API}/pacientes/`, {headers,data:{nombre:'Ficha compartida',apellido:'Sintética',tipo_documento:'PASAPORTE',numero_documento:documento}});
  expect(alta.status()).toBe(201);
  for (const rol of ['recepcion','asistente','administradora','auditor','superadministrador','profesional'] satisfies Rol[]) {
    await acceder(page,rol);await irA(page,'Pacientes');
    const busqueda=page.getByRole('form',{name:'Buscar pacientes'});
    await busqueda.getByRole('textbox',{name:/buscar por nombre/i}).fill(documento);
    await busqueda.getByRole('button',{name:'Buscar',exact:true}).click();
    await page.getByRole('row').filter({hasText:documento}).getByRole('button',{name:'Ver ficha',exact:true}).click();
    await expect(page.getByRole('tab',{name:'Historia y recetas',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'Elegir qué registrar',exact:true}).click();
    const herramientas=page.getByRole('dialog',{name:'Herramientas del paciente',exact:true});
    await expect(herramientas).toBeVisible();
    await expect(herramientas.getByRole('button',{name:/Periodontograma e índice de placa/})).toBeEnabled();
    await expect(herramientas.getByRole('button',{name:/Faciograma Mapa/})).toBeEnabled();
    if(rol!=='profesional'){
      await expect(herramientas).not.toContainText('Consultar y registrar');
      await expect(herramientas.getByRole('button',{name:'Comenzar atención sin cita',exact:true})).toHaveCount(0);
    }
    await herramientas.getByRole('button',{name:/Periodontograma e índice de placa/}).click();
    await expect(page.getByRole('heading',{name:'Periodontograma',exact:true})).toBeVisible();
    await expect(page.getByRole('heading',{name:'Aún no hay controles periodontales'})).toBeVisible();
    if(rol!=='profesional') await expect(page.getByRole('button',{name:'Nuevo examen',exact:true})).toHaveCount(0);
    const rechazos = await page.locator('[role="alert"]').allTextContents();
    expect(rechazos.filter(t=>/no existe|sin permiso|no disponible/i.test(t)),rol).toEqual([]);
  }
  await page.screenshot({path:'../tmp/qa-20261007/ficha-paciente-herramientas.png'});
});

test('primera atención sin cita y consulta posterior sin edición para asistencia', async ({ page, request }) => {
  test.setTimeout(60_000);
  const acceso = await request.post(`${API}/autenticacion/sesion-local`, {data:{codigo_rol:'administrador_clinica'}});
  expect(acceso.ok()).toBe(true);
  const documento = String(Date.now());
  const alta = await request.post(`${API}/pacientes/`, {headers:{Authorization:`Bearer ${(await acceso.json()).token_acceso}`,'Idempotency-Key':randomUUID()},
    data:{nombre:'Primera atención',apellido:'Sintética',tipo_documento:'PASAPORTE',numero_documento:documento}});
  expect(alta.status()).toBe(201);
  for(const rol of ['profesional','asistente'] satisfies Rol[]){
    await acceder(page,rol);await irA(page,'Pacientes');
    const busqueda=page.getByRole('form',{name:'Buscar pacientes'});
    await busqueda.getByRole('textbox',{name:/buscar por nombre/i}).fill(documento);
    await busqueda.getByRole('button',{name:'Buscar',exact:true}).click();
    await page.getByRole('row').filter({hasText:documento}).getByRole('button',{name:'Ver ficha',exact:true}).click();
    await page.getByRole('button',{name:'Elegir qué registrar',exact:true}).click();
    const herramientas=page.getByRole('dialog',{name:'Herramientas del paciente',exact:true});
    if(rol==='profesional'){
      const inicio=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/atencion-profesional'));
      await herramientas.getByRole('button',{name:'Comenzar atención sin cita',exact:true}).click();
      expect((await inicio).status()).toBe(204);
      await page.getByRole('button',{name:'Nueva nota',exact:true}).click();
      const editor=page.getByRole('dialog',{name:'Nueva nota de evolución',exact:true});
      await editor.getByLabel('Motivo de consulta',{exact:true}).fill(`Primera evaluación sintética ${documento}`);
      await editor.getByLabel('Subjetivo (lo que refiere el paciente)',{exact:true}).fill('Registro sintético de primera atención para verificar el recorrido.');
      const guardado=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/historia/notas'));
      await editor.getByRole('button',{name:'Guardar nota',exact:true}).click();
      expect((await guardado).status()).toBe(201);
      await expect(editor).not.toBeVisible();
    }else{
      await herramientas.getByRole('button',{name:/Odontograma Piezas/}).click();
      await page.getByRole('button',{name:'Elegir qué registrar',exact:true}).click();
      await herramientas.getByRole('button',{name:/Evolución y antecedentes/}).click();
      await expect(page.getByRole('button',{name:'Nueva nota',exact:true})).toHaveCount(0);
      await expect(page.getByRole('button',{name:'Corregir',exact:true})).toHaveCount(0);
    }
    await expect(page.locator('app-historia-clinica')).toContainText(`Primera evaluación sintética ${documento}`);
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'Elegir qué registrar',exact:true}).click();
    await expect(herramientas).toBeVisible();
    expect(await herramientas.evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1;})).toBe(true);
    await herramientas.getByRole('button',{name:'Cerrar',exact:true}).click();
    await page.setViewportSize({width:1440,height:900});
  }
});
