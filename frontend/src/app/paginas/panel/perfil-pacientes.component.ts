/** Perfil agregado del periodo: categorías, valores y barras con estilos propios. */
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { IconoComponent } from '../../compartido/icono.component';
import type { ResumenPanel } from '../../nucleo/servicios/operaciones.service';

@Component({
  selector: 'app-perfil-pacientes',
  standalone: true,
  imports: [IconoComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let perfil = demografia();
    <section class="tarjeta tarjeta-vidrio demografia" aria-labelledby="demografia-titulo">
      <header class="demografia__cabecera">
        <span class="demografia__icono" aria-hidden="true"><app-icono nombre="pacientes" [tamano]="18" /></span>
        <div class="demografia__intro">
          <h3 id="demografia-titulo" class="cifra__titulo">Perfil de pacientes</h3>
          <p class="campo__ayuda">Personas con cita en el periodo y filtros actuales</p>
        </div>
      </header>
      @if (!perfil) {
        <p class="campo__ayuda demografia__protegida" role="status">Desglose oculto para proteger grupos de menos de 5 pacientes.</p>
      } @else {
        <div class="demografia__rejilla">
          <section class="demografia__grupo" aria-labelledby="demografia-edades">
            <h4 id="demografia-edades" class="cifra__titulo">Edades</h4>
            <ul class="demografia__lista">
              @for (celda of perfil.edades; track celda.categoria) {
                <li class="demografia__fila">
                  <span class="demografia__categoria">{{ celda.categoria }}</span>
                  <span class="tendencia__pista demografia__pista" aria-hidden="true">
                    @if (celda.pacientes !== null && celda.pacientes > 0) {
                      <span [style.width.%]="anchoDemografico(perfil.edades, celda.pacientes)"></span>
                    }
                  </span>
                  <strong class="numerico demografia__valor" [class.demografia__valor--protegido]="celda.suprimida">{{ celda.suprimida ? 'Protegido' : celda.pacientes }}</strong>
                </li>
              }
            </ul>
          </section>
          <section class="demografia__grupo" aria-labelledby="demografia-sexos">
            <h4 id="demografia-sexos" class="cifra__titulo">Sexo registrado</h4>
            <ul class="demografia__lista">
              @for (celda of perfil.sexos; track celda.categoria) {
                <li class="demografia__fila">
                  <span class="demografia__categoria">{{ celda.categoria }}</span>
                  <span class="tendencia__pista demografia__pista" aria-hidden="true">
                    @if (celda.pacientes !== null && celda.pacientes > 0) {
                      <span [style.width.%]="anchoDemografico(perfil.sexos, celda.pacientes)"></span>
                    }
                  </span>
                  <strong class="numerico demografia__valor" [class.demografia__valor--protegido]="celda.suprimida">{{ celda.suprimida ? 'Protegido' : celda.pacientes }}</strong>
                </li>
              }
            </ul>
          </section>
        </div>
        <p class="campo__ayuda demografia__nota">Datos administrativos agregados. Las celdas pequeñas y una celda adicional se ocultan para que no se calculen a partir de las otras celdas del mismo desglose.</p>
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .tarjeta-vidrio {
      border: 1px solid rgb(255 255 255 / 76%);
      background:
        radial-gradient(ellipse at 92% 6%, rgb(104 214 203 / 22%), transparent 48%),
        linear-gradient(145deg, rgb(255 255 255 / 84%), rgb(232 247 244 / 72%));
      box-shadow: 0 12px 32px rgb(20 61 66 / 9%), inset 0 1px rgb(255 255 255 / 94%);
      -webkit-backdrop-filter: blur(22px) saturate(145%);
      backdrop-filter: blur(22px) saturate(145%);
    }
    .demografia__cabecera { display: flex; align-items: center; gap: var(--espacio-2); }
    .demografia__cabecera .cifra__titulo { margin-bottom: 2px; }
    .demografia__cabecera .campo__ayuda { margin: 0; }
    .demografia__icono {
      display: grid;
      flex: 0 0 38px;
      width: 38px;
      height: 38px;
      place-items: center;
      border: 1px solid rgb(255 255 255 / 82%);
      border-radius: 13px;
      color: var(--acento-fuerte);
      background: rgb(255 255 255 / 62%);
      box-shadow: inset 0 1px rgb(255 255 255 / 90%);
    }
    .cifra__titulo {
      margin: 0 0 var(--espacio-1);
      font-size: .85rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: var(--texto-suave);
    }
    .tendencia__pista { overflow: hidden; height: 8px; border-radius: 999px; background: var(--superficie-hundida); }
    .tendencia__pista span { display: block; height: 100%; min-width: 3px; border-radius: inherit; background: var(--acento); }

    .demografia { min-width: 0; margin-top: var(--espacio-3); }
    .demografia__intro { min-width: 0; }
    .demografia__rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
      gap: var(--espacio-5);
      margin-top: var(--espacio-4);
    }
    .demografia__grupo { min-width: 0; }
    .demografia__grupo h4 { margin: 0 0 var(--espacio-3); }
    .demografia__lista { display: grid; gap: var(--espacio-3); list-style: none; margin: 0; padding: 0; }
    /* El valor reserva su ancho real; la barra ocupa una fila independiente. */
    .demografia__fila {
      display: grid;
      grid-template-columns: minmax(0, 1fr) max-content;
      grid-template-areas: 'categoria valor' 'barra barra';
      align-items: start;
      gap: var(--espacio-1) var(--espacio-2);
      min-width: 0;
      font-size: .84rem;
    }
    .demografia__categoria { grid-area: categoria; min-width: 0; overflow-wrap: anywhere; }
    .demografia__valor { grid-area: valor; white-space: nowrap; text-align: right; }
    .demografia__valor--protegido { color: var(--texto-suave); font-weight: 600; }
    .demografia__pista { grid-area: barra; min-width: 0; }
    .demografia__nota { margin: var(--espacio-4) 0 0; overflow-wrap: anywhere; }
  `,
})
export class PerfilPacientesComponent {
  readonly demografia = input<ResumenPanel['demografia']>(null);

  protected anchoDemografico(
    celdas: readonly { pacientes: number | null }[],
    cantidad: number | null,
  ): number {
    if (cantidad === null || cantidad <= 0) return 0;
    const mayor = Math.max(0, ...celdas.map((celda) => celda.pacientes ?? 0));
    return mayor ? Math.round((cantidad / mayor) * 100) : 0;
  }
}
