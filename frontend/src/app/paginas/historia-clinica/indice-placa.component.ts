/**
 * Índice de placa de O'Leary (periodoncia).
 *
 * Se marcan las piezas presentes y, en cada una, las superficies teñidas
 * (V, L, M, D). El porcentaje lo calcula el servidor; aquí se muestra una
 * vista previa y la serie de controles anteriores para ver la evolución.
 * Los registros no se editan: un control equivocado se compensa con otro.
 */
import { Component, computed, effect, inject, input, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type { RegistroPlaca } from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';

const CARAS = ['V', 'L', 'M', 'D'] as const;
const ARCADAS = [
  { nombre: 'Superior', piezas: [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28] },
  { nombre: 'Inferior', piezas: [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38] },
];
const NOMBRES_CARA: Record<string, string> = {
  V: 'Vestibular',
  L: 'Lingual o palatina',
  M: 'Mesial',
  D: 'Distal',
};

@Component({
  selector: 'app-indice-placa',
  standalone: true,
  imports: [DatePipe, DecimalPipe, FormsModule],
  template: `
    <section class="placa" aria-labelledby="titulo-placa">
      <!-- Cabecera en una fila: explicación, evolución y último control. En la
           historia la pantalla no se desplaza y el registro necesita su alto. -->
      <div class="placa__cabecera">
        <div class="placa__titulo">
          <p class="ceja">PERIODONCIA</p>
          <h2 id="titulo-placa">Índice de placa (O'Leary)</h2>
          <p class="placa__ayuda">
            Superficies con placa ÷ superficies evaluadas × 100. Marque las piezas presentes y las
            superficies teñidas. El sistema registra; la valoración es del profesional.
          </p>
        </div>
        @if (serie().length > 1) {
          <!-- Evolución: barras por control, del más antiguo al más reciente. -->
          <div class="placa__serie" role="img" [attr.aria-label]="'Evolución del índice: ' + resumenSerie()">
            @for (registro of serieCronologica(); track registro.id) {
              <div class="placa__barra" [style.height.%]="registro.porcentaje" [title]="registro.porcentaje + ' % · ' + (registro.creado_en | date: 'mediumDate')"></div>
            }
          </div>
        }
        @if (serie().length) {
          <div class="placa__ultimo">
            <span class="placa__cifra numerico">{{ serie()[0].porcentaje | number: '1.0-1' }} %</span>
            <span>último control · {{ serie()[0].creado_en | date: 'mediumDate' }}</span>
          </div>
        }
      </div>

      @if (error()) {
        <p class="aviso-error" role="alert">{{ error() }}</p>
      }
      @if (exito()) {
        <p class="exito" role="status">{{ exito() }}</p>
      }

      @if (puedeEscribir()) {
        <div class="tarjeta placa__registro">
          <div class="placa__arcadas">
            @for (arcada of arcadas; track arcada.nombre) {
              <div class="placa__arcada" [attr.aria-label]="'Arcada ' + arcada.nombre">
                @for (pieza of arcada.piezas; track pieza) {
                  <div class="pieza" [class.pieza--evaluada]="evaluada(pieza)">
                    <button type="button" class="pieza__numero numerico" [attr.aria-pressed]="evaluada(pieza)" (click)="alternarPieza(pieza)">
                      {{ pieza }}
                    </button>
                    <div class="pieza__caras">
                      @for (cara of caras; track cara) {
                        <button
                          type="button"
                          class="pieza__cara"
                          [class.pieza__cara--placa]="tienePlaca(pieza, cara)"
                          [disabled]="!evaluada(pieza)"
                          [attr.aria-pressed]="tienePlaca(pieza, cara)"
                          [attr.aria-label]="'Pieza ' + pieza + ', ' + nombreCara(cara)"
                          (click)="alternarCara(pieza, cara)"
                        >{{ cara }}</button>
                      }
                    </div>
                  </div>
                }
              </div>
            }
          </div>
          <div class="placa__pie">
            <label class="campo placa__observacion">
              <span class="campo__etiqueta">Observación (opcional)</span>
              <input class="campo__control" name="observacion" maxlength="500" [(ngModel)]="observacion" />
            </label>
            <span class="numerico placa__recuento">
              {{ evaluadas().size }} pieza(s) · {{ conPlaca() }} de {{ evaluadas().size * 4 }} superficies
              @if (evaluadas().size) { · <strong>{{ porcentajePrevio() | number: '1.0-1' }} %</strong> }
            </span>
            <div class="acciones">
              <button type="button" class="boton boton--pequeno" (click)="marcarTodas()">Marcar todas presentes</button>
              <button type="button" class="boton boton--principal" [disabled]="!evaluadas().size || guardando()" (click)="guardar()">
                Registrar control
              </button>
            </div>
          </div>
        </div>
      }
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: block; min-width: 0; }
    .placa { display: grid; gap: var(--espacio-3); }
    .placa__cabecera { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--espacio-3); }
    .placa__titulo { flex: 1 1 22rem; min-width: 0; }
    .placa__cabecera h2 { margin: 0; }
    .placa__cabecera .ceja { margin: 0; }
    .placa__ayuda { margin: 4px 0 0; color: var(--texto-suave); font-size: .88rem; max-width: 42rem; }
    .placa__ultimo { display: grid; justify-items: end; color: var(--texto-suave); font-size: .82rem; }
    .placa__cifra { font-size: 2rem; font-weight: 800; color: var(--acento-fuerte); }
    .placa__serie { display: flex; flex: 1 1 12rem; align-items: flex-end; gap: 6px; height: 80px; max-width: 24rem; padding: var(--espacio-2); border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie-elevada); }
    .placa__barra { flex: 1; min-height: 2px; max-width: 28px; border-radius: 4px 4px 0 0; background: var(--acento); }
    .placa__registro { display: grid; gap: var(--espacio-3); min-width: 0; }
    /* El registro conserva su ancho mínimo y desplaza en horizontal dentro de
       su marco si no cabe (teléfono): las dieciséis piezas de una arcada se
       leen en fila, como en la boca. */
    .placa__arcadas { display: grid; gap: var(--espacio-2); overflow-x: auto; padding-bottom: 2px; }
    .placa__arcada { display: grid; grid-template-columns: repeat(16, minmax(38px, 1fr)); gap: 4px; min-width: 676px; }
    .pieza { display: grid; gap: 2px; padding: 3px; border: 1px solid var(--borde); border-radius: 6px; opacity: .55; }
    .pieza--evaluada { opacity: 1; border-color: var(--acento); }
    .pieza__numero { min-height: 24px; border: 0; background: transparent; font-size: .78rem; font-weight: 700; cursor: pointer; }
    .pieza__caras { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; }
    .pieza__cara { min-height: 24px; padding: 0; border: 1px solid var(--borde); border-radius: 3px; background: var(--superficie-elevada); font-size: .68rem; cursor: pointer; }
    .pieza__cara--placa { border-color: #a1306f; background: #f6d4e6; color: #6b1747; font-weight: 700; }
    .pieza__cara:disabled { cursor: not-allowed; }
    .placa__pie { display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: var(--espacio-3); }
    .placa__observacion { flex: 1 1 16rem; min-width: 0; margin: 0; }
    .placa__recuento { align-self: center; color: var(--texto-suave); font-size: .9rem; }
    .placa__pie .acciones { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }

    /* Modo «llena» (pestaña de la historia en escritorio): todo a la vista,
       sin desplazamiento; el registro se queda con el alto sobrante. */
    @media (min-width: 821px) and (min-height: 600px) {
      :host(.llena) { display: flex; flex-direction: column; min-height: 0; }
      :host(.llena) .placa { display: flex; flex: 1 1 0; flex-direction: column; min-height: 0; }
      :host(.llena) .placa > * { flex: none; margin: 0; }
      :host(.llena) .placa__cabecera h2 { font-size: 1.15rem; }
      :host(.llena) .placa__serie { height: 64px; }
      :host(.llena) .placa__registro { align-content: start; padding: var(--espacio-3) var(--espacio-4); }
    }
  `,
})
export class IndicePlacaComponent {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);

  readonly pacienteId = input.required<string>();

  protected readonly caras = CARAS;
  protected readonly arcadas = ARCADAS;
  protected readonly serie = signal<readonly RegistroPlaca[]>([]);
  protected readonly evaluadas = signal<ReadonlySet<number>>(new Set());
  protected readonly placa = signal<ReadonlyMap<number, ReadonlySet<string>>>(new Map());
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  protected readonly exito = signal('');
  protected observacion = '';

  protected readonly puedeEscribir = computed(() =>
    this.sesion.tienePermiso(PERMISOS.odontogramaEscribir),
  );
  protected readonly conPlaca = computed(() =>
    [...this.placa().values()].reduce((total, caras) => total + caras.size, 0),
  );
  protected readonly porcentajePrevio = computed(() => {
    const total = this.evaluadas().size * 4;
    return total ? (this.conPlaca() * 100) / total : 0;
  });
  protected readonly serieCronologica = computed(() => [...this.serie()].reverse());
  protected readonly resumenSerie = computed(() =>
    this.serieCronologica()
      .map((r) => `${r.porcentaje} %`)
      .join(', '),
  );

  constructor() {
    effect(() => this.cargar(this.pacienteId()));
  }

  private cargar(pacienteId: string): void {
    this.api.indicePlaca(pacienteId).subscribe({
      next: (serie) => this.serie.set(serie),
      error: (fallo: unknown) => this.error.set(this.mensaje(fallo)),
    });
  }

  protected evaluada(pieza: number): boolean {
    return this.evaluadas().has(pieza);
  }

  protected tienePlaca(pieza: number, cara: string): boolean {
    return this.placa().get(pieza)?.has(cara) ?? false;
  }

  protected nombreCara(cara: string): string {
    return NOMBRES_CARA[cara] ?? cara;
  }

  protected alternarPieza(pieza: number): void {
    const evaluadas = new Set(this.evaluadas());
    if (evaluadas.has(pieza)) {
      evaluadas.delete(pieza);
      const placa = new Map(this.placa());
      placa.delete(pieza);
      this.placa.set(placa);
    } else {
      evaluadas.add(pieza);
    }
    this.evaluadas.set(evaluadas);
  }

  protected marcarTodas(): void {
    this.evaluadas.set(new Set(ARCADAS.flatMap((arcada) => arcada.piezas)));
  }

  protected alternarCara(pieza: number, cara: string): void {
    if (!this.evaluada(pieza)) return;
    const placa = new Map(this.placa());
    const caras = new Set(placa.get(pieza) ?? []);
    if (caras.has(cara)) caras.delete(cara);
    else caras.add(cara);
    placa.set(pieza, caras);
    this.placa.set(placa);
  }

  protected guardar(): void {
    if (!this.evaluadas().size || this.guardando()) return;
    const superficies: Record<string, string[]> = {};
    for (const [pieza, caras] of this.placa()) {
      if (caras.size) superficies[String(pieza)] = [...caras];
    }
    this.guardando.set(true);
    this.error.set('');
    this.api
      .registrarIndicePlaca(this.pacienteId(), {
        piezas_evaluadas: [...this.evaluadas()],
        superficies_con_placa: superficies,
        observacion: this.observacion.trim() || null,
      })
      .subscribe({
        next: (registro) => {
          this.guardando.set(false);
          this.serie.update((serie) => [registro, ...serie]);
          this.evaluadas.set(new Set());
          this.placa.set(new Map());
          this.observacion = '';
          this.exito.set(`Control registrado: ${registro.porcentaje} % de superficies con placa.`);
        },
        error: (fallo: unknown) => {
          this.guardando.set(false);
          this.error.set(this.mensaje(fallo));
        },
      });
  }

  private mensaje(fallo: unknown): string {
    return fallo instanceof FalloApi ? fallo.message : 'No se pudo completar la operación.';
  }
}
