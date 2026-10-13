/**
 * Recolección de evidencia para la auditoría de usabilidad (heurísticas de
 * Nielsen) y de espaciado. No evalúa: captura pantallas y mide la geometría
 * del DOM. Solo bajo demanda: AUDITORIA_NIELSEN=1.
 *
 * Datos exclusivamente de la base aislada de pruebas. No crea ni modifica
 * registros: solo navega, abre ventanas y las cierra sin guardar.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { test, expect } from '../apoyo/prueba';
import { acceder, type Rol } from '../apoyo/sesion';
import { esperaDeConsultas, solapesVisibles } from '../apoyo/espacio';

test.skip(!process.env.AUDITORIA_NIELSEN, 'Solo bajo demanda');
test.use({ viewport: { width: 1440, height: 900 }, actionTimeout: 15_000 });

const CARPETA = resolve(process.cwd(), '..', 'tmp', 'auditoria-nielsen');
const ARCHIVO = resolve(CARPETA, 'mediciones.json');
mkdirSync(CARPETA, { recursive: true });

type Medicion = Record<string, unknown>;
/** Todas las mediciones de la ejecución; se reescriben tras cada pantalla. */
const mediciones: Medicion[] = [];
const usados = new Set<string>();

function slug(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function persistir(): void {
  writeFileSync(ARCHIVO, JSON.stringify(mediciones, null, 2), 'utf8');
}

/** El menú es un acordeón: abre un grupo y cierra el anterior (un solo aria-expanded="true"). */
async function abrirGrupo(page: Page, indice: number): Promise<void> {
  const boton = page.locator('#navegacion-principal .navegacion__categoria').nth(indice).locator('.navegacion__desplegar');
  if (await boton.getAttribute('aria-expanded') === 'false') await boton.click();
}

/** Abre el grupo que contiene el enlace (los enlaces plegados existen en el DOM, ocultos). */
async function abrirGrupoDe(page: Page, href: string): Promise<void> {
  const grupos = page.locator('#navegacion-principal .navegacion__categoria');
  const total = await grupos.count();
  for (let i = 0; i < total; i++) {
    if (await grupos.nth(i).locator(`a[href="${href}"]`).count()) {
      await abrirGrupo(page, i);
      return;
    }
  }
}

async function irMenuRuta(page: Page, href: string): Promise<void> {
  await abrirGrupoDe(page, href);
  await page.locator(`#navegacion-principal a[href="${href}"]`).first().click();
}

/** Navega por el texto exacto del enlace del menú. */
async function irMenu(page: Page, texto: string): Promise<void> {
  const enlace = page.locator('#navegacion-principal a').filter({ hasText: new RegExp(`^\\s*${texto}\\s*$`) }).first();
  const href = await enlace.getAttribute('href', { timeout: 15_000 });
  await irMenuRuta(page, href!);
}

const esperarTitulo = (page: Page) => async () => {
  await expect(page.locator('main h1').first()).toBeVisible({ timeout: 15_000 });
};

/** Medición del DOM. Autocontenida: se serializa y se ejecuta en el navegador. */
function medirDom() {
  const redondear = (n: number) => Math.round(n * 10) / 10;
  const dialogos = [...document.querySelectorAll('dialog[open]')];
  const raiz: Element = dialogos.at(-1) ?? document.body;
  const visible = (e: Element): boolean => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    return (e as any).checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  };
  const etiqueta = (e: Element): string => {
    const clase = typeof e.className === 'string'
      ? e.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.') : '';
    const texto = (e.getAttribute('aria-label') ?? e.textContent ?? (e as HTMLInputElement).placeholder
      ?? e.getAttribute('title') ?? '').trim().replace(/\s+/g, ' ').slice(0, 40);
    return `${e.tagName.toLowerCase()}${clase ? '.' + clase : ''} "${texto}"`;
  };
  const SEL_CONTROL = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=tab],[role=checkbox],[role=radio],[role=switch]';
  const control = (e: Element): boolean => e.matches(SEL_CONTROL) || e.querySelector(SEL_CONTROL) !== null;
  const contenido = (e: Element): boolean => (e.textContent ?? '').trim() !== '' || control(e);
  /** Pares de hijos visibles consecutivos y apilados en vertical. */
  const pares = (c: Element) => {
    const hijos = [...c.children].filter(visible);
    const res: { a: Element; b: Element; distancia: number }[] = [];
    for (let i = 1; i < hijos.length; i++) {
      const a = hijos[i - 1].getBoundingClientRect();
      const b = hijos[i].getBoundingClientRect();
      const horizontal = Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2;
      if (!horizontal || b.top < a.top) continue;
      res.push({ a: hijos[i - 1], b: hijos[i], distancia: redondear(b.top - a.bottom) });
    }
    return res;
  };
  const contenedores = [...document.querySelectorAll(
    'form, fieldset, section, .tarjeta, dialog[open] .ventana__cuerpo, .pantalla__fijo, .pantalla__resto',
  )].filter(c => raiz.contains(c) && visible(c));

  const pegados: Record<string, unknown>[] = [];
  const irregulares: Record<string, unknown>[] = [];
  for (const c of contenedores) {
    const todos = pares(c);
    for (const p of todos) {
      if (p.distancia < 4 && contenido(p.a) && contenido(p.b)) {
        pegados.push({ contenedor: etiqueta(c), anterior: etiqueta(p.a), siguiente: etiqueta(p.b), distancia: p.distancia });
      }
    }
    const huecos = todos.map(p => p.distancia);
    if (huecos.length >= 2) {
      const minimo = Math.min(...huecos);
      const maximo = Math.max(...huecos);
      if (maximo - minimo > 12) irregulares.push({ contenedor: etiqueta(c), huecos, minimo, maximo });
    }
  }

  const SEL_OBJETIVO = 'button,a[href],input:not([type=hidden]),select,textarea,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch]';
  const objetivosPequenos = [...raiz.querySelectorAll(SEL_OBJETIVO)]
    .filter(e => !e.closest('.solo-lectores,[aria-hidden="true"]') && visible(e))
    .map(e => ({ e, r: e.getBoundingClientRect() }))
    .filter(({ r }) => r.width > 2 && r.height > 2 && (r.width < 24 || r.height < 24))
    .map(({ e, r }) => ({ elemento: etiqueta(e), ancho: redondear(r.width), alto: redondear(r.height) }));

  const recortados = [...raiz.querySelectorAll('*')]
    .filter(e => {
      if (e.closest('.solo-lectores,svg,[aria-hidden="true"]')) return false;
      if ((e.textContent ?? '').trim() === '' || !visible(e)) return false;
      const r = e.getBoundingClientRect();
      if (r.width <= 2 || r.height <= 2) return false;
      const estilo = getComputedStyle(e);
      if (!/(hidden|clip)/.test(estilo.overflowX) || estilo.textOverflow === 'ellipsis') return false;
      return (e as HTMLElement).scrollWidth > (e as HTMLElement).clientWidth + 1;
    })
    .map(e => ({
      elemento: etiqueta(e),
      ancho: (e as HTMLElement).clientWidth,
      scroll: (e as HTMLElement).scrollWidth,
      overflowX: getComputedStyle(e).overflowX,
    }));

  return {
    pegados,
    irregulares,
    objetivosPequenos,
    recortados,
    scrollPagina: document.documentElement.scrollHeight - innerHeight,
  };
}

