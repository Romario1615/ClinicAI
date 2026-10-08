import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';

import { MovimientoService } from '../nucleo/movimiento/movimiento.service';

/** Ambiente decorativo estable: sin azar, peticiones ni bucles de JavaScript. */
@Component({
  selector: 'app-fondo-ia',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg viewBox="0 0 1200 900" preserveAspectRatio="xMidYMid slice"
      aria-hidden="true" focusable="false" class="fondo"
      [class.fondo--oscuro]="oscuro()" [class.fondo--quieto]="!movimiento.activo()">
      <g class="fondo__conexiones">
        <path d="M20 190 160 80 350 150 520 45 700 140 850 80 1120 190M160 80 210 350 350 150 490 320 700 140 800 360 1120 190 1060 450M20 190 210 350 90 590 300 720 490 550 490 320 800 360 910 650 1060 450 1190 710M90 590 490 550 660 740 910 650 1120 850M300 720 420 890 660 740 750 900M490 550 800 360M660 740 1060 450" />
      </g>
      @for (punto of puntos; track $index) {
        <circle class="fondo__particula" [attr.cx]="punto[0]" [attr.cy]="punto[1]"
          [attr.r]="$index % 3 === 0 ? 3 : 2" [style.animation-delay.s]="-$index * 1.7" />
      }
    </svg>
  `,
  styles: `
    :host { display:block; position:absolute; inset:0; overflow:hidden; pointer-events:none; }
    .fondo { width:100%; height:100%; color:#4163c4; opacity:.16; }
    .fondo--oscuro { color:#8bc8ff; opacity:.3; }
    .fondo__conexiones { fill:none; stroke:currentColor; stroke-width:.65; }
    .fondo__particula { fill:currentColor; animation:particula-ia 18s ease-in-out infinite; }
    @keyframes particula-ia { 0%,100% { opacity:.35; transform:translateY(0); } 50% { opacity:1; transform:translateY(-5px); } }
    .fondo--quieto .fondo__particula { animation:none; }
    @media (prefers-reduced-motion:reduce) { .fondo__particula { animation:none; } }
    @media (prefers-contrast:more), (prefers-reduced-transparency:reduce) { .fondo { display:none; } }
  `,
})
export class FondoIAComponent {
  protected readonly movimiento = inject(MovimientoService);
  readonly oscuro = input(false);
  protected readonly puntos = [
    [20, 190], [160, 80], [350, 150], [520, 45], [700, 140], [850, 80],
    [1120, 190], [210, 350], [490, 320], [800, 360], [1060, 450], [90, 590],
    [300, 720], [490, 550], [660, 740], [910, 650], [1190, 710], [1120, 850],
    [420, 890], [750, 900], [90, 90], [580, 200], [1020, 60], [590, 850],
  ] as const;
}
