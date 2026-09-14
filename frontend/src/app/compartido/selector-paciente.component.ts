import { Component, EventEmitter, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../nucleo/servicios/api.service';
import type { Paciente } from '../nucleo/modelos/dominio';

@Component({
  selector: 'app-selector-paciente', standalone: true, imports: [FormsModule],
  template: `
    <div class="selector-paciente">
      <label>Buscar paciente
        <input [(ngModel)]="termino" [ngModelOptions]="{standalone: true}"
          placeholder="Nombre o apellido, al menos 3 letras" (keydown.enter)="buscar(); $event.preventDefault()" />
      </label>
      <button type="button" class="boton" (click)="buscar()" [disabled]="cargando()">Buscar</button>
      @if (error()) { <p role="alert">{{ error() }}</p> }
      <label>Paciente
        <select [(ngModel)]="id" [ngModelOptions]="{standalone: true}" (ngModelChange)="elegir()">
          <option value="">Seleccione un paciente</option>
          @for (p of pacientes(); track p.id) {
            <option [value]="p.id">{{ p.apellido }}, {{ p.nombre }} · {{ p.numero_documento || 'Sin documento' }}</option>
          }
        </select>
      </label>
      @if (total() > pacientes().length) { <small>Se muestran {{ pacientes().length }} de {{ total() }}. Acote la búsqueda.</small> }
    </div>
  `,
  styles: `.selector-paciente { display: grid; gap: 8px; } label { display: grid; gap: 4px; }`,
})
export class SelectorPacienteComponent {
  private readonly api = inject(ApiService);
  @Output() readonly seleccion = new EventEmitter<Paciente | null>();
  protected termino = '';
  protected id = '';
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly total = signal(0);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');
  constructor() { this.buscar(); }
  protected buscar(): void {
    this.cargando.set(true); this.error.set(''); this.id = ''; this.seleccion.emit(null);
    this.api.pacientes({ termino: this.termino.trim() || undefined, limite: 25 }).subscribe({
      next: p => { this.pacientes.set(p.elementos); this.total.set(p.total); this.cargando.set(false);
        if (p.termino_ignorado) this.error.set('Escriba al menos tres letras.'); },
      error: (e: FalloApi) => { this.error.set(e.message); this.cargando.set(false); },
    });
  }
  protected elegir(): void { this.seleccion.emit(this.pacientes().find(p => p.id === this.id) ?? null); }
}
