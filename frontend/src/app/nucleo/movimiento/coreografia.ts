/**
 * Coreografía global: lo que se mueve en todas las pantallas sin que cada
 * pantalla tenga que pedirlo.
 *
 * La aplicación tiene más de sesenta componentes. Añadir una directiva de
 * movimiento a cada tarjeta, tabla y botón sería repetir lo mismo sesenta
 * veces y olvidarlo en la pantalla sesenta y uno. En su lugar, esta pieza
 * observa el documento y aplica tres comportamientos por delegación:
 *
 * 1. **Bloques que llegan.** Cuando aparece una cabecera de módulo, una
 *    tarjeta, una tabla o las filas de un listado (también lo que llega
 *    tarde, al responder la API, y la pantalla entera al cambiar de ruta),
 *    entran escalonados con un resorte. Se limita el número por tanda:
 *    animar 200 filas no aporta nada y cuesta fotogramas en la tableta del
 *    mostrador.
 * 2. **Presión.** Botones y elementos pulsables ceden bajo el puntero y
 *    vuelven con un rebote corto.
 * 3. **Luz.** Sobre las superficies de vidrio, un reflejo sigue al puntero.
 *    Solo con ratón o lápiz (`hover: hover` y `pointer: fine`): en pantalla
 *    táctil no hay puntero que seguir.
 *
 * No hace falta una «transición de ruta» aparte: al navegar, el enrutador
 * inserta la pantalla nueva y el observador la ve llegar como cualquier otro
 * bloque. Una segunda vía animaría dos veces lo mismo.
 *
 * El interior de las ventanas flotantes queda fuera: la propia ventana ya
 * entra con su resorte, y animar también su contenido se lee como un temblor.
 *
 * Vive en el módulo diferido del motor y no es un servicio de Angular: la
 * crea `MovimientoService` cuando el motor ha cargado y le pasa el motor, lo
 * que además permite probarla con un motor de mentira.
 */
import type { OpcionesEscalonado } from './motor';

/** Bloques de una pantalla que merecen entrar con movimiento. */
export const SELECTOR_BLOQUES = [
  '.modulo-cabecera',
  '.tarjeta',
  '.tabla-envoltorio',
  '.rejilla > *',
  '[data-aparecer]',
].join(', ');

/**
 * Barras de un gráfico: crecen desde su origen hasta su valor. Las barras
 * conservan su anchura real en el DOM; el movimiento es solo una escala.
 */
export const SELECTOR_BARRAS = [
  '.tendencia__pista > span',
  '.carga__barra',
  '.estados__barra',
  '[data-crecer]',
].join(', ');

/** Filas de un listado: entran más rápido y en menor distancia. */
export const SELECTOR_FILAS = '.tabla tbody > tr';

/** Lo que cede al pulsarlo. */
export const SELECTOR_PULSABLES = [
  '.boton:not(:disabled)',
  '.acceso__rol:not(:disabled)',
  '.navegacion__enlace',
  '[data-presion]',
].join(', ');

/** Superficies de vidrio que reflejan el puntero. */
export const SELECTOR_VIDRIO = [
  '.tarjeta',
  '.modulo-cabecera',
  '.boton',
  '.navegacion__enlace',
  '.acceso__rol',
  '[data-reflejo]',
].join(', ');

/** Tope de elementos animados por tanda. Lo demás aparece quieto. */
const MAXIMO_BLOQUES_POR_TANDA = 14;
const MAXIMO_FILAS_POR_TANDA = 18;
const MAXIMO_BARRAS_POR_TANDA = 60;

/** Las tres operaciones del motor que usa la coreografía. */
export interface MotorCoreografia {
  entrarEscalonado(elementos: readonly Element[], opciones?: OpcionesEscalonado): Promise<void>;
  crecer(barras: readonly Element[], retraso?: number): Promise<void>;
  presionar(elemento: Element): void;
  soltar(elemento: Element): void;
}

/** Lo que la coreografía necesita del exterior. */
export interface EntornoCoreografia {
  readonly documento: Document;
  readonly motor: MotorCoreografia;
  /** Si se puede animar en este instante (preferencia del sistema incluida). */
  readonly activo: () => boolean;
  /** Ejecuta fuera de la detección de cambios de Angular. */
  readonly fueraDeAngular: (funcion: () => void) => void;
}

export class Coreografia {
  private observador: MutationObserver | null = null;
  private reflejado: HTMLElement | null = null;
  private fotogramaReflejo = 0;
  private presionado: Element | null = null;
  private readonly retiradas: (() => void)[] = [];

  constructor(private readonly entorno: EntornoCoreografia) {}

  /** Instala la observación y la delegación de eventos. */
  iniciar(raiz: Element): void {
    const { documento } = this.entorno;
    const vista = documento.defaultView;
    const conPunteroFino =
      typeof vista?.matchMedia === 'function' && vista.matchMedia('(hover: hover) and (pointer: fine)').matches;

    // Fuera de Angular: mover un reflejo no cambia ningún dato y no debe
    // disparar detección de cambios en cada píxel.
    this.entorno.fueraDeAngular(() => {
      this.escuchar(documento, 'pointerdown', (evento) => this.alPresionar(evento as PointerEvent));
      for (const tipo of ['pointerup', 'pointercancel', 'dragstart']) {
        this.escuchar(documento, tipo, () => this.alSoltar());
      }
      if (conPunteroFino) {
        this.escuchar(documento, 'pointermove', (evento) => this.alMoverPuntero(evento as PointerEvent));
        this.escuchar(documento.documentElement, 'pointerleave', () => this.apagarReflejo());
      }
      if (typeof MutationObserver !== 'undefined') {
        this.observador = new MutationObserver((registros) => this.alMutar(registros));
        this.observador.observe(raiz, { childList: true, subtree: true });
      }
    });
  }

