import { chromium } from '@playwright/test';
import { writeFileSync } from 'node:fs';
const S = process.env.SALIDA;
const TITULO = `Horarios de fin de semana ${Date.now()}`;
const archivo = `${S}/horarios.txt`;
writeFileSync(archivo, 'Horario de atención sintético. Los sábados la clínica atiende de 8:00 a 13:00. Los domingos y feriados no hay atención. Para urgencias fuera de horario llame a la línea de la clínica.');
const b = await chromium.launch();
const errores = [];
async function entrar(rol) {
  const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
  p.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 400) errores.push(`${rol} ${r.status()} ${r.request().method()} ${r.url().replace(/^.*api\/v1/, '')}`); });
  await p.goto('http://localhost:4200/acceso');
  await p.getByRole('button', { name: rol }).click();
  await p.waitForURL(/\/(panel|agenda)/);
  await p.getByRole('navigation', { name: 'Secciones' }).locator('a[href="/conocimiento"]').click();
  await p.waitForLoadState('networkidle');
  return p;
}
const paso = async (p, n) => { await p.waitForTimeout(700); await p.screenshot({ path: `${S}/${n}.png` }); console.log('paso', n); };
const fila = (p) => p.getByRole('row').filter({ hasText: TITULO });
async function accion(p, nombre, n) {
  const boton = fila(p).getByRole('button', { name: nombre });
  await boton.waitFor({ timeout: 8000 }).catch(() => {});
  if (!(await boton.isVisible().catch(() => false))) { console.log('NO VISIBLE', nombre); await fila(p).scrollIntoViewIfNeeded().catch(() => {}); await paso(p, `x-${n}`); return false; }
  await boton.click();
  await p.waitForTimeout(1500);
  await paso(p, n);
  return true;
}
// 1. Administración carga y envía a revisión.
let p = await entrar(/administración de clínica/i);
await p.getByRole('button', { name: 'Cargar documento' }).first().click();
const d = p.getByRole('dialog');
await d.getByLabel('Título').fill(TITULO);
await d.locator('input[type=file]').setInputFiles(archivo);
await d.getByRole('button', { name: 'Cargar documento' }).click();
await d.getByRole('button', { name: 'Listo' }).click();
await accion(p, 'Enviar a revisión', '01-en-revision');
await p.close();
// 2. Profesional aprueba, publica y habilita para el asistente.
p = await entrar(/profesional de salud/i);
await accion(p, 'Aprobar', '02-aprobado');
await accion(p, 'Publicar', '03-publicado');
if (await accion(p, 'Accesos', '04-accesos')) {
  const panel = p.getByRole('region', { name: 'Accesos del documento' });
  console.log('ACCESOS:', (await panel.innerText()).replace(/\s+/g, ' ').slice(0, 600));
}
console.log('ERRORES', JSON.stringify(errores));
console.log('TITULO', TITULO);
await b.close();
