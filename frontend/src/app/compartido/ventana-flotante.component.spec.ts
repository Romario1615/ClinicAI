/**
 * Pruebas de la ventana flotante.
 *
 * Aquí no se comprueba estética: se comprueba que quien navega con teclado no
 * se queda atrapado ni perdido. Cada una fija una afirmación concreta del
 * componente, y todas son cosas que se rompen sin darse cuenta al refactorizar.
 */
import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { VentanaFlotanteComponent } from './ventana-flotante.component';

@Component({
  standalone: true,
  imports: [VentanaFlotanteComponent],
  template: `
    <button type="button" id="origen" #origen>Abrir</button>
    @if (abierta()) {
      <app-ventana-flotante
        titulo="Ficha de prueba"
        ceja="Paciente"
        [forma]="forma()"
        [cierraAlPulsarFuera]="cierraFuera()"
        (cerrar)="abierta.set(false)"
      >
        <button type="button" id="primero">Uno</button>
        <button type="button" id="ultimo">Dos</button>
      </app-ventana-flotante>
    }
  `,
})
class AnfitrionComponent {
  readonly abierta = signal(false);
  readonly forma = signal<'lateral' | 'centrada'>('lateral');
  readonly cierraFuera = signal(true);
}

describe('VentanaFlotanteComponent', () => {
  let fixture: ComponentFixture<AnfitrionComponent>;

  function elemento(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function abrir(): void {
    elemento().querySelector<HTMLButtonElement>('#origen')?.focus();
    fixture.componentInstance.abierta.set(true);
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [AnfitrionComponent] });
    fixture = TestBed.createComponent(AnfitrionComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    // Si una prueba dejara el `overflow` puesto, la siguiente pantalla del
    // navegador de pruebas no se podria desplazar.
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('anuncia que es un diálogo modal y con qué título', () => {
    abrir();

    const dialogo = elemento().querySelector('[role="dialog"]');
    expect(dialogo).not.toBeNull();
    expect(dialogo?.getAttribute('aria-modal')).toBe('true');
    expect(dialogo?.getAttribute('aria-label')).toBe('Ficha de prueba');
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('mete el foco dentro al abrir, en el primer elemento enfocable', () => {
    abrir();

    // Sin esto, quien navega con teclado abre la ventana y sigue tabulando por
    // la lista de detrás sin saber que hay algo abierto.
    //
    // El primero es el botón de cerrar de la cabecera, no el contenido, y eso
    // es lo correcto: la salida queda a una pulsación de Enter.
    expect(document.activeElement?.classList.contains('ventana__cerrar')).toBeTrue();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('devuelve el foco a donde estaba al cerrarse', () => {
    abrir();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();

    expect(document.activeElement?.id).toBe('origen');
  });

  it('cierra con Escape', () => {
    abrir();

    elemento()
      .querySelector('[role="dialog"]')
      ?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();

    expect(fixture.componentInstance.abierta()).toBeFalse();
  });

  it('cicla el foco: del último vuelve al primero', () => {
    abrir();
    // `#ultimo` es el último del DOM dentro de la ventana.
    elemento().querySelector<HTMLButtonElement>('#ultimo')?.focus();

    const evento = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
    fixture.detectChanges();

    expect(evento.defaultPrevented).toBeTrue();
    // Vuelve al botón de cerrar, que es el primero de la ventana.
    expect(document.activeElement?.classList.contains('ventana__cerrar')).toBeTrue();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('con Shift+Tab en el primero salta al último', () => {
    abrir();
    // El primero es el botón de cerrar; desde él, hacia atrás, se va al final.
    elemento().querySelector<HTMLButtonElement>('.ventana__cerrar')?.focus();

    const evento = new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
    fixture.detectChanges();

    expect(document.activeElement?.id).toBe('ultimo');
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('cierra al pulsar el fondo', () => {
    abrir();

    elemento().querySelector<HTMLElement>('.capa')?.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.abierta()).toBeFalse();
  });

  it('tabular en medio de la ventana no la secuestra', () => {
    // Solo se intercepta en los extremos: en medio, el navegador hace su
    // trabajo y forzarlo produciría saltos raros.
    abrir();
    elemento().querySelector<HTMLButtonElement>('#primero')?.focus();

    const evento = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    elemento().querySelector('[role="dialog"]')?.dispatchEvent(evento);
    fixture.detectChanges();

    expect(evento.defaultPrevented).toBeFalse();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('un clic dentro no la cierra', () => {
    // El clic burbujea hasta el fondo: sin comprobar el origen, soltar el
    // ratón sobre cualquier texto cerraría la ventana.
    abrir();

    elemento().querySelector<HTMLButtonElement>('#primero')?.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.abierta()).toBeTrue();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('no cierra por el fondo cuando hay algo a medio escribir', () => {
    fixture.componentInstance.cierraFuera.set(false);
    abrir();

    elemento().querySelector<HTMLElement>('.capa')?.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.abierta()).toBeTrue();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });

  it('bloquea el desplazamiento del fondo mientras está abierta', () => {
    abrir();
    expect(document.body.style.overflow).toBe('hidden');

    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
    expect(document.body.style.overflow).toBe('');
  });

  it('la forma centrada tapa el contexto a propósito', () => {
    fixture.componentInstance.forma.set('centrada');
    abrir();

    expect(elemento().querySelector('.capa')?.classList.contains('capa--centrada')).toBeTrue();
    fixture.componentInstance.abierta.set(false);
    fixture.detectChanges();
  });
});
