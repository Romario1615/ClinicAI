/**
 * Revisión de un documento marcado por el análisis de inyección.
 *
 * Muestra qué disparó la alerta y el texto de la versión vigente, y solo
 * entonces deja marcarlo como revisado con una nota. Sin leerlo, el desbloqueo
 * sería un trámite: justo lo que el bloqueo quiere evitar. El backend vuelve a
 * exigir el permiso de aprobación en la lectura y en la escritura.
 */
import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, input, output, signal, type OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import type { Documento } from '../../nucleo/servicios/api.service';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';

/** Longitud mínima de la nota: la misma que exige el backend. */
const MINIMO_NOTA = 10;

interface HallazgoRiesgo {
  readonly patron: string;
  readonly riesgo: string;
  readonly motivo: string;
  readonly extracto: string;
}

export interface RevisionRiesgo {
  readonly document_id: string;
  readonly titulo: string;
  readonly version: number;
  readonly riesgo: string;
  readonly hallazgos: readonly HallazgoRiesgo[];
  readonly fragmentos: readonly string[];
  readonly fragmentos_totales: number;
  readonly revisado: boolean;
  readonly revisado_en: string | null;
  readonly nota_revision: string | null;
}

@Component({
  selector: 'app-revision-riesgo',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent],
  template: `
    <app-ventana-flotante ceja="Revisión de seguridad" [titulo]="documento().titulo" forma="centrada" [anchoMaximo]="720" (cerrar)="cerrar.emit()">
      @if (cargando()) {
        <p role="status">Cargando el contenido marcado…</p>
      } @else if (revision()) {
        @let r = revision()!;
        <p class="riesgo__intro">
          El análisis encontró texto que parece una instrucción para el asistente (riesgo {{ r.riesgo }}, versión {{ r.version }}).
          Léalo: si es parte legítima del documento, márquelo como revisado; si no, cargue una versión corregida.
        </p>
        <h3 class="riesgo__subtitulo">Qué disparó la alerta</h3>
        <ul class="riesgo__hallazgos">
          @for (h of r.hallazgos; track $index) {
            <li><strong>{{ h.motivo }}</strong> <q>{{ h.extracto }}</q></li>
          } @empty {
            <li>El análisis no guardó extractos.</li>
          }
        </ul>
        <h3 class="riesgo__subtitulo">Texto de la versión</h3>
        <div class="riesgo__texto" tabindex="0" aria-label="Texto de la versión marcada">
          @for (f of r.fragmentos; track $index) { <p>{{ f }}</p> }
        </div>
        @if (r.fragmentos_totales > r.fragmentos.length) {
          <p class="campo__ayuda">Se muestran {{ r.fragmentos.length }} de {{ r.fragmentos_totales }} fragmentos.</p>
        }
        @if (r.revisado) {
          <p class="riesgo__hecho" role="status">Ya revisado. Nota: {{ r.nota_revision }}</p>
        } @else {
          <form class="riesgo__form" (ngSubmit)="marcar(r)">
            <label class="campo">
              <span class="campo__etiqueta">Nota de revisión</span>
              <textarea class="campo__control" name="nota-riesgo" rows="2" maxlength="1000" [(ngModel)]="nota"
                placeholder="Por qué el texto es aceptable"></textarea>
              <span class="campo__ayuda">Mínimo {{ minimoNota }} caracteres. Queda en la auditoría.</span>
            </label>
            <button class="boton boton--principal" type="submit" [disabled]="guardando() || !notaValida()">
              Marcar como revisado
            </button>
          </form>
        }
      }
      @if (error()) { <p class="campo__error" role="alert">{{ error() }}</p> }
    </app-ventana-flotante>
  `,
  styles: `
    .riesgo__intro { margin: 0 0 var(--espacio-3); }
    .riesgo__subtitulo { margin: var(--espacio-3) 0 var(--espacio-2); font-size: 0.8rem; letter-spacing: 0.05em;
      text-transform: uppercase; color: var(--texto-suave); }
    .riesgo__hallazgos { margin: 0; padding-left: 1.2em; display: grid; gap: var(--espacio-1); }
    .riesgo__texto { max-height: 260px; overflow-y: auto; padding: var(--espacio-2) var(--espacio-3);
      border: 1px solid var(--borde); border-radius: var(--radio); white-space: pre-wrap; font-size: 0.9rem; }
    .riesgo__texto p { margin: 0 0 var(--espacio-2); }
    .riesgo__form { display: grid; gap: var(--espacio-2); margin-top: var(--espacio-3); justify-items: start; }
    .riesgo__form .campo { width: 100%; }
    .riesgo__hecho { margin-top: var(--espacio-3); }
  `,
})
export class RevisionRiesgoComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly base = inject(CONFIGURACION).urlApi + '/conocimiento/documentos';

  readonly documento = input.required<Documento>();
  readonly cerrar = output<void>();
  /** El documento quedó revisado: la lista debe recargarse. */
  readonly revisado = output<string>();

  protected readonly minimoNota = MINIMO_NOTA;
  protected readonly revision = signal<RevisionRiesgo | null>(null);
  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly textoNota = signal('');
  protected readonly notaValida = computed(() => this.textoNota().trim().length >= MINIMO_NOTA);

  protected get nota(): string {
    return this.textoNota();
  }
  protected set nota(valor: string) {
    this.textoNota.set(valor);
  }

  ngOnInit(): void {
    this.http.get<RevisionRiesgo>(this.ruta()).subscribe({
      next: (r) => {
        this.revision.set(r);
        this.cargando.set(false);
      },
      error: () => {
        this.error.set('No se pudo cargar el contenido marcado.');
        this.cargando.set(false);
      },
    });
  }

  protected marcar(r: RevisionRiesgo): void {
    if (!this.notaValida()) {
      return;
    }
    this.guardando.set(true);
    this.error.set('');
    this.http.post(this.ruta(), { version: r.version, nota: this.textoNota().trim() }).subscribe({
      next: () => {
        this.guardando.set(false);
        this.revisado.emit(`«${r.titulo}» marcado como revisado. Ya puede aprobarse.`);
      },
      error: () => {
        this.guardando.set(false);
        this.error.set('No se pudo marcar como revisado. Compruebe su permiso de aprobación.');
      },
    });
  }

  private ruta(): string {
    return `${this.base}/${encodeURIComponent(this.documento().id)}/revision-de-riesgo`;
  }
}
