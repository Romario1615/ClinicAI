import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { PuntoFacial, ZonaFacial } from '../nucleo/servicios/registros-paciente.service';

@Component({
  selector: 'app-mapa-facial', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <figure class="mapa">
      <svg viewBox="0 0 320 400" role="group" aria-label="Mapa facial, vista frontal. Derecha e izquierda del paciente">
        <image href="/images/faciograma-anatomia-v1.png" x="0" y="0" width="320" height="400" preserveAspectRatio="none" aria-hidden="true" />
        <text x="25" y="165" fill="#385c65" font-size="12">D</text><text x="286" y="165" fill="#385c65" font-size="12">I</text>
        @for (p of puntos(); track p.codigo; let i = $index) {
          <g role="button" tabindex="0" [attr.aria-label]="p.nombre + ': ' + estado(p.codigo)" [attr.aria-pressed]="seleccion() === p.codigo" (click)="elegir.emit(p.codigo)" (keydown.enter)="elegir.emit(p.codigo)" (keydown.space)="$event.preventDefault(); elegir.emit(p.codigo)" class="punto" [class.punto--activo]="seleccion() === p.codigo" [class.punto--plan]="estado(p.codigo) === 'PLANIFICADO'" [class.punto--hecho]="estado(p.codigo) === 'REALIZADO'" [class.punto--observado]="estado(p.codigo) === 'OBSERVACION'">
            <title>{{ p.nombre }}</title><circle [attr.cx]="p.x" [attr.cy]="p.y" r="11"/><text [attr.x]="p.x" [attr.y]="p.y + 3.5" text-anchor="middle">{{ i + 1 }}</text>
          </g>
        }
      </svg>
      <figcaption>Vista frontal · D/I del paciente<br />Zonas de registro y seguimiento; no son puntos de inyección.</figcaption>
      <div class="leyenda"><span>○ Sin registro</span><span class="observacion">● Observación</span><span class="plan">● Planificado</span><span class="hecho">● Realizado</span></div>
    </figure>
  `,
  styles: `:host{display:block;min-width:0}.mapa{margin:0;padding:16px;border:1px solid var(--borde);border-radius:24px;background:linear-gradient(145deg,rgb(255 255 255 / 88%),rgb(218 240 242 / 45%));backdrop-filter:blur(16px)}svg{width:100%;max-height:580px}.punto{cursor:pointer}.punto circle{fill:#fff;stroke:#547b83;stroke-width:2.5}.punto text{pointer-events:none;fill:#294750;font-size:10px;font-weight:700}.punto--observado circle{fill:#e0edff;stroke:#2860b0}.punto--plan circle{fill:#fff0d6;stroke:#966100}.punto--hecho circle{fill:#d6f4ea;stroke:#147d65}.punto--activo circle,.punto:focus-visible circle{stroke:#083e4b;stroke-width:4}figcaption{text-align:center;font-size:.78rem;color:var(--texto-suave);line-height:1.6}.leyenda{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:.75rem}.observacion{color:#2860b0}.plan{color:#966100}.hecho{color:#147d65}`,
})
export class MapaFacialComponent {
  readonly puntos = input.required<readonly PuntoFacial[]>();
  readonly zonas = input<readonly ZonaFacial[]>([]);
  readonly seleccion = input<string | null>(null);
  readonly elegir = output<string>();
  protected estado(codigo: string): string { return this.zonas().find(z => z.zona === codigo)?.estado ?? 'SIN_REGISTRO'; }
}
