/** Recorridos con PostgreSQL real y datos exclusivamente sintéticos. */
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import AxeBuilder from '@axe-core/playwright';
import type { APIRequestContext, Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, irA } from '../apoyo/sesion';
import { pacienteConNotas } from '../apoyo/datos';

const API=process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';
const IMAGEN=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6wsAAAAASUVORK5CYII=','base64');

test('el agente prepara cambios, descarta y confirma la cancelación de su paciente',async({page,request})=>{
  test.setTimeout(60_000);
  const token=await request.post(`${API}/autenticacion/sesion-local`,{data:{codigo_rol:'administrador_clinica'}});
  expect(token.ok()).toBeTruthy();
  const headers={Authorization:`Bearer ${(await token.json()).token_acceso}`};
  const leer=async(ruta:string)=>{const r=await request.get(API+ruta,{headers});expect(r.ok(),ruta).toBeTruthy();return r.json();};
  const sede=(await leer('/catalogo/sedes'))[0],servicio=(await leer('/catalogo/servicios'))[0];
  const profesional=(await leer(`/catalogo/profesionales?sede_id=${sede.id}&especialidad_id=${servicio.especialidad_id}`))[0];
  const desde=new Date(Date.now()+21*86400000).toISOString(),hasta=new Date(Date.now()+28*86400000).toISOString();
  const query=new URLSearchParams({sede_id:sede.id,profesional_id:profesional.id,servicio_id:servicio.id,desde,hasta});
  const turno=(await leer(`/agenda/disponibilidad?${query}`)).turnos[0];expect(turno).toBeTruthy();
  const nombre=`Paciente agente E2E ${randomUUID().slice(0,8)}`;
  const alta=await request.post(`${API}/pacientes/`,{headers:{...headers,'Idempotency-Key':randomUUID()},data:{nombre,apellido:'Sintético',tipo_documento:'SIN_DOCUMENTO'}});
  expect(alta.status(),await alta.text()).toBe(201);const paciente=await alta.json();
  const reserva=await request.post(`${API}/agenda/citas`,{headers:{...headers,'Idempotency-Key':randomUUID()},data:{sede_id:sede.id,profesional_id:profesional.id,servicio_id:servicio.id,paciente_id:paciente.id,inicio:turno.inicio}});
  expect(reserva.status(),await reserva.text()).toBe(201);const cita=await reserva.json();expect(cita.estado).toBe('CONFIRMED');
  await acceder(page,'administradora');await irA(page,'Pacientes');
  const buscar=page.getByRole('form',{name:'Buscar pacientes'});await buscar.getByRole('textbox',{name:/buscar por nombre/i}).fill(nombre);await buscar.getByRole('button',{name:'Buscar',exact:true}).click();
  await page.getByRole('row').filter({hasText:nombre}).getByRole('button',{name:'Ver ficha'}).click();
  await page.getByRole('button',{name:'Agente del paciente',exact:true}).click();
  const agente=page.getByRole('region',{name:'Agente del paciente'});await expect(agente).toContainText('Funciones locales');
  await agente.getByRole('button',{name:'Mis citas',exact:true}).click();
  await agente.getByRole('button',{name:'Usar esta cita',exact:true}).click();
  await expect(agente).toContainText('Cita seleccionada:');
  await agente.locator('summary').filter({hasText:'Más gestiones'}).click();
  await agente.getByLabel('Motivo para cancelar la cita seleccionada').fill('Solicitud administrativa sintética E2E');
  await agente.getByRole('button',{name:'Preparar cancelación',exact:true}).click();
  await expect(agente.getByRole('button',{name:'Confirmar acción'})).toBeVisible();
  expect((await leer(`/agenda/citas/${cita.id}`)).estado).toBe('CONFIRMED');
  await agente.getByRole('button',{name:'Descartar',exact:true}).click();
  await expect(agente.getByRole('button',{name:'Confirmar acción'})).toHaveCount(0);
  expect((await leer(`/agenda/citas/${cita.id}`)).estado).toBe('CONFIRMED');
  await agente.getByRole('button',{name:'Preparar cancelación',exact:true}).click();
  await agente.getByRole('button',{name:'Confirmar acción',exact:true}).click();
  await expect.poll(async()=>(await leer(`/agenda/citas/${cita.id}`)).estado).toBe('CANCELLED');
  await expect(agente.getByRole('button',{name:'Confirmar acción'})).toHaveCount(0);
});

async function ficha(page:Page,request:APIRequestContext){
  const paciente=await pacienteConNotas(request);
  await acceder(page,'profesional');await irA(page,'Pacientes');
  const busqueda=page.getByRole('form',{name:'Buscar pacientes'});
  await busqueda.getByRole('textbox',{name:/buscar por nombre/i}).fill(paciente.numero_documento!);
  await busqueda.getByRole('button',{name:'Buscar',exact:true}).click();
  await page.getByRole('row').filter({hasText:paciente.numero_documento!}).getByRole('button',{name:'Ver ficha'}).click();
  return paciente;
}