/** Captura y mide la pantalla o ventana actual. Un fallo de medición no detiene el recorrido. */
async function medir(page: Page, esperar: () => Promise<void>, rol: string, pantalla: string): Promise<void> {
  await esperar();
  let base = `${rol}-${slug(pantalla)}`;
  if (usados.has(base)) base = `${base}-${mediciones.length}`;
  usados.add(base);
  const captura = `tmp/auditoria-nielsen/${base}.png`;
  await page.screenshot({ path: resolve(CARPETA, `${base}.png`) });
  let solapes: string[];
  try {
    solapes = await solapesVisibles(page);
  } catch (error) {
    solapes = [`no medible: ${(error as Error).message.split('\n')[0]}`];
  }
  const dom = await page.evaluate(medirDom);
  mediciones.push({
    rol,
    pantalla,
    ruta: new URL(page.url()).pathname,
    captura,
    pegados: dom.pegados,
    irregulares: dom.irregulares,
    objetivosPequenos: dom.objetivosPequenos,
    recortados: dom.recortados,
    solapes,
    scrollPagina: dom.scrollPagina,
  });
  persistir();
}

/** Navega a una pantalla; si no aparece en 15 s, la anota como no encontrada y sigue. */
async function visitar(
  page: Page,
  esperar: () => Promise<void>,
  rol: string,
  pantalla: string,
  navegar: () => Promise<void>,
  listo: () => Promise<void> = esperarTitulo(page),
): Promise<void> {
  try {
    await navegar();
    await listo();
  } catch (error) {
    mediciones.push({ rol, pantalla, no_encontrado: true, motivo: (error as Error).message.split('\n')[0].slice(0, 200) });
    persistir();
    return;
  }
  await medir(page, esperar, rol, pantalla);
}

/** Abre una ventana (diálogo) desde la pantalla actual, la mide y la cierra. */
async function ventana(
  page: Page,
  esperar: () => Promise<void>,
  rol: string,
  pantalla: string,
  abrir: () => Promise<void>,
): Promise<void> {
  try {
    await abrir();
    await expect(page.locator('dialog[open]').last()).toBeVisible({ timeout: 15_000 });
  } catch (error) {
    mediciones.push({ rol, pantalla, no_encontrado: true, motivo: (error as Error).message.split('\n')[0].slice(0, 200) });
    persistir();
    return;
  }
  await medir(page, esperar, rol, pantalla);
  await page.keyboard.press('Escape');
  await page.locator('dialog[open]').last().waitFor({ state: 'detached', timeout: 5_000 }).catch(() => undefined);
}

