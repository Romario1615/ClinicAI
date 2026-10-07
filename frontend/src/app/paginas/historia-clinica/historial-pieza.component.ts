/**
 * Historial de una pieza dental.
 *
 * Reúne en un solo panel lo que le ha pasado a la pieza elegida en el
 * odontograma: cada versión en la que su estado cambió (con fecha y motivo),
 * los procedimientos del plan que la afectan y sus fotos. No guarda nada por
 * sí mismo: el registro de un hallazgo nuevo crea una versión del odontograma
 * en el componente padre, y las fotos pasan por el API de imágenes.
 */
import { Component, computed, input, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';

import type {
  Odontograma,
  PlanTratamiento,
  ProcedimientoPlan,
} from '../../nucleo/servicios/api.service';
import { FotosClinicasComponent } from '../../compartido/fotos-clinicas.component';
import { describirEstado, mismoEstado } from './odontograma.vocabulario';

export interface CambioPieza {
  readonly version: number;
  readonly fecha: string;
  readonly motivo: string | null;
  readonly descripcion: string;
  readonly nota: string | null;
  readonly porProcedimiento: boolean;
}

const ESTADOS_PROCEDIMIENTO: Readonly<Record<string, string>> = {
  PENDIENTE: 'Pendiente',
  COMPLETADO: 'Completado',
  CANCELADO: 'Cancelado',
};

@Component({
  selector: 'app-historial-pieza',
  standalone: true,
  imports: [DatePipe, FotosClinicasComponent],
  template: `
    <section class="historial" [attr.aria-label]="'Historial de la pieza ' + pieza()">
      <h4>Historial de la pieza {{ pieza() }}</h4>

      <ol class="historial__linea">
        @for (cambio of cambios(); track cambio.version) {
          <li class="historial__cambio">
            <span class="historial__punto" aria-hidden="true"></span>
            <div>
              <p class="historial__cabecera">
                <strong>{{ cambio.fecha | date: 'mediumDate' }}</strong>
                <span class="historial__version">versión {{ cambio.version }}</span>
                @if (cambio.porProcedimiento) {
                  <span class="historial__etiqueta">por procedimiento</span>
                }
              </p>
              <p class="historial__descripcion">{{ cambio.descripcion }}</p>
              @if (cambio.nota) {
                <p class="historial__nota">Nota: {{ cambio.nota }}</p>
              }
              @if (cambio.motivo) {
                <p class="historial__motivo">Motivo: {{ cambio.motivo }}</p>
              }
            </div>
          </li>
        } @empty {
          <li class="historial__vacio">Sin cambios registrados en esta pieza.</li>
        }
      </ol>

      @if (procedimientos().length) {
        <h5>Procedimientos del plan</h5>
        <ul class="historial__procedimientos">
          @for (item of procedimientos(); track item.procedimiento.id) {
            <li [class]="'proc proc--' + item.procedimiento.estado.toLowerCase()">
              <span>
                {{ item.procedimiento.descripcion }}
                @if (item.procedimiento.caras) { <small>({{ item.procedimiento.caras }})</small> }
              </span>
              <small>{{ item.plan }} · {{ estadoProcedimiento(item.procedimiento.estado) }}
                @if (item.procedimiento.completado_en) { · {{ item.procedimiento.completado_en | date: 'mediumDate' }} }
              </small>
            </li>
          }
        </ul>
      }

      <h5>Fotos de la pieza</h5>
      <app-fotos-clinicas
        [pacienteId]="pacienteId()"
        [pieza]="pieza()"
        [etiqueta]="'Fotos de la pieza ' + pieza()"
        vacio="Aún no hay fotos de esta pieza."
      />
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .historial { display: grid; gap: var(--espacio-2); }
    h4, h5 { margin: 0; }
    h5 { margin-top: var(--espacio-2); font-size: 0.85rem; color: var(--texto-suave); text-transform: uppercase; letter-spacing: 0.04em; }
    .historial__linea { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--espacio-2); }
    .historial__cambio { display: grid; grid-template-columns: 12px 1fr; gap: var(--espacio-2); }
    .historial__punto { width: 10px; height: 10px; margin-top: 5px; border-radius: 50%; background: var(--acento); }
    .historial__cabecera { margin: 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
    .historial__version { font-size: 0.75rem; color: var(--texto-suave); }
    .historial__etiqueta { font-size: 0.7rem; padding: 0 6px; border-radius: 999px; background: var(--acento-suave); color: var(--acento-fuerte); }
    .historial__descripcion, .historial__nota, .historial__motivo { margin: 2px 0 0; font-size: 0.875rem; }
    .historial__nota, .historial__motivo { color: var(--texto-suave); }
    .historial__vacio { font-size: 0.875rem; color: var(--texto-suave); }
    .historial__procedimientos { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
    .proc { display: grid; gap: 2px; padding: 6px 8px; border-radius: 6px; background: var(--superficie-hundida, var(--acento-suave)); font-size: 0.875rem; }
    .proc small { color: var(--texto-suave); }
    .proc--completado { box-shadow: inset 3px 0 0 var(--exito); }
    .proc--pendiente { box-shadow: inset 3px 0 0 var(--aviso, var(--acento)); }
    .proc--cancelado { opacity: 0.7; text-decoration: line-through; }
  `,
})
export class HistorialPiezaComponent {
  readonly pacienteId = input.required<string>();
  readonly pieza = input.required<number>();
  readonly versiones = input<readonly Odontograma[]>([]);
  readonly planes = input<readonly PlanTratamiento[]>([]);

  /** Cambios de la pieza, del más reciente al más antiguo. */
  protected readonly cambios = computed<readonly CambioPieza[]>(() => {
    const codigo = String(this.pieza());
    const ordenadas = [...this.versiones()].sort((a, b) => a.version - b.version);
    const cambios: CambioPieza[] = [];
    let anterior: Odontograma | null = null;
    for (const version of ordenadas) {
      const estado = version.piezas[codigo];
      if (!mismoEstado(anterior?.piezas[codigo], estado)) {
        cambios.push({
          version: version.version,
          fecha: version.creado_en,
          motivo: version.motivo_modificacion,
          descripcion: describirEstado(estado),
          nota: estado?.nota ?? null,
          porProcedimiento: Boolean(version.procedimiento_id),
        });
      }
      anterior = version;
    }
    return cambios.reverse();
  });

  protected readonly procedimientos = computed<
    readonly { plan: string; procedimiento: ProcedimientoPlan }[]
  >(() =>
    this.planes().flatMap((plan) =>
      plan.procedimientos
        .filter((procedimiento) => procedimiento.pieza === this.pieza())
        .map((procedimiento) => ({ plan: plan.titulo, procedimiento })),
    ),
  );

  protected estadoProcedimiento(estado: string): string {
    return ESTADOS_PROCEDIMIENTO[estado] ?? estado;
  }
}
