import { Component, inject, input, OnInit, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { Cita, Consultorio, TurnoDisponible } from '../../nucleo/modelos/dominio';
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
          @if (consultorios().length && inicio) {
            <!-- Solo se ofrecen salas libres a la nueva hora. Mantener la
                 actual es la opción por defecto: no se envía cambio de sala. -->
            <label class="campo"><span class="campo__etiqueta">Consultorio</span>
              <select class="campo__control" name="salaNueva" [(ngModel)]="consultorioId">
                <option value="">{{ cita().consultorio_id ? 'Mantener ' + nombreSala(cita().consultorio_id) : 'Sin asignar' }}</option>
                @for (sala of salasLibres(); track sala.id) {
                  @if (sala.id !== cita().consultorio_id) {
                    <option [value]="sala.id">{{ sala.nombre }}</option>
                  }
                }
              </select>
              @if (cita().consultorio_id && !salaActualLibre()) {
                <span class="campo__ayuda">La sala actual está ocupada a esa hora: elija otra.</span>
              }
            </label>
          }
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
  /** Salas de la sede y citas del día, para ofrecer solo salas libres. */
  readonly consultorios = input<readonly Consultorio[]>([]);
  readonly citasSede = input<readonly Cita[]>([]);
  readonly cerrar = output<void>();
  readonly guardada = output<Cita>();
  private readonly api = inject(ApiService);
  protected fecha = '';
  protected inicio = '';
  protected motivo = '';
  protected consultorioId = '';
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
    this.inicio = ''; this.consultorioId = ''; this.turnos.set([]); this.error.set('');
    if (!this.fecha) { this.cargando.set(false); return; }
    this.cargando.set(true);
    const cita = this.cita();
    this.api.disponibilidad({ sede_id: cita.sede_id, servicio_id: cita.servicio_id,
      profesional_id: cita.profesional_id, ...rangoDelDia(this.fecha, this.zona()) }).subscribe({
      next: datos => {
        if (consulta === this.consulta) {
          // La disponibilidad puede incluir la misma cita al recalcular el día.
          // No la ofrezcamos como si fuese un horario nuevo.
          this.turnos.set(datos.turnos.filter(turno => turno.inicio !== cita.inicio));
          this.cargando.set(false);
        }
      },
      error: (e: unknown) => { if (consulta === this.consulta) { this.error.set(this.mensaje(e)); this.cargando.set(false); } },
    });
  }

  /** Salas sin otra cita que ocupe el bloque del turno elegido. */
  protected salasLibres(): readonly Consultorio[] {
    const turno = this.turnos().find((t) => t.inicio === this.inicio);
    if (!turno) return [];
    const inicio = Date.parse(turno.inicio);
    const fin = Date.parse(turno.fin_bloque);
    const ocupadas = new Set(
      this.citasSede()
        .filter(
          (otra) =>
            otra.id !== this.cita().id &&
            otra.consultorio_id &&
            ['PENDING', 'HELD', 'CONFIRMED', 'RESCHEDULED'].includes(otra.estado) &&
            Date.parse(otra.inicio) < fin &&
            inicio < Date.parse(otra.fin),
        )
        .map((otra) => otra.consultorio_id),
    );
    return this.consultorios().filter((sala) => !ocupadas.has(sala.id));
  }

  protected salaActualLibre(): boolean {
    const actual = this.cita().consultorio_id;
    return !actual || this.salasLibres().some((sala) => sala.id === actual);
  }

  protected nombreSala(id: string | null): string {
    return this.consultorios().find((sala) => sala.id === id)?.nombre ?? 'sala actual';
  }

  protected guardar(): void {
    if (this.ocupado() || this.cargando() || !this.inicio || this.motivo.trim().length < 3) return;
    const datos: { nuevo_inicio: string; motivo: string; nuevo_consultorio_id?: string } = {
      nuevo_inicio: this.inicio,
      motivo: this.motivo.trim(),
    };
    if (this.consultorioId) datos.nuevo_consultorio_id = this.consultorioId;
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
