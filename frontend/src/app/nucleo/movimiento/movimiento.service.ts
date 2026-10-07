/**
 * Movimiento de la interfaz con Motion.
 *
 * Por qué Motion y no las animaciones de Angular
 * ----------------------------------------------
 * Motion es el motor de Framer Motion publicado también como API de
 * JavaScript sin React (`animate`, `stagger`, resortes). Angular no puede usar
 * los componentes `<motion.div>` de React, pero sí el mismo motor: resortes
 * con física real que se asientan en lugar de seguir una curva fija. Es lo
 * que da la sensación de «vidrio líquido».
 *
 * Este servicio es la fachada ligera que vive en el paquete inicial. Motion y
 * la coreografía global están en `motor.ts` y `coreografia.ts`, que se cargan
 * de forma diferida justo después del arranque (ver `motor.ts`).
 *
 * Reglas que este servicio hace cumplir
 * -------------------------------------
 * * **`prefers-reduced-motion` manda.** Con la preferencia activa no se anima
 *   nada: el elemento aparece en su estado final. La preferencia se escucha
 *   en vivo; cambiarla en el sistema surte efecto sin recargar.
 * * **Sin WAAPI no hay movimiento.** Un navegador (o un entorno de pruebas)
 *   sin `Element.animate` ni `matchMedia` recibe la interfaz estática. Es
 *   detección de capacidades, no de entorno.
 * * **Nada queda a medias.** Al terminar se borran los estilos en línea que
 *   deja la animación (ver `limpiar` en `motor.ts`).
 * * **El movimiento acompaña, no informa.** Ningún dato depende de una
 *   animación para entenderse; quitar este servicio dejaría la misma
 *   aplicación, quieta.
 */
import { DOCUMENT } from '@angular/common';
import { Injectable, NgZone, computed, effect, inject, signal } from '@angular/core';

import type { Coreografia } from './coreografia';
import type { ControlBucle, DireccionMovimiento, OpcionesEntrada, OpcionesEscalonado } from './motor';

export type { ControlBucle, DireccionMovimiento, OpcionesEntrada, OpcionesEscalonado } from './motor';

type Motor = typeof import('./motor');

@Injectable({ providedIn: 'root' })
export class MovimientoService {
  private readonly documento = inject(DOCUMENT);
  private readonly zona = inject(NgZone);
  private readonly vista = this.documento.defaultView;

  /** El navegador sabe animar: WAAPI y consultas de medios. */
  readonly soportado: boolean =
    !!this.vista &&
    typeof this.vista.matchMedia === 'function' &&
    typeof this.vista.Element?.prototype.animate === 'function';

  private readonly consultaReducido = this.soportado
    ? this.vista!.matchMedia('(prefers-reduced-motion: reduce)')
    : null;

  /** La persona pidió reducir el movimiento en su sistema operativo. */
  readonly reducido = signal(this.consultaReducido?.matches ?? true);

  /** Se anima solo si el navegador puede y la persona no pidió lo contrario. */
  readonly activo = computed(() => this.soportado && !this.reducido());

  /** El motor, cuando ha cargado. Hasta entonces, nada se mueve. */
  private motor: Motor | null = null;
  private cargaMotor: Promise<Motor | null> | null = null;
  private coreografia: Coreografia | null = null;

  constructor() {
    this.consultaReducido?.addEventListener?.('change', (evento) => this.reducido.set(evento.matches));
    // La clase en <html> apaga las animaciones CSS de respaldo cuando Motion
    // toma el relevo: dos animaciones de entrada a la vez se ven como un salto.
    effect(() => {
      this.documento.documentElement.classList.toggle('movimiento-activo', this.activo());
    });
  }

