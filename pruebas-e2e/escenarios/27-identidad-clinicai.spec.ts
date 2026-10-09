import { test, expect } from '../apoyo/prueba';
import { acceder } from '../apoyo/sesion';

test('los cuatro vectores de ClinicAI son portables y se sirven sin fuentes externas', async ({ page }) => {
  for (const nombre of ['simbolo', 'logo-claro', 'logo-oscuro', 'logo-monocromo']) {
    const respuesta = await page.request.get(`/images/clinicai-${nombre}.svg`);
    expect(respuesta.status()).toBe(200);
    expect(respuesta.headers()['content-type']).toContain('image/svg+xml');
    const svg = await respuesta.text();
    expect(svg).toContain('<title id="titulo">ClinicAI</title>');
    expect(svg).toContain('aria-labelledby="titulo descripcion"');
    expect(svg).not.toMatch(/<(script|foreignObject|text)\b|https?:\/\/(?!www.w3.org\/2000\/svg)/);
    expect(svg).toContain('<path');
  }
});

test('PNG transparentes, favicon y manifiesto usan la misma identidad', async ({ page }) => {
  await page.goto('/acceso');
  const manifest = await page.request.get('/manifest.webmanifest');
  expect(manifest.status()).toBe(200);
  const datos = await manifest.json();
  expect(datos.short_name).toBe('ClinicAI');
  expect(datos.theme_color).toBe('#0e2935');
  expect(datos.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ src: 'images/clinicai-icono-192.png', sizes: '192x192', purpose: 'any' }),
    expect.objectContaining({ src: 'images/clinicai-icono-512.png', sizes: '512x512', purpose: 'any' }),
    expect.objectContaining({ src: 'images/clinicai-icono-maskable-512.png', sizes: '512x512', purpose: 'maskable' }),
  ]));
  for (const [archivo, ancho, alto, transparente] of [
    ['clinicai-logo-claro.png', 1436, 512, true],
    ['clinicai-logo-oscuro.png', 1436, 512, true],
    ['clinicai-logo-monocromo.png', 1436, 512, true],
    ['clinicai-icono-192.png', 192, 192, true],
    ['clinicai-icono-512.png', 512, 512, true],
    ['clinicai-icono-maskable-512.png', 512, 512, false],
    ['clinicai-apple-touch.png', 180, 180, false],
  ] as const) {
    const imagen = await page.evaluate(async archivo => {
      const img = new Image();
      img.src = `/images/${archivo}`;
      await img.decode();
      const lienzo = document.createElement('canvas');
      lienzo.width = img.naturalWidth;
      lienzo.height = img.naturalHeight;
      const pincel = lienzo.getContext('2d')!;
      pincel.drawImage(img, 0, 0);
      return { ancho: img.naturalWidth, alto: img.naturalHeight, alfaEsquina: pincel.getImageData(0, 0, 1, 1).data[3] };
    }, archivo);
    expect(imagen, archivo).toEqual({ ancho, alto, alfaEsquina: transparente ? 0 : 255 });
  }
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute('href', '/images/clinicai-simbolo.svg');
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute('href', '/images/clinicai-apple-touch.png');
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', datos.theme_color);
  const ico = await page.request.get('/favicon.ico');
  expect(ico.status()).toBe(200);
  const fichero = await ico.body();
  expect(fichero.readUInt16LE(2)).toBe(1);
  expect(fichero.readUInt16LE(4)).toBe(4);
  expect([0, 1, 2, 3].map(i => fichero[6 + i * 16])).toEqual([16, 32, 48, 64]);
});

test('la marca se ve completa en el menú y en la cabecera móvil', async ({ page }) => {
  await acceder(page, 'recepcion');
  for (const tamano of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }, { width: 900, height: 768 }, { width: 821, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 844 }, { width: 320, height: 568 }]) {
    await page.setViewportSize(tamano);
    const marca = tamano.width > 820
      ? page.locator('.navegacion__marca .marca')
      : page.locator('.cabecera__marca .marca');
    await expect(marca).toBeVisible();
    await expect(marca).toHaveAccessibleName('ClinicAI · Gestión clínica con inteligencia artificial');
    await expect(marca.locator('.marca__nombre')).toHaveText('ClinicAI');
    await marca.locator('img').evaluate(img => (img as HTMLImageElement).decode());
    const limites = await marca.evaluate(elemento => {
      const r = elemento.getBoundingClientRect();
      const siguiente = elemento.closest('.cabecera')?.querySelector('.cabecera__notificaciones')?.getBoundingClientRect();
      return { dentro: r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1, sinSolapamiento: !siguiente || r.right <= siguiente.left + 1 };
    });
    expect(limites, JSON.stringify(tamano)).toEqual({ dentro: true, sinSolapamiento: true });
    if (tamano.width > 820) await expect(marca.locator('.marca__descriptor')).toHaveText('Gestión clínica con IA');
    else await expect(marca.locator('.marca__descriptor')).toHaveCount(0);
  }
});
