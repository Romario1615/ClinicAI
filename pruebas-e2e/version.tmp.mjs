import { chromium } from '@playwright/test';
import { writeFileSync } from 'node:fs';
const S = process.env.SALIDA, TITULO = process.env.TITULO;
writeFileSync(`${S}/horarios-v2.txt`, 'Horario de atención sintético actualizado. Los sábados la clínica atiende de 9:00 a 12:00. Los domingos no hay atención.');
const b = await chromium.launch();
const errores = [];
async function entrar(rol, seccion = '/conocimiento') {
  const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
  p.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 400) errores.push(`${r.status()} ${r.request().method()} ${r.url().replace(/^.*api\/v1/, '')}`); });
  await p.goto('http://localhost:4200/acceso');
  await p.getByRole('button', { name: rol }).click();
  await p.waitForURL(/\/(panel|agenda)/);
  await p.getByRole('navigation', { name: 'Secciones' }).locator(`a[href="${seccion}"]`).click();
  await p.waitForLoadState('networkidle');
  return p;
}
const fila = (p) => p.getByRole('row').filter({ hasText: TITULO });
async function accion(p, nombre) {
  const boton = fila(p).getByRole('button', { name: nombre });
  await boton.click({ timeout: 8000 });
  await p.waitForTimeout(1500);
  console.log('ok', nombre, '·', (await fila(p).innerText()).replace(/\s+/g, ' ').slice(0, 120));
}
let p = await entrar(/administración de clínica/i);
await accion(p, 'Retirar para corregir');
await fila(p).getByRole('button', { name: /versión nueva/i }).click();
const d = p.getByRole('dialog');
await d.locator('input[type=file]').setInputFiles(`${S}/horarios-v2.txt`);
await d.getByRole('button', { name: 'Subir versión' }).click();
await d.getByRole('button', { name: 'Listo' }).click();
await accion(p, 'Enviar a revisión');
await p.close();
p = await entrar(/profesional de salud/i);
await accion(p, 'Aprobar');
await accion(p, 'Publicar');
await p.close();
p = await entrar(/recepción/i, '/asistente');
const chat = p.getByRole('region', { name: 'Conversación con el asistente' });
await chat.getByLabel('Mensaje').fill('¿Qué horario tiene la clínica los sábados?');
await chat.getByRole('button', { name: 'Enviar' }).click();
await chat.locator('article.mensaje').nth(1).waitFor({ timeout: 20000 });
await p.waitForTimeout(800);
const respuesta = (await chat.locator('article.mensaje').last().innerText()).replace(/\s+/g, ' ');
console.log('ASISTENTE:', respuesta.slice(0, 300));
console.log('nuevo 9:00-12:00 =', respuesta.includes('9:00 a 12:00'), '| viejo 8:00-13:00 =', respuesta.includes('8:00 a 13:00'));
console.log('ERRORES', JSON.stringify(errores));
await b.close();
