/**
 * Gráfico en movimiento: la clínica conectada.
 *
 * Un núcleo de vidrio (el escudo de ClinicAI) unido por conexiones curvas a
 * las piezas del trabajo diario: agenda, pacientes, mensajes, conocimiento,
 * pagos e historia. Con Motion, las conexiones se dibujan, los nodos se posan
 * con un resorte, un pulso de luz recorre cada conexión, los nodos respiran y
 * unas partículas flotan alrededor. Es una ilustración de lo que hace el
 * sistema, no un dato: va con `aria-hidden` y nadie necesita verla moverse
 * para usar la pantalla.
 *
 * * Con `prefers-reduced-motion` (o sin WAAPI) se pinta quieta y completa.
 * * Fuera de pantalla los bucles se pausan: un gráfico que nadie ve no tiene
 *   por qué gastar batería en la tableta del mostrador.
 * * Todo el dibujo es SVG en línea, sin imágenes externas.
 */
import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  inject,
  input,
  signal,
  ChangeDetectionStrategy,
} from '@angular/core';

import { MovimientoService, type ControlBucle } from '../nucleo/movimiento/movimiento.service';

interface Nodo {
  readonly clave: string;
  readonly x: number;
  readonly y: number;
  /** Curva desde el núcleo, con su punto de control desplazado. */
  readonly conexion: string;
  /** Trazado del pictograma, en coordenadas locales de 24 × 24. */
  readonly icono: string;
}

const CENTRO = { x: 200, y: 150 };
const RADIO_X = 150;
const RADIO_Y = 104;

const PICTOGRAMAS: readonly { clave: string; icono: string }[] = [
  { clave: 'agenda', icono: 'M5 7h14v12H5zM5 11h14M9 5v4M15 5v4M9 15h2' },
  { clave: 'pacientes', icono: 'M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM5.5 19a6.5 6.5 0 0 1 13 0' },
  { clave: 'mensajes', icono: 'M5 6h14v9H10l-4 3v-3H5zM8.5 10.5h7' },
  { clave: 'conocimiento', icono: 'M6 5h9l3 3v11H6zM15 5v3h3M9 12h6M9 15h4' },
  { clave: 'pagos', icono: 'M4.5 7.5h15v9h-15zM4.5 10.5h15M8 14h3' },
  { clave: 'historia', icono: 'M12 5v14M5 12h14M8 8h8v8H8z' },
];

/** Coloca los seis nodos en una elipse y traza cada conexión. */
function construirNodos(): readonly Nodo[] {
  return PICTOGRAMAS.map(({ clave, icono }, indice) => {
    const angulo = ((-90 + indice * 60) * Math.PI) / 180;
    const x = Math.round(CENTRO.x + RADIO_X * Math.cos(angulo));
    const y = Math.round(CENTRO.y + RADIO_Y * Math.sin(angulo));
    // El punto de control se desvía en perpendicular: curvas que giran en
    // el mismo sentido, como órbitas, y no radios rígidos.
    const medioX = (CENTRO.x + x) / 2 - (y - CENTRO.y) * 0.28;
    const medioY = (CENTRO.y + y) / 2 + (x - CENTRO.x) * 0.28;
    return {
      clave,
      x,
      y,
      conexion: `M ${CENTRO.x} ${CENTRO.y} Q ${Math.round(medioX)} ${Math.round(medioY)} ${x} ${y}`,
      icono,
    };
  });
}

/** Partículas fijas: posición y tamaño, sin azar para que el dibujo sea estable. */
const PARTICULAS: readonly { x: number; y: number; r: number }[] = [
  { x: 64, y: 40, r: 2.2 },
  { x: 342, y: 34, r: 1.6 },
  { x: 372, y: 150, r: 2.6 },
  { x: 318, y: 272, r: 1.8 },
  { x: 120, y: 278, r: 2.4 },
  { x: 26, y: 156, r: 1.6 },
  { x: 150, y: 70, r: 1.4 },
  { x: 262, y: 236, r: 1.5 },
];

