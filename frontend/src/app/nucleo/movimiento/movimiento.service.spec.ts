/**
 * Pruebas del servicio de movimiento.
 *
 * El entorno de pruebas (jsdom) no tiene WAAPI ni `matchMedia`, y eso es
 * justo lo primero que se comprueba: sin capacidades no se anima y todo
 * resuelve en el acto. Después se simula un navegador capaz para comprobar
 * que la preferencia de movimiento reducido se respeta y se escucha en vivo.
 */
import { TestBed } from '@angular/core/testing';

import { limpiar, origen } from './motor';
import { MovimientoService } from './movimiento.service';

describe('MovimientoService sin capacidades de animación', () => {
  it('no se declara soportado ni activo, y sus operaciones resuelven sin tocar nada', async () => {
    const servicio = TestBed.inject(MovimientoService);
    const elemento = document.createElement('div');

    expect(servicio.soportado).toBe(false);
    expect(servicio.activo()).toBe(false);

    await servicio.entrar(elemento);
    await servicio.salir(elemento);
    await servicio.fundir(elemento, 0);
    servicio.iniciar(document.body);
    servicio.detener();

    expect(elemento.getAttribute('style')).toBeNull();
    expect(document.documentElement.classList.contains('movimiento-activo')).toBe(false);
  });
});

describe('MovimientoService en un navegador capaz', () => {
  let oyentes: ((evento: { matches: boolean }) => void)[];
  let animateOriginal: unknown;

  function simularNavegador(reducido: boolean): void {
    oyentes = [];
    vi.stubGlobal('matchMedia', (consulta: string) => ({
      matches: consulta.includes('reduced-motion') ? reducido : false,
      media: consulta,
      addEventListener: (_tipo: string, oyente: (evento: { matches: boolean }) => void) => oyentes.push(oyente),
      removeEventListener: () => undefined,
    }));
    animateOriginal = (Element.prototype as { animate?: unknown }).animate;
    (Element.prototype as { animate?: unknown }).animate = () => ({});
  }

  afterEach(() => {
    vi.unstubAllGlobals();
    (Element.prototype as { animate?: unknown }).animate = animateOriginal;
    document.documentElement.classList.remove('movimiento-activo');
  });

  it('respeta prefers-reduced-motion y no marca el documento', () => {
    simularNavegador(true);
    const servicio = TestBed.inject(MovimientoService);
    TestBed.tick();

    expect(servicio.soportado).toBe(true);
    expect(servicio.activo()).toBe(false);
    expect(document.documentElement.classList.contains('movimiento-activo')).toBe(false);
  });

  it('se activa sin la preferencia y reacciona en vivo cuando la persona la cambia', () => {
    simularNavegador(false);
    const servicio = TestBed.inject(MovimientoService);
    TestBed.tick();

    expect(servicio.activo()).toBe(true);
    expect(document.documentElement.classList.contains('movimiento-activo')).toBe(true);

    oyentes.forEach((oyente) => oyente({ matches: true }));
    TestBed.tick();

    expect(servicio.activo()).toBe(false);
    expect(document.documentElement.classList.contains('movimiento-activo')).toBe(false);
  });
});

describe('MovimientoService con el motor cargado', () => {
  let animateOriginal: unknown;

  beforeEach(() => {
    vi.stubGlobal('matchMedia', (consulta: string) => ({
      matches: false,
      media: consulta,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    animateOriginal = (Element.prototype as { animate?: unknown }).animate;
    // Una WAAPI mínima que termina en la siguiente microtarea.
    (Element.prototype as { animate?: unknown }).animate = function (
      _fotogramas: unknown,
      opciones: KeyframeAnimationOptions,
    ) {
      const animacion = {
        onfinish: null as null | (() => void),
        currentTime: 0,
        playbackRate: 1,
        playState: 'running',
        effect: { getComputedTiming: () => ({ duration: 300 }), updateTiming: () => undefined },
        finished: Promise.resolve(),
        play: () => undefined,
        pause: () => undefined,
        cancel: () => undefined,
        finish: () => animacion.onfinish?.(),
      };
      if (opciones?.iterations !== Infinity) {
        queueMicrotask(() => animacion.onfinish?.());
      }
      return animacion;
    };
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    (Element.prototype as { animate?: unknown }).animate = animateOriginal;
    document.documentElement.classList.remove('movimiento-activo');
  });

  it('carga el motor, anima un gráfico y entrega sus controles; después entra y cuenta', async () => {
    const servicio = TestBed.inject(MovimientoService);
    const raiz = document.createElement('div');
    raiz.innerHTML = '<span data-trazo></span><span data-nodo></span><span data-pulso></span>';
    document.body.appendChild(raiz);

    const controles = await servicio.animarGrafico(raiz);
    expect(controles).not.toBeNull();
    controles?.stop();

    // Ya cargado, las demás operaciones usan el motor sin esperar.
    const bloque = document.createElement('div');
    document.body.appendChild(bloque);
    await servicio.entrar(bloque);
    await servicio.salir(bloque);
    await servicio.fundir(bloque, 1);
    servicio.limpiar(bloque);
    expect(bloque.style.getPropertyValue('translate')).toBe('');

    const cancelar = servicio.contar(0, 5, () => undefined);
    expect(cancelar).toBeInstanceOf(Function);
    cancelar?.();

    raiz.remove();
    bloque.remove();
  });

  it('no anima un gráfico que ya salió del documento', async () => {
    const servicio = TestBed.inject(MovimientoService);
    const suelto = document.createElement('div');

    expect(await servicio.animarGrafico(suelto)).toBeNull();
  });

  it('pone en marcha la coreografía global una sola vez', async () => {
    const servicio = TestBed.inject(MovimientoService);
    servicio.iniciar(document.body);
    servicio.iniciar(document.body);
    await servicio.animarGrafico(document.body);
    await new Promise((resolver) => setTimeout(resolver, 0));

    expect(() => servicio.detener()).not.toThrow();
  });
});

describe('auxiliares del motor', () => {
  it('traduce cada dirección de llegada a un desplazamiento CSS', () => {
    expect(origen('abajo', 14)).toEqual({ translate: '0px 14px', scale: 1 });
    expect(origen('arriba', 8)).toEqual({ translate: '0px -8px', scale: 1 });
    expect(origen('izquierda', 10)).toEqual({ translate: '-10px 0px', scale: 1 });
    expect(origen('derecha', 36)).toEqual({ translate: '36px 0px', scale: 1 });
    expect(origen('escala', 99)).toEqual({ translate: '0px 0px', scale: 0.94 });
  });

  it('retira los estilos transitorios y respeta los demás', () => {
    const elemento = document.createElement('div');
    elemento.style.setProperty('opacity', '0.5');
    elemento.style.setProperty('translate', '0px 4px');
    elemento.style.setProperty('scale', '0.9');
    elemento.style.setProperty('filter', 'blur(2px)');
    elemento.style.setProperty('color', 'red');

    limpiar(elemento);

    expect(elemento.style.getPropertyValue('opacity')).toBe('');
    expect(elemento.style.getPropertyValue('filter')).toBe('');
    expect(elemento.style.getPropertyValue('color')).toBe('red');
  });
});
