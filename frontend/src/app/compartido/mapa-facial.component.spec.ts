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

  it('asigna identificadores distintos a mapas simultáneos', () => {
    const mapas = [TestBed.createComponent(MapaFacialComponent), TestBed.createComponent(MapaFacialComponent)];
    mapas.forEach(f => { f.componentRef.setInput('puntos', []); f.detectChanges(); });
    const ids = mapas.map(f => f.nativeElement.querySelector('linearGradient').id);
    expect(ids[0]).not.toBe(ids[1]);
    mapas.forEach((f, i) => expect(f.nativeElement.querySelector('path').getAttribute('fill')).toBe(`url(#${ids[i]})`));
  });
});
