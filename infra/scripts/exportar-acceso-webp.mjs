/** Exporta fotos existentes y pictogramas propios del acceso a WebP real. */
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const raiz = fileURLToPath(new URL('../../', import.meta.url));
const imagenes = resolve(raiz, 'frontend/public/images');
const require = createRequire(new URL('../../pruebas-e2e/package.json', import.meta.url));
const { chromium } = require('playwright');
const fotos = [
  ['acceso-equipo', 'png'],
  ['panel-seguimiento-clinicai', 'jpg'],
  ['acceso-clinica-recepcion', 'jpg'],
  ['panel-clinicai-dental-network-v1', 'jpg'],
];
// Los trazados conservan la familia de pictogramas ya usada en el acceso.
const escudo = 'M12 3.25 19 6v5.2c0 4.4-2.9 7.4-7 9.55-4.1-2.15-7-5.15-7-9.55V6l7-2.75ZM9 12l2 2 4-4';
const iconos = {
  administradora: escudo,
  superadministrador: 'M4 21V7h10v14M14 11h6v10M8 11h2M8 15h2M8 19h2M17 15h1M17 19h1M7 7V3h4v4',
  recepcion: 'M4 8h16v11H4zM4 11h16M8 8V5h8v3M9 15h6',
  profesional: 'M12 21s-7.5-4.1-7.5-10.4A4.3 4.3 0 0 1 12 7.9a4.3 4.3 0 0 1 7.5 2.7C19.5 16.9 12 21 12 21ZM12 10v6M9 13h6',
  asistente: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21a8 8 0 0 1 16 0M15.5 15l1.5 2 2-3',
  auditor: 'M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h3M14 16l1.5 1.5L19 14',
  agenda: 'M5 7h14v12H5zM5 11h14M9 5v4M15 5v4M9 15h2',
  agente: 'M9 4h6M12 4v3M5 7h14v12H5zM8 11h1M15 11h1M9 15h6M2 10v5M22 10v5',
  conocimiento: 'M6 5h9l3 3v11H6zM15 5v3h3M9 12h6M9 15h4',
  seguridad: escudo,
};
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

async function exportar(nombre, contenido, mime, ancho, calidad) {
  const datos = await page.evaluate(async ({ uri, ancho, calidad }) => {
    const imagen = new Image();
    imagen.src = uri;
    await imagen.decode();
    const lienzo = document.createElement('canvas');
    lienzo.width = Math.min(ancho, imagen.naturalWidth);
    lienzo.height = Math.round(imagen.naturalHeight * lienzo.width / imagen.naturalWidth);
    lienzo.getContext('2d').drawImage(imagen, 0, 0, lienzo.width, lienzo.height);
    return { uri: lienzo.toDataURL('image/webp', calidad), ancho: lienzo.width, alto: lienzo.height };
  }, { uri: `data:${mime};base64,${contenido.toString('base64')}`, ancho, calidad });
  if (!datos.uri.startsWith('data:image/webp;base64,')) throw new Error('Chromium no exporta WebP.');
  const salida = Buffer.from(datos.uri.split(',')[1], 'base64');
  if (salida.toString('ascii', 0, 4) !== 'RIFF' || salida.toString('ascii', 8, 12) !== 'WEBP') throw new Error('Formato WebP inválido.');
  await writeFile(resolve(imagenes, `${nombre}.webp`), salida);
  console.log(`${nombre}.webp: ${datos.ancho} × ${datos.alto}, ${salida.length} bytes`);
  return salida.length;
}

try {
  let originales = 0;
  let webp = 0;
  for (const [nombre, extension] of fotos) {
    const contenido = await readFile(resolve(imagenes, `${nombre}.${extension}`));
    originales += contenido.length;
    webp += await exportar(nombre, contenido, extension === 'png' ? 'image/png' : 'image/jpeg', 1920, .83);
    await exportar(`${nombre}-900`, contenido, extension === 'png' ? 'image/png' : 'image/jpeg', 900, .81);
  }
  await exportar('clinicai-simbolo', await readFile(resolve(imagenes, 'clinicai-icono-512.png')), 'image/png', 192, 1);
  for (const [nombre, trazado] of Object.entries(iconos)) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24"><path d="${trazado}" fill="none" stroke="#086c7f" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    await exportar(`acceso-icono-${nombre}`, Buffer.from(svg), 'image/svg+xml', 96, 1);
  }
  console.log(`Fotos grandes: ${originales} → ${webp} bytes (${(100 * (1 - webp / originales)).toFixed(1)} % menos). Originales conservados.`);
} finally {
  await browser.close();
}