  /**
   * Carga el motor y pone en marcha la coreografía global sobre `raiz`.
   *
   * Lo llama el armazón una vez al arrancar. Sin soporte de animación no
   * descarga nada: un navegador que no va a animar no paga la biblioteca.
   */
  iniciar(raiz: Element): void {
    if (!this.soportado || this.coreografia) {
      return;
    }
    void Promise.all([this.cargarMotor(), import('./coreografia')]).then(([motor, modulo]) => {
      if (!motor || this.coreografia) {
        return;
      }
      this.coreografia = new modulo.Coreografia({
        documento: this.documento,
        motor,
        activo: () => this.activo(),
        fueraDeAngular: (funcion) => this.zona.runOutsideAngular(funcion),
      });
      this.coreografia.iniciar(raiz);
    });
  }

  /** Detiene la coreografía global (al destruir el armazón). */
  detener(): void {
    this.coreografia?.detener();
    this.coreografia = null;
  }

  /** Hace llegar un elemento a su sitio con un resorte. */
  entrar(elemento: Element, opciones: OpcionesEntrada = {}): Promise<void> {
    return this.entrarEscalonado([elemento], opciones);
  }

  /**
   * Hace llegar varios elementos, uno tras otro.
   *
   * Es la «coreografía» de una lista: el ojo sigue el orden de lectura en vez
   * de recibir todo de golpe.
   */
  async entrarEscalonado(elementos: readonly Element[], opciones: OpcionesEscalonado = {}): Promise<void> {
    const motor = this.motorActivo();
    if (!motor || elementos.length === 0) {
      return;
    }
    await motor.entrarEscalonado(elementos, opciones);
  }

  /**
   * Retira un elemento antes de que Angular lo quite del documento.
   *
   * Resuelve al terminar; quien llama decide entonces cerrar de verdad. Sin
   * movimiento resuelve de inmediato.
   */
  async salir(elemento: Element, hacia: DireccionMovimiento = 'abajo', distancia = 12): Promise<void> {
    await this.motorActivo()?.salir(elemento, hacia, distancia);
  }

  /** Solo la opacidad: el velo de fondo de una ventana. */
  async fundir(elemento: Element, hasta: 0 | 1, duracion = 0.2): Promise<void> {
    await this.motorActivo()?.fundir(elemento, hasta, duracion);
  }

  /**
   * Arranca la escena de un gráfico en movimiento (ver `escena` en el motor).
   *
   * Resuelve con sus controles, o con `null` si no se va a animar (sin
   * soporte, con movimiento reducido o si el motor no carga). Si el motor ya
   * estaba cargado hay presentación completa; si llega después, el gráfico
   * ya se pintó quieto y solo arrancan los bucles.
   */
  async animarGrafico(raiz: Element): Promise<ControlBucle | null> {
    if (!this.activo()) {
      return null;
    }
    const conEntrada = this.motor !== null;
    const motor = this.motor ?? (await this.cargarMotor());
    if (!motor || !this.activo() || !raiz.isConnected) {
      return null;
    }
    return motor.escena(raiz, conEntrada);
  }

  /**
   * Cuenta hasta una cifra con un resorte, llamando a `pintar` en cada
   * fotograma. Devuelve cómo cancelarlo, o `null` si no se anima: entonces
   * quien llama pinta el valor final directamente.
   */
  contar(desde: number, hasta: number, pintar: (valor: number) => void): (() => void) | null {
    const motor = this.motorActivo();
    return motor ? motor.contar(desde, hasta, pintar) : null;
  }

  /** Borra los estilos en línea que deja una animación. */
  limpiar(elemento: Element): void {
    this.motor?.limpiar(elemento);
  }

  /** El motor, solo si se puede animar ahora mismo y ya está cargado. */
  private motorActivo(): Motor | null {
    if (!this.activo()) {
      return null;
    }
    if (!this.motor) {
      // Aún no ha llegado: esta animación se omite y la siguiente ya podrá.
      void this.cargarMotor();
      return null;
    }
    return this.motor;
  }

  private cargarMotor(): Promise<Motor | null> {
    this.cargaMotor ??= import('./motor')
      .then((motor) => (this.motor = motor))
      .catch(() => null);
    return this.cargaMotor;
  }
}
