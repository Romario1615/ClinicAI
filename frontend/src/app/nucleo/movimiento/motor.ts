/**
 * Motor de movimiento: todo lo que usa Motion vive aquí.
 *
 * Este módulo se carga de forma diferida (`import('./motor')`) desde
 * `MovimientoService`, justo después del arranque. Así Motion no cuenta en
 * el paquete inicial, que tiene un presupuesto de 500 kB: lo que ve la
 * recepcionista al abrir la aplicación por la mañana no espera a una
 * biblioteca de animación.
 *
 * Se usa `motion/mini` (el `animate` sobre WAAPI) y no el motor completo. Los
 * resortes se conservan: el generador `spring` de Motion calcula la física
 * (rigidez, amortiguación, masa) y la convierte en una curva `linear()` que
 * ejecuta el propio navegador, fuera del hilo de JavaScript. A cambio se
 * animan propiedades CSS reales (`translate`, `scale`, `opacity`, `filter`) y
 * no los atajos `x`/`y`; tienen otra ventaja, se suman al `transform` que ya
 * tenga el elemento en vez de pisarlo.
 *
 * Ninguna función de aquí comprueba `prefers-reduced-motion`: lo decide
 * `MovimientoService` antes de llamar. El motor solo sabe mover.
 *
 * Además de las transiciones de interfaz, aquí viven los gráficos en
 * movimiento (motion graphics): trazos SVG que se dibujan, pulsos que
 * recorren una conexión, nodos que respiran, cifras que cuentan y barras que
 * crecen. Los bucles infinitos devuelven sus controles para que quien los
 * crea pueda pausarlos fuera de pantalla y detenerlos al destruirse.
 */
import { spring, stagger } from 'motion';
import { animate } from 'motion/mini';

/** Resortes con nombre: la misma física en toda la aplicación. */
export const RESORTES = {
  /** Paneles y bloques que entran: casi críticos, se asientan sin rebasar. */
  suave: { type: spring, stiffness: 260, damping: 30, mass: 0.9 },
  /** Respuesta a la pulsación: rápida y con un rebote corto. */
  presion: { type: spring, stiffness: 600, damping: 22, mass: 0.6 },
} as const;

/** Controles mínimos de una animación en bucle. */
export interface ControlBucle {
  pause(): void;
  play(): void;
  stop(): void;
}

/** Curva de salida: acelera al irse, como algo que se retira. */
const CURVA_SALIDA = [0.4, 0, 1, 1] as const;
/** Curva de entrada para fundidos sin desplazamiento. */
const CURVA_ENTRADA = [0.22, 1, 0.36, 1] as const;

/** Propiedades que la animación deja en línea y hay que retirar al acabar. */
const ESTILOS_TRANSITORIOS = ['opacity', 'translate', 'scale', 'filter', 'will-change'] as const;

export type DireccionMovimiento = 'abajo' | 'arriba' | 'izquierda' | 'derecha' | 'escala';

export interface OpcionesEntrada {
  /** Segundos antes de empezar. */
  readonly retraso?: number;
  /** De dónde llega el elemento. Por omisión, desde abajo. */
  readonly desde?: DireccionMovimiento;
  /** Distancia del desplazamiento, en píxeles. */
  readonly distancia?: number;
  /** Desenfoque inicial: el elemento «se enfoca» al llegar. */
  readonly desenfoque?: boolean;
}

export interface OpcionesEscalonado extends OpcionesEntrada {
  /** Segundos entre un elemento y el siguiente. */
  readonly intervalo?: number;
}

/** Desplazamiento inicial (`translate` y `scale`) según la dirección de llegada. */
export function origen(desde: DireccionMovimiento, distancia: number): { translate: string; scale: number } {
  switch (desde) {
    case 'arriba':
      return { translate: `0px ${-distancia}px`, scale: 1 };
    case 'izquierda':
      return { translate: `${-distancia}px 0px`, scale: 1 };
    case 'derecha':
      return { translate: `${distancia}px 0px`, scale: 1 };
    case 'escala':
      return { translate: '0px 0px', scale: 0.94 };
    default:
      return { translate: `0px ${distancia}px`, scale: 1 };
  }
}

/**
 * Borra los estilos en línea que deja una animación terminada.
 *
 * Imprescindible: un `filter` o una transformación residual crean un bloque
 * contenedor nuevo, rompen el `position: fixed` de los desplegables y el
 * `backdrop-filter` de los paneles de vidrio anidados.
 */
export function limpiar(elemento: Element): void {
  const estilo = (elemento as HTMLElement).style;
  if (!estilo) {
    return;
  }
  for (const propiedad of ESTILOS_TRANSITORIOS) {
    estilo.removeProperty(propiedad);
  }
}