@Component({
  selector: 'app-grafico-red',
  standalone: true,
  template: `
    <svg
      class="red"
      [class.red--oscura]="tono() === 'oscuro'"
      [class.red--viva]="viva()"
      viewBox="0 0 400 300"
      role="presentation"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient [attr.id]="id('nucleo')" cx="35%" cy="30%" r="75%">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95" />
          <stop offset="55%" stop-color="#bff0e8" stop-opacity="0.8" />
          <stop offset="100%" stop-color="#5fd1c4" stop-opacity="0.7" />
        </radialGradient>
        <radialGradient [attr.id]="id('halo')" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#5fd1c4" stop-opacity="0.45" />
          <stop offset="100%" stop-color="#5fd1c4" stop-opacity="0" />
        </radialGradient>
        <linearGradient [attr.id]="id('nodo')" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.92" />
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0.6" />
        </linearGradient>
      </defs>

      <ellipse class="red__orbita" cx="200" cy="150" rx="150" ry="104" pathLength="1" />
      <circle class="red__halo" cx="200" cy="150" r="92" [attr.fill]="url('halo')" data-respira />

      @for (nodo of nodos; track nodo.clave) {
        <path class="red__conexion" [attr.d]="nodo.conexion" pathLength="1" data-trazo />
        <path class="red__pulso" [attr.d]="nodo.conexion" pathLength="1" data-pulso />
      }

      @for (particula of particulas; track $index) {
        <circle class="red__particula" [attr.cx]="particula.x" [attr.cy]="particula.y" [attr.r]="particula.r" data-particula />
      }

      @for (nodo of nodos; track nodo.clave) {
        <!-- Tres capas: la posición (atributo), la respiración y la llegada.
             Cada animación mueve su propia capa; dos animaciones de escala
             sobre el mismo elemento se cancelarían entre sí. -->
        <g class="red__nodo" [attr.transform]="'translate(' + nodo.x + ' ' + nodo.y + ')'">
          <g class="red__capa" data-respira>
            <g class="red__capa" data-nodo>
              <circle r="23" class="red__nodo-vidrio" [attr.fill]="url('nodo')" />
              <path class="red__icono" [attr.d]="nodo.icono" transform="translate(-12 -12)" />
            </g>
          </g>
        </g>
      }

      <g class="red__nucleo" transform="translate(200 150)">
        <g class="red__capa" data-nodo>
          <circle r="44" class="red__anillo" data-anillo />
          <circle r="34" class="red__nucleo-vidrio" [attr.fill]="url('nucleo')" />
          <path class="red__escudo" d="M0 -17 14 -11.5v10.5C14 9 7.5 15 0 19 -7.5 15 -14 9 -14 -1v-10.5Z" />
          <path class="red__marca" d="m-6 1 4.5 4.5L7 -4" />
        </g>
      </g>
    </svg>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host {
      display: block;
      width: 100%;
    }

    .red {
      display: block;
      width: 100%;
      height: auto;
      overflow: visible;
      --red-trazo: rgb(11 110 106 / 34%);
      --red-pulso: #0b6e6a;
      --red-icono: #0b6e6a;
      --red-borde: rgb(11 110 106 / 28%);
      --red-particula: #5fd1c4;
    }

    .red--oscura {
      --red-trazo: rgb(170 244 233 / 34%);
      --red-pulso: #aaf4e9;
      --red-icono: #0a4b4c;
      --red-borde: rgb(255 255 255 / 55%);
      --red-particula: #aaf4e9;
    }

    /* Con pathLength="1", un guion de longitud 1 es el trazo completo. */
    .red__orbita,
    .red__conexion {
      fill: none;
      stroke: var(--red-trazo);
      stroke-width: 1.4;
      stroke-dasharray: 1;
      stroke-linecap: round;
    }

    .red__orbita {
      stroke-width: 1;
      stroke-dasharray: 0.004 0.012;
    }

    /* El pulso es un guion corto de luz; quieto no se ve. */
    .red__pulso {
      fill: none;
      stroke: var(--red-pulso);
      stroke-width: 2.6;
      stroke-linecap: round;
      stroke-dasharray: 0.07 1.1;
      stroke-dashoffset: 1.1;
      opacity: 0;
      filter: drop-shadow(0 0 3px var(--red-particula));
    }

    .red--viva .red__pulso {
      opacity: 1;
    }

    .red__particula {
      fill: var(--red-particula);
      opacity: 0.6;
    }

    .red__capa,
    .red__halo,
    .red__anillo,
    .red__particula {
      transform-box: fill-box;
      transform-origin: center;
    }

    .red__nodo-vidrio {
      stroke: var(--red-borde);
      stroke-width: 1;
      filter: drop-shadow(0 6px 10px rgb(6 38 41 / 18%));
    }

    .red__icono,
    .red__marca {
      fill: none;
      stroke: var(--red-icono);
      stroke-width: 1.6;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .red__anillo {
      fill: none;
      stroke: var(--red-pulso);
      stroke-opacity: 0.45;
      stroke-width: 1.2;
      stroke-dasharray: 3 7;
    }

    .red__nucleo-vidrio {
      stroke: rgb(255 255 255 / 85%);
      stroke-width: 1.2;
      filter: drop-shadow(0 10px 18px rgb(6 38 41 / 24%));
    }

    .red__escudo {
      fill: rgb(11 110 106 / 14%);
      stroke: #0b6e6a;
      stroke-width: 1.8;
      stroke-linejoin: round;
    }

    .red__marca {
      stroke: #0b6e6a;
      stroke-width: 2.2;
    }
  `,
})
export class GraficoRedComponent {
  private static siguienteId = 0;

  private readonly anfitrion = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly movimiento = inject(MovimientoService);

  /** `claro` sobre vidrio claro; `oscuro` sobre el panel de marca. */
  readonly tono = input<'claro' | 'oscuro'>('claro');

  protected readonly nodos = construirNodos();
  protected readonly particulas = PARTICULAS;
  /** Los bucles están corriendo: los pulsos se hacen visibles. */
  protected readonly viva = signal(false);

  /** Prefijo único: dos gráficos en la misma página no comparten degradados. */
  private readonly prefijo = `red-${GraficoRedComponent.siguienteId++}`;
  private controles: ControlBucle | null = null;
  private observador: IntersectionObserver | null = null;
  private destruido = false;

  constructor() {
    afterNextRender(() => void this.arrancar());
    inject(DestroyRef).onDestroy(() => {
      this.destruido = true;
      this.observador?.disconnect();
      this.controles?.stop();
    });
  }

  protected id(nombre: string): string {
    return `${this.prefijo}-${nombre}`;
  }

  protected url(nombre: string): string {
    return `url(#${this.id(nombre)})`;
  }

  private async arrancar(): Promise<void> {
    const svg = this.anfitrion.nativeElement.querySelector('svg');
    if (!svg) {
      return;
    }
    const controles = await this.movimiento.animarGrafico(svg);
    if (!controles || this.destruido) {
      controles?.stop();
      return;
    }
    this.controles = controles;
    this.viva.set(true);
    if (typeof IntersectionObserver !== 'undefined') {
      this.observador = new IntersectionObserver(([entrada]) => {
        if (entrada?.isIntersecting) {
          this.controles?.play();
        } else {
          this.controles?.pause();
        }
      });
      this.observador.observe(svg);
    }
  }
}
