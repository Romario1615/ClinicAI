import { ChangeDetectionStrategy, Component, computed, effect, inject, input, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HistoriaClinicaComponent } from '../paginas/historia-clinica/historia-clinica.component';
import { OperacionesService } from '../nucleo/servicios/operaciones.service';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';
import { formatearFechaHora } from '../nucleo/utilidades/fechas';

export interface ContextoAtencion { id: string; inicio: string; estado: string; sede_id: string; sede: string; zona_horaria: string; especialidad_id: string; especialidad: string; profesional: string; servicio: string }
@Component({
  selector: 'app-atencion-paciente', standalone: true, imports: [FormsModule, HistoriaClinicaComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="contexto">
      <h3>Atención del paciente</h3>
      @if (sesion.tienePermiso('agenda.leer')) {
        <label class="campo">Cita de referencia<select class="campo__control" [ngModel]="elegida()?.id ?? ''" (ngModelChange)="elegir($event)"><option value="">Atención sin cita asociada</option>@for (cita of citas(); track cita.id) { <option [value]="cita.id">{{ fecha(cita) }} · {{ cita.sede }} · {{ cita.servicio }}</option> }</select></label>
      }
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (cargando()) { <p role="status">Cargando citas de su ámbito…</p> }
      @if (elegida(); as cita) { <dl><div><dt>Sede</dt><dd>{{ cita.sede }}</dd></div><div><dt>Especialidad</dt><dd>{{ cita.especialidad }}</dd></div><div><dt>Especialista</dt><dd>{{ cita.profesional }}</dd></div><div><dt>Servicio</dt><dd>{{ cita.servicio }}</dd></div><div><dt>Estado</dt><dd>{{ cita.estado }}</dd></div></dl> }
      <div class="acciones">@if (sesion.tienePermiso('agenda.leer')) { <button class="boton" type="button" (click)="abrirAgenda()">Gestionar citas</button> }@if (sesion.tienePermiso('pago.leer')) { <button class="boton" type="button" (click)="abrirPagos()">Pagos de esta cita</button> }</div>
      @if (elegida() && !especialidadDisponible()) { <p>La especialidad de esta cita no está asignada a su cuenta. Los datos clínicos de esa atención requieren acceso del administrador.</p> }
    </section>
    @if (!cargando() && !error() && puedeVerClinico() && especialidadDisponible()) {
      @for (contexto of contextoVista(); track contexto) {
      <app-historia-clinica class="historia-embebida" [pacienteInicial]="pacienteId()" [citaContexto]="elegida()?.id ?? null" [sedeContexto]="elegida()?.sede_id ?? null" [embebida]="true" />
      }
    } @else if (!puedeVerClinico()) { <p>Su rol permite gestionar los datos administrativos de esta atención.</p> }
  `,
  styles: `.contexto{padding:16px;border:1px solid var(--borde);border-radius:20px;background:var(--superficie-elevada);backdrop-filter:blur(16px)}h3{margin-top:0}dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px}dl>div{min-width:0}dt{font-size:.75rem;color:var(--texto-suave)}dd{margin:4px 0;overflow-wrap:anywhere}.acciones{display:flex;gap:10px;flex-wrap:wrap}.historia-embebida{display:flex;flex-direction:column;min-height:660px;margin-top:18px}:host{display:block;min-width:0}`,
})
export class AtencionPacienteComponent implements OnInit {
  private readonly api = inject(OperacionesService);
  private readonly router = inject(Router);
  protected readonly sesion = inject(SesionService);
  private readonly especialidades = inject(EspecialidadHistoriaService);
  readonly pacienteId = input.required<string>();
  readonly citaInicial = input<string | null>(null);
  protected readonly citas = signal<ContextoAtencion[]>([]);
  protected readonly elegida = signal<ContextoAtencion | null>(null);
  protected readonly error = signal('');
  protected readonly cargando = signal(false);
  protected readonly contextoVista = computed(() => [this.elegida()?.id ?? 'sin-cita']);
  constructor() {
    this.especialidades.cargar();
    effect(() => {
      const cita = this.elegida();
      if (cita && this.especialidades.disponibles().some(e => e.id === cita.especialidad_id)) {
        this.especialidades.elegir(cita.especialidad_id);
      }
    });
  }
  ngOnInit(): void {
    if (!this.sesion.tienePermiso('agenda.leer')) return;
    this.cargando.set(true);
    this.api.leer<ContextoAtencion[]>(`/pacientes/${this.pacienteId()}/contextos-atencion`).subscribe({
      next: citas => { this.citas.set(citas); this.cargando.set(false); if (this.citaInicial()) this.elegir(this.citaInicial()!); },
      error: error => { this.cargando.set(false); this.error.set(error.message); },
    });
  }
  protected elegir(id: string): void {
    const cita = this.citas().find(c => c.id === id) ?? null;
    this.error.set(id && !cita ? 'La cita solicitada no está disponible en su ámbito. Seleccione otra atención.' : '');
    this.elegida.set(cita);
    if (cita && this.especialidades.disponibles().some(e => e.id === cita.especialidad_id)) this.especialidades.elegir(cita.especialidad_id);
  }
  protected especialidadDisponible(): boolean { return !this.elegida() || this.especialidades.disponibles().some(e => e.id === this.elegida()!.especialidad_id); }
  protected puedeVerClinico(): boolean { return this.sesion.tieneAlgunPermiso('historia_clinica.leer', 'receta.leer'); }
  protected fecha(cita: ContextoAtencion): string { return formatearFechaHora(cita.inicio, cita.zona_horaria); }
  protected abrirAgenda(): void { void this.router.navigate(['/agenda'], { queryParams: { paciente: this.pacienteId(), cita: this.elegida()?.id } }); }
  protected abrirPagos(): void { void this.router.navigate(['/pagos'], { queryParams: { paciente: this.pacienteId(), cita: this.elegida()?.id } }); }
}
