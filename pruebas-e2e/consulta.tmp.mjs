import { chromium } from '@playwright/test';
const S = process.env.SALIDA;
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
const errores = [];
p.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 400) errores.push(`${r.status()} ${r.url().replace(/^.*api\/v1/, '')}`); });
await p.goto('http://localhost:4200/acceso');
await p.getByRole('button', { name: /recepción/i }).click();
await p.waitForURL(/\/(panel|agenda)/);
const nav = p.getByRole('navigation', { name: 'Secciones' });
// Búsqueda del personal
await nav.locator('a[href="/conocimiento"]').click();
await p.getByLabel('¿Qué necesita consultar?').fill('¿atienden el fin de semana?');
await p.getByRole('region', { name: 'Buscar en la base de conocimiento' }).getByRole('button', { name: 'Buscar' }).click();
await p.waitForTimeout(2500);
await p.screenshot({ path: `${S}/10-busqueda.png` });
console.log('BUSQUEDA:', (await p.getByRole('region', { name: 'Buscar en la base de conocimiento' }).innerText()).replace(/\s+/g, ' ').slice(0, 400));
// Asistente
await nav.locator('a[href="/asistente"]').click();
const chat = p.getByRole('region', { name: 'Conversación con el asistente' });
await chat.getByLabel('Mensaje').fill('¿Qué horario tiene la clínica los sábados?');
await chat.getByRole('button', { name: 'Enviar' }).click();
await chat.locator('article.mensaje').nth(1).waitFor({ timeout: 20000 });
await p.waitForTimeout(800);
console.log('ASISTENTE:', (await chat.locator('article.mensaje').last().innerText()).replace(/\s+/g, ' ').slice(0, 400));
await p.screenshot({ path: `${S}/11-asistente.png` });
console.log('ERRORES', JSON.stringify(errores));
await b.close();
