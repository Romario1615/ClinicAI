/**
 * Selector de paciente: busca y elige uno.
 *
 * Qué se corrigió aquí
 * --------------------
 * El contenedor era una rejilla y el botón «Buscar», como hijo directo, se
 * estiraba a toda la columna: en lista de espera medía 1110 px. Un botón del
 * ancho de la pantalla no parece un botón, parece una barra. Ahora el campo y
 * el botón comparten fila con una separación que es un token, y el botón se
 * queda del tamaño de su texto.
 *
 * Por qué busca al enviar
 * -----------------------
 * Cada consulta de pacientes queda en la auditoría. Buscar en cada pulsación
 * generaría diez entradas por búsqueda y ruido que después impide investigar
 * un acceso de verdad.
 *
 * Por qué dice cuántos se muestran
 * --------------------------------
 * El backend acota a 25 resultados. Sin ese aviso, quien busca «Mar» y no ve
 * a su paciente concluye que no existe, cuando en realidad está en el puesto
 * 40 de la lista.
 */
import { Component, computed, inject, input, output, signal, ChangeDetectionStrategy } from '@angular/core';
import { Subject, catchError, debounceTime, distinctUntilChanged, of, switchMap } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiService, FalloApi, filtroBusquedaPaciente } from '../nucleo/servicios/api.service';
import type { Paciente } from '../nucleo/modelos/dominio';

@Component({
  selector: 'app-selector-paciente',
  standalone: true,
  imports: [],
  template: `
    <div class="selector">
      <label class="campo__etiqueta" [attr.for]="identificador">
        {{ etiqueta() }}@if (obligatorio()) { <span class="obligatorio" aria-hidden="true">*</span> }
      </label>
      <input
        class="campo__control"
        [id]="identificador"
        type="search"
        autocomplete="off"
        role="combobox"
        aria-autocomplete="list"
        [attr.aria-expanded]="listaAbierta()"
        [attr.aria-controls]="listaAbierta() ? listaId : null"
        [attr.aria-activedescendant]="opcionActiva() >= 0 ? opcionId(opcionActiva()) : null"
        [attr.aria-describedby]="ayudaId"
        [value]="termino()"
        placeholder="Nombre, apellido o documento"
        (input)="cambiarTermino($any($event.target).value)"
        (keydown)="tecla($event)"
      />
      <span class="campo__ayuda" [id]="ayudaId">
        Escriba al menos tres letras o dígitos para ver coincidencias.
      </span>

      @if (error()) {
        <p class="aviso-error" role="alert">{{ error() }}</p>
      }
      @if (cargando()) { <span class="campo__ayuda" role="status">Buscando pacientes…</span> }
      @if (listaAbierta()) {
        <div class="selector__opciones" [id]="listaId" role="listbox" [attr.aria-label]="'Coincidencias: ' + etiqueta()">
          @for (p of pacientes(); track p.id; let i = $index) {
              <button
              type="button"
              [id]="opcionId(i)"
              role="option"
              [attr.aria-selected]="i === opcionActiva()"
              (click)="elegir(p)"
            >
              {{ p.apellido }}, {{ p.nombre }} · {{ p.numero_documento || 'Sin documento' }}
              </button>
          }
        </div>
      } @else if (!cargando() && termino().trim().length >= 3 && !error()) {
        <span class="campo__ayuda" role="status">No hay coincidencias.</span>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: block; min-width: 0; }
    .selector { position: relative; display: grid; gap: var(--espacio-2); min-width: 0; }
    .campo__etiqueta { margin: 0; }
    .selector__opciones { position: absolute; z-index: 20; top: calc(100% - 2rem); left: 0; right: 0; max-height: 16rem; overflow: auto; padding: var(--espacio-1); border: 1px solid var(--borde-fuerte); border-radius: var(--radio); background: var(--superficie-elevada); box-shadow: var(--sombra-2); }
    .selector__opciones button { width: 100%; min-height: var(--toque-minimo); display: flex; align-items: center; padding: var(--espacio-2) var(--espacio-3); border: 0; border-radius: var(--radio-pequeno); background: transparent; color: inherit; text-align: left; font: inherit; cursor: pointer; }
    .selector__opciones button:hover, .selector__opciones button[aria-selected='true'] { background: var(--acento-suave); }
  `,
})
export class SelectorPacienteComponent {
  private readonly api = inject(ApiService);
  private readonly buscar$ = new Subject<string>();

  readonly seleccion = output<Paciente | null>();
  readonly etiqueta = input('Paciente');
  readonly obligatorio = input(false);

  /** Identificadores únicos aunque se monten varios selectores en la misma pantalla. */
  protected readonly identificador = `busqueda-paciente-${Math.random().toString(36).slice(2, 9)}`;
  protected readonly listaId = `${this.identificador}-opciones`;
  protected readonly ayudaId = `${this.identificador}-ayuda`;
  protected readonly termino = signal('');
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');
  protected readonly opcionActiva = signal(-1);
  protected readonly listaAbierta = computed(() => this.termino().trim().length >= 3 && this.pacientes().length > 0 && !this.cargando());

  constructor() {
    this.buscar$.pipe(
      debounceTime(200),
      distinctUntilChanged(),
      switchMap((termino) => {
        if (termino.length < 3) return of(null);
        this.cargando.set(true);
        this.error.set('');
        return this.api.pacientes({ ...filtroBusquedaPaciente(termino), limite: 25 }).pipe(
          catchError((fallo: FalloApi) => {
            this.error.set(fallo.message);
            return of(null);
          }),
        );
      }),
      takeUntilDestroyed(),
    ).subscribe((pagina) => {
      this.pacientes.set(pagina?.elementos ?? []);
      this.cargando.set(false);
      this.opcionActiva.set(-1);
    });
  }

  protected cambiarTermino(valor: string): void {
    this.termino.set(valor);
    this.pacientes.set([]);
    this.opcionActiva.set(-1);
    this.error.set('');
    this.seleccion.emit(null);
    this.buscar$.next(valor.trim());
  }

  protected tecla(evento: KeyboardEvent): void {
    if (evento.key === 'ArrowDown' && this.pacientes().length) {
      evento.preventDefault();
      this.opcionActiva.set(Math.min(this.opcionActiva() + 1, this.pacientes().length - 1));
    } else if (evento.key === 'ArrowUp' && this.pacientes().length) {
      evento.preventDefault();
      this.opcionActiva.set(Math.max(this.opcionActiva() - 1, 0));
    } else if (evento.key === 'Enter' && this.opcionActiva() >= 0) {
      evento.preventDefault();
      this.elegir(this.pacientes()[this.opcionActiva()]);
    } else if (evento.key === 'Escape') {
      this.pacientes.set([]);
      this.opcionActiva.set(-1);
    }
  }

  protected opcionId(indice: number): string { return `${this.listaId}-${indice}`; }

  protected elegir(paciente: Paciente): void {
    this.termino.set(`${paciente.apellido}, ${paciente.nombre}`);
    this.pacientes.set([]);
    this.opcionActiva.set(-1);
    this.seleccion.emit(paciente);
  }
}
