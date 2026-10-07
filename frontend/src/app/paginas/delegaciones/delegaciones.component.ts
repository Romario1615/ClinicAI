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
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

@Component({
  selector: 'app-delegaciones',
  standalone: true,
  imports: [DatePipe, FormsModule, VentanaFlotanteComponent],
  template: `
    <header class="cabecera">
      <div>
        <p class="ceja">PROFESIONALES</p>
        <h1>Delegaciones de firma</h1>
        <p class="cabecera__sub">
          Quién puede firmar recetas a nombre de otro profesional, desde cuándo y hasta cuándo.
          Sin una delegación vigente, cada profesional firma solo las suyas.
        </p>
      </div>
      <button class="boton boton--principal" type="button" (click)="abrirEditor()"
              [disabled]="profesionalesCargando() || profesionales().length < 2" aria-haspopup="dialog">
        Nueva delegación
      </button>
    </header>

    @if (profesionalesCargando()) {
      <p class="campo__ayuda aviso-profesionales" role="status">Cargando perfiles profesionales…</p>
    } @else if (profesionales().length < 2) {
      <p class="campo__ayuda aviso-profesionales">
        Se necesitan al menos dos perfiles profesionales activos para crear una delegación.
      </p>
    }

    @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (exito()) { <p class="exito" role="status">{{ exito() }}</p> }

    @if (editorAbierto()) {
      <app-ventana-flotante ceja="Profesionales" titulo="Nueva delegación de firma"
                            forma="centrada" [anchoMaximo]="680" [cierraAlPulsarFuera]="false"
                            (cerrar)="cerrarEditor()">
        <p class="editor__ayuda">
          La autorización queda limitada a este profesional, este periodo y el motivo registrado.
          La firma y cada receta siguen quedando auditadas.
        </p>
        <form id="form-delegacion" class="formulario" #formulario="ngForm" (ngSubmit)="crear()" novalidate>
          <div class="formulario__rejilla">
            <label class="campo"><span class="campo__etiqueta">Profesional responsable</span>
              <select class="campo__control" name="delegante" [(ngModel)]="delegante" required>
                <option value="">Seleccione…</option>
                @for (p of profesionales(); track p.id) { <option [value]="p.id">{{ p.nombre }} {{ p.apellido }}</option> }
              </select>
              <span class="campo__ayuda">La receta se registra a nombre de esta persona.</span>
            </label>
            <label class="campo"><span class="campo__etiqueta">Profesional autorizado</span>
              <select class="campo__control" name="delegado" [(ngModel)]="delegado" required>
                <option value="">Seleccione…</option>
                @for (p of profesionales(); track p.id) {
                  @if (p.id !== delegante) { <option [value]="p.id">{{ p.nombre }} {{ p.apellido }}</option> }
                }
              </select>
              <span class="campo__ayuda">No puede ser la misma persona que la responsable.</span>
            </label>
            <label class="campo"><span class="campo__etiqueta">Vigente desde</span>
              <input class="campo__control" type="date" name="desde" [(ngModel)]="desde"
                     [max]="hasta || null" required />
            </label>
            <label class="campo"><span class="campo__etiqueta">Vigente hasta</span>
              <input class="campo__control" type="date" name="hasta" [(ngModel)]="hasta"
                     [min]="desde || null" required />
            </label>
          </div>
          <label class="campo"><span class="campo__etiqueta">Motivo</span>
            <textarea class="campo__control" name="motivo" rows="3" minlength="5" maxlength="500"
                      [(ngModel)]="motivo" required
                      placeholder="Ej. Cobertura durante vacaciones del profesional"></textarea>
            <span class="campo__ayuda">Mínimo 5 caracteres. Este motivo queda en el historial de auditoría.</span>
          </label>
          @if (errorEditor()) { <p class="aviso-error" role="alert">{{ errorEditor() }}</p> }
        </form>
        <div class="acciones acciones--final" pie>
          <button class="boton" type="button" (click)="cerrarEditor()">Cancelar</button>
          <button class="boton boton--principal" type="submit" form="form-delegacion"
                  [disabled]="guardando() || formulario.invalid">
            {{ guardando() ? 'Registrando…' : 'Registrar delegación' }}
          </button>
        </div>
      </app-ventana-flotante>
    }

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
    .cabecera { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--espacio-4); margin-bottom: var(--espacio-5); }
    .cabecera__sub { color: var(--texto-suave); max-width: 44rem; }
    .editor__ayuda { max-width: 58ch; color: var(--texto-suave); }
    .formulario { display: grid; gap: var(--espacio-4); }
    .formulario__rejilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--espacio-3); }
    .delegacion { display: flex; align-items: center; gap: var(--espacio-3); margin-bottom: var(--espacio-2); }
    .delegacion > div { flex: 1; }
    .delegacion--vigente { box-shadow: inset 3px 0 0 var(--exito), var(--sombra-1); }
    .delegacion__detalle { margin: 4px 0 0; font-size: .85rem; color: var(--texto-suave); }
    .delegacion__estado { font-size: .8rem; font-weight: 700; color: var(--texto-suave); }
    .delegacion--vigente .delegacion__estado { color: var(--exito); }
    .aviso-profesionales { margin: calc(-1 * var(--espacio-3)) 0 var(--espacio-4); }
    @media (max-width: 640px) {
      .cabecera { align-items: stretch; flex-direction: column; }
      .cabecera > .boton { align-self: flex-start; }
      .delegacion { align-items: flex-start; flex-wrap: wrap; }
      .delegacion > div { flex-basis: 100%; }
    }
  `,
})
export class DelegacionesComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);

  protected readonly delegaciones = signal<readonly DelegacionFirma[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly profesionalesCargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly errorEditor = signal('');
  protected readonly exito = signal('');
  protected readonly editorAbierto = signal(false);
  protected delegante = '';
  protected delegado = '';
  protected desde = '';
  protected hasta = '';
  protected motivo = '';

  private readonly nombres = computed(
    () => new Map(this.profesionales().map((p) => [p.id, `${p.nombre} ${p.apellido}`])),
  );

  constructor() {
    this.catalogo.profesionales().subscribe({
      next: (lista) => {
        this.profesionales.set(lista);
        this.profesionalesCargando.set(false);
      },
      error: () => {
        this.profesionalesCargando.set(false);
        this.error.set('No se pudieron cargar los perfiles profesionales. Vuelva a intentarlo.');
      },
    });
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

  protected abrirEditor(): void {
    this.limpiarFormulario();
    this.errorEditor.set('');
    this.exito.set('');
    this.editorAbierto.set(true);
  }

  protected cerrarEditor(): void {
    if (this.guardando()) return;
    this.editorAbierto.set(false);
    this.errorEditor.set('');
    this.limpiarFormulario();
  }

  private limpiarFormulario(): void {
    this.delegante = '';
    this.delegado = '';
    this.desde = '';
    this.hasta = '';
    this.motivo = '';
  }

  protected crear(): void {
    if (!this.delegante || !this.delegado || !this.desde || !this.hasta || this.motivo.trim().length < 5) {
      this.errorEditor.set('Complete profesionales, fechas y un motivo (mínimo 5 caracteres).');
      return;
    }
    if (this.delegante === this.delegado) {
      this.errorEditor.set('Seleccione dos profesionales distintos.');
      return;
    }
    if (this.hasta < this.desde) {
      this.errorEditor.set('La fecha de término debe ser igual o posterior a la fecha de inicio.');
      return;
    }
    this.guardando.set(true);
    this.errorEditor.set('');
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
          this.editorAbierto.set(false);
          this.exito.set('Delegación registrada.');
          this.limpiarFormulario();
        },
        error: (fallo: unknown) => {
          this.guardando.set(false);
          this.errorEditor.set(this.mensaje(fallo));
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
