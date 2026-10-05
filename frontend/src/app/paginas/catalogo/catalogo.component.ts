import { Component, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';

import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import type { Sede, Servicio, Profesional } from '../../nucleo/modelos/dominio';

@Component({
  selector: 'app-catalogo', standalone: true,
  template: `
    <header class="modulo-cabecera"><div class="modulo-cabecera__texto"><p class="ceja">CONFIGURACIÓN</p><h1>Catálogo de la clínica</h1><p>Sedes, servicios y profesionales disponibles para su sesión.</p></div><img class="modulo-cabecera__imagen" src="/images/catalogo-clinica.png" alt="" aria-hidden="true" loading="lazy" /></header>
    @if (error()) { <p role="alert">{{ error() }}</p><button (click)="cargar()" class="boton">Reintentar</button> }
    @if (cargando()) { <p role="status">Cargando catálogo…</p> }
    <h2>Sedes</h2><div class="rejilla">@for (s of sedes(); track s.id) { <article class="tarjeta"><h3>{{ s.nombre }}</h3><p>{{ s.direccion || 'Dirección no registrada' }}</p><small>{{ s.zona_horaria }}</small></article> }</div>
    <h2>Servicios</h2><div class="tabla-envoltorio"><table class="tabla"><thead><tr><th>Servicio</th><th>Duración</th><th>Preparación</th><th>Precio</th></tr></thead><tbody>
    @for (s of servicios(); track s.id) { <tr><td>{{ s.nombre }}</td><td>{{ s.duracion_minutos }} min</td><td>{{ s.minutos_preparacion }} min</td><td>{{ s.precio === null ? 'Consultar' : '$' + s.precio }}</td></tr> }
    </tbody></table></div><h2>Profesionales</h2><div class="rejilla">@for (p of profesionales(); track p.id) { <article class="tarjeta"><h3>{{ p.nombre }} {{ p.apellido }}</h3><p>Registro {{ p.numero_registro_profesional }}</p></article> }</div>
  `,
  styles: `h2 { margin-top: 24px; }`,
})
export class CatalogoComponent {
  private readonly catalogo = inject(CatalogoService);
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  constructor() { this.cargar(); }
  protected cargar(): void {
    this.error.set(''); this.cargando.set(true);
    forkJoin({ sedes: this.catalogo.sedes(), servicios: this.catalogo.servicios(), profesionales: this.catalogo.profesionales() }).subscribe({
      next: r => { this.sedes.set(r.sedes); this.servicios.set(r.servicios); this.profesionales.set(r.profesionales); this.cargando.set(false); },
      error: () => { this.error.set('No se pudo cargar el catálogo.'); this.cargando.set(false); },
    });
  }
}