/** Hace llegar varios elementos, uno tras otro, con un resorte. */
export async function entrarEscalonado(
  elementos: readonly Element[],
  opciones: OpcionesEscalonado = {},
): Promise<void> {
  if (elementos.length === 0) {
    return;
  }
  const { translate, scale } = origen(opciones.desde ?? 'abajo', opciones.distancia ?? 14);
  const retraso = opciones.retraso ?? 0;
  const fotogramas: Record<string, (string | number)[]> = {
    opacity: [0, 1],
    translate: [translate, '0px 0px'],
  };
  if (scale !== 1) {
    fotogramas['scale'] = [scale, 1];
  }
  if (opciones.desenfoque ?? true) {
    fotogramas['filter'] = ['blur(6px)', 'blur(0px)'];
  }
  try {
    // Un único resorte casi crítico para todo: opacidad, posición y
    // desenfoque llegan juntos y sin rebasar su valor final.
    await animate([...elementos], fotogramas, {
      ...RESORTES.suave,
      delay: elementos.length > 1 ? stagger(opciones.intervalo ?? 0.05, { startDelay: retraso }) : retraso,
    });
  } catch {
    // Una animación interrumpida (el elemento salió del documento) no es un
    // error de la aplicación: se limpia y se sigue.
  } finally {
    elementos.forEach(limpiar);
  }
}

/** Retira un elemento; quien llama decide después quitarlo del documento. */
export async function salir(elemento: Element, hacia: DireccionMovimiento, distancia: number): Promise<void> {
  const { translate } = origen(hacia, distancia);
  const fotogramas: Record<string, (string | number)[]> = {
    opacity: [1, 0],
    translate: ['0px 0px', translate],
  };
  if (hacia === 'escala') {
    fotogramas['scale'] = [1, 0.96];
  }
  try {
    await animate(elemento, fotogramas, { duration: 0.18, ease: CURVA_SALIDA });
  } catch {
    // Interrumpida: el cierre sigue adelante igualmente.
  }
}

/** Solo la opacidad: el velo de fondo de una ventana. */
export async function fundir(elemento: Element, hasta: 0 | 1, duracion: number): Promise<void> {
  try {
    await animate(
      elemento,
      { opacity: hasta === 1 ? [0, 1] : [1, 0] },
      { duration: duracion, ease: hasta === 1 ? CURVA_ENTRADA : CURVA_SALIDA },
    );
  } catch {
    // Interrumpida: no hay nada que deshacer.
  } finally {
    if (hasta === 1) {
      limpiar(elemento);
    }
  }
}

/** El elemento cede bajo el dedo o el puntero. */
export function presionar(elemento: Element): void {
  void Promise.resolve(animate(elemento, { scale: [1, 0.965] }, RESORTES.presion)).catch(() => undefined);
}

/** Vuelve a su tamaño con un rebote corto, y no deja transformación detrás. */
export function soltar(elemento: Element): void {
  void Promise.resolve(animate(elemento, { scale: [null, 1] }, RESORTES.presion))
    .catch(() => undefined)
    .finally(() => limpiar(elemento));
}

// ---------------------------------------------------------------------------
//  Gráficos en movimiento
// ---------------------------------------------------------------------------

/**
 * Cuenta de un número a otro con un resorte y pinta cada fotograma.
 *
 * Motion mini solo anima elementos; para una cifra se usa directamente su
 * generador de resortes, que da el valor en cada instante. Devuelve cómo
 * cancelarlo.
 */
export function contar(desde: number, hasta: number, pintar: (valor: number) => void): () => void {
  const generador = spring({ keyframes: [desde, hasta], stiffness: 90, damping: 20, mass: 1 });
  let inicio: number | null = null;
  let fotograma = 0;
  const paso = (ahora: number): void => {
    inicio ??= ahora;
    const { value, done } = generador.next(ahora - inicio);
    pintar(done ? hasta : value);
    if (!done) {
      fotograma = requestAnimationFrame(paso);
    }
  };
  fotograma = requestAnimationFrame(paso);
  return () => cancelAnimationFrame(fotograma);
}

/**
 * Dibuja trazos SVG desde su origen, uno tras otro.
 *
 * Los trazos deben llevar `pathLength="1"`: así la longitud de todos vale 1 y
 * una sola animación sirve para curvas de cualquier tamaño.
 */
export async function dibujarTrazos(trazos: readonly Element[], retraso = 0): Promise<void> {
  if (trazos.length === 0) {
    return;
  }
  try {
    await animate([...trazos], { strokeDashoffset: [1, 0] }, {
      duration: 1.1,
      ease: CURVA_ENTRADA,
      delay: stagger(0.12, { startDelay: retraso }),
    });
  } catch {
    // Interrumpido: el trazo queda como esté; el CSS lo da por dibujado.
  }
}

