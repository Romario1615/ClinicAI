/** Geometría del perfil agregado con categorías largas, valores y celdas protegidas. */
import { acceder } from '../apoyo/sesion';
import { expect, test } from '../apoyo/prueba';

test('el perfil de pacientes contiene textos y barras sin solaparlos en escritorio y móvil', async ({ page }) => {
  // Solo se sustituye el desglose agregado para reproducir los extremos de
  // presentación; los permisos y el resto del dashboard usan la API real.
  await page.route('**/api/v1/dashboard/**', async (ruta) => {
    const respuesta = await ruta.fetch();
    expect(respuesta.ok()).toBeTruthy();
    const resumen = await respuesta.json();
    await ruta.fulfill({ response: respuesta, json: {
      ...resumen,
      demografia: {
        edades: [
          { categoria: '0-17 años', pacientes: null, suprimida: true },
          { categoria: '18-29 años', pacientes: 123456, suprimida: false },
          { categoria: '30-44 años', pacientes: 50, suprimida: false },
          { categoria: '45-59 años', pacientes: 5, suprimida: false },
          { categoria: '60 o más', pacientes: 0, suprimida: false },
          { categoria: 'Sin fecha de nacimiento', pacientes: null, suprimida: true },
          { categoria: 'Fecha no válida', pacientes: 0, suprimida: false },
        ],
        sexos: [
          { categoria: 'Femenino', pacientes: 20, suprimida: false },
          { categoria: 'Masculino', pacientes: 10, suprimida: false },
          { categoria: 'Otro', pacientes: null, suprimida: true },
          { categoria: 'Sin registrar', pacientes: null, suprimida: true },
        ],
      },
    } });
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await acceder(page, 'administradora');
  const tarjeta = page.getByRole('region', { name: 'Perfil de pacientes', exact: true });
  await expect(tarjeta.locator('.demografia__fila')).toHaveCount(11);
  await expect(tarjeta).toContainText('123456');
  await expect(tarjeta).toContainText('Sin fecha de nacimiento');

  for (const ancho of [1440, 1280, 1024, 821, 768, 390, 320]) {
    await page.setViewportSize({ width: ancho, height: 900 });
    await tarjeta.scrollIntoViewIfNeeded();
    const medidas = await tarjeta.evaluate((nodo) => {
      const marco = nodo.getBoundingClientRect();
      const solapan = (a: DOMRect, b: DOMRect) =>
        a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1;
      return {
        ancho: nodo.clientWidth,
        contenido: nodo.scrollWidth,
        dentroDePantalla: marco.left >= -1 && marco.right <= window.innerWidth + 1,
        filas: [...nodo.querySelectorAll<HTMLElement>('.demografia__fila')].map((fila) => {
          const categoria = fila.querySelector<HTMLElement>('.demografia__categoria')!;
          const pista = fila.querySelector<HTMLElement>('.demografia__pista')!;
          const valor = fila.querySelector<HTMLElement>('.demografia__valor')!;
          const texto = document.createRange();
          texto.selectNodeContents(valor);
          const cajaCategoria = categoria.getBoundingClientRect();
          const cajaPista = pista.getBoundingClientRect();
          const cajaValor = texto.getBoundingClientRect();
          const cajaFila = fila.getBoundingClientRect();
          return {
            categoria: categoria.textContent?.trim(),
            desborde: [cajaCategoria, cajaPista, cajaValor].some((caja) =>
              caja.left < cajaFila.left - 1 || caja.right > cajaFila.right + 1 ||
              caja.top < cajaFila.top - 1 || caja.bottom > cajaFila.bottom + 1) ||
              categoria.scrollWidth > categoria.clientWidth + 1 || valor.scrollWidth > valor.clientWidth + 1,
            solapamiento: solapan(cajaCategoria, cajaPista) || solapan(cajaCategoria, cajaValor) || solapan(cajaPista, cajaValor),
          };
        }),
      };
    });
    expect(medidas.dentroDePantalla, `Tarjeta a ${ancho}px`).toBeTruthy();
    expect(medidas.contenido, `Contenido a ${ancho}px`).toBeLessThanOrEqual(medidas.ancho + 1);
    expect(medidas.filas.filter((fila) => fila.desborde || fila.solapamiento), `Filas a ${ancho}px`).toEqual([]);
  }
  const protegidas = tarjeta.locator('.demografia__fila').filter({ hasText: 'Protegido' });
  await expect(protegidas).toHaveCount(4);
  await expect(protegidas.locator('.demografia__pista > span')).toHaveCount(0);
  await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click();
});
