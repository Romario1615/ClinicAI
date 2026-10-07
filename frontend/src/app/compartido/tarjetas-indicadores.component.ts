/**
 * Fila de indicadores: número grande, qué es y, si hace falta, qué hacer.
 *
 * Una tarjeta con `tono: 'alerta'` es algo que espera a alguien (citas por
 * confirmar, pagos por validar). Con `enlace` la tarjeta lleva al sitio donde
 * se resuelve: el número no es decoración, es la entrada a la tarea.
 */
import { Component, input, ChangeDetectionStrategy } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { RouterLink } from '@angular/router';

export interface Indicador {
  readonly etiqueta: string;
  readonly valor: string | number;
  readonly detalle?: string;
  readonly tono?: 'normal' | 'alerta' | 'bien';
  readonly enlace?: string;
  readonly consulta?: Record<string, string>;
}

@Component({
  selector: 'app-tarjetas-indicadores',
  standalone: true,
  imports: [RouterLink, NgTemplateOutlet],
  template: `
    @if (indicadores().length) {
      <div class="indicadores" [attr.aria-label]="titulo() || 'Indicadores'" role="list">
        @for (item of indicadores(); track item.etiqueta) {
          @if (item.enlace) {
            <a
              role="listitem"
              [class]="'indicador indicador--' + (item.tono ?? 'normal') + ' indicador--enlace'"
              [routerLink]="item.enlace"
              [queryParams]="item.consulta ?? null"
            >
              <ng-container *ngTemplateOutlet="cuerpo; context: { $implicit: item }" />
            </a>
          } @else {
            <div role="listitem" [class]="'indicador indicador--' + (item.tono ?? 'normal')">
              <ng-container *ngTemplateOutlet="cuerpo; context: { $implicit: item }" />
            </div>
          }
        }
      </div>
    }
    <ng-template #cuerpo let-item>
      <span class="indicador__valor numerico">{{ item.valor }}</span>
      <span class="indicador__etiqueta">{{ item.etiqueta }}</span>
      @if (item.detalle) {
        <span class="indicador__detalle">{{ item.detalle }}</span>
      }
    </ng-template>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: block; }
    .indicadores {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
      gap: var(--espacio-3);
    }
    .indicador {
      display: grid;
      align-content: start;
      gap: 2px;
      min-height: 96px;
      padding: var(--espacio-3) var(--espacio-4);
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
      color: var(--texto);
      text-decoration: none;
      box-shadow: var(--sombra-1);
      transition: border-color 140ms ease, transform 140ms ease;
    }
    .indicador--enlace:hover { border-color: var(--acento); transform: translateY(-1px); }
    .indicador--enlace:focus-visible { outline: 3px solid var(--acento); outline-offset: 2px; }
    .indicador__valor { font-size: 1.75rem; font-weight: 750; line-height: 1.1; }
    .indicador__etiqueta { font-weight: 650; font-size: 0.88rem; }
    .indicador__detalle { color: var(--texto-suave); font-size: 0.78rem; }
    .indicador--alerta { background: var(--aviso-fondo); border-color: color-mix(in srgb, var(--aviso) 45%, transparent); }
    .indicador--alerta .indicador__valor { color: var(--aviso); }
    .indicador--bien .indicador__valor { color: var(--exito); }
  `,
})
export class TarjetasIndicadoresComponent {
  readonly indicadores = input<readonly Indicador[]>([]);
  readonly titulo = input('');
}
