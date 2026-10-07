import { DatePipe } from '@angular/common';
import { Component, inject, signal, ChangeDetectionStrategy } from '@angular/core';

import {
  ApiService,
  FalloApi,
  type AvisoAccesoEmergencia,
} from '../../nucleo/servicios/api.service';
import { PendientesService } from '../../nucleo/servicios/pendientes.service';
import { IconoComponent } from '../../compartido/icono.component';

@Component({
  selector: 'app-accesos-emergencia',
  standalone: true,
  imports: [DatePipe, IconoComponent],
  template: `
    <header class="seguridad__cabecera">
      <div>
        <p class="ceja"><app-icono nombre="escudo" [tamano]="16" /> SEGURIDAD CLÍNICA</p>
        <h1>Accesos de emergencia</h1>
        <p>Revisa los accesos temporales declarados por profesionales. Esta lista no muestra datos del paciente ni el motivo clínico.</p>
      </div>
      <span class="seguridad__total" aria-label="Avisos pendientes">{{ avisos().length }}</span>
    </header>

    @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (cargando() && avisos().length === 0) {
      <p class="tarjeta" role="status">Cargando avisos…</p>
    } @else if (avisos().length === 0) {
      <section class="tarjeta seguridad__vacio">
        <img src="/images/notificaciones-vacias.png" alt="" aria-hidden="true" width="96" height="100" />
        <div><h2>Sin avisos pendientes</h2><p>Los accesos temporales que se soliciten aparecerán aquí para revisión administrativa.</p></div>
      </section>
    } @else {
      <section class="seguridad__lista" aria-label="Avisos de acceso de emergencia">
        @for (aviso of avisos(); track aviso.id) {
          <article class="tarjeta seguridad__aviso">
            <span class="seguridad__icono"><app-icono nombre="aviso" [tamano]="20" /></span>
            <div class="seguridad__detalle">
              <h2>Acceso temporal utilizado</h2>
              <p>Profesional: <strong>{{ aviso.profesional }}</strong></p>
              <p>Solicitado: {{ aviso.creado_en | date: 'd MMM y, HH:mm' }}</p>
              <p>Vigencia hasta: {{ aviso.vence_en | date: 'd MMM y, HH:mm' }}</p>
            </div>
            <button class="boton boton--pequeno" type="button" [disabled]="procesando() === aviso.id" (click)="revisar(aviso)">
              {{ procesando() === aviso.id ? 'Guardando…' : 'Marcar como revisado' }}
            </button>
          </article>
        }
      </section>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .seguridad__cabecera { display:flex; align-items:center; justify-content:space-between; gap:var(--espacio-4); padding:var(--espacio-5); margin-bottom:var(--espacio-5); border:1px solid var(--borde); border-radius:var(--radio); background:linear-gradient(115deg,#f2f9f8,#fff 64%,#e2f5f2); }
    .seguridad__cabecera p:not(.ceja) { max-width:720px; margin:0; color:var(--texto-suave); }
    .seguridad__cabecera .ceja { display:flex; align-items:center; gap:var(--espacio-2); }
    .seguridad__total { display:grid; place-items:center; min-width:46px; height:46px; padding:0 12px; border-radius:50%; background:var(--acento-suave); color:var(--acento-fuerte); font-size:1.1rem; font-weight:800; }
    .seguridad__lista { display:grid; gap:var(--espacio-3); }
    .seguridad__aviso { display:flex; align-items:center; gap:var(--espacio-4); }
    .seguridad__icono { display:grid; place-items:center; flex:0 0 42px; height:42px; border-radius:50%; background:var(--aviso-fondo); color:var(--aviso); }
    .seguridad__detalle { flex:1; }
    .seguridad__detalle h2 { margin:0 0 4px; font-size:1rem; }
    .seguridad__detalle p { margin:0; color:var(--texto-suave); font-size:.88rem; }
    .seguridad__vacio { display:flex; align-items:center; gap:var(--espacio-4); }
    .seguridad__vacio img { width:76px; height:80px; object-fit:contain; }
    .seguridad__vacio h2 { margin:0; font-size:1rem; }
    .seguridad__vacio p { margin:4px 0 0; color:var(--texto-suave); }
    @media(max-width:680px) { .seguridad__aviso { align-items:flex-start; flex-wrap:wrap; } .seguridad__aviso .boton { margin-left:58px; } }
  `,
})
export class AccesosEmergenciaComponent {
  private readonly api = inject(ApiService);
  private readonly pendientes = inject(PendientesService);
  protected readonly avisos = signal<readonly AvisoAccesoEmergencia[]>([]);
  protected readonly cargando = signal(false);
  protected readonly procesando = signal<string | null>(null);
  protected readonly error = signal('');

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.api.avisosAccesoEmergencia().subscribe({
      next: (avisos) => { this.avisos.set(avisos); this.cargando.set(false); },
      error: (fallo: unknown) => {
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudieron cargar los avisos.');
        this.cargando.set(false);
      },
    });
  }

  protected revisar(aviso: AvisoAccesoEmergencia): void {
    this.procesando.set(aviso.id);
    this.error.set('');
    this.api.revisarAvisoAccesoEmergencia(aviso.id).subscribe({
      next: () => {
        this.avisos.update((actuales) => actuales.filter((actual) => actual.id !== aviso.id));
        this.procesando.set(null);
        this.pendientes.cargar();
      },
      error: (fallo: unknown) => {
        this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo guardar la revisión.');
        this.procesando.set(null);
      },
    });
  }
}
