/** Convierte únicamente ilustraciones públicas de la interfaz a WebP. */
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const raiz = fileURLToPath(new URL('../../', import.meta.url));
const imagenes = resolve(raiz, 'frontend/public/images');
const require = createRequire(new URL('../../pruebas-e2e/package.json', import.meta.url));
const { chromium } = require('playwright');
const recursos = [
  ['notificaciones-vacias', 'png', 320],
  ['agenda-turnos', 'png', 640],
  ['pagos-administrativos', 'png', 480],
  ['catalogo-clinica', 'png', 480],
  ['medicacion-seguimiento', 'png', 480],
  ['busqueda-pacientes', 'png', 640],
  ['lista-espera', 'png', 480],
  ['integraciones-clinicai-banner', 'png', 1200],
  ['bandeja-sin-pendientes', 'png', 480],
  ['campanas-pacientes', 'jpg', 1400],
  ['equipo-clinica-colaboracion', 'jpg', 1400],
  ['sedes-red-clinicas', 'jpg', 1400],
  ['usuarios-roles-acceso', 'jpg', 1400],
  ['conocimiento-evidencia', 'jpg', 1400],
  ['historia-clinica-integral', 'jpg', 1400],
];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
try {
  let bytesOriginales = 0;
  let bytesWebp = 0;
  for (const [nombre, extension, limiteAncho] of recursos) {
    const original = await readFile(resolve(imagenes, `${nombre}.${extension}`));
    const mime = extension === 'png' ? 'image/png' : 'image/jpeg';
    const imagen = await page.evaluate(async ({ uri, limiteAncho }) => {
      const img = new Image(); img.src = uri; await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = Math.min(limiteAncho, img.naturalWidth);
      canvas.height = Math.round(img.naturalHeight * canvas.width / img.naturalWidth);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      return { uri:canvas.toDataURL('image/webp', .88), ancho:canvas.width, alto:canvas.height };
    }, { uri:`data:${mime};base64,${original.toString('base64')}`, limiteAncho });
    if (!imagen.uri.startsWith('data:image/webp;base64,')) throw new Error('No se pudo codificar WebP.');
    const salida = Buffer.from(imagen.uri.split(',')[1], 'base64');
    if (salida.toString('ascii', 0, 4) !== 'RIFF' || salida.toString('ascii', 8, 12) !== 'WEBP') throw new Error('WebP inválido.');
    await writeFile(resolve(imagenes, `${nombre}.webp`), salida);
    bytesOriginales += original.length; bytesWebp += salida.length;
    console.log(`${nombre}.webp: ${imagen.ancho} × ${imagen.alto}, ${salida.length} bytes`);
  }
  console.log(`Interfaz: ${bytesOriginales} → ${bytesWebp} bytes (${(100 * (1 - bytesWebp / bytesOriginales)).toFixed(1)} % menos). Originales conservados.`);
} finally {
  await browser.close();
}
