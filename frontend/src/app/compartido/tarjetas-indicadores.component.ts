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

import { ContadorDirective } from './contador.directive';

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
  imports: [RouterLink, NgTemplateOutlet, ContadorDirective],
  template: `
    @if (indicadores().length) {
      <div class="indicadores" [attr.aria-label]="titulo() || 'Indicadores'" role="list">
        @for (item of indicadores(); track item.etiqueta) {
          @if (item.enlace) {
            <a
              role="listitem"
              data-aparecer
              [class]="clases(item, true)"
              [routerLink]="item.enlace"
              [queryParams]="item.consulta ?? null"
            >
              <ng-container *ngTemplateOutlet="cuerpo; context: { $implicit: item }" />
            </a>
          } @else {
            <div role="listitem" data-aparecer [class]="clases(item, false)">
              <ng-container *ngTemplateOutlet="cuerpo; context: { $implicit: item }" />
            </div>
          }
        }
      </div>
    }
    <ng-template #cuerpo let-item>
      <!-- La cifra cuenta hasta su valor (gráfico en movimiento). -->
      <span class="indicador__valor numerico" [appContador]="item.valor"></span>
      <span class="indicador__etiqueta">{{ item.etiqueta }}</span>
      @if (item.detalle) {
        <span class="indicador__detalle" [attr.title]="item.detalle">{{ item.detalle }}</span>
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
      border: 1px solid var(--vidrio-borde, var(--borde));
      border-radius: var(--radio-vidrio, var(--radio));
      /* Ficha de vidrio: canto iluminado y reflejo que sigue al puntero. */
      background: var(--vidrio-reflejo, none), var(--vidrio-especular, none), var(--vidrio-cuerpo, var(--superficie-elevada));
      color: var(--texto);
      text-decoration: none;
      box-shadow: var(--vidrio-canto, 0 0 0 transparent), var(--vidrio-sombra, var(--sombra-1));
      transition: border-color 160ms ease, box-shadow 200ms ease;
    }
    .indicador--enlace:hover { border-color: rgb(11 110 106 / 40%); box-shadow: var(--vidrio-canto, 0 0 0 transparent), 0 16px 32px -16px rgb(16 42 46 / 35%); }
    .indicador--enlace:focus-visible { outline: 3px solid var(--acento); outline-offset: 2px; }
    .indicador__valor { font-size: 1.75rem; font-weight: 750; line-height: 1.1; }
    .indicador__etiqueta { font-weight: 650; font-size: 0.88rem; }
    .indicador__detalle { color: var(--texto-suave); font-size: 0.78rem; }
    .indicador--alerta { background: var(--aviso-fondo); border-color: color-mix(in srgb, var(--aviso) 45%, transparent); }
    .indicador--alerta .indicador__valor { color: var(--aviso); }
    .indicador--bien .indicador__valor { color: var(--exito); }
    .indicador--cero { border-style: dashed; background: var(--superficie); box-shadow: none; }
    .indicador--cero .indicador__valor { color: var(--texto-suave); }

    /* Pantalla de trabajo (escritorio): ficha apaisada de una sola altura, con
       la cifra a la izquierda. Ocupa la mitad y deja el alto a la lista. */
    @media (min-width: 821px) and (min-height: 600px) {
      .indicadores { grid-template-columns: repeat(auto-fill, minmax(196px, 1fr)); gap: var(--espacio-2); }
      .indicador {
        grid-template-columns: auto minmax(0, 1fr);
        align-content: center;
        align-items: center;
        column-gap: var(--espacio-3);
        row-gap: 0;
        min-height: 0;
        padding: var(--espacio-2) var(--espacio-3);
      }
      .indicador__valor { grid-row: span 2; font-size: 1.45rem; }
      .indicador__etiqueta { align-self: end; }
      .indicador__etiqueta:last-child { grid-row: span 2; align-self: center; }
      .indicador__detalle { align-self: start; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    }
  `,
})
export class TarjetasIndicadoresComponent {
  readonly indicadores = input<readonly Indicador[]>([]);
  readonly titulo = input('');
  readonly atenuarCero = input(false);

  protected clases(item: Indicador, enlace: boolean): string {
    const cero = this.atenuarCero() && Number(item.valor) === 0;
    return `indicador indicador--${item.tono ?? 'normal'}${enlace ? ' indicador--enlace' : ''}${cero ? ' indicador--cero' : ''}`;
  }
}