/**
 * Hace aparecer nodos con un resorte que rebota un poco, como algo que se
 * posa. Para elementos SVG, que necesitan `transform-box: fill-box`.
 */
export async function posar(nodos: readonly Element[], retraso = 0): Promise<void> {
  if (nodos.length === 0) {
    return;
  }
  try {
    await animate([...nodos], { opacity: [0, 1], scale: [0.4, 1] }, {
      type: spring,
      stiffness: 320,
      damping: 16,
      mass: 0.8,
      delay: stagger(0.09, { startDelay: retraso }),
    });
  } catch {
    // Interrumpido.
  } finally {
    nodos.forEach(limpiar);
  }
}

/** Agrupa varios bucles en un solo control. */
function agrupar(animaciones: readonly ControlBucle[]): ControlBucle {
  return {
    pause: () => animaciones.forEach((animacion) => animacion.pause()),
    play: () => animaciones.forEach((animacion) => animacion.play()),
    stop: () => animaciones.forEach((animacion) => animacion.stop()),
  };
}

/**
 * Pulsos que recorren conexiones sin fin: un guion corto (`stroke-dasharray`
 * sobre `pathLength="1"`) avanza por la curva. Cada conexión lleva su propio
 * desfase para que no parpadeen a la vez.
 */
export function recorrer(pulsos: readonly Element[]): ControlBucle {
  return agrupar(
    pulsos.map((pulso, indice) =>
      animate(pulso, { strokeDashoffset: [1.1, -0.1] }, {
        duration: 2.4 + (indice % 3) * 0.35,
        ease: 'linear',
        repeat: Infinity,
        delay: 0.9 + indice * 0.37,
      }),
    ),
  );
}

/** Nodos que respiran: crecen y vuelven, cada uno a su ritmo. */
export function respirar(nodos: readonly Element[]): ControlBucle {
  return agrupar(
    nodos.map((nodo, indice) =>
      animate(nodo, { scale: [1, 1.07] }, {
        duration: 2.2 + (indice % 4) * 0.3,
        ease: 'easeInOut',
        repeat: Infinity,
        repeatType: 'reverse',
        delay: indice * 0.25,
      }),
    ),
  );
}

/** Partículas que flotan arriba y abajo, desfasadas. */
export function flotar(particulas: readonly Element[]): ControlBucle {
  return agrupar(
    particulas.map((particula, indice) =>
      animate(particula, { translate: ['0px 0px', `0px ${indice % 2 ? -7 : 6}px`], opacity: [0.35, 0.9] }, {
        duration: 3.2 + (indice % 5) * 0.45,
        ease: 'easeInOut',
        repeat: Infinity,
        repeatType: 'reverse',
        delay: indice * 0.2,
      }),
    ),
  );
}

/** Un anillo que gira despacio, sin fin. */
export function girar(elemento: Element, segundos = 36): ControlBucle {
  return animate(elemento, { rotate: ['0deg', '360deg'] }, { duration: segundos, ease: 'linear', repeat: Infinity });
}

/** Barras que crecen desde su origen hasta el valor que ya tienen. */
export async function crecer(barras: readonly Element[], retraso = 0): Promise<void> {
  if (barras.length === 0) {
    return;
  }
  try {
    await animate([...barras], { scale: ['0 1', '1 1'] }, {
      ...RESORTES.suave,
      delay: stagger(0.03, { startDelay: retraso }),
    });
  } catch {
    // Interrumpido.
  } finally {
    barras.forEach(limpiar);
  }
}

/**
 * Pone en marcha la escena de un gráfico SVG marcado con atributos:
 *
 * * `data-trazo`: conexiones que se dibujan (con `pathLength="1"`).
 * * `data-nodo`: piezas que se posan con un resorte.
 * * `data-pulso`: guiones que recorren las conexiones sin fin.
 * * `data-respira`, `data-particula`, `data-anillo`: bucles de ambiente.
 *
 * Con `entrada` falso se omite la presentación y solo arrancan los bucles:
 * es el caso del gráfico que ya se pintó quieto mientras el motor cargaba,
 * para no hacerlo desaparecer y volver a aparecer.
 */
export function escena(raiz: Element, entrada: boolean): ControlBucle {
  const todos = (selector: string): Element[] => Array.from(raiz.querySelectorAll(selector));
  if (entrada) {
    void dibujarTrazos(todos('[data-trazo]'));
    void posar(todos('[data-nodo]'), 0.3);
  }
  return agrupar([
    recorrer(todos('[data-pulso]')),
    respirar(todos('[data-respira]')),
    flotar(todos('[data-particula]')),
    ...todos('[data-anillo]').map((anillo) => girar(anillo)),
  ]);
}
