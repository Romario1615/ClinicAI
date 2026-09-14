import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { OperacionesService, EntradaEspera, Pagina } from '../../nucleo/servicios/operaciones.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { FalloApi } from '../../nucleo/servicios/api.service';
import type { Paciente, Sede, Servicio } from '../../nucleo/modelos/dominio';

@Component({
  selector: 'app-lista-espera', standalone: true, imports: [FormsModule, SelectorPacienteComponent],
  template: `
    <h1>Lista de espera</h1><p>Las cancelaciones generan una oferta para una persona a la vez.</p>
    <section class="tarjeta editor-demo"><h2>Anotar a un paciente</h2><app-selector-paciente (seleccion)="paciente = $event" />
      <form #formulario="ngForm" (ngSubmit)="anotar()"><div class="formulario-demo">
        <label>Sede<select name="sede" [(ngModel)]="sedeId" required><option value="">Seleccione</option>@for (s of sedes(); track s.id) { <option [value]="s.id">{{ s.nombre }}</option> }</select></label>
        <label>Servicio<select name="servicio" [(ngModel)]="servicioId" required><option value="">Seleccione</option>@for (s of servicios(); track s.id) { <option [value]="s.id">{{ s.nombre }}</option> }</select></label>
        <label>Antelación mínima (horas)<input type="number" name="antelacion" [(ngModel)]="antelacion" required min="0" max="168" /></label>
      </div><button class="boton boton--principal" [disabled]="formulario.invalid || !paciente || ocupado()">Añadir a la lista</button></form>
    </section>
    @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (aviso()) { <p role="status">{{ aviso() }}</p> }
    <div class="cabecera-pagina"><h2>Entradas · {{ total() }}</h2><button class="boton" (click)="cargar()" [disabled]="ocupado()">Actualizar ofertas</button></div>
    @if (cargando()) { <p role="status">Consultando lista…</p> }
    @if (!cargando() && entradas().length === 0) { <p class="tarjeta">Todavía no hay pacientes en lista de espera.</p> }
    @for (e of entradas(); track e.id) {
      <article class="tarjeta fila-demo"><div><h3>{{ nombreServicio(e.servicio_id) }}</h3><p>Paciente {{ nombres[e.paciente_id] || e.paciente_id.slice(0, 8) }} · {{ e.estado }}</p>
        <small>Antelación mínima: {{ e.horas_antelacion_minima }} horas</small>
        @if (e.oferta_id) { <p><strong>Turno ofrecido: {{ fecha(e.oferta_inicio) }}</strong></p><p>Responder hasta {{ fecha(e.oferta_expira_en) }}</p> }
      </div><div class="acciones-demo">
        @if (e.oferta_id) { <button class="boton boton--principal" [disabled]="ocupado()" (click)="resolver(e, 'aceptar')">Aceptar oferta</button><button class="boton" [disabled]="ocupado()" (click)="resolver(e, 'rechazar')">Rechazar oferta</button> }
        @if (e.estado === 'ACTIVA' || e.estado === 'OFERTADA') { <button class="boton" [disabled]="ocupado()" (click)="resolver(e, 'cancelar')">Retirar de la lista</button> }
      </div></article>
    }
    <div class="acciones-demo"><button class="boton" (click)="mover(-1)" [disabled]="pagina() === 0 || cargando()">Anterior</button><span>Página {{ pagina() + 1 }}</span><button class="boton" (click)="mover(1)" [disabled]="(pagina() + 1) * 25 >= total() || cargando()">Siguiente</button></div>
  `,
})
export class ListaEsperaComponent {
  private readonly api = inject(OperacionesService); private readonly catalogo = inject(CatalogoService);
  protected paciente: Paciente | null = null; protected sedeId = ''; protected servicioId = ''; protected antelacion = 4;
  protected readonly sedes = signal<readonly Sede[]>([]); protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly entradas = signal<EntradaEspera[]>([]); protected readonly total = signal(0); protected readonly pagina = signal(0);
  protected readonly cargando = signal(false); protected readonly ocupado = signal(false); protected readonly error = signal(''); protected readonly aviso = signal('');
  protected nombres: Record<string, string> = {}; private clave = crypto.randomUUID(); private ultimoCuerpo = '';
  constructor() {
    forkJoin({ sedes: this.catalogo.sedes(), servicios: this.catalogo.servicios() }).subscribe({ next: r => { this.sedes.set(r.sedes); this.servicios.set(r.servicios); }, error: () => this.error.set('No se pudo cargar el catálogo.') });
    this.cargar();
  }
  protected cargar(): void {
    this.cargando.set(true); this.error.set('');
    this.api.leer<Pagina<EntradaEspera>>('/lista-espera/', { limite: 25, desplazamiento: this.pagina() * 25 }).subscribe({
      next: r => { this.entradas.set(r.elementos); this.total.set(r.total); this.cargando.set(false);
        for (const id of new Set(r.elementos.map(e => e.paciente_id))) {
          this.api.leer<Paciente>(`/pacientes/${id}`).subscribe({ next: p => { this.nombres = { ...this.nombres, [id]: `${p.nombre} ${p.apellido}` }; }, error: () => { /* El identificador queda visible si falta permiso de ficha. */ } });
        }
      }, error: (e: FalloApi) => { this.error.set(e.message); this.cargando.set(false); },
    });
  }
  protected mover(n: number): void { this.pagina.update(p => p + n); this.cargar(); }
  protected anotar(): void {
    const servicio = this.servicios().find(s => s.id === this.servicioId); if (!servicio || !this.paciente) return;
    this.enviar('/lista-espera/', { paciente_id: this.paciente.id, sede_id: this.sedeId, servicio_id: servicio.id, especialidad_id: servicio.especialidad_id, horas_antelacion_minima: this.antelacion });
  }
  protected resolver(e: EntradaEspera, accion: string): void { this.enviar(`/lista-espera/${e.id}/resolver`, { accion }); }
  private enviar(ruta: string, datos: unknown): void {
    if (this.ocupado()) return;
    const cuerpo = JSON.stringify({ ruta, datos }); if (cuerpo !== this.ultimoCuerpo) this.clave = crypto.randomUUID(); this.ultimoCuerpo = cuerpo;
    this.ocupado.set(true); this.error.set(''); this.aviso.set('');
    this.api.guardar<EntradaEspera>(ruta, datos, this.clave).subscribe({ next: () => { this.ocupado.set(false); this.aviso.set('Lista de espera actualizada.'); this.cargar(); }, error: (e: FalloApi) => { this.error.set(e.message); this.ocupado.set(false); } });
  }
  protected nombreServicio(id: string): string { return this.servicios().find(s => s.id === id)?.nombre || 'Servicio'; }
  protected fecha(s: string | null): string { return s ? new Date(s).toLocaleString('es-EC', { timeZone: 'America/Guayaquil' }) : ''; }
}
