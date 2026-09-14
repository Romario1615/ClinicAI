import { Component, inject, input, OnInit, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { Cita, TurnoDisponible } from '../../nucleo/modelos/dominio';
import { formatearHora, rangoDelDia } from '../../nucleo/utilidades/fechas';

@Component({
  selector: 'app-reprogramar-cita', standalone: true, imports: [FormsModule],
  template: `
    <dialog open aria-labelledby="titulo-reprogramar">
      <form (ngSubmit)="guardar()" class="tarjeta">
        <h2 id="titulo-reprogramar">Reprogramar cita</h2>
        <p>Elija un nuevo horario con el mismo profesional. Horas en {{ zona() }}.</p>
        <fieldset [disabled]="ocupado()">
          <label class="campo"><span class="campo__etiqueta">Nueva fecha</span>
            <input class="campo__control" type="date" name="fechaNueva" [(ngModel)]="fecha" (ngModelChange)="buscar()" required />
          </label>
          @if (cargando()) { <p role="status">Buscando horarios…</p> }
          @else if (!turnos().length) { <p>No hay turnos libres. Consulte otra fecha.</p> }
          <label class="campo"><span class="campo__etiqueta">Nuevo horario</span>
            <select class="campo__control" name="turnoNuevo" [(ngModel)]="inicio" required [disabled]="cargando()">
              <option value="">Seleccione…</option>
              @for (turno of turnos(); track turno.inicio) {
                <option [value]="turno.inicio">{{ hora(turno.inicio) }} – {{ hora(turno.fin_consulta) }}</option>
              }
            </select>
          </label>
          <label class="campo"><span class="campo__etiqueta">Motivo del cambio</span>
            <textarea class="campo__control" name="motivoCambio" [(ngModel)]="motivo" minlength="3" maxlength="500" required></textarea>
            <span class="campo__ayuda">Indique un motivo administrativo, sin información clínica.</span>
          </label>
        </fieldset>
        @if (error()) { <p role="alert">{{ error() }}</p> }
        <div class="fila">
          <button class="boton boton--principal" type="submit" [disabled]="ocupado() || cargando() || !inicio || motivo.trim().length < 3">{{ ocupado() ? 'Guardando…' : 'Guardar cambio' }}</button>
          <button class="boton" type="button" [disabled]="ocupado()" (click)="cerrar.emit()">Volver</button>
        </div>
      </form>
    </dialog>
  `,
  styles: `
    :host { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 1rem; background: rgb(22 32 46 / 45%); }
    dialog { position: static; border: 0; padding: 0; max-width: 520px; width: 100%; max-height: 90vh; overflow: auto; background: transparent; }
    fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
    [role=alert] { color: var(--peligro); }
  `,
})
export class ReprogramarCitaComponent implements OnInit {
  readonly cita = input.required<Cita>();
  readonly zona = input.required<string>();
  readonly cerrar = output<void>();
  readonly guardada = output<Cita>();
  private readonly api = inject(ApiService);
  protected fecha = '';
  protected inicio = '';
  protected motivo = '';
  protected readonly turnos = signal<readonly TurnoDisponible[]>([]);
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  private consulta = 0;
  private peticion = { cuerpo: '', clave: '' };

  ngOnInit(): void {
    this.fecha = new Intl.DateTimeFormat('en-CA', { timeZone: this.zona(), year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(this.cita().inicio));
    this.buscar();
  }

  protected buscar(): void {
    const consulta = ++this.consulta;
    this.inicio = ''; this.turnos.set([]); this.error.set('');
    if (!this.fecha) { this.cargando.set(false); return; }
    this.cargando.set(true);
    const cita = this.cita();
    this.api.disponibilidad({ sede_id: cita.sede_id, servicio_id: cita.servicio_id,
      profesional_id: cita.profesional_id, ...rangoDelDia(this.fecha, this.zona()) }).subscribe({
      next: datos => { if (consulta === this.consulta) { this.turnos.set(datos.turnos); this.cargando.set(false); } },
      error: (e: unknown) => { if (consulta === this.consulta) { this.error.set(this.mensaje(e)); this.cargando.set(false); } },
    });
  }

  protected guardar(): void {
    if (this.ocupado() || this.cargando() || !this.inicio || this.motivo.trim().length < 3) return;
    const datos = { nuevo_inicio: this.inicio, motivo: this.motivo.trim() };
    const cuerpo = JSON.stringify(datos);
    if (cuerpo !== this.peticion.cuerpo) this.peticion = { cuerpo, clave: crypto.randomUUID() };
    this.ocupado.set(true); this.error.set('');
    this.api.reprogramarCita(this.cita().id, datos, this.peticion.clave).subscribe({
      next: cita => { this.ocupado.set(false); this.guardada.emit(cita); },
      error: (e: unknown) => { this.ocupado.set(false); this.error.set(this.mensaje(e)); },
    });
  }

  protected hora(inicio: string): string { return formatearHora(inicio, this.zona()); }
  private mensaje(e: unknown): string { return e instanceof FalloApi ? e.message : 'No se pudo guardar el cambio. Inténtelo de nuevo.'; }
}
