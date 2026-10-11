/** Textos y controles visibles deben conservar un espacio propio. */
import { test, expect } from '../apoyo/prueba';
import { acceder, irA, type Rol } from '../apoyo/sesion';
import { esperaDeConsultas, solapesVisibles } from '../apoyo/espacio';

const tamanosSecciones = [
  { width: 1366, height: 768 }, { width: 1024, height: 768 },
  { width: 821, height: 600 }, { width: 390, height: 844 },
  { width: 320, height: 568 },
];
const tamanosFormularios = tamanosSecciones.slice(1);

test('la medición detecta cruces reales y respeta una elipsis intencional', async ({ page }) => {
  // Contrato del auxiliar, sin datos ni respuestas del producto.
  await page.setContent(`
    <main style="position:relative; padding:20px">
      <h1>Texto que debe conservar su espacio</h1>
      <button style="position:absolute; left:20px; top:40px">Acción encima</button>
      <p style="width:70px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">Detalle muy largo recortado</p>
      <input aria-label="Campo separado" style="position:absolute; left:160px; top:100px">
    </main>
  `);
  expect(await solapesVisibles(page)).toEqual(expect.arrayContaining([
    expect.stringContaining('Texto/control: Texto que debe conservar su espacio'),
  ]));
  await page.locator('button').evaluate(e => { e.style.display = 'none'; });
  expect(await solapesVisibles(page)).toEqual([]);
});

