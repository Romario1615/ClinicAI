/**
 * Indicaciones para el paciente después de la consulta.
 *
 * El profesional escribe lo que el paciente debe hacer y, si quiere, adjunta
 * la receta confirmada. Al publicar, el paciente recibe por WhatsApp un aviso
 * **sin** contenido clínico con un enlace que caduca; para leer, confirma su
 * fecha de nacimiento. Si el paciente no aceptó mensajes, la pantalla lo dice
 * y ofrece copiar el enlace para entregarlo en mano.
 *
 * Una indicación publicada no se edita: se anula con motivo y se publica otra.
 */
import { Component, effect, inject, input, signal, untracked, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { FalloApi } from '../../nucleo/servicios/api.service';

export interface Indicacion {
  readonly id: string;
  readonly texto: string;
  readonly receta_id: string | null;
  readonly creado_en: string;
  readonly expira_en: string;
  readonly lecturas: number;
  readonly primera_lectura_en: string | null;
  readonly bloqueada: boolean;
  readonly anulada_en: string | null;
}

export interface RecetaOpcion {
  readonly id: string;
  readonly etiqueta: string;
}

@Component({
  selector: 'app-indicaciones-paciente',
  standalone: true,
  imports: [DatePipe, FormsModule, VentanaFlotanteComponent],
  template: `
    <section class="indicaciones tarjeta" aria-labelledby="titulo-indicaciones">
      <!-- Acción principal arriba a la derecha; la lista de publicadas es lo
           único que desplaza. -->
      <header class="indicaciones__cabecera">
        <div>
          <h3 id="titulo-indicaciones">Indicaciones para el paciente</h3>
          <p class="ayuda">
            El paciente recibe por WhatsApp solo un aviso con un enlace seguro: el texto y la medicación
            se ven tras confirmar su fecha de nacimiento.
          </p>
        </div>
        @if (puedeEscribir()) {
          <button class="boton boton--principal" type="button" (click)="abrirEditor()" aria-haspopup="dialog">Redactar indicaciones</button>
        }
      </header>
      @if (editorAbierto()) {
        <app-ventana-flotante
          ceja="Seguimiento clínico"
          titulo="Redactar indicaciones"
          forma="centrada"
          [anchoMaximo]="680"
          [cierraAlPulsarFuera]="false"
          (cerrar)="cerrarEditor()"
        >
        <form id="formulario-indicaciones-paciente" class="formulario" (ngSubmit)="publicar()" novalidate>
          <label class="campo">
            <span class="campo__etiqueta">Indicaciones</span>
            <textarea class="campo__control" name="texto" rows="5" maxlength="4000" required minlength="10"
                      [(ngModel)]="texto" placeholder="Cuidados en casa, signos de alarma, cuándo volver…"></textarea>
            <span class="campo__ayuda">{{ texto.length }}/4000</span>
          </label>
          <div class="fila">
            <label class="campo">
              <span class="campo__etiqueta">Adjuntar receta (opcional)</span>
              <select class="campo__control" name="receta" [(ngModel)]="recetaId">
                <option value="">Sin receta</option>
                @for (r of recetas(); track r.id) { <option [value]="r.id">{{ r.etiqueta }}</option> }
              </select>
            </label>
            <label class="campo">
              <span class="campo__etiqueta">El enlace caduca en</span>
              <select class="campo__control" name="dias" [(ngModel)]="dias">
                <option [ngValue]="3">3 días</option>
                <option [ngValue]="7">7 días</option>
                <option [ngValue]="15">15 días</option>
                <option [ngValue]="30">30 días</option>
              </select>
            </label>
          </div>
          @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
        </form>
        <div pie>
          <button class="boton" type="button" (click)="cerrarEditor()" [disabled]="ocupado()">Cancelar</button>
          <button class="boton boton--principal" type="submit" form="formulario-indicaciones-paciente" [disabled]="ocupado()">
            {{ ocupado() ? 'Publicando…' : 'Publicar indicaciones' }}
          </button>
        </div>
        </app-ventana-flotante>
      }

      @if (publicada(); as p) {
        <div class="resultado" [class.resultado--sin-aviso]="!p.aviso_enviado" role="status">
          <strong>{{ p.aviso_enviado ? 'Publicada. El paciente recibirá el aviso por WhatsApp.' : 'Publicada, sin aviso automático.' }}</strong>
          @if (p.motivo_sin_aviso) { <p>{{ p.motivo_sin_aviso }}</p> }
          <div class="enlace">
            <input class="campo__control" readonly [value]="p.enlace" aria-label="Enlace para el paciente" />
            <button class="boton boton--pequeno" type="button" (click)="copiar(p.enlace)">{{ copiado() ? 'Copiado' : 'Copiar enlace' }}</button>
          </div>
          <small>Caduca el {{ p.expira_en | date: 'dd/MM/yyyy HH:mm' }}. El enlace solo se muestra ahora.</small>
        </div>
      }

      <h4>Publicadas</h4>
      <ul class="lista desplazable">
        @for (i of lista(); track i.id) {
          <li [class.anulada]="!!i.anulada_en">
            <div>
              <span class="numerico">{{ i.creado_en | date: 'dd/MM/yy HH:mm' }}</span>
              <p>{{ i.texto }}</p>
              <small>
                @if (i.anulada_en) { Anulada }
                @else if (i.bloqueada) { Enlace bloqueado por intentos fallidos }
                @else if (i.lecturas > 0) { Leída {{ i.lecturas }} vez/veces · primera {{ i.primera_lectura_en | date: 'dd/MM HH:mm' }} }
                @else { Sin leer · caduca {{ i.expira_en | date: 'dd/MM' }} }
                @if (i.receta_id) { · con receta }
              </small>
            </div>
            @if (puedeEscribir() && !i.anulada_en) {
              <button class="boton boton--pequeno boton--plano" type="button" (click)="abrirAnulacion(i.id)">Anular</button>
            }
          </li>
        } @empty {
          <li class="vacio">Aún no hay indicaciones para este paciente.</li>
        }
      </ul>
    </section>
    @if (anulando(); as id) {
      @if (indicacionPorId(id); as indicacion) {
        <app-ventana-flotante
          ceja="Seguimiento clínico"
          titulo="Anular indicación"
          forma="centrada"
          [anchoMaximo]="520"
          [cierraAlPulsarFuera]="false"
          (cerrar)="cerrarAnulacion()"
        >
        <p>La publicación quedará marcada como anulada. Registra un motivo para conservar el contexto asistencial.</p>
        <form [id]="'formulario-anulacion-' + id" (ngSubmit)="anular(indicacion)">
          <label class="campo">
            <span class="campo__etiqueta">Motivo de anulación</span>
            <textarea class="campo__control" name="motivoAnulacion" [(ngModel)]="motivoAnulacion" minlength="5" maxlength="500" required></textarea>
          </label>
          @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
        </form>
        <div pie>
          <button class="boton" type="button" (click)="cerrarAnulacion()" [disabled]="anulandoEnCurso()">Volver</button>
          <button class="boton boton--peligro" type="submit" [attr.form]="'formulario-anulacion-' + id" [disabled]="anulandoEnCurso()">
            {{ anulandoEnCurso() ? 'Anulando…' : 'Confirmar anulación' }}
          </button>
        </div>
        </app-ventana-flotante>
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: block; min-width: 0; }
    .indicaciones { display: grid; gap: var(--espacio-3); padding: var(--espacio-3) var(--espacio-4); }
    .indicaciones__cabecera { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--espacio-2) var(--espacio-4); }
    .indicaciones__cabecera > div { flex: 1 1 20rem; min-width: 0; }
    .indicaciones__cabecera .ayuda { margin-top: var(--espacio-1); }
    h3 { margin: 0; font-size: 1.15rem; } h4 { margin: var(--espacio-1) 0 0; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--texto-suave); }
    .ayuda { margin: 0; color: var(--texto-suave); font-size: 0.88rem; }
    .formulario { display: grid; gap: var(--espacio-2); padding: var(--espacio-4); border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie); }
    .formulario textarea { min-height: 110px; padding: var(--espacio-2) var(--espacio-3); }
    .fila { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--espacio-3); }
    .resultado { display: grid; gap: var(--espacio-2); padding: var(--espacio-3); border-radius: var(--radio); background: color-mix(in srgb, var(--exito) 12%, transparent); }
    .resultado--sin-aviso { background: var(--aviso-fondo); color: var(--aviso); }
    .resultado p { margin: 0; }
    .enlace { display: flex; gap: var(--espacio-2); }
    .enlace input { flex: 1; font-size: 0.82rem; }
    .lista { list-style: none; margin: 0; padding: 0; display: grid; align-content: start; gap: var(--espacio-2); min-width: 0; }
    .lista li { display: flex; justify-content: space-between; gap: var(--espacio-3); padding: var(--espacio-3); border: 1px solid var(--superficie-hundida); border-radius: var(--radio); overflow-wrap: anywhere; }
    .lista li > div { min-width: 0; }
    .lista li .boton { flex: none; align-self: flex-start; }

    /* Modo «llena» (pestaña de la historia en escritorio). */
    @media (min-width: 821px) and (min-height: 600px) {
      :host(.llena) { display: flex; flex-direction: column; min-height: 0; }
      :host(.llena) .indicaciones { display: flex; flex: 1 1 0; flex-direction: column; min-height: 0; }
      :host(.llena) .indicaciones > * { flex: none; }
      :host(.llena) .indicaciones > .lista { flex: 1 1 0; min-height: 0; padding: 2px; }
    }
    .lista p { margin: 4px 0; white-space: pre-line; }
    .lista small { color: var(--texto-suave); }
    .anular { display: flex; gap: 6px; align-items: center; }
    .anular input { width: 12rem; }
    .anulada { opacity: 0.6; }
    .anulada p { text-decoration: line-through; }
    .vacio { color: var(--texto-suave); border: 0 !important; }
  `,
})
export class IndicacionesPacienteComponent {
  private readonly api = inject(OperacionesService);
  readonly pacienteId = input.required<string>();
  readonly puedeEscribir = input(false);
  readonly recetas = input<readonly RecetaOpcion[]>([]);

  protected readonly lista = signal<readonly Indicacion[]>([]);
  protected readonly ocupado = signal(false);
  protected readonly anulandoEnCurso = signal(false);
  protected readonly editorAbierto = signal(false);
  protected readonly error = signal('');
  protected readonly copiado = signal(false);
  protected readonly publicada = signal<{ enlace: string; expira_en: string; aviso_enviado: boolean; motivo_sin_aviso: string | null } | null>(null);
  protected texto = '';
  protected recetaId = '';
  protected dias = 7;

  constructor() {
    effect(() => {
      const id = this.pacienteId();
      untracked(() => this.cargar(id));
    });
  }

  private cargar(id: string): void {
    this.api.leer<Indicacion[]>(`/historia/pacientes/${id}/indicaciones`).subscribe({
      next: (lista) => this.lista.set(lista),
      error: () => this.lista.set([]),
    });
  }

  protected abrirEditor(): void {
    this.error.set('');
    this.texto = '';
    this.recetaId = '';
    this.dias = 7;
    this.editorAbierto.set(true);
  }

  protected cerrarEditor(): void {
    if (this.ocupado()) return;
    this.editorAbierto.set(false);
    this.error.set('');
    this.texto = '';
    this.recetaId = '';
    this.dias = 7;
  }

  protected indicacionPorId(id: string): Indicacion | null {
    return this.lista().find((indicacion) => indicacion.id === id) ?? null;
  }

  protected abrirAnulacion(id: string): void {
    this.error.set('');
    this.motivoAnulacion = '';
    this.anulando.set(id);
  }

  protected cerrarAnulacion(): void {
    if (this.anulandoEnCurso()) return;
    this.anulando.set(null);
    this.motivoAnulacion = '';
    this.error.set('');
  }

  protected publicar(): void {
    if (!this.puedeEscribir() || this.ocupado()) return;
    if (this.texto.trim().length < 10) {
      this.error.set('Escriba las indicaciones (mínimo 10 caracteres).');
      return;
    }
    this.ocupado.set(true);
    this.error.set('');
    this.api
      .guardar<{ enlace: string; expira_en: string; aviso_enviado: boolean; motivo_sin_aviso: string | null }>(
        `/historia/pacientes/${this.pacienteId()}/indicaciones`,
        { texto: this.texto.trim(), receta_id: this.recetaId || null, dias_validez: this.dias },
        crypto.randomUUID(),
      )
      .subscribe({
        next: (resultado) => {
          this.ocupado.set(false);
          this.publicada.set(resultado);
          this.copiado.set(false);
          this.texto = '';
          this.recetaId = '';
          this.dias = 7;
          this.editorAbierto.set(false);
          this.cargar(this.pacienteId());
        },
        error: (fallo: FalloApi) => {
          this.ocupado.set(false);
          this.error.set(fallo.message);
        },
      });
  }

  protected copiar(enlace: string): void {
    void navigator.clipboard?.writeText(enlace).then(() => this.copiado.set(true), () => undefined);
  }

  protected readonly anulando = signal<string | null>(null);
  protected motivoAnulacion = '';

  protected anular(indicacion: Indicacion): void {
    const motivo = this.motivoAnulacion.trim();
    if (motivo.length < 5) {
      this.error.set('Escriba el motivo de la anulación (mínimo 5 caracteres).');
      return;
    }
    if (this.anulandoEnCurso()) return;
    this.anulandoEnCurso.set(true);
    this.api.cambiar<Indicacion>(`/historia/indicaciones/${indicacion.id}/anulacion`, { motivo }).subscribe({
      next: () => {
        this.anulandoEnCurso.set(false);
        this.anulando.set(null);
        this.motivoAnulacion = '';
        this.cargar(this.pacienteId());
      },
      error: (fallo: FalloApi) => { this.anulandoEnCurso.set(false); this.error.set(fallo.message); },
    });
  }
}