test('periodontograma: seis sitios, fotos privadas, persistencia, PDF y diseño móvil',async({page,request})=>{
  await ficha(page,request);
  await page.getByRole('tab',{name:'Periodoncia',exact:true}).click();
  await page.getByRole('button',{name:'Nuevo examen',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Registrar examen periodontal'});
  await editor.getByRole('combobox',{name:/^Sede/}).selectOption({index:1});
  await editor.getByRole('button',{name:'Editar pieza 16',exact:true}).click();
  const sitios=editor.locator('fieldset.perio__sitio');await expect(sitios).toHaveCount(6);
  await sitios.nth(0).getByLabel('Profundidad (mm)',{exact:true}).fill('4');
  await sitios.nth(0).getByLabel('Margen (mm)',{exact:true}).fill('2');
  await sitios.nth(0).getByLabel('Sangrado',{exact:true}).selectOption({label:'Sí'});
  await sitios.nth(1).getByLabel('Profundidad (mm)',{exact:true}).fill('3');
  await sitios.nth(1).getByLabel('Sangrado',{exact:true}).selectOption({label:'No'});
  await editor.getByRole('button',{name:'Aplicar pieza 16'}).click();
  await editor.getByLabel('Motivo del registro o corrección').fill('Control periodontal sintético E2E');
  await editor.locator('app-captura-fotos input[type=file]').first().setInputFiles({name:'control-sintetico.png',mimeType:'image/png',buffer:IMAGEN});
  const guardado=page.waitForResponse(r=>r.request().method()==='POST' && /\/periodontogramas$/.test(r.url()));
  await editor.getByRole('button',{name:'Guardar examen',exact:true}).click();
  const resultado=await guardado;expect(resultado.status(),await resultado.text()).toBe(201);
  const datos=await resultado.json();expect(datos.resumen.sitios_sondados).toBe(2);expect(datos.resumen.sangrado_porcentaje).toBe(50);
  await expect(editor).not.toBeVisible();
  await expect(page.locator('.perio__metricas')).toContainText('2 / 192');
  await expect(page.locator('.perio__metricas')).toContainText('50%');
  await page.getByRole('button',{name:'Palatina / lingual',exact:true}).click();
  const descarga=page.waitForEvent('download');await page.locator('app-periodontograma').getByRole('button',{name:'Descargar PDF'}).click();
  expect((await readFile((await (await descarga).path())!)).subarray(0,5).toString()).toBe('%PDF-');
  await page.locator('app-periodontograma').getByRole('button',{name:'Fotos y adjuntos'}).click();
  const galeria=page.getByRole('dialog',{name:'Fotos del registro'});
  await expect(galeria.locator('figure img')).toHaveCount(1);
  await expect(galeria.locator('figure img')).toBeVisible();
  await page.screenshot({path:'../tmp/qa-20261007/periodontograma-fotos.png'});
  await galeria.getByRole('button',{name:'Cerrar Fotos del registro',exact:true}).click();
  const a11y=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('heading',{name:'Periodontograma',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:'../tmp/qa-20261007/periodontograma-movil.png'});
});

test('agente de la ficha: historial al lado, resumen, citas, permisos y teclado',async({page,request})=>{
  const paciente=await ficha(page,request);
  await page.getByRole('tab',{name:'Historia y recetas',exact:true}).click();
  await page.getByRole('button',{name:'Agente del paciente',exact:true}).click();
  const agente=page.getByRole('region',{name:'Agente del paciente'});
  await expect(agente).toContainText(`${paciente.nombre} ${paciente.apellido}`);
  await expect(agente).toContainText('Funciones locales');
  await agente.getByRole('button',{name:'Resumen clínico',exact:true}).click();
  await expect(agente).toContainText('Resumen de lo registrado');
  await expect(agente).toContainText('Alergias');
  await agente.getByRole('button',{name:'Mis citas',exact:true}).click();
  await expect(agente.getByRole('log')).toContainText(/citas?|proximas/i);
  await page.screenshot({path:'../tmp/qa-20261007/agente-en-ficha.png'});
  const a11y=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
  await agente.getByRole('button',{name:'Cerrar agente del paciente',exact:true}).click();
  await expect(agente).not.toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Agente del paciente',exact:true}).click();
  await expect(agente).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});

test('analítica descriptiva, predictiva y prescriptiva con metodología visible',async({page})=>{
  await acceder(page,'administradora');
  await irA(page,'Analítica IA');
  await expect(page.getByRole('heading',{name:'Tu clínica, con perspectiva'})).toBeVisible();
  await expect(page.locator('.analitica__kpi').first()).toBeVisible();
  await page.getByRole('button',{name:'Predictivo · qué puede pasar',exact:true}).click();
  await expect(page.locator('.analitica__modelo').first()).toBeVisible();
  await expect(page.locator('.analitica__modelo').first()).toContainText(/historia|observaciones/);
  await page.screenshot({path:'../tmp/qa-20261007/analitica-predictiva.png'});
  await page.getByRole('button',{name:'Prescriptivo · qué revisar',exact:true}).click();
  await expect(page.getByText('Cada decisión requiere la revisión de una persona autorizada.',{exact:false})).toBeVisible();
  const a11y=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});

test('recepción tiene apoyo administrativo, sin herramientas ni resumen clínico',async({page,request})=>{
  const paciente=await pacienteConNotas(request);
  await acceder(page,'recepcion');await irA(page,'Pacientes');
  const buscar=page.getByRole('form',{name:'Buscar pacientes'});
  await buscar.getByRole('textbox',{name:/buscar por nombre/i}).fill(paciente.numero_documento!);
  await buscar.getByRole('button',{name:'Buscar',exact:true}).click();
  await page.getByRole('row').filter({hasText:paciente.numero_documento!}).getByRole('button',{name:'Ver ficha'}).click();
  await expect(page.getByRole('tab',{name:'Periodoncia',exact:true})).toHaveCount(0);
  await expect(page.getByRole('tab',{name:'Faciograma',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Agente del paciente',exact:true}).click();
  const agente=page.getByRole('region',{name:'Agente del paciente'});
  await expect(agente.getByRole('button',{name:'Resumen clínico',exact:true})).toHaveCount(0);
  await agente.getByRole('button',{name:'Mis citas',exact:true}).click();
  await expect(agente.getByRole('log')).toContainText(/citas?|proximas/i);
});
