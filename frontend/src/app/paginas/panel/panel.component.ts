import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { OperacionesService, ResumenPanel } from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { FalloApi } from '../../nucleo/servicios/api.service';

@Component({
  selector: 'app-panel', standalone: true, imports: [FormsModule, RouterLink],
  template: `
    <div class="cabecera-pagina"><div><p class="ceja">GESTIÓN CLÍNICA</p><h1>Resumen de actividad</h1></div>
      <a class="boton boton--principal" routerLink="/agenda">Abrir agenda</a></div>
    <p>Datos de demostración guardados en la clínica local.</p>
    @if (sesion.tienePermiso('dashboard.leer')) {
      <form class="tarjeta filtros-demo" (ngSubmit)="cargar()">
        <label>Desde<input type="date" name="desde" [(ngModel)]="desde" required /></label>
        <label>Hasta (inclusive)<input type="date" name="hasta" [(ngModel)]="hasta" required /></label>
        <button class="boton" [disabled]="cargando()">Actualizar resumen</button>
      </form>
      @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
      @if (cargando()) { <p role="status">Consultando actividad…</p> }
      @if (resumen(); as r) {
        <div class="rejilla metricas-demo">
          <article class="tarjeta"><p>Citas del periodo</p><strong>{{ r.total_citas }}</strong></article>
          <article class="tarjeta"><p>Confirmadas</p><strong>{{ (r.citas['CONFIRMED'] || 0) + (r.citas['RESCHEDULED'] || 0) }}</strong></article>
          <article class="tarjeta"><p>Canceladas</p><strong>{{ r.citas['CANCELLED'] || 0 }}</strong></article>
          <article class="tarjeta"><p>Pacientes atendidos o agendados</p><strong>{{ r.pacientes }}</strong></article>
        </div>
        <section class="tarjeta"><h2>Estado de las citas</h2>
          @for (estado of estados; track estado.codigo) {
            <div class="barra-estado"><span>{{ estado.nombre }}</span><meter [value]="r.citas[estado.codigo] || 0" [max]="r.total_citas || 1" [attr.aria-label]="estado.nombre"></meter><b>{{ r.citas[estado.codigo] || 0 }}</b></div>
          }
        </section>
        @if (r.pagos; as pagos) {
          <section class="tarjeta"><h2>Pagos de las citas del periodo</h2>
            <p>Confirmados: <strong>{{ moneda(pagos['CONFIRMED']) }}</strong></p>
            <p>Pendientes o en revisión: <strong>{{ moneda(pendiente(pagos)) }}</strong></p>
            <a routerLink="/pagos">Gestionar pagos</a>
          </section>
        }
      }
    } @else { <div class="tarjeta"><h2>Su espacio de trabajo</h2><p>Use el menú para acceder a las gestiones habilitadas para su rol.</p></div> }
  `,
  styles: `.metricas-demo strong { font-size: 2.2rem; color: var(--acento); } section { margin-top: 20px; } .barra-estado { display:grid; grid-template-columns: 130px 1fr 40px; gap: 16px; align-items:center; padding:8px 0; } meter { width:100%; }`,
})
export class PanelComponent {
  private readonly api = inject(OperacionesService);
  protected readonly sesion = inject(SesionService);
  protected desde = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toLocaleDateString('en-CA');
  protected hasta = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).toLocaleDateString('en-CA');
  protected readonly resumen = signal<ResumenPanel | null>(null);
  protected readonly cargando = signal(false);
  protected readonly error = signal('');
  protected readonly estados = [
    { codigo: 'HELD', nombre: 'Apartadas' }, { codigo: 'CONFIRMED', nombre: 'Confirmadas' },
    { codigo: 'RESCHEDULED', nombre: 'Reprogramadas' }, { codigo: 'COMPLETED', nombre: 'Completadas' },
    { codigo: 'CANCELLED', nombre: 'Canceladas' }, { codigo: 'NO_SHOW', nombre: 'Inasistencias' },
  ];
  constructor() { if (this.sesion.tienePermiso('dashboard.leer')) this.cargar(); }
  protected cargar(): void {
    if (!this.desde || !this.hasta || this.hasta < this.desde) { this.error.set('Revise el periodo seleccionado.'); return; }
    this.cargando.set(true); this.error.set(''); this.resumen.set(null);
    const fin = new Date(`${this.hasta}T00:00:00-05:00`); fin.setTime(fin.getTime() + 86400000);
    this.api.leer<ResumenPanel>('/dashboard/', { desde: `${this.desde}T00:00:00-05:00`, hasta: fin.toISOString() }).subscribe({
      next: r => { this.resumen.set(r); this.cargando.set(false); },
      error: (e: FalloApi) => { this.error.set(e.message); this.cargando.set(false); },
    });
  }
  protected moneda(valor: string | number | undefined): string { return new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' }).format(Number(valor || 0)); }
  protected pendiente(pagos: Record<string, string>): number { return ['PENDING', 'PROOF_RECEIVED', 'UNDER_REVIEW'].reduce((s, e) => s + Number(pagos[e] || 0), 0); }
}
