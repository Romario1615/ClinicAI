import type { Page, Request } from '@playwright/test';
import { expect } from './prueba';

/** Espera el render y sus consultas; networkidle puede ser de la ruta anterior. */
export function esperaDeConsultas(page: Page): () => Promise<void> {
  const pendientes = new Set<Request>();
  page.on('request', r => {
    if (r.url().includes('/api/v1/')) pendientes.add(r);
  });
  page.on('requestfinished', r => pendientes.delete(r));
  page.on('requestfailed', r => pendientes.delete(r));
  return async () => {
    await page.evaluate(() => new Promise<void>(r => {
      requestAnimationFrame(() => requestAnimationFrame(() => r()));
    }));
    await expect.poll(() => pendientes.size, {
      message: 'Consultas de la pantalla completadas',
    }).toBe(0);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await new Promise<void>(r => requestAnimationFrame(() => r()));
      await Promise.all(document.getAnimations()
        .filter(a => a.effect?.getTiming().iterations !== Infinity)
        .map(a => a.finished.catch(() => undefined)));
    });
  };
}

/** Compara solo píxeles visibles: respeta recortes, elipsis y ventanas nativas. */
export async function solapesVisibles(page: Page, selector?: string): Promise<string[]> {
  return page.evaluate(selector => {
    type Caja = { left: number; right: number; top: number; bottom: number };
    const dialogo = [...document.querySelectorAll('dialog[open]')].at(-1);
    const raiz = selector ? document.querySelector(selector)! : dialogo ?? document.querySelector('main')!;
    const cabecera = document.querySelector('.cabecera');
    // Tras desplazar una página móvil, el contenido pasa por debajo de su
    // cabecera fija. Ese tramo queda fuera del área de trabajo visible.
    const bordeSuperior = !selector && !dialogo && scrollY > 0 && cabecera
      && /^(sticky|fixed)$/.test(getComputedStyle(cabecera).position)
      ? cabecera.getBoundingClientRect().bottom : 0;
    const recortar = (caja: Caja, padre: Caja): Caja => ({
      left: Math.max(caja.left, padre.left),
      right: Math.min(caja.right, padre.right),
      top: Math.max(caja.top, padre.top),
      bottom: Math.min(caja.bottom, padre.bottom),
    });
    const visible = (elemento: Element, caja: Caja): Caja | null => {
      if (!elemento.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return null;
      let rect = recortar(caja, { left: 0, right: innerWidth, top: 0, bottom: innerHeight });
      if (raiz.contains(elemento)) rect.top = Math.max(rect.top, bordeSuperior);
      for (let padre: Element | null = elemento; padre; padre = padre.parentElement) {
        const estilo = getComputedStyle(padre);
        if (/(auto|scroll|hidden|clip)/.test(`${estilo.overflowX} ${estilo.overflowY}`)) {
          rect = recortar(rect, padre.getBoundingClientRect());
        }
      }
      return rect.right - rect.left > 3 && rect.bottom - rect.top > 3 ? rect : null;
    };
    const seCruzan = (a: Caja, b: Caja) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2
      && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 2;
    const etiqueta = (e: Element) => {
      const clase = String(e.className).trim().replace(/\s+/g, '.');
      const texto = (e.getAttribute('aria-label') ?? e.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 85);
      return `${e.tagName.toLowerCase()}.${clase} ${texto}`;
    };
    const nodos = [...raiz.querySelectorAll('button,input,select,textarea,a[href]')];
    if (!selector && !dialogo) nodos.push(...document.querySelectorAll('.cabecera button,.cabecera input,.cabecera a'));
    const controles = nodos.flatMap(e => {
      const caja = visible(e, e.getBoundingClientRect());
      return caja ? [{ e, caja }] : [];
    });
    const errores: string[] = [];
    for (let i = 0; i < controles.length; i++) {
      for (let j = i + 1; j < controles.length; j++) {
        const a = controles[i], b = controles[j];
        if (!a.e.contains(b.e) && !b.e.contains(a.e) && seCruzan(a.caja, b.caja)) {
          errores.push(`Controles: ${etiqueta(a.e)} / ${etiqueta(b.e)}`);
        }
      }
    }
    const textos: { e: Element; caja: Caja; texto: string }[] = [];
    const recorrido = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT);
    for (let nodo = recorrido.nextNode(); nodo; nodo = recorrido.nextNode()) {
      const e = nodo.parentElement!;
      const texto = nodo.textContent?.trim();
      if (!texto || e.closest('svg,canvas,style,script,.solo-lectores,[aria-hidden="true"],[role="tooltip"]')) continue;
      const rango = document.createRange();
      rango.selectNodeContents(nodo);
      for (const rect of rango.getClientRects()) {
        const caja = visible(e, rect);
        if (caja) textos.push({ e, caja, texto: texto.slice(0, 70) });
      }
    }
    for (let i = 0; i < textos.length; i++) {
      for (let j = i + 1; j < textos.length; j++) {
        const a = textos[i], b = textos[j];
        if (a.e !== b.e && seCruzan(a.caja, b.caja)) errores.push(`Textos: ${a.texto} / ${b.texto}`);
      }
    }
    for (const texto of textos) {
      for (const control of controles) {
        if (!control.e.contains(texto.e) && seCruzan(texto.caja, control.caja)) {
          errores.push(`Texto/control: ${texto.texto} / ${etiqueta(control.e)}`);
        }
      }
    }
    return [...new Set(errores)];
  }, selector);
}
