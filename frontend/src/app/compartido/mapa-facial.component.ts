import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { PuntoFacial, ZonaFacial } from '../nucleo/servicios/registros-paciente.service';

@Component({
  selector: 'app-mapa-facial', standalone: true, changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <figure class="mapa">
      <svg viewBox="0 0 320 400" role="group" aria-label="Mapa facial, vista frontal. Derecha e izquierda del paciente">
        <defs><linearGradient [id]="degradado" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#edf9f8"/><stop offset="1" stop-color="#b9d8dc"/></linearGradient></defs>
        <path d="M118 282 L117 331 Q99 343 50 361 L40 398 H280 L270 361 Q221 343 203 331 L202 282" [attr.fill]="'url(#' + degradado + ')'" stroke="#70949b" stroke-width="1.5"/>
        <ellipse cx="83" cy="192" rx="12" ry="28" fill="#d5e8e9" stroke="#70949b"/><ellipse cx="237" cy="192" rx="12" ry="28" fill="#d5e8e9" stroke="#70949b"/>
        <path d="M83 157 Q70 43 160 35 Q250 43 237 157 L229 220 Q218 278 180 301 Q160 310 140 301 Q102 278 91 220 Z" [attr.fill]="'url(#' + degradado + ')'" stroke="#70949b" stroke-width="1.7"/>
        <path d="M103 141 Q124 131 141 142 M179 142 Q196 131 217 141 M102 157 Q125 147 143 158 Q124 171 102 157 M177 158 Q196 147 218 157 Q197 171 177 158 M158 159 L147 199 Q160 206 173 199 M139 238 Q151 230 160 235 Q169 230 181 238 Q161 255 139 238 M137 217 Q127 220 125 235 M183 217 Q193 220 195 235" fill="none" stroke="#70949b" stroke-linecap="round" stroke-width="1.5"/>
        <path d="M160 52 V287" stroke="#70949b" stroke-dasharray="3 7" opacity=".3"/>
        <text x="25" y="165" fill="#385c65" font-size="12">D</text><text x="286" y="165" fill="#385c65" font-size="12">I</text>
        @for (p of puntos(); track p.codigo; let i = $index) {
          <g role="button" tabindex="0" [attr.aria-label]="p.nombre + ': ' + estado(p.codigo)" [attr.aria-pressed]="seleccion() === p.codigo" (click)="elegir.emit(p.codigo)" (keydown.enter)="elegir.emit(p.codigo)" (keydown.space)="$event.preventDefault(); elegir.emit(p.codigo)" class="punto" [class.punto--activo]="seleccion() === p.codigo" [class.punto--plan]="estado(p.codigo) === 'PLANIFICADO'" [class.punto--hecho]="estado(p.codigo) === 'REALIZADO'" [class.punto--observado]="estado(p.codigo) === 'OBSERVACION'">
            <title>{{ p.nombre }}</title><circle [attr.cx]="p.x" [attr.cy]="p.y" r="13"/><text [attr.x]="p.x" [attr.y]="p.y + 3.5" text-anchor="middle">{{ i + 1 }}</text>
          </g>
        }
      </svg>
      <figcaption>Vista frontal · D/I del paciente<br />Zonas de registro y seguimiento; no son puntos de inyección.</figcaption>
      <div class="leyenda"><span>○ Sin registro</span><span class="observacion">● Observación</span><span class="plan">● Planificado</span><span class="hecho">● Realizado</span></div>
    </figure>
  `,
  styles: `:host{display:block;min-width:0}.mapa{margin:0;padding:16px;border:1px solid var(--borde);border-radius:24px;background:linear-gradient(145deg,rgb(255 255 255 / 78%),rgb(218 240 242 / 55%));backdrop-filter:blur(16px)}svg{width:100%;max-height:460px}.punto{cursor:pointer}.punto circle{fill:#fff;stroke:#547b83;stroke-width:1.5}.punto text{pointer-events:none;fill:#294750;font-size:10px;font-weight:700}.punto--observado circle{fill:#e0edff;stroke:#2860b0}.punto--plan circle{fill:#fff0d6;stroke:#966100}.punto--hecho circle{fill:#d6f4ea;stroke:#147d65}.punto--activo circle,.punto:focus-visible circle{stroke:#083e4b;stroke-width:4}figcaption{text-align:center;font-size:.78rem;color:var(--texto-suave);line-height:1.6}.leyenda{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:.75rem}.observacion{color:#2860b0}.plan{color:#966100}.hecho{color:#147d65}`,
})
export class MapaFacialComponent {
  protected readonly degradado = 'piel-' + crypto.randomUUID();
  readonly puntos = input.required<readonly PuntoFacial[]>();
  readonly zonas = input<readonly ZonaFacial[]>([]);
  readonly seleccion = input<string | null>(null);
  readonly elegir = output<string>();
  protected estado(codigo: string): string { return this.zonas().find(z => z.zona === codigo)?.estado ?? 'SIN_REGISTRO'; }
}