async function primeraVez(page: Page, rol: Rol): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await acceder(page, rol);
}

test('A · administradora: cada ruta de cada grupo del menú', async ({ page }) => {
  test.setTimeout(900_000);
  const esperar = esperaDeConsultas(page);
  await primeraVez(page, 'administradora');
  const enlaces: { href: string; texto: string }[] = [];
  const grupos = await page.locator('#navegacion-principal .navegacion__categoria').count();
  for (let i = 0; i < grupos; i++) {
    await abrirGrupo(page, i);
    enlaces.push(...await page.locator('#navegacion-principal .navegacion__categoria').nth(i).locator('a[href^="/"]').evaluateAll(es =>
      es.map(e => ({ href: e.getAttribute('href')!, texto: (e.textContent ?? '').trim().replace(/\s+/g, ' ') }))));
  }
  const vistos = new Set<string>();
  for (const { href, texto } of enlaces) {
    if (vistos.has(href)) continue;
    vistos.add(href);
    await visitar(page, esperar, 'administradora', texto || href, () => irMenuRuta(page, href));
  }
  expect(vistos.size).toBeGreaterThan(0);
});

test('B · recepción: Agenda, Pacientes, Lista de espera y Pagos', async ({ page }) => {
  test.setTimeout(900_000);
  const esperar = esperaDeConsultas(page);
  await primeraVez(page, 'recepcion');
  for (const seccion of ['Agenda', 'Pacientes', 'Lista de espera', 'Pagos']) {
    await visitar(page, esperar, 'recepcion', seccion, () => irMenu(page, seccion));
  }
});

test('C · profesional: Agenda, Historia clínica y ficha del primer paciente', async ({ page }) => {
  test.setTimeout(900_000);
  const esperar = esperaDeConsultas(page);
  await primeraVez(page, 'profesional');
  for (const seccion of ['Agenda', 'Historia clínica']) {
    await visitar(page, esperar, 'profesional', seccion, () => irMenu(page, seccion));
  }
  await visitar(page, esperar, 'profesional', 'Pacientes', () => irMenu(page, 'Pacientes'));
  const ficha = async () => {
    await page.getByRole('button', { name: 'Ver ficha', exact: true }).first().click();
  };
  const esperarPestanas = async () => {
    await expect(page.getByRole('tab', { name: 'Odontograma', exact: true })).toBeVisible({ timeout: 15_000 });
  };
  await visitar(page, esperar, 'profesional', 'Ficha del paciente', ficha, esperarPestanas);
  for (const pestana of ['Odontograma', 'Resumen', 'Plan de tratamiento']) {
    await visitar(page, esperar, 'profesional', `Ficha - ${pestana}`,
      () => page.getByRole('tab', { name: pestana, exact: true }).click(),
      async () => { await expect(page.getByRole('tab', { name: pestana, exact: true })).toHaveAttribute('aria-selected', 'true', { timeout: 15_000 }); });
  }
});

test('D · ventanas de recepción: Nueva cita, Registrar paciente y reserva de un hueco libre', async ({ page }) => {
  test.setTimeout(900_000);
  const esperar = esperaDeConsultas(page);
  await primeraVez(page, 'recepcion');

  await visitar(page, esperar, 'recepcion', 'Agenda', () => irMenu(page, 'Agenda'));
  await ventana(page, esperar, 'recepcion', 'Ventana - Nueva cita', () =>
    page.getByRole('button', { name: 'Nueva cita', exact: true }).click());

  await visitar(page, esperar, 'recepcion', 'Pacientes', () => irMenu(page, 'Pacientes'));
  await ventana(page, esperar, 'recepcion', 'Ventana - Registrar paciente', () =>
    page.getByRole('button', { name: 'Registrar paciente', exact: true }).click());

  await visitar(page, esperar, 'recepcion', 'Agenda (día siguiente)', () => irMenu(page, 'Agenda'));
  const huecos = async () => {
    const vista = page.getByRole('group', { name: 'Vista de la agenda' }).getByRole('button', { name: 'Día', exact: true });
    if (await vista.count()) await vista.click();
    await page.getByRole('button', { name: 'Día siguiente', exact: true }).click();
    await esperar();
    const primero: Locator = page.locator('.fila-dia--hueco').first();
    await expect(primero).toBeVisible({ timeout: 15_000 });
    await primero.click();
  };
  await ventana(page, esperar, 'recepcion', 'Ventana - Reserva de hueco libre', huecos);
});
