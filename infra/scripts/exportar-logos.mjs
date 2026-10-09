/** Exporta los vectores propios a PNG, ICO y una lámina de presentación. */
import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const raiz = fileURLToPath(new URL('../../', import.meta.url));
const imagenes = resolve(raiz, 'frontend/public/images');
const require = createRequire(new URL('../../pruebas-e2e/package.json', import.meta.url));
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const uri = svg => `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
const simbolo = await readFile(resolve(imagenes, 'clinicai-simbolo.svg'), 'utf8');
const claro = await readFile(resolve(imagenes, 'clinicai-logo-claro.svg'), 'utf8');
const oscuro = await readFile(resolve(imagenes, 'clinicai-logo-oscuro.svg'), 'utf8');
const monocromo = await readFile(resolve(imagenes, 'clinicai-logo-monocromo.svg'), 'utf8');

async function png(svg, ancho, alto, fondo = 'transparent', tamanoImagen = ancho) {
  await page.setViewportSize({ width: ancho, height: alto });
  await page.setContent(`<style>html,body{margin:0;width:100%;height:100%;background:${fondo}}body{display:grid;place-items:center}img{width:${tamanoImagen}px;height:auto;display:block}</style><img alt="ClinicAI" src="${uri(svg)}">`);
  await page.locator('img').evaluate(img => img.decode());
  return page.screenshot({ omitBackground: fondo === 'transparent' });
}

try {
  for (const [nombre, svg] of [['claro', claro], ['oscuro', oscuro], ['monocromo', monocromo]]) {
    const ancho = Number(svg.match(/viewBox="0 0 (\d+) 128"/)[1]);
    await writeFile(resolve(imagenes, `clinicai-logo-${nombre}.png`), await png(svg, ancho * 4, 512));
  }
  for (const medida of [192, 512]) {
    await writeFile(resolve(imagenes, `clinicai-icono-${medida}.png`), await png(simbolo, medida, medida));
  }
  await writeFile(resolve(imagenes, 'clinicai-icono-maskable-512.png'), await png(simbolo, 512, 512, '#80DEDF', 384));
  await writeFile(resolve(imagenes, 'clinicai-apple-touch.png'), await png(simbolo, 180, 180, '#80DEDF'));

  // ICO multiresolución: cada entrada contiene el PNG de ese tamaño.
  const medidas = [16, 32, 48, 64];
  const iconos = [];
  for (const medida of medidas) iconos.push(await png(simbolo, medida, medida));
  const cabecera = Buffer.alloc(6 + medidas.length * 16);
  cabecera.writeUInt16LE(1, 2);
  cabecera.writeUInt16LE(medidas.length, 4);
  let posicion = cabecera.length;
  medidas.forEach((medida, indice) => {
    const entrada = 6 + indice * 16;
    cabecera[entrada] = medida;
    cabecera[entrada + 1] = medida;
    cabecera.writeUInt16LE(1, entrada + 4);
    cabecera.writeUInt16LE(32, entrada + 6);
    cabecera.writeUInt32LE(iconos[indice].length, entrada + 8);
    cabecera.writeUInt32LE(posicion, entrada + 12);
    posicion += iconos[indice].length;
  });
  await writeFile(resolve(raiz, 'frontend/public/favicon.ico'), Buffer.concat([cabecera, ...iconos]));

  const fuente = await readFile(resolve(raiz, 'frontend/node_modules/@fontsource-variable/plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2'));
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.setContent(`<!doctype html><html lang="es"><head><style>
    @font-face{font-family:Jakarta;src:url(data:font/woff2;base64,${fuente.toString('base64')}) format('woff2');font-weight:200 800}
    *{box-sizing:border-box}body{margin:0;font-family:Jakarta,sans-serif;color:#133f52;background:#f3fafb}
    .oscuro{position:relative;height:420px;padding:38px 64px;overflow:hidden;background:radial-gradient(ellipse at 82% 30%,#1b5860 0,transparent 48%),#0e2935;color:#b3d8dd}
    .oscuro:after{content:'';position:absolute;width:570px;height:570px;right:-180px;top:-120px;border:1px solid #86e2e122;border-radius:50%}
    header{display:flex;justify-content:space-between;font-size:11px;letter-spacing:3px;font-weight:650;text-transform:uppercase}
    .principal{display:block;width:660px;margin:36px 0 10px}
    .mensaje{margin:0 0 0 222px;font-size:15px;letter-spacing:.1px;color:#b3d8dd}
    .claro{display:grid;grid-template-columns:1.1fr .9fr;gap:70px;padding:38px 64px}
    h2{font-size:10px;font-weight:750;letter-spacing:2px;margin:0 0 22px;color:#456875;text-transform:uppercase}
    .secundario{width:440px;display:block}
    .aplicaciones{display:flex;gap:16px;align-items:center;margin-bottom:29px;height:90px}
    .aplicaciones img{width:78px}.aplicaciones .mini{width:36px}.aplicaciones .mono{width:245px;margin-left:7px}
    .paleta{display:flex;align-items:center;gap:11px;font-size:10px;color:#456875}
    .muestra{display:inline-block;width:30px;height:30px;border-radius:10px;border:1px solid #133f520a}
    .nota{margin:28px 0 0;font-size:12px;color:#456875;line-height:1.7}
  </style></head><body>
    <section class="oscuro"><header><span>ClinicAI / Identidad visual</span><span>Clínicas conectadas con inteligencia</span></header>
      <img class="principal" src="${uri(oscuro)}" alt="ClinicAI, gestión clínica con IA">
      <p class="mensaje">Cuidado, conexión e inteligencia.</p>
    </section>
    <section class="claro"><div><h2>Marca sobre fondo claro</h2><img class="secundario" src="${uri(claro)}" alt="ClinicAI sobre fondo claro"><p class="nota">Una C que reúne el cuidado clínico y una red de IA.<br>Vector escalable · PNG transparente · Iconos de aplicación</p></div>
      <div><h2>Símbolo y versión de una tinta</h2><div class="aplicaciones"><img src="${uri(simbolo)}" alt="Símbolo ClinicAI"><img class="mini" src="${uri(simbolo)}" alt="Icono pequeño"><img class="mono" src="${uri(monocromo)}" alt="Logo de una tinta"></div>
        <h2>Celeste + turquesa</h2><div class="paleta"><span class="muestra" style="background:#b9eff8"></span><span>#B9EFF8</span><span class="muestra" style="background:#51c7b7"></span><span>#51C7B7</span><span class="muestra" style="background:#133f52"></span><span>#133F52</span></div>
      </div>
    </section>
  </body></html>`);
  await page.locator('img').evaluateAll(imgs => Promise.all(imgs.map(img => img.decode())));
  await page.evaluate(() => document.fonts.ready);
  const destino = resolve(raiz, 'docs/imagenes');
  await mkdir(destino, { recursive: true });
  await page.screenshot({ path: resolve(destino, 'clinicai-identidad.png') });
  console.log('Exportados: tres logos PNG, iconos PWA/iOS, favicon ICO y lámina de identidad.');
} finally {
  await browser.close();
}
