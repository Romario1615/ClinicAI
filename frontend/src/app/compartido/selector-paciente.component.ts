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
import { Component, computed, inject, output, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { Subscription } from 'rxjs';

import { IconoComponent } from './icono.component';
import { ApiService, FalloApi, filtroBusquedaPaciente } from '../nucleo/servicios/api.service';
import type { Paciente } from '../nucleo/modelos/dominio';

@Component({
  selector: 'app-selector-paciente',
  standalone: true,
  imports: [FormsModule, IconoComponent],
  template: `
    <div class="selector">
      <div class="campo">
        <label class="campo__etiqueta" [attr.for]="'busqueda-' + identificador">
          Buscar paciente
        </label>
        <div class="acciones selector__busqueda">
          <input
            class="campo__control"
            [id]="'busqueda-' + identificador"
            name="termino"
            autocomplete="off"
            [(ngModel)]="termino"
            [ngModelOptions]="{ standalone: true }"
            placeholder="Nombre, apellido o documento"
            (keydown.enter)="buscar(); $event.preventDefault()"
          />
          <button type="button" class="boton" (click)="buscar()" [disabled]="cargando()">
            <app-icono nombre="buscar" [tamano]="16" />
            {{ cargando() ? 'Buscando…' : 'Buscar' }}
          </button>
        </div>
        <span class="campo__ayuda">
          @if (soloDigitos()) {
            Se buscará por número de documento.
          } @else {
            Nombre o apellido, al menos tres letras. Solo dígitos busca por documento.
          }
        </span>
      </div>

      @if (error()) {
        <p class="aviso-error" role="alert">{{ error() }}</p>
      }

      <label class="campo">
        <span class="campo__etiqueta">Paciente</span>
        <select
          class="campo__control"
          name="paciente"
          [(ngModel)]="id"
          [ngModelOptions]="{ standalone: true }"
          (ngModelChange)="elegir()"
        >
          <option value="">Seleccione un paciente</option>
          @for (p of pacientes(); track p.id) {
            <option [value]="p.id">
              {{ p.apellido }}, {{ p.nombre }} · {{ p.numero_documento || 'Sin documento' }}
            </option>
          }
        </select>
        @if (recortado()) {
          <span class="campo__ayuda">
            Se muestran {{ pacientes().length }} de {{ total() }}. Acote la búsqueda para ver el
            resto.
          </span>
        }
      </label>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .selector {
      display: flex;
      flex-direction: column;
      gap: var(--espacio-3);
    }

    /* El campo crece y el botón se queda del tamaño de su texto. Antes, como
       hijo de una rejilla, el botón se estiraba a toda la columna. */
    .selector__busqueda .campo__control {
      flex: 1 1 200px;
      min-width: 0;
    }

    .campo:last-child {
      margin-bottom: 0;
    }
  `,
})
export class SelectorPacienteComponent {
  private readonly api = inject(ApiService);

  readonly seleccion = output<Paciente | null>();

  /** Sufijo único: puede haber dos selectores en la misma pantalla. */
  protected readonly identificador = Math.random().toString(36).slice(2, 8);

  protected termino = '';
  protected id = '';
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly total = signal(0);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');
  /** Búsqueda en curso: una nueva la cancela para que su respuesta no pise a la nueva. */
  private consulta: Subscription | null = null;

  protected readonly soloDigitos = computed(() => /^\d+$/.test(this.termino.trim()));
  protected readonly recortado = computed(() => this.total() > this.pacientes().length);

  constructor() {
    this.buscar();
  }

  protected buscar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.id = '';
    this.seleccion.emit(null);

    const limpio = this.termino.trim();
    this.consulta?.unsubscribe();
    this.consulta = this.api.pacientes({ ...filtroBusquedaPaciente(limpio), limite: 25 }).subscribe({
      next: (pagina) => {
        this.pacientes.set(pagina.elementos);
        this.total.set(pagina.total);
        this.cargando.set(false);
        if (pagina.termino_ignorado) {
          // El backend devuelve CERO elementos cuando ignora el término. Sin
          // este aviso, la lista vacía se lee como «no existe ese paciente».
          this.error.set('Escriba al menos tres letras, o el número de documento completo.');
        }
      },
      error: (fallo: FalloApi) => {
        this.error.set(fallo.message);
        this.cargando.set(false);
      },
    });
  }

  protected elegir(): void {
    this.seleccion.emit(this.pacientes().find((p) => p.id === this.id) ?? null);
  }
}
