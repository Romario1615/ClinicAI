/**
 * Cifra que cuenta hasta su valor.
 *
 * `<span [appContador]="valor"></span>` pinta el valor; si es una cifra y se
 * puede animar, cuenta con un resorte desde la cifra anterior (o desde cero la
 * primera vez). Es un gráfico en movimiento pequeño: dice «esto acaba de
 * calcularse» sin añadir ruido.
 *
 * Lo que no se anima, se pinta tal cual: textos («—», «09:30»), cifras con
 * separador de miles ambiguo o cualquier cosa con movimiento reducido. El
 * valor final que queda en el DOM es siempre exactamente el recibido, con su
 * formato original: lo que lee un lector de pantalla o una prueba no depende
 * de la animación.
 */
import { Directive, ElementRef, effect, inject, input, untracked, type OnDestroy } from '@angular/core';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';

/** Cifra animable: prefijo, número con a lo sumo un separador decimal, sufijo. */
interface CifraAnimable {
  readonly prefijo: string;
  readonly numero: number;
  readonly decimales: number;
  readonly separador: '.' | ',';
  readonly sufijo: string;
}

const PATRON_CIFRA = /^([^\d-]*)(-?\d+)(?:([.,])(\d+))?([^\d]*)$/;

/** Descompone el valor si es una cifra que se puede contar. */
export function cifraAnimable(valor: string | number | null | undefined): CifraAnimable | null {
  if (typeof valor === 'number') {
    if (!Number.isFinite(valor)) {
      return null;
    }
    const texto = String(valor);
    const decimales = texto.includes('.') ? texto.split('.')[1].length : 0;
    return { prefijo: '', numero: valor, decimales, separador: '.', sufijo: '' };
  }
  if (typeof valor !== 'string') {
    return null;
  }
  const partes = PATRON_CIFRA.exec(valor.trim());
  if (!partes) {
    return null;
  }
  const [, prefijo, entero, separador, fraccion, sufijo] = partes;
  const numero = Number(`${entero}.${fraccion ?? '0'}`);
  return {
    prefijo,
    numero,
    decimales: fraccion?.length ?? 0,
    separador: (separador as '.' | ',' | undefined) ?? '.',
    sufijo,
  };
}

/** Pinta un valor intermedio con el mismo formato que el final. */
export function formatearCifra(cifra: CifraAnimable, valor: number): string {
  const texto = valor.toFixed(cifra.decimales);
  return `${cifra.prefijo}${cifra.separador === ',' ? texto.replace('.', ',') : texto}${cifra.sufijo}`;
}

@Directive({
  selector: '[appContador]',
  standalone: true,
})
export class ContadorDirective implements OnDestroy {
  private readonly elemento = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly movimiento = inject(MovimientoService);

  readonly appContador = input<string | number | null | undefined>('');

  private anterior: number | null = null;
  private cancelar: (() => void) | null = null;

  constructor() {
    effect(() => {
      const valor = this.appContador();
      untracked(() => this.pintar(valor));
    });
  }

  ngOnDestroy(): void {
    this.cancelar?.();
  }

  private pintar(valor: string | number | null | undefined): void {
    this.cancelar?.();
    this.cancelar = null;
    const final = valor === null || valor === undefined ? '' : String(valor);
    const cifra = cifraAnimable(valor);
    if (!cifra) {
      this.anterior = null;
      this.elemento.textContent = final;
      return;
    }
    const desde = this.anterior ?? 0;
    this.anterior = cifra.numero;
    if (desde === cifra.numero) {
      this.elemento.textContent = final;
      return;
    }
    this.cancelar = this.movimiento.contar(desde, cifra.numero, (actual) => {
      // El último fotograma deja el texto exacto que llegó, con su formato.
      this.elemento.textContent = actual === cifra.numero ? final : formatearCifra(cifra, actual);
    });
    if (!this.cancelar) {
      this.elemento.textContent = final;
    }
  }
}
