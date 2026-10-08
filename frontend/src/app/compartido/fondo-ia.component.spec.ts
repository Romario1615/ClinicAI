import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';
import { FondoIAComponent } from './fondo-ia.component';

describe('FondoIAComponent', () => {
  function crear(activo = false) {
    const movimiento = { activo: signal(activo) };
    TestBed.configureTestingModule({ imports: [FondoIAComponent], providers: [{ provide: MovimientoService, useValue: movimiento }] });
    const fixture = TestBed.createComponent(FondoIAComponent);
    fixture.detectChanges();
    return { fixture, movimiento, svg: fixture.nativeElement.querySelector('svg') as SVGElement };
  }

  it('mantiene las partículas fuera de la navegación y de la lectura accesible', () => {
    const { svg } = crear();
    expect(svg.getAttribute('aria-hidden')).toBe('true');
    expect(svg.getAttribute('focusable')).toBe('false');
    expect(svg.querySelectorAll('circle')).toHaveLength(24);
    expect(svg.querySelectorAll('[tabindex], button, a')).toHaveLength(0);
  });

  it('apaga el movimiento cuando cambia la preferencia del usuario', () => {
    const { fixture, movimiento, svg } = crear(true);
    expect(svg.classList.contains('fondo--quieto')).toBe(false);
    movimiento.activo.set(false);
    fixture.detectChanges();
    expect(svg.classList.contains('fondo--quieto')).toBe(true);
  });

  it('adapta el tono al fondo oscuro sin cambiar la posición de los puntos', () => {
    const { fixture, svg } = crear();
    fixture.componentRef.setInput('oscuro', true);
    fixture.detectChanges();
    expect(svg.classList.contains('fondo--oscuro')).toBe(true);
    expect(svg.querySelector('circle')?.getAttribute('cx')).toBe('20');
  });
});
