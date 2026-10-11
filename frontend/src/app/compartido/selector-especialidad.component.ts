/**
 * «Revisando como»: elige la especialidad desde la que se ve la historia.
 *
 * Con una sola especialidad se muestra como etiqueta, sin botones. Avisa de
 * que alergias, medicamentos y recetas se comparten entre especialidades, para
 * que nadie crea que lo que no ve no existe.
 */
import { Component, inject, input, output, ChangeDetectionStrategy } from '@angular/core';

import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';

@Component({
  selector: 'app-selector-especialidad',
  standalone: true,
  template: `
    @if (servicio.disponibles().length > 0) {
      <div class="contexto" [class.contexto--compacto]="compacto()">
        <span class="contexto__etiqueta" id="contexto-especialidad">Revisando como</span>
        @if (servicio.disponibles().length === 1) {
          <strong class="contexto__unica">{{ servicio.elegida()?.nombre }}</strong>
        } @else if (compacto()) {
          <select class="contexto__selector" aria-label="Especialidad de la historia" [value]="servicio.elegida()?.id" (change)="elegir($any($event.target).value)">
            @for (especialidad of servicio.disponibles(); track especialidad.id) {
              <option [value]="especialidad.id">{{ especialidad.nombre }}{{ especialidad.propia ? ' · la suya' : ' · solo consulta' }}</option>
            }
          </select>
        } @else {
          <div class="contexto__opciones" role="group" aria-labelledby="contexto-especialidad">
            @for (especialidad of servicio.disponibles(); track especialidad.id) {
              <button
                type="button"
                class="contexto__opcion"
                [attr.aria-pressed]="servicio.elegida()?.id === especialidad.id"
                (click)="elegir(especialidad.id)"
              >
                {{ especialidad.nombre }}
                @if (especialidad.propia) { <span class="contexto__propia">· la suya</span> }
              </button>
            }
          </div>
        }
        <span class="contexto__nota">Alergias, medicamentos y recetas se comparten entre especialidades.</span>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .contexto { display: flex; flex-wrap: wrap; align-items: center; gap: var(--espacio-2) var(--espacio-3);
      padding: var(--espacio-2) var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio);
      background: var(--superficie); }
    .contexto--compacto { flex-wrap: nowrap; gap: 6px 10px; padding: 0; border: 0; background: transparent; }
    .contexto__etiqueta { color: var(--texto-suave); font-size: 0.8rem; font-weight: 600;
      letter-spacing: 0.04em; text-transform: uppercase; }
    .contexto__unica { padding: 2px 10px; border-radius: 999px; background: var(--acento-suave);
      color: var(--acento-fuerte); font-size: 0.9rem; }
    .contexto__opciones { display: flex; flex-wrap: wrap; gap: 6px; }
    .contexto__opcion { padding: 4px 12px; border: 1px solid var(--borde); border-radius: 999px;
      background: transparent; color: var(--texto); font: inherit; font-size: 0.9rem; cursor: pointer; }
    .contexto__opcion:hover { border-color: var(--acento); }
    .contexto__opcion:focus-visible { outline: 3px solid var(--acento); outline-offset: 2px; }
    .contexto__opcion[aria-pressed='true'] { border-color: var(--acento); background: var(--acento-suave);
      color: var(--acento-fuerte); font-weight: 600; }
    .contexto__propia { color: var(--texto-suave); font-weight: 400; }
    .contexto__selector { flex: 0 1 18rem; min-width: 0; max-width: 100%; min-height: 2.5rem; padding: .4rem .7rem; border: 1px solid var(--borde); border-radius: var(--radio-md); background: var(--fondo); color: var(--texto); font: inherit; font-size: .85rem; }
    .contexto__nota { flex: 1 1 260px; color: var(--texto-suave); font-size: 0.8rem; text-align: right; }
    .contexto--compacto .contexto__nota { flex: 0 1 auto; min-width: 0; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .72rem; }
    @media (max-width: 640px) { .contexto__nota { text-align: left; } }
  `,
})
export class SelectorEspecialidadComponent {
  protected readonly servicio = inject(EspecialidadHistoriaService);
  /** Avisa para recargar lo que dependa de la especialidad (las notas). */
  readonly cambio = output<string>();
  readonly compacto = input(false);

  protected elegir(id: string): void {
    if (this.servicio.elegida()?.id === id) return;
    this.servicio.elegir(id);
    this.cambio.emit(id);
  }
}
