/**
 * Pestañas de una sección.
 *
 * Una pantalla que no se desplaza no puede apilar seis bloques: los reparte en
 * pestañas y muestra uno a la vez. Este componente dibuja solo la fila de
 * pestañas; el contenido lo pinta la página, envuelto así:
 *
 * ```html
 * <app-pestanas grupo="panel" etiqueta="Vistas del panel" [opciones]="vistas" [(activa)]="vista" />
 * <section role="tabpanel" [id]="'panel-panel-' + vista()" [attr.aria-labelledby]="'panel-pestana-' + vista()">
 * ```
 *
 * Los identificadores siguen siempre el mismo patrón, `{grupo}-pestana-{clave}`
 * y `{grupo}-panel-{clave}`, para que la página los escriba sin consultar nada.
 *
 * Teclado (patrón de pestañas de WAI-ARIA, activación automática): las
 * flechas izquierda y derecha cambian de pestaña, Inicio y Fin van a los
 * extremos, y solo la pestaña activa está en el orden de tabulación.
 */
import { ChangeDetectionStrategy, Component, ElementRef, inject, input, model } from '@angular/core';

import { IconoComponent, type NombreIcono } from './icono.component';

export interface OpcionPestana {
  readonly clave: string;
  readonly etiqueta: string;
  /** Cuántos elementos esperan en esa pestaña; 0 o vacío no se muestra. */
  readonly cuenta?: number | null;
  readonly icono?: NombreIcono;
}

@Component({
  selector: 'app-pestanas',
  standalone: true,
  imports: [IconoComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="pestanas" role="tablist" [attr.aria-label]="etiqueta()">
      @for (opcion of opciones(); track opcion.clave; let indice = $index) {
        <button
          type="button"
          role="tab"
          class="pestanas__opcion"
          [id]="grupo() + '-pestana-' + opcion.clave"
          [attr.aria-selected]="opcion.clave === activa()"
          [attr.aria-controls]="grupo() + '-panel-' + opcion.clave"
          [attr.tabindex]="opcion.clave === activa() ? 0 : -1"
          (click)="activa.set(opcion.clave)"
          (keydown)="alTeclear($event, indice)"
        >
          @if (opcion.icono) {
            <app-icono [nombre]="opcion.icono" [tamano]="16" />
          }
          <span>{{ opcion.etiqueta }}</span>
          @if (opcion.cuenta) {
            <span class="pestanas__cuenta numerico">{{ opcion.cuenta }}</span>
          }
        </button>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
      min-width: 0;
    }

    /* Cápsula de vidrio: el mismo lenguaje que el buscador de la cabecera. */
    .pestanas {
      display: flex;
      gap: 4px;
      max-width: 100%;
      width: max-content;
      padding: 4px;
      overflow-x: auto;
      border: 1px solid var(--vidrio-borde);
      border-radius: 999px;
      background: var(--vidrio-especular), var(--vidrio-cuerpo);
      box-shadow: var(--vidrio-canto);
      scrollbar-width: none;
    }

    .pestanas__opcion {
      display: inline-flex;
      align-items: center;
      gap: var(--espacio-2);
      min-height: 36px;
      padding: 0 var(--espacio-4);
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--texto-suave);
      font: inherit;
      font-size: 0.9rem;
      font-weight: 650;
      white-space: nowrap;
      cursor: pointer;
      transition:
        background-color 160ms ease,
        color 160ms ease,
        box-shadow 160ms ease;
    }

    .pestanas__opcion:hover {
      background: rgb(220 240 238 / 70%);
      color: var(--texto);
    }

    .pestanas__opcion[aria-selected='true'] {
      background: linear-gradient(180deg, var(--acento), var(--acento-fuerte));
      color: var(--acento-texto);
      box-shadow: 0 6px 16px -8px rgb(6 66 70 / 60%);
    }

    .pestanas__cuenta {
      min-width: 20px;
      padding: 0 6px;
      border-radius: 999px;
      background: #f6c766;
      color: #3d2800;
      font-size: 0.72rem;
      font-weight: 800;
      line-height: 20px;
      text-align: center;
    }

    @media (prefers-reduced-motion: reduce) {
      .pestanas__opcion {
        transition: none;
      }
    }
  `,
})
export class PestanasComponent {
  readonly opciones = input.required<readonly OpcionPestana[]>();
  readonly activa = model.required<string>();
  /** Nombre accesible de la fila de pestañas. */
  readonly etiqueta = input.required<string>();
  /** Prefijo de los identificadores; único en la página. */
  readonly grupo = input.required<string>();

  private readonly raiz = inject<ElementRef<HTMLElement>>(ElementRef);

  protected alTeclear(evento: KeyboardEvent, indice: number): void {
    const opciones = this.opciones();
    let destino: number;
    switch (evento.key) {
      case 'ArrowRight':
        destino = (indice + 1) % opciones.length;
        break;
      case 'ArrowLeft':
        destino = (indice - 1 + opciones.length) % opciones.length;
        break;
      case 'Home':
        destino = 0;
        break;
      case 'End':
        destino = opciones.length - 1;
        break;
      default:
        return;
    }
    evento.preventDefault();
    this.activa.set(opciones[destino].clave);
    this.raiz.nativeElement.querySelectorAll<HTMLButtonElement>('[role="tab"]')[destino]?.focus();
  }
}