for (const rol of ['administradora', 'superadministrador'] as Rol[]) {
  test(`textos y controles no se cruzan en las secciones de ${rol}`, async ({ page }, info) => {
    test.setTimeout(240_000);
    const esperar = esperaDeConsultas(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await acceder(page, rol);
    const rutas = await page.locator('nav.navegacion a[href^="/"]').evaluateAll(enlaces =>
      [...new Set(enlaces.map(e => e.getAttribute('href')!))]);
    const incidencias: unknown[] = [];
    let mediciones = 0;
    for (const tamano of tamanosSecciones) {
      await page.setViewportSize(tamano);
      for (const ruta of rutas) {
        await page.evaluate(href => {
          document.querySelector<HTMLAnchorElement>(`nav.navegacion a[href="${href}"]`)!.click();
        }, ruta);
        await page.waitForURL(url => url.pathname.startsWith(ruta));
        await expect(page.locator('main h1').first()).toBeVisible();
        await esperar();
        const errores = await solapesVisibles(page);
        mediciones++;
        if (errores.length) {
          incidencias.push({ ruta, tamano, errores });
          await page.screenshot({ path: info.outputPath(`${ruta.replaceAll('/', '_')}-${tamano.width}.png`) });
        }
        if (tamano.width === 821 && ['/panel', '/agenda', '/analitica', '/configuracion', '/catalogo', '/conocimiento'].includes(ruta)) {
          await page.screenshot({ path: info.outputPath(`revision${ruta.replaceAll('/', '_')}.png`) });
        }
      }
    }
    await info.attach('incidencias-geometria', {
      body: JSON.stringify({ rutas, mediciones, incidencias }, null, 2), contentType: 'application/json',
    });
    expect(incidencias).toEqual([]);
  });
}

test('pestañas del panel y de administración conservan espacio con los datos cargados', async ({ page }, info) => {
  test.setTimeout(240_000);
  const esperar = esperaDeConsultas(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await acceder(page, 'administradora');
  const incidencias: unknown[] = [];
  let mediciones = 0;
  for (const tamano of tamanosSecciones.filter(t => t.width !== 1024)) {
    await page.setViewportSize(tamano);
    for (const seccion of ['Panel', 'Configuración', 'Catálogo', 'Usuarios y roles', 'Gastos y caja', 'Atención de mensajes', 'Medicamentos']) {
      await irA(page, seccion);
      await esperar();
      const pestanas = page.getByRole('tab');
      const total = await pestanas.count();
      for (let i = 0; i < total; i++) {
        await pestanas.nth(i).click();
        await esperar();
        const nombre = await pestanas.nth(i).innerText();
        const errores = await solapesVisibles(page);
        mediciones++;
        if (errores.length) {
          incidencias.push({ seccion, nombre, tamano, errores });
          await page.screenshot({ path: info.outputPath(`pestana-${seccion.replaceAll(' ', '_')}-${i}-${tamano.width}.png`) });
        }
      }
    }
  }
  await info.attach('pestanas-geometria', {
    body: JSON.stringify({ mediciones, incidencias }, null, 2), contentType: 'application/json',
  });
  expect(incidencias).toEqual([]);
});

test('once formularios flotantes separan sus campos, mensajes y botones', async ({ page }, info) => {
  test.setTimeout(240_000);
  const esperar = esperaDeConsultas(page);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await acceder(page, 'administradora');
  const casos = [
    { seccion: 'Pacientes', boton: 'Registrar paciente', titulo: 'Registrar paciente' },
    { seccion: 'Equipo clínico', boton: 'Agregar profesional', titulo: 'Agregar profesional' },
    { seccion: 'Usuarios y roles', boton: 'Dar acceso a una persona', titulo: 'Dar acceso a una persona' },
    { seccion: 'Usuarios y roles', boton: 'Crear rol', titulo: 'Crear un rol para la clínica' },
    { seccion: 'Catálogo', pestana: 'Sedes y consultorios', boton: 'Nuevo consultorio', titulo: 'Nuevo consultorio' },
    { seccion: 'Catálogo', pestana: 'Especialidades', boton: 'Nueva especialidad', titulo: 'Nueva especialidad' },
    { seccion: 'Catálogo', pestana: 'Servicios', boton: 'Nuevo servicio', titulo: 'Nuevo servicio' },
    { seccion: 'Gastos y caja', boton: 'Registrar gasto', titulo: 'Registrar gasto' },
    { seccion: 'Pagos', boton: 'Registrar un abono', titulo: 'Registrar un abono' },
    { seccion: 'Delegaciones de firma', boton: 'Nueva delegación', titulo: 'Nueva delegación de firma' },
    { seccion: 'Conocimiento', boton: 'Cargar documento', titulo: 'Cargar documento' },
  ];
  const incidencias: unknown[] = [];
  let mediciones = 0;
  for (const caso of casos) {
    await page.setViewportSize({ width: 1366, height: 768 });
    await irA(page, caso.seccion);
    await esperar();
    if (caso.pestana) {
      const pestana = page.getByRole('tab', { name: new RegExp(`^${caso.pestana}`) });
      await expect(pestana).toBeVisible();
      await pestana.click();
      await esperar();
    }
    if (caso.boton === 'Nuevo consultorio') {
      const sede = page.getByRole('combobox', { name: 'Sede', exact: true });
      if (!await sede.inputValue()) await sede.selectOption({ index: 1 });
      await esperar();
    }
    const boton = page.getByRole('button', { name: caso.boton, exact: true });
    await expect(boton).toBeEnabled();
    await boton.click();
    const ventana = page.getByRole('dialog', { name: caso.titulo, exact: true });
    await expect(ventana).toBeVisible();
    await esperar();
    for (const tamano of tamanosFormularios) {
      await page.setViewportSize(tamano);
      const cuerpo = ventana.locator('.ventana__cuerpo');
      for (const posicion of [0, .5, 1]) {
        await cuerpo.evaluate((e, p) => { e.scrollTop = p * (e.scrollHeight - e.clientHeight); }, posicion);
        await esperar();
        const errores = await solapesVisibles(page);
        mediciones++;
        if (errores.length) {
          incidencias.push({ formulario: caso.titulo, tamano, posicion, errores });
          await page.screenshot({ path: info.outputPath(`formulario-${caso.titulo.replaceAll(' ', '_')}-${tamano.width}-${posicion}.png`) });
        }
      }
    }
    await page.keyboard.press('Escape');
    await expect(ventana).toHaveCount(0);
  }
  await info.attach('formularios-geometria', {
    body: JSON.stringify({ formularios: casos.map(c => c.titulo), mediciones, incidencias }, null, 2),
    contentType: 'application/json',
  });
  expect(incidencias).toEqual([]);
});
