/**
 * Pruebas de la insignia de estado.
 *
 * Lo que se verifica no es el color: es que **siempre haya texto**. Una cita
 * cancelada y una confirmada no pueden distinguirse solo por el tono — hay
 * personal que no percibe esa diferencia —, y confundirlas significa que
 * alguien espera a un paciente que no va a venir, o al revés.
 */
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { InsigniaEstadoComponent } from './insignia-estado.component';
import type { EstadoCita } from '../nucleo/modelos/dominio';

const TODOS: readonly EstadoCita[] = [
  'PENDING',
  'HELD',
  'CONFIRMED',
  'RESCHEDULED',
  'CANCELLED',
  'COMPLETED',
  'NO_SHOW',
];

describe('InsigniaEstadoComponent', () => {
  let fixture: ComponentFixture<InsigniaEstadoComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [InsigniaEstadoComponent] }).compileComponents();
    fixture = TestBed.createComponent(InsigniaEstadoComponent);
  });

  it('todos los estados tienen etiqueta de texto', () => {
    for (const estado of TODOS) {
      fixture.componentRef.setInput('estado', estado);
      fixture.detectChanges();

      const texto = (fixture.nativeElement.textContent as string).trim();
      expect(texto.length)
        .withContext(`el estado ${estado} no tiene etiqueta`)
        .toBeGreaterThan(0);
    }
  });

  it('las etiquetas son distintas entre sí', () => {
    // Dos estados con la misma etiqueta serían indistinguibles en pantalla
    // aunque el color cambiara.
    const etiquetas = new Set<string>();
    for (const estado of TODOS) {
      fixture.componentRef.setInput('estado', estado);
      fixture.detectChanges();
      etiquetas.add((fixture.nativeElement.textContent as string).trim());
    }
    expect(etiquetas.size).toBe(TODOS.length);
  });

  it('todos los estados tienen descripción para el atributo title', () => {
    for (const estado of TODOS) {
      fixture.componentRef.setInput('estado', estado);
      fixture.detectChanges();

      const insignia = fixture.nativeElement.querySelector('.insignia') as HTMLElement;
      expect(insignia.title.length)
        .withContext(`el estado ${estado} no tiene descripcion`)
        .toBeGreaterThan(0);
    }
  });

  it('traduce los estados al español para mostrarlos', () => {
    // Los estados se conservan en inglés en el modelo (ADR-0015); la
    // traducción vive aquí para que el contrato con el backend no dependa
    // del idioma de la interfaz.
    fixture.componentRef.setInput('estado', 'NO_SHOW');
    fixture.detectChanges();
    expect((fixture.nativeElement.textContent as string).trim()).toBe('No asistió');

    fixture.componentRef.setInput('estado', 'CONFIRMED');
    fixture.detectChanges();
    expect((fixture.nativeElement.textContent as string).trim()).toBe('Confirmada');
  });

  it('un estado desconocido no rompe la pantalla', () => {
    // El backend podría introducir un estado nuevo antes de que la interfaz
    // lo conozca. Caer con un error dejaría toda la tabla de agenda en
    // blanco por una fila.
    fixture.componentRef.setInput('estado', 'ESTADO_FUTURO' as EstadoCita);
    fixture.detectChanges();
    expect((fixture.nativeElement.textContent as string).trim().length).toBeGreaterThan(0);
  });
});
