/** Portada WebP: recursos reales, teclado, contraste y acceso de altura reducida. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '../apoyo/prueba';

test('sirve los diecinueve recursos como WebP decodificable y conserva el original', async ({ page }) => {
  const fotos = ['acceso-equipo', 'panel-seguimiento-clinicai', 'acceso-clinica-recepcion', 'panel-clinicai-dental-network-v1'];
  const iconos = ['administradora', 'superadministrador', 'recepcion', 'profesional', 'asistente', 'auditor', 'agenda', 'agente', 'conocimiento', 'seguridad'];
  const archivos = [...fotos.flatMap(f => [f, `${f}-900`]), 'clinicai-simbolo', ...iconos.map(i => `acceso-icono-${i}`)];
  await page.goto('/acceso');
  for (const archivo of archivos) {
    const respuesta = await page.request.get(`/images/${archivo}.webp`);
    expect(respuesta.status(), archivo).toBe(200);
    expect(respuesta.headers()['content-type']).toContain('image/webp');
    const cuerpo = await respuesta.body();
    expect(cuerpo.toString('ascii', 0, 4)).toBe('RIFF');
    expect(cuerpo.toString('ascii', 8, 12)).toBe('WEBP');
    expect(await page.evaluate(async archivo => {
      const img = new Image(); img.src = `/images/${archivo}.webp`; await img.decode();
      return img.naturalWidth > 0 && img.naturalHeight > 0;
    }, archivo)).toBe(true);
  }
  const original = await page.request.get('/images/acceso-equipo.png');
  expect(original.status()).toBe(200);
  expect(original.headers()['content-type']).toContain('image/png');
  expect(await page.evaluate(async () => {
    const img = new Image(); img.src = '/images/clinicai-simbolo.webp'; await img.decode();
    const canvas = document.createElement('canvas'); canvas.width = img.width; canvas.height = img.height;
    const contexto = canvas.getContext('2d')!; contexto.drawImage(img, 0, 0);
    return contexto.getImageData(0, 0, 1, 1).data[3];
  })).toBe(0);
});

test('la portada ocupa la ventana y todos los roles son alcanzables en ocho tamaños', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/acceso');
  await expect(page.getByRole('heading', { name: 'Elige un rol' })).toBeVisible();
  for (const tamano of [{ width:1440,height:900 },{ width:1366,height:768 },{ width:1024,height:768 },{ width:821,height:600 },{ width:900,height:500 },{ width:844,height:390 },{ width:390,height:844 },{ width:320,height:568 }]) {
    await page.setViewportSize(tamano);
    // Espera la actualización de dvh tras el cambio de ventana, sin medir el fotograma anterior.
    await expect(page.locator('.acceso')).toHaveCSS('height', `${tamano.height}px`);
    const medidas = await page.locator('.acceso').evaluate(e => {
      const r = e.getBoundingClientRect();
      const c = e.querySelector('.acceso__tarjeta')!.getBoundingClientRect();
      return { ancho:r.width, alto:r.height, horizontal:document.documentElement.scrollWidth <= innerWidth + 1,
        vertical:document.documentElement.scrollHeight <= innerHeight + 1,
        tarjetaDentro:c.top >= -1 && c.bottom <= innerHeight + 1 && c.left >= -1 && c.right <= innerWidth + 1 };
    });
    expect(medidas, JSON.stringify(tamano)).toEqual({ ancho:tamano.width, alto:tamano.height, horizontal:true, vertical:true, tarjetaDentro:true });
    const botones = page.locator('.acceso__rol');
    await expect(botones).toHaveCount(6);
    for (const boton of await botones.all()) {
      await boton.scrollIntoViewIfNeeded();
      expect(await boton.evaluate(b => {
        const r = b.getBoundingClientRect();
        const texto = b.querySelector('.acceso__rol-texto')!.getBoundingClientRect();
        const icono = b.querySelector('.acceso__rol-icono')!.getBoundingClientRect();
        return r.top >= -1 && r.bottom <= innerHeight + 1 && r.width >= 44 && r.height >= 44 &&
          texto.left >= r.left && texto.right <= r.right + 1 && texto.bottom <= r.bottom + 1 &&
          (icono.right <= texto.left + 1 || icono.bottom <= texto.top + 1);
      }), await boton.textContent()).toBe(true);
    }
    await page.locator('.acceso__tarjeta').evaluate(e => { e.scrollTop = 0; });
    if (tamano.width === 1440 || tamano.width === 390) await page.screenshot({ path:info.outputPath(`acceso-${tamano.width}.png`) });
  }
});

test('el teclado recorre las seis tarjetas sin perder el foco en móvil', async ({ page }) => {
  await page.setViewportSize({width:320,height:568});
  await page.goto('/acceso');
  await expect(page.locator('.acceso__rol')).toHaveCount(6);
  const primero = page.locator('.acceso__rol').first(); await primero.focus();
  for (let i = 0; i < 6; i++) {
    const boton = page.locator('.acceso__rol').nth(i); await expect(boton).toBeFocused();
    expect(await boton.evaluate(e => {
      const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight + 1 && getComputedStyle(e).outlineStyle !== 'none';
    })).toBe(true);
    if (i < 5) await page.keyboard.press('Tab');
  }
});

test('el movimiento reducido fija la foto original y el contraste conserva la accesibilidad', async ({ page }) => {
  await page.emulateMedia({ reducedMotion:'reduce' }); await page.goto('/acceso');
  await expect(page.getByRole('heading',{name:'Elige un rol'})).toBeVisible();
  await expect(page.locator('.acceso__foto').first()).toHaveCSS('opacity','1');
  await expect(page.locator('.acceso__foto').first()).toHaveCSS('animation-name','none');
  for (const contraste of ['no-preference','more'] as const) {
    await page.emulateMedia({ reducedMotion:'reduce', contrast:contraste });
    for (const tamano of [{width:1440,height:900},{width:390,height:844}]) {
      await page.setViewportSize(tamano);
      expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()).violations).toEqual([]);
    }
  }
});

test('el formulario normal y el segundo factor conservan sus campos y errores', async ({ page }) => {
  // Solo presentación: estas dos respuestas son dobles HTTP, no aceptación real de credenciales.
  await page.route('**/autenticacion/accesos-locales', r => r.fulfill({json:{habilitado:false,roles:[]}}));
  let intento = 0;
  await page.route('**/autenticacion/sesion', r => {
    intento++;
    return r.fulfill({ status:intento === 1 ? 401 : 503, json:intento === 1
      ? {codigo:'SEGUNDO_FACTOR_REQUERIDO',mensaje:'Introduce el código de verificación.'}
      : {codigo:'NO_DISPONIBLE',mensaje:'Servicio temporalmente no disponible.',correlacion_id:'referencia-sintetica-'.repeat(15)} });
  });
  await page.setViewportSize({width:320,height:568}); await page.goto('/acceso');
  await expect(page.getByRole('heading',{name:'Iniciar sesión'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Entrar',exact:true})).toBeDisabled();
  await page.getByLabel('Correo',{exact:true}).fill('sintetico@example.invalid');
  await page.getByLabel('Contraseña',{exact:true}).fill('PruebaSintetica');
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page.getByLabel('Código de verificación')).toBeVisible();
  await expect(page.getByLabel('Contraseña',{exact:true})).toHaveValue('');
  await page.getByLabel('Contraseña',{exact:true}).fill('PruebaSintetica');
  await page.getByLabel('Código de verificación').fill('123456');
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Servicio temporalmente no disponible.');
  await page.getByRole('alert').scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()).violations).toEqual([]);
});
