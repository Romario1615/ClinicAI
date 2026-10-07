/**
 * Delegaciones de firma de recetas.
 *
 * Administración registra que un profesional (por ejemplo, un residente)
 * puede firmar recetas a nombre de otro (su adjunto) durante un periodo y con
 * un motivo. Sin delegación vigente nadie firma por otro; el servidor lo
 * comprueba en cada receta y la auditoría registra quién actuó.
 */
import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { DelegacionFirma } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import type { Profesional } from '../../nucleo/modelos/dominio';

@Component({
  selector: 'app-delegaciones',
  standalone: true,
  imports: [DatePipe, FormsModule],
  template: `
    <header class="cabecera">
      <p class="ceja">PROFESIONALES</p>
      <h1>Delegaciones de firma</h1>
      <p class="cabecera__sub">
        Quién puede firmar recetas a nombre de otro profesional, desde cuándo y hasta cuándo.
        Sin una delegación vigente, cada profesional firma solo las suyas.
      </p>
    </header>

    @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (exito()) { <p class="exito" role="status">{{ exito() }}</p> }

    <form class="tarjeta formulario" (ngSubmit)="crear()">
      <h2>Nueva delegación</h2>
      <div class="formulario__rejilla">
        <label class="campo"><span class="campo__etiqueta">Firma (responsable)</span>
          <select class="campo__control" name="delegante" [(ngModel)]="delegante">
            <option value="">Seleccione…</option>
            @for (p of profesionales(); track p.id) { <option [value]="p.id">{{ p.nombre }} {{ p.apellido }}</option> }
          </select>
        </label>
        <label class="campo"><span class="campo__etiqueta">Puede firmar por él/ella</span>
          <select class="campo__control" name="delegado" [(ngModel)]="delegado">
            <option value="">Seleccione…</option>
            @for (p of profesionales(); track p.id) {
              @if (p.id !== delegante) { <option [value]="p.id">{{ p.nombre }} {{ p.apellido }}</option> }
            }
          </select>
        </label>
        <label class="campo"><span class="campo__etiqueta">Desde</span>
          <input class="campo__control" type="date" name="desde" [(ngModel)]="desde" />
        </label>
        <label class="campo"><span class="campo__etiqueta">Hasta</span>
          <input class="campo__control" type="date" name="hasta" [(ngModel)]="hasta" />
        </label>
      </div>
      <label class="campo"><span class="campo__etiqueta">Motivo</span>
        <input class="campo__control" name="motivo" maxlength="500" [(ngModel)]="motivo" placeholder="Residencia de odontopediatría 2026" />
      </label>
      <div class="acciones acciones--final">
        <button class="boton boton--principal" type="submit" [disabled]="guardando()">Registrar delegación</button>
      </div>
    </form>

    <section aria-label="Delegaciones registradas">
      @for (d of delegaciones(); track d.id) {
        <article class="tarjeta delegacion" [class.delegacion--vigente]="d.vigente">
          <div>
            <strong>{{ nombre(d.delegado_id) }}</strong> firma por <strong>{{ nombre(d.delegante_id) }}</strong>
            <p class="delegacion__detalle">
              {{ d.vigente_desde | date: 'mediumDate' }} – {{ d.vigente_hasta | date: 'mediumDate' }} · {{ d.motivo }}
              @if (d.revocada_en) { · revocada {{ d.revocada_en | date: 'mediumDate' }} }
            </p>
          </div>
          <span class="delegacion__estado">{{ d.vigente ? 'Vigente' : d.revocada_en ? 'Revocada' : 'No vigente' }}</span>
          @if (d.vigente) {
            <button class="boton boton--plano boton--pequeno" type="button" (click)="revocar(d)">Revocar</button>
          }
        </article>
      } @empty {
        <p class="cabecera__sub">No hay delegaciones registradas.</p>
      }
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .cabecera { margin-bottom: var(--espacio-5); }
    .cabecera__sub { color: var(--texto-suave); max-width: 44rem; }
    .formulario { display: grid; gap: var(--espacio-3); margin-bottom: var(--espacio-5); }
    .formulario h2 { margin: 0; }
    .formulario__rejilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--espacio-3); }
    .delegacion { display: flex; align-items: center; gap: var(--espacio-3); margin-bottom: var(--espacio-2); }
    .delegacion > div { flex: 1; }
    .delegacion--vigente { box-shadow: inset 3px 0 0 var(--exito), var(--sombra-1); }
    .delegacion__detalle { margin: 4px 0 0; font-size: .85rem; color: var(--texto-suave); }
    .delegacion__estado { font-size: .8rem; font-weight: 700; color: var(--texto-suave); }
    .delegacion--vigente .delegacion__estado { color: var(--exito); }
  `,
})
export class DelegacionesComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);

  protected readonly delegaciones = signal<readonly DelegacionFirma[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly exito = signal('');
  protected delegante = '';
  protected delegado = '';
  protected desde = '';
  protected hasta = '';
  protected motivo = '';

  private readonly nombres = computed(
    () => new Map(this.profesionales().map((p) => [p.id, `${p.nombre} ${p.apellido}`])),
  );

  constructor() {
    this.catalogo.profesionales().subscribe({ next: (lista) => this.profesionales.set(lista), error: () => undefined });
    this.cargar();
  }

  private cargar(): void {
    this.api.delegaciones().subscribe({
      next: (lista) => this.delegaciones.set(lista),
      error: (fallo: unknown) => this.error.set(this.mensaje(fallo)),
    });
  }

  protected nombre(id: string): string {
    return this.nombres().get(id) ?? 'Profesional';
  }

  protected crear(): void {
    if (!this.delegante || !this.delegado || !this.desde || !this.hasta || this.motivo.trim().length < 5) {
      this.error.set('Complete profesionales, fechas y un motivo (mínimo 5 caracteres).');
      return;
    }
    this.guardando.set(true);
    this.error.set('');
    this.api
      .crearDelegacion({
        delegante_id: this.delegante,
        delegado_id: this.delegado,
        // Inicio del día "desde" y fin del día "hasta", en hora local con zona.
        vigente_desde: new Date(`${this.desde}T00:00:00`).toISOString(),
        vigente_hasta: new Date(`${this.hasta}T23:59:59`).toISOString(),
        motivo: this.motivo.trim(),
      })
      .subscribe({
        next: (nueva) => {
          this.guardando.set(false);
          this.delegaciones.update((lista) => [nueva, ...lista]);
          this.exito.set('Delegación registrada.');
          this.motivo = '';
        },
        error: (fallo: unknown) => {
          this.guardando.set(false);
          this.error.set(this.mensaje(fallo));
        },
      });
  }

  protected revocar(delegacion: DelegacionFirma): void {
    this.api.revocarDelegacion(delegacion.id).subscribe({
      next: (actualizada) => {
        this.delegaciones.update((lista) => lista.map((d) => (d.id === actualizada.id ? actualizada : d)));
        this.exito.set('Delegación revocada.');
      },
      error: (fallo: unknown) => this.error.set(this.mensaje(fallo)),
    });
  }

  private mensaje(fallo: unknown): string {
    return fallo instanceof FalloApi ? fallo.message : 'No se pudo completar la operación.';
  }
}
