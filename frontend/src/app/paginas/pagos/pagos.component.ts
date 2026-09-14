import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import { OperacionesService, Pago, Pagina } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Cita, Paciente } from '../../nucleo/modelos/dominio';

@Component({
  selector: 'app-pagos', standalone: true, imports: [FormsModule, SelectorPacienteComponent],
  template: `
    <h1>Pagos</h1><p>Registro de efectivo y transferencias en USD. La confirmación la realiza el personal autorizado.</p>
    @if (sesion.tienePermiso('pago.registrar')) {
      <section class="tarjeta editor-demo"><h2>Registrar un pago</h2>
        <app-selector-paciente (seleccion)="seleccionar($event)" />
        <form #formulario="ngForm" (ngSubmit)="registrar()">
          <div class="formulario-demo">
            <label>Cita<select name="cita" [(ngModel)]="citaId" required><option value="">Seleccione una cita</option>
              @for (c of citas(); track c.id) { <option [value]="c.id">{{ fecha(c.inicio) }} · {{ c.estado }}</option> }
            </select></label>
            <label>Importe (USD)<input type="number" name="importe" [(ngModel)]="importe" min="0.01" max="9999999999" step="0.01" required /></label>
            <label>Método<select name="metodo" [(ngModel)]="metodo"><option value="EFECTIVO">Efectivo</option><option value="TRANSFERENCIA">Transferencia</option></select></label>
            <label>Referencia del comprobante (opcional)<input name="referencia" [(ngModel)]="referencia" maxlength="100" /></label>
          </div>
          <p class="ayuda-demo">Registre solo la referencia administrativa. No introduzca tarjetas, claves ni códigos de seguridad.</p>
          <button class="boton boton--principal" [disabled]="formulario.invalid || ocupado()">Registrar pago pendiente</button>
        </form>
      </section>
    }
    @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (aviso()) { <p role="status">{{ aviso() }}</p> }
    <div class="cabecera-pagina"><h2>Pagos registrados · {{ total() }}</h2><button class="boton" (click)="cargar()" [disabled]="ocupado()">Actualizar</button></div>
    @if (cargando()) { <p role="status">Cargando pagos…</p> }
    @if (!cargando() && pagos().length === 0) { <p class="tarjeta">No hay pagos registrados en esta página.</p> }
    @for (p of pagos(); track p.id) {
      <article class="tarjeta fila-demo"><div><h3>{{ moneda(p.importe) }} · {{ p.metodo === 'EFECTIVO' ? 'Efectivo' : 'Transferencia' }}</h3><p>{{ estado(p.estado) }} · {{ p.referencia || 'Sin referencia' }}</p>
        <small>Pago {{ p.id.slice(0, 8) }} · Cita {{ p.cita_id.slice(0, 8) }}</small>
        @if (p.comentario) { <p>{{ p.comentario }}</p> }</div>
        @if (sesion.tienePermiso('pago.validar') && p.estado !== 'REFUND_PENDING') { <button class="boton" (click)="abrirCambio(p)">Revisar pago</button> }
      </article>
    }
    <div class="acciones-demo"><button class="boton" (click)="mover(-1)" [disabled]="pagina() === 0 || cargando()">Anterior</button><span>Página {{ pagina() + 1 }}</span><button class="boton" (click)="mover(1)" [disabled]="(pagina() + 1) * 25 >= total() || cargando()">Siguiente</button></div>
    @if (revisando(); as pago) {
      <section class="tarjeta editor-demo"><h2>Revisión de {{ moneda(pago.importe) }}</h2>
        <form #revision="ngForm" (ngSubmit)="cambiar()">
          <label>Nuevo estado<select name="estado" [(ngModel)]="nuevoEstado" required>@for (e of transiciones[pago.estado]; track e) { <option [value]="e">{{ estado(e) }}</option> }</select></label>
          <label>Comentario de revisión<textarea name="comentario" [(ngModel)]="comentario" required minlength="3" maxlength="500"></textarea></label>
          <div class="acciones-demo"><button class="boton boton--principal" [disabled]="revision.invalid || ocupado()">Guardar revisión</button><button type="button" class="boton" (click)="revisando.set(null)">Cerrar</button></div>
        </form>
      </section>
    }
  `,
})
export class PagosComponent {
  private readonly api = inject(OperacionesService); private readonly agenda = inject(ApiService);
  protected readonly sesion = inject(SesionService);
  protected readonly pagos = signal<Pago[]>([]); protected readonly total = signal(0); protected readonly pagina = signal(0);
  protected readonly citas = signal<readonly Cita[]>([]); protected readonly cargando = signal(false); protected readonly ocupado = signal(false);
  protected readonly error = signal(''); protected readonly aviso = signal(''); protected readonly revisando = signal<Pago | null>(null);
  protected citaId = ''; protected importe: number | null = null; protected metodo = 'EFECTIVO'; protected referencia = '';
  protected nuevoEstado = ''; protected comentario = ''; private clave = crypto.randomUUID(); private cuerpoAnterior = '';
  protected readonly transiciones: Record<string, string[]> = {
    PENDING: ['PROOF_RECEIVED', 'CONFIRMED', 'REJECTED'], PROOF_RECEIVED: ['UNDER_REVIEW', 'CONFIRMED', 'REJECTED'],
    UNDER_REVIEW: ['CONFIRMED', 'REJECTED'], REJECTED: ['PROOF_RECEIVED', 'UNDER_REVIEW'], CONFIRMED: ['REFUND_PENDING'], REFUND_PENDING: [],
  };
  constructor() { this.cargar(); }
  protected cargar(): void {
    this.cargando.set(true); this.error.set('');
    this.api.leer<Pagina<Pago>>('/pagos/', { limite: 25, desplazamiento: this.pagina() * 25 }).subscribe({
      next: p => { this.pagos.set(p.elementos); this.total.set(p.total); this.cargando.set(false); },
      error: (e: FalloApi) => { this.error.set(e.message); this.cargando.set(false); },
    });
  }
  protected mover(n: number): void { this.pagina.update(p => p + n); this.cargar(); }
  protected seleccionar(p: Paciente | null): void {
    this.citaId = ''; this.citas.set([]); if (!p) return;
    this.agenda.citas({ paciente_id: p.id, limite: 200 }).subscribe({ next: r => this.citas.set(r.elementos), error: (e: FalloApi) => this.error.set(e.message) });
  }
  protected registrar(): void { this.enviar('/pagos/', { cita_id: this.citaId, importe: this.importe, metodo: this.metodo, referencia: this.referencia.trim() || null }); }
  protected abrirCambio(p: Pago): void { this.revisando.set(p); this.nuevoEstado = this.transiciones[p.estado][0]; this.comentario = ''; this.clave = crypto.randomUUID(); this.cuerpoAnterior = ''; }
  protected cambiar(): void { const p = this.revisando(); if (p) this.enviar(`/pagos/${p.id}/estado`, { estado: this.nuevoEstado, comentario: this.comentario }); }
  private enviar(ruta: string, datos: unknown): void {
    if (this.ocupado()) return;
    const cuerpo = JSON.stringify({ ruta, datos }); if (this.cuerpoAnterior && cuerpo !== this.cuerpoAnterior) this.clave = crypto.randomUUID(); this.cuerpoAnterior = cuerpo;
    this.ocupado.set(true); this.error.set(''); this.aviso.set('');
    this.api.guardar<Pago>(ruta, datos, this.clave).subscribe({
      next: () => { this.ocupado.set(false); this.revisando.set(null); this.aviso.set('Pago guardado.'); this.clave = crypto.randomUUID(); this.cuerpoAnterior = ''; this.cargar(); },
      error: (e: FalloApi) => { this.error.set(e.message); this.ocupado.set(false); },
    });
  }
  protected fecha(s: string): string { return new Date(s).toLocaleString('es-EC', { timeZone: 'America/Guayaquil' }); }
  protected moneda(s: string): string { return new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' }).format(Number(s)); }
  protected estado(s: string): string { return ({ PENDING: 'Pendiente', PROOF_RECEIVED: 'Comprobante recibido', UNDER_REVIEW: 'En revisión', CONFIRMED: 'Confirmado', REJECTED: 'Rechazado', REFUND_PENDING: 'Devolución pendiente' } as Record<string, string>)[s] || s; }
}