  /** Suelta todo: escuchas, observador y reflejo. */
  detener(): void {
    this.observador?.disconnect();
    this.observador = null;
    this.retiradas.splice(0).forEach((retirar) => retirar());
    this.apagarReflejo();
  }

  private escuchar(objetivo: EventTarget, tipo: string, manejador: (evento: Event) => void): void {
    objetivo.addEventListener(tipo, manejador, { passive: true });
    this.retiradas.push(() => objetivo.removeEventListener(tipo, manejador));
  }

  private alMutar(registros: readonly MutationRecord[]): void {
    if (!this.entorno.activo()) {
      return;
    }
    const bloques: Element[] = [];
    const filas: Element[] = [];
    const barras: Element[] = [];
    for (const registro of registros) {
      registro.addedNodes.forEach((nodo) => {
        if (!(nodo instanceof Element) || fueraDeCoreografia(nodo)) {
          return;
        }
        if (nodo.matches(SELECTOR_BARRAS)) {
          barras.push(nodo);
          return;
        }
        barras.push(...Array.from(nodo.querySelectorAll(SELECTOR_BARRAS)));
        if (nodo.matches(SELECTOR_FILAS)) {
          filas.push(nodo);
          return;
        }
        if (nodo.matches(SELECTOR_BLOQUES)) {
          bloques.push(nodo);
          return;
        }
        bloques.push(...Array.from(nodo.querySelectorAll(SELECTOR_BLOQUES)));
        filas.push(...Array.from(nodo.querySelectorAll(SELECTOR_FILAS)));
      });
    }
    const bloquesSuperiores = superiores(bloques).filter((elemento) => !fueraDeCoreografia(elemento));
    // Las filas que van dentro de un bloque que ya entra se mueven con él.
    const filasSueltas = filas.filter((fila) => !bloquesSuperiores.some((bloque) => bloque.contains(fila)));
    const { motor } = this.entorno;
    if (bloquesSuperiores.length > 0) {
      void motor.entrarEscalonado(bloquesSuperiores.slice(0, MAXIMO_BLOQUES_POR_TANDA), { intervalo: 0.045 });
    }
    if (barras.length > 0) {
      // Después de que el bloque que las contiene empiece a llegar.
      void motor.crecer(barras.slice(0, MAXIMO_BARRAS_POR_TANDA), 0.18);
    }
    if (filasSueltas.length > 0) {
      void motor.entrarEscalonado(filasSueltas.slice(0, MAXIMO_FILAS_POR_TANDA), {
        intervalo: 0.022,
        distancia: 6,
        desenfoque: false,
      });
    }
  }

  private alPresionar(evento: PointerEvent): void {
    if (evento.button !== 0 || !(evento.target instanceof Element) || !this.entorno.activo()) {
      return;
    }
    const pulsable = evento.target.closest(SELECTOR_PULSABLES);
    if (!pulsable) {
      return;
    }
    this.presionado = pulsable;
    this.entorno.motor.presionar(pulsable);
  }

  private alSoltar(): void {
    if (this.presionado) {
      this.entorno.motor.soltar(this.presionado);
      this.presionado = null;
    }
  }

  private alMoverPuntero(evento: PointerEvent): void {
    if (this.fotogramaReflejo || !this.entorno.activo()) {
      return;
    }
    const objetivo = evento.target;
    const { clientX, clientY } = evento;
    // Un cálculo por fotograma como mucho: `pointermove` llega más rápido
    // de lo que la pantalla puede pintar.
    this.fotogramaReflejo = requestAnimationFrame(() => {
      this.fotogramaReflejo = 0;
      const superficie = objetivo instanceof Element ? objetivo.closest<HTMLElement>(SELECTOR_VIDRIO) : null;
      if (superficie !== this.reflejado) {
        this.apagarReflejo();
      }
      if (!superficie || fueraDeCoreografia(superficie)) {
        return;
      }
      const caja = superficie.getBoundingClientRect();
      superficie.style.setProperty('--luz-x', `${Math.round(clientX - caja.left)}px`);
      superficie.style.setProperty('--luz-y', `${Math.round(clientY - caja.top)}px`);
      superficie.setAttribute('data-luz', '');
      this.reflejado = superficie;
    });
  }

  private apagarReflejo(): void {
    if (!this.reflejado) {
      return;
    }
    this.reflejado.removeAttribute('data-luz');
    this.reflejado.style.removeProperty('--luz-x');
    this.reflejado.style.removeProperty('--luz-y');
    this.reflejado = null;
  }
}

/** Quita de la lista los elementos que están dentro de otro de la lista. */
export function superiores(elementos: readonly Element[]): Element[] {
  const unicos = Array.from(new Set(elementos));
  return unicos.filter((elemento) => !unicos.some((otro) => otro !== elemento && otro.contains(elemento)));
}

/**
 * Lo que no se anima desde aquí: el interior de las ventanas flotantes (ya
 * entran con su propio resorte) y lo marcado expresamente como quieto.
 */
export function fueraDeCoreografia(elemento: Element): boolean {
  return elemento.closest('dialog, [data-sin-movimiento]') !== null;
}
