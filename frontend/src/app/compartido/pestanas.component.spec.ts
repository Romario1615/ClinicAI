/** Pruebas de las pestañas: estado ARIA, ratón y teclado. */
import { Component, signal } from '@angular/core';
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import { PestanasComponent, type OpcionPestana } from './pestanas.component';

@Component({
  standalone: true,
  imports: [PestanasComponent],
  template: `<app-pestanas grupo="prueba" etiqueta="Vistas de prueba" [opciones]="opciones" [(activa)]="activa" />`,
})
class AnfitrionComponent {
  readonly opciones: readonly OpcionPestana[] = [
    { clave: 'hoy', etiqueta: 'Hoy' },
    { clave: 'pendientes', etiqueta: 'Pendientes', cuenta: 4 },
    { clave: 'periodo', etiqueta: 'Periodo', cuenta: 0 },
  ];
  readonly activa = signal('hoy');
}

describe('PestanasComponent', () => {
  let fixture: ComponentFixture<AnfitrionComponent>;

  function pestanas(): HTMLButtonElement[] {
    return Array.from((fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  }

  beforeEach(() => {
    fixture = TestBed.createComponent(AnfitrionComponent);
    fixture.detectChanges();
  });

  it('marca la activa, enlaza el panel y deja solo una en el orden de tabulación', () => {
    const [hoy, pendientes] = pestanas();
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="tablist"]')!.getAttribute('aria-label')).toBe('Vistas de prueba');
    expect(hoy.getAttribute('aria-selected')).toBe('true');
    expect(hoy.id).toBe('prueba-pestana-hoy');
    expect(hoy.getAttribute('aria-controls')).toBe('prueba-panel-hoy');
    expect(hoy.tabIndex).toBe(0);
    expect(pendientes.tabIndex).toBe(-1);
  });

  it('muestra la cuenta solo cuando hay algo pendiente', () => {
    const [hoy, pendientes, periodo] = pestanas();
    expect(hoy.textContent?.trim()).toBe('Hoy');
    expect(pendientes.textContent).toContain('4');
    expect(periodo.querySelector('.pestanas__cuenta')).toBeNull();
  });

  it('cambia con un clic y actualiza el modelo del anfitrión', () => {
    pestanas()[1].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.activa()).toBe('pendientes');
    expect(pestanas()[1].getAttribute('aria-selected')).toBe('true');
  });

  it('recorre con flechas, Inicio y Fin, de forma circular, y mueve el foco', () => {
    const teclear = (indice: number, key: string) => {
      pestanas()[indice].dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      fixture.detectChanges();
    };
    teclear(0, 'ArrowLeft');
    expect(fixture.componentInstance.activa()).toBe('periodo');
    expect(document.activeElement).toBe(pestanas()[2]);
    teclear(2, 'ArrowRight');
    expect(fixture.componentInstance.activa()).toBe('hoy');
    teclear(0, 'End');
    expect(fixture.componentInstance.activa()).toBe('periodo');
    teclear(2, 'Home');
    expect(fixture.componentInstance.activa()).toBe('hoy');
  });

  it('ignora las demás teclas', () => {
    const evento = new KeyboardEvent('keydown', { key: 'a', bubbles: true, cancelable: true });
    pestanas()[0].dispatchEvent(evento);
    expect(evento.defaultPrevented).toBe(false);
    expect(fixture.componentInstance.activa()).toBe('hoy');
  });
});
