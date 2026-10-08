import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FondoIAComponent } from '../../compartido/fondo-ia.component';
import { IconoComponent } from '../../compartido/icono.component';

/** Encabezado independiente: encapsula el ambiente IA y su movimiento accesible. */
@Component({
  selector: 'app-portada-panel',
  standalone: true,
  host: { class: 'pantalla__fijo' },
  imports: [RouterLink, FondoIAComponent, IconoComponent],
  template: `
    <div class="cabecera-pagina panel__portada ">
      <app-fondo-ia [oscuro]="true" />
      <div>
        <p class="ceja panel__ceja"><app-icono nombre="agente" [tamano]="16" /> CLINICAI · GESTIÓN CON IA</p>
        <h1>Panel de seguimiento</h1>
        <p class="panel__contexto">{{ fecha() }} · horario de {{ zona() }}</p>
      </div>
      <a class="boton boton--principal" routerLink="/agenda"><app-icono nombre="calendario-check" [tamano]="18" /> Abrir agenda</a>
    </div>
  `,
  styles: `
    .cabecera-pagina {
      position: relative;
      min-height: 138px;
      padding: var(--espacio-5) var(--espacio-6);
      overflow: hidden;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background-image:
        radial-gradient(ellipse at 85% 20%, rgb(99 128 223 / 35%), transparent 52%),
        linear-gradient(115deg, #132445, #172a52 65%, #253e73);
      background-position: center, 50% 52%;
      background-size: cover;
      isolation: isolate;
      color: #fff;
    }

    .cabecera-pagina::after {
      content: '';
      position: absolute;
      z-index: 0;
      inset: -55% 12% -55% 42%;
      pointer-events: none;
      background: radial-gradient(ellipse, rgb(129 166 255 / 20%), transparent 66%);
      opacity: .8;
      animation: panel-resplandor 14s ease-in-out infinite alternate;
    }

    .cabecera-pagina::before {
      content: '';
      position: absolute;
      z-index: 0;
      inset: 0;
      pointer-events: none;
      background: linear-gradient(112deg, transparent 36%, rgb(182 255 246 / 9%) 52%, transparent 68%);
      background-size: 220% 100%;
      animation: panel-brillo 18s ease-in-out infinite;
    }

    @keyframes panel-fondo-desplazamiento {
      from { background-position: center, 48% 52%; }
      to { background-position: center, 54% 52%; }
    }

    @keyframes panel-resplandor {
      from { transform: translate3d(-2%, 0, 0) scale(.96); opacity: .55; }
      to { transform: translate3d(2%, 1%, 0) scale(1.04); opacity: .9; }
    }

    @keyframes panel-brillo {
      0%, 18% { background-position: 100% 0; }
      72%, 100% { background-position: 0 0; }
    }

    .cabecera-pagina > div,
    .cabecera-pagina > a {
      position: relative;
      z-index: 1;
    }

    .cabecera-pagina h1 { color: #fff; }
    .cabecera-pagina .boton--principal { background:#e9efff; color:#243f8e; border-color:#f5f8ff; box-shadow:0 4px 20px rgb(0 0 0 / 12%); }
    .cabecera-pagina .boton--principal:hover { background:#fff; }

    @media (max-width: 600px) {
      .cabecera-pagina {
        min-height: 132px;
        padding: var(--espacio-4);
        background-position: center, 68% center;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .cabecera-pagina,
      .cabecera-pagina::after,
      .cabecera-pagina::before,
      .panel__ceja app-icono { animation: none; }
    }

    .panel__contexto {
      margin: 2px 0 0;
      color: #d1def5;
      font-size: 0.9rem;
    }

    .panel__ceja { display: flex; align-items: center; gap: var(--espacio-2); color: #aad8ff; }
    .panel__ceja app-icono { animation: panel-latido 5s ease-in-out infinite; }
    @keyframes panel-latido {
      0%, 100% { transform: scale(1); filter: drop-shadow(0 0 0 rgb(170 244 233 / 0%)); }
      50% { transform: scale(1.08); filter: drop-shadow(0 0 7px rgb(170 244 233 / 60%)); }
    }

    @media (min-width: 821px) and (min-height: 600px) {
      .cabecera-pagina {
        min-height: 0;
        padding: var(--espacio-2) var(--espacio-5);
      }

      .cabecera-pagina .ceja { margin-bottom: 2px; font-size: .72rem; }
      .panel__contexto { margin: 0; font-size: .8rem; }
    }
  `,
})
export class PortadaPanelComponent {
  readonly fecha = input.required<string>();
  readonly zona = input.required<string>();
}
