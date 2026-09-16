/**
 * Pruebas de la cola de trabajo.
 *
 * Lo que se verifica
 * ------------------
 * **No hay estado vacío mudo.** Cuando no queda nada pendiente lo dice: un
 * bloque en blanco se lee como «no cargó», y en una recepción eso significa
 * que alguien recarga la página en lugar de empezar a trabajar.
 *
 * **Lo urgente no se distingue solo por el color.** La marca ámbar va siempre
 * acompañada del texto del plazo, porque hay personal que no percibe esa
 * diferencia y esta es la pantalla donde se decide a quién se llama antes.
 *
 * **Los botones emiten en lugar de actuar.** Este componente pinta; ejecutar
 * es del contenedor, que es quien tiene la sesión y el permiso.
 */
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ColaTrabajoComponent } from './cola-trabajo.component';
import type { TareaPendiente } from '../nucleo/utilidades/pendientes';

function tarea(extra: Partial<TareaPendiente> = {}): TareaPendiente {
  return {
    clase: 'caduca',
    etiqueta: 'Caduca',
    plazo: 'en 6 min',
    titulo: 'Turno bloqueado de Reyna Jurado',
    detalle: 'Al caducar, el hueco vuelve a la agenda.',
    accion: 'Confirmar',
    urgente: true,
    citas: ['cita-1'],
    entradas: [],
    ...extra,
  };
}

describe('ColaTrabajoComponent', () => {
  let fixture: ComponentFixture<ColaTrabajoComponent>;

  function montar(tareas: readonly TareaPendiente[]): void {
    fixture = TestBed.createComponent(ColaTrabajoComponent);
    fixture.componentRef.setInput('tareas', tareas);
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [ColaTrabajoComponent] });
  });

  it('dice que no queda nada en lugar de dejar el bloque en blanco', () => {
    montar([]);

    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Nada pendiente');
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('.cola__item').length).toBe(0);
  });

  it('pinta una tarjeta por tarea con su plazo', () => {
    montar([tarea(), tarea({ clase: 'confirmar', etiqueta: 'Sin confirmar', plazo: '2 citas' })]);

    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.querySelectorAll('.cola__item').length).toBe(2);
    expect(elemento.textContent).toContain('en 6 min');
    expect(elemento.textContent).toContain('2 citas');
  });

  it('marca lo urgente con clase y además con el texto del plazo', () => {
    montar([tarea({ urgente: true, plazo: 'vencido' })]);

    const elemento = fixture.nativeElement as HTMLElement;
    const item = elemento.querySelector('.cola__item');
    expect(item?.classList.contains('cola__item--urgente')).toBeTrue();
    // El texto es lo que hace que no dependa del color.
    expect(elemento.querySelector('.cola__plazo')?.textContent?.trim()).toBe('vencido');
  });

  it('no marca de urgente lo que no tiene cuenta atrás', () => {
    montar([tarea({ urgente: false })]);

    expect(
      (fixture.nativeElement as HTMLElement)
        .querySelector('.cola__item')
        ?.classList.contains('cola__item--urgente'),
    ).toBeFalse();
  });

  it('emite la tarea al pulsar la acción principal, sin ejecutar nada', () => {
    const laTarea = tarea();
    montar([laTarea]);

    let emitida: TareaPendiente | undefined;
    fixture.componentInstance.actuar.subscribe((t: TareaPendiente) => {
      emitida = t;
    });

    (
      (fixture.nativeElement as HTMLElement).querySelector(
        '.cola__item .boton--principal',
      ) as HTMLButtonElement
    ).click();

    expect(emitida).toBe(laTarea);
  });

  it('emite por separado el «ver en la agenda»', () => {
    montar([tarea()]);

    let localizada = false;
    fixture.componentInstance.localizar.subscribe(() => (localizada = true));

    const botones = (fixture.nativeElement as HTMLElement).querySelectorAll(
      '.cola__item .boton',
    ) as NodeListOf<HTMLButtonElement>;
    botones[botones.length - 1].click();

    expect(localizada).toBeTrue();
  });

  it('cuenta las urgentes para que la cabecera pueda decirlo', () => {
    montar([tarea({ urgente: true }), tarea({ clase: 'confirmar', urgente: false })]);

    expect(fixture.componentInstance.urgentes()).toBe(1);
  });

  it('pasa a rejilla cuando hay ancho, sin cambiar el contenido', () => {
    fixture = TestBed.createComponent(ColaTrabajoComponent);
    fixture.componentRef.setInput('tareas', [tarea()]);
    fixture.componentRef.setInput('rejilla', true);
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.cola')?.classList.contains(
        'cola--rejilla',
      ),
    ).toBeTrue();
  });
});
