/**
 * Pruebas del gráfico en movimiento.
 *
 * Es decorativo: lo que se comprueba es que no estorba a la accesibilidad,
 * que se dibuja completo aunque no se anime, y que detiene sus bucles al
 * destruirse.
 */
import { TestBed } from '@angular/core/testing';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';
import { GraficoRedComponent } from './grafico-red.component';

describe('GraficoRedComponent', () => {
  it('se pinta completo, oculto a los lectores de pantalla, sin animar', async () => {
    const fixture = TestBed.createComponent(GraficoRedComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const svg = (fixture.nativeElement as HTMLElement).querySelector('svg')!;

    expect(svg.getAttribute('aria-hidden')).toBe('true');
    expect(svg.querySelectorAll('[data-trazo]')).toHaveLength(6);
    expect(svg.querySelectorAll('[data-pulso]')).toHaveLength(6);
    // Sin movimiento los pulsos no se encienden: quieto, no hay luz que viaje.
    expect(svg.classList.contains('red--viva')).toBe(false);
  });

  it('dos gráficos en la misma página no comparten identificadores de degradado', () => {
    const primero = TestBed.createComponent(GraficoRedComponent);
    const segundo = TestBed.createComponent(GraficoRedComponent);
    primero.detectChanges();
    segundo.detectChanges();
    const id = (fixture: typeof primero) =>
      (fixture.nativeElement as HTMLElement).querySelector('radialGradient')?.getAttribute('id');

    expect(id(primero)).not.toBe(id(segundo));
  });

  it('con movimiento enciende los bucles y los detiene al destruirse', async () => {
    const controles = { pause: vi.fn(), play: vi.fn(), stop: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        { provide: MovimientoService, useValue: { animarGrafico: vi.fn(() => Promise.resolve(controles)) } },
      ],
    });
    const fixture = TestBed.createComponent(GraficoRedComponent);
    fixture.componentRef.setInput('tono', 'oscuro');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const svg = (fixture.nativeElement as HTMLElement).querySelector('svg')!;

    expect(svg.classList.contains('red--viva')).toBe(true);
    expect(svg.classList.contains('red--oscura')).toBe(true);

    fixture.destroy();
    expect(controles.stop).toHaveBeenCalled();
  });
});
