/**
 * Pruebas de la cifra que cuenta.
 *
 * Lo esencial: el texto final es siempre exactamente el valor recibido, con
 * su formato, se anime o no. Y lo que no es una cifra se pinta tal cual.
 */
import { Component, signal, ChangeDetectionStrategy } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';
import { ContadorDirective, cifraAnimable, formatearCifra } from './contador.directive';

@Component({
  standalone: true,
  imports: [ContadorDirective],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `<span [appContador]="valor()"></span>`,
})
class AnfitrionComponent {
  readonly valor = signal<string | number | null>(0);
}

describe('cifraAnimable', () => {
  it('reconoce enteros, decimales con punto o coma, prefijos y sufijos', () => {
    expect(cifraAnimable(42)).toEqual({ prefijo: '', numero: 42, decimales: 0, separador: '.', sufijo: '' });
    expect(cifraAnimable('12.5 %')).toEqual({ prefijo: '', numero: 12.5, decimales: 1, separador: '.', sufijo: ' %' });
    expect(cifraAnimable('$ 4,50')).toEqual({ prefijo: '$ ', numero: 4.5, decimales: 2, separador: ',', sufijo: '' });
  });

  it('rechaza lo que no es una cifra inequívoca', () => {
    expect(cifraAnimable('—')).toBeNull();
    expect(cifraAnimable('09:30')).toBeNull();
    expect(cifraAnimable('1.234,50')).toBeNull();
    expect(cifraAnimable(Number.NaN)).toBeNull();
    expect(cifraAnimable(null)).toBeNull();
  });

  it('pinta los valores intermedios con el formato del final', () => {
    const cifra = cifraAnimable('$ 4,50')!;
    expect(formatearCifra(cifra, 2.333)).toBe('$ 2,33');
  });
});

describe('ContadorDirective', () => {
  it('sin movimiento pinta el valor final al instante y sigue sus cambios', () => {
    const fixture = TestBed.createComponent(AnfitrionComponent);
    fixture.componentInstance.valor.set('12.5 %');
    fixture.detectChanges();
    const elemento = (fixture.nativeElement as HTMLElement).querySelector('span')!;
    expect(elemento.textContent).toBe('12.5 %');

    fixture.componentInstance.valor.set('—');
    fixture.detectChanges();
    expect(elemento.textContent).toBe('—');

    fixture.componentInstance.valor.set(null);
    fixture.detectChanges();
    expect(elemento.textContent).toBe('');
  });

  it('con movimiento cuenta desde la cifra anterior y termina en el texto exacto', () => {
    const pasos: number[] = [];
    let pintar: ((valor: number) => void) | null = null;
    const cancelar = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        {
          provide: MovimientoService,
          useValue: {
            contar: (desde: number, hasta: number, alPintar: (valor: number) => void) => {
              pasos.push(desde, hasta);
              pintar = alPintar;
              return cancelar;
            },
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(AnfitrionComponent);
    fixture.componentInstance.valor.set('$ 4,50');
    fixture.detectChanges();
    const elemento = (fixture.nativeElement as HTMLElement).querySelector('span')!;

    expect(pasos).toEqual([0, 4.5]);
    pintar!(2.25);
    expect(elemento.textContent).toBe('$ 2,25');
    pintar!(4.5);
    expect(elemento.textContent).toBe('$ 4,50');

    // Un valor nuevo cancela la cuenta en curso y parte del anterior.
    fixture.componentInstance.valor.set('$ 6,00');
    fixture.detectChanges();
    expect(cancelar).toHaveBeenCalled();
    expect(pasos.slice(2)).toEqual([4.5, 6]);
    fixture.destroy();
  });
});
