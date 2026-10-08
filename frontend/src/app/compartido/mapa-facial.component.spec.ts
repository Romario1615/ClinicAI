import { TestBed } from '@angular/core/testing';
import { MapaFacialComponent } from './mapa-facial.component';

describe('MapaFacialComponent', () => {
  it('permite elegir la zona con teclado y comunica su estado', () => {
    const fixture = TestBed.createComponent(MapaFacialComponent);
    fixture.componentRef.setInput('puntos', [{ codigo: 'menton', nombre: 'Mentón', x: 160, y: 280 }]);
    fixture.componentRef.setInput('zonas', [{ zona: 'menton', estado: 'PLANIFICADO', observacion: 'Sintética', procedimiento: null }]);
    fixture.componentRef.setInput('seleccion', 'menton');
    const elegir = vi.fn(); fixture.componentInstance.elegir.subscribe(elegir);
    fixture.detectChanges();
    const punto: SVGGElement = fixture.nativeElement.querySelector('g[role="button"]');
    expect(punto.getAttribute('aria-label')).toContain('PLANIFICADO');
    expect(punto.getAttribute('aria-pressed')).toBe('true');
    punto.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(elegir).toHaveBeenCalledWith('menton');
    expect(fixture.nativeElement.textContent).toContain('no son puntos de inyección');
  });

  it('muestra la ilustración anatómica con controles independientes', () => {
    const f = TestBed.createComponent(MapaFacialComponent);
    f.componentRef.setInput('puntos', []); f.detectChanges();
    expect(f.nativeElement.querySelector('image').getAttribute('href')).toBe('/images/faciograma-anatomia-v1.png');
    expect(f.nativeElement.querySelector('svg').getAttribute('role')).toBe('group');
  });
});
