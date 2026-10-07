/**
 * Pruebas del motor de movimiento.
 *
 * jsdom no implementa la Web Animations API. Se simula `Element.animate` con
 * una animación que termina en la siguiente microtarea: suficiente para que
 * Motion recorra su camino real (resolver fotogramas, crear la animación,
 * esperar su fin) y comprobar lo que importa aquí: qué propiedades se piden,
 * con qué repetición, y que al terminar no quedan estilos en línea.
 */
import {
  contar,
  crecer,
  dibujarTrazos,
  entrarEscalonado,
  escena,
  fundir,
  posar,
  presionar,
  salir,
  soltar,
} from './motor';

interface Peticion {
  readonly elemento: Element;
  readonly fotogramas: Record<string, unknown>;
  readonly opciones: KeyframeAnimationOptions;
}

describe('motor de movimiento', () => {
  let peticiones: Peticion[];
  let animateOriginal: unknown;

  beforeEach(() => {
    peticiones = [];
    animateOriginal = (Element.prototype as { animate?: unknown }).animate;
    (Element.prototype as { animate?: unknown }).animate = function (
      this: Element,
      fotogramas: Record<string, unknown>,
      opciones: KeyframeAnimationOptions,
    ) {
      peticiones.push({ elemento: this, fotogramas, opciones });
      const animacion = {
        onfinish: null as null | (() => void),
        currentTime: 0,
        startTime: null,
        playbackRate: 1,
        playState: 'running',
        effect: { getComputedTiming: () => ({ duration: 300 }), updateTiming: () => undefined },
        finished: Promise.resolve(),
        play: () => undefined,
        pause: () => undefined,
        cancel: () => undefined,
        finish: () => animacion.onfinish?.(),
        commitStyles: () => undefined,
      };
      // Las animaciones infinitas no terminan nunca, como en el navegador.
      if (opciones?.iterations !== Infinity) {
        queueMicrotask(() => animacion.onfinish?.());
      }
      return animacion;
    };
  });

  afterEach(() => {
    (Element.prototype as { animate?: unknown }).animate = animateOriginal;
  });

  function elementos(cantidad: number, etiqueta = 'div'): HTMLElement[] {
    return Array.from({ length: cantidad }, () => {
      const elemento = document.createElement(etiqueta);
      document.body.appendChild(elemento);
      return elemento;
    });
  }

  it('hace entrar escalonado y no deja estilos en línea al terminar', async () => {
    const bloques = elementos(3);

    await entrarEscalonado(bloques, { intervalo: 0.05, distancia: 10 });

    // Motion prueba una vez si el navegador admite curvas `linear()` con un
    // elemento propio: se cuentan solo las animaciones de los bloques.
    const propias = peticiones.filter((p) => bloques.includes(p.elemento as HTMLElement));
    const propiedades = new Set(propias.map((p) => Object.keys(p.fotogramas)[0]));
    expect(propiedades).toEqual(new Set(['opacity', 'translate', 'filter']));
    // Cada elemento empieza más tarde que el anterior.
    const retrasos = propias.filter((p) => 'opacity' in p.fotogramas).map((p) => p.opciones.delay);
    expect(retrasos).toEqual([0, 50, 100]);
    for (const bloque of bloques) {
      expect(bloque.getAttribute('style') ?? '').toBe('');
    }
  });

  it('sin elementos no pide ninguna animación', async () => {
    await entrarEscalonado([]);
    await dibujarTrazos([]);
    await posar([]);
    await crecer([]);
    expect(peticiones).toHaveLength(0);
  });

  it('la entrada desde «escala» encoge al principio y sin desenfoque si se pide', async () => {
    const [ventana] = elementos(1);
    await entrarEscalonado([ventana], { desde: 'escala', desenfoque: false });

    const nombres = peticiones.map((p) => Object.keys(p.fotogramas)[0]);
    expect(nombres).toContain('scale');
    expect(nombres).not.toContain('filter');
  });

  it('retira y funde hacia fuera', async () => {
    const [ventana, velo] = elementos(2);
    await salir(ventana, 'escala', 20);
    await fundir(velo, 0, 0.2);
    await fundir(velo, 1, 0.2);

    expect(peticiones.filter((p) => p.elemento === ventana).map((p) => Object.keys(p.fotogramas)[0])).toEqual([
      'opacity',
      'translate',
      'scale',
    ]);
    expect(peticiones.filter((p) => p.elemento === velo)).toHaveLength(2);
  });

  it('cede al presionar y vuelve al soltar sin dejar escala', async () => {
    const [boton] = elementos(1, 'button');
    presionar(boton);
    soltar(boton);
    await new Promise((resolver) => setTimeout(resolver, 0));

    expect(peticiones.filter((p) => p.elemento === boton).every((p) => 'scale' in p.fotogramas)).toBe(true);
    expect(boton.style.getPropertyValue('scale')).toBe('');
  });

  it('dibuja trazos, posa nodos y hace crecer barras', async () => {
    const trazos = elementos(2, 'span');
    const nodos = elementos(2, 'span');
    const barras = elementos(2, 'span');

    await Promise.all([dibujarTrazos(trazos), posar(nodos), crecer(barras, 0.1)]);

    const pedidas = (lista: Element[]) =>
      peticiones.filter((p) => lista.includes(p.elemento)).map((p) => Object.keys(p.fotogramas)[0]);
    expect(pedidas(trazos)).toEqual(['strokeDashoffset', 'strokeDashoffset']);
    expect(new Set(pedidas(nodos))).toEqual(new Set(['opacity', 'scale']));
    expect(pedidas(barras)).toEqual(['scale', 'scale']);
  });

  it('una escena arranca sus bucles infinitos y se puede detener', () => {
    const raiz = document.createElement('svg');
    raiz.innerHTML = `
      <path data-trazo></path><g data-nodo></g>
      <path data-pulso></path><path data-pulso></path>
      <g data-respira></g><circle data-particula></circle><circle data-anillo></circle>`;
    document.body.appendChild(raiz);

    const controles = escena(raiz, true);

    const infinitas = peticiones.filter((p) => p.opciones?.iterations === Infinity);
    // Dos pulsos, una respiración, una partícula (2 propiedades) y un anillo.
    expect(infinitas.length).toBe(6);
    expect(peticiones.some((p) => 'strokeDashoffset' in p.fotogramas && p.opciones?.iterations === 1)).toBe(true);
    expect(() => {
      controles.pause();
      controles.play();
      controles.stop();
    }).not.toThrow();
  });

  it('sin presentación solo arranca los bucles', () => {
    const raiz = document.createElement('div');
    raiz.innerHTML = '<span data-trazo></span><span data-nodo></span><span data-pulso></span>';
    document.body.appendChild(raiz);

    escena(raiz, false).stop();

    const propias = peticiones.filter((p) => raiz.contains(p.elemento));
    expect(propias.length).toBeGreaterThan(0);
    expect(propias.every((p) => p.opciones.iterations === Infinity)).toBe(true);
  });

  it('cuenta con un resorte hasta el valor exacto y se puede cancelar', async () => {
    const valores: number[] = [];
    await new Promise<void>((resolver) => {
      contar(0, 10, (valor) => {
        valores.push(valor);
        if (valor === 10) {
          resolver();
        }
      });
    });

    expect(valores.at(-1)).toBe(10);
    expect(valores.length).toBeGreaterThan(1);

    const cancelados: number[] = [];
    const cancelar = contar(0, 100, (valor) => cancelados.push(valor));
    cancelar();
    await new Promise((resolver) => setTimeout(resolver, 50));
    expect(cancelados).toEqual([]);
  });
});
