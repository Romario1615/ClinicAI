/**
 * Insignia de estado de una cita.
 *
 * El color acompaña, no informa. La etiqueta de texto está siempre presente,
 * porque una cita cancelada y una confirmada no pueden distinguirse solo por
 * el tono: hay personal que no percibe esa diferencia, y confundirlas
 * significa que alguien espera a un paciente que no va a venir, o al
 * contrario.
 *
 * Los estados se conservan en inglés en el modelo (ADR‑0015) y se traducen
 * **solo para mostrarlos**. La traducción vive aquí y no en el modelo para
 * que el contrato con el backend no dependa del idioma de la interfaz.
 */
import { Component, computed, input } from '@angular/core';

import type { EstadoCita } from '../nucleo/modelos/dominio';

interface Presentacion {
  readonly etiqueta: string;
  readonly clase: string;
  /** Explicación para el atributo `title` y para lectores de pantalla. */
  readonly descripcion: string;
}

const PRESENTACION: Record<EstadoCita, Presentacion> = {
  PENDING: {
    etiqueta: 'Pendiente',
    clase: 'neutra',
    descripcion: 'Creada, todavía sin confirmar',
  },
  HELD: {
    etiqueta: 'Bloqueada',
    clase: 'aviso',
    descripcion: 'Turno reservado temporalmente; caduca si no se confirma',
  },
  CONFIRMED: {
    etiqueta: 'Confirmada',
    clase: 'exito',
    descripcion: 'El paciente tiene la cita confirmada',
  },
  RESCHEDULED: {
    etiqueta: 'Reprogramada',
    clase: 'info',
    descripcion: 'Movida a otro horario; conserva el mismo identificador',
  },
  CANCELLED: {
    etiqueta: 'Cancelada',
    clase: 'peligro',
    descripcion: 'Anulada, con motivo registrado',
  },
  COMPLETED: {
    etiqueta: 'Atendida',
    clase: 'neutra',
    descripcion: 'La atención se completó',
  },
  NO_SHOW: {
    etiqueta: 'No asistió',
    clase: 'peligro',
    descripcion: 'El paciente no se presentó; cuenta para las métricas de ausentismo',
  },
};

@Component({
  selector: 'app-insignia-estado',
  standalone: true,
  template: `
    <span class="insignia" [class]="'insignia--' + presentacion().clase" [title]="presentacion().descripcion">
      {{ presentacion().etiqueta }}
    </span>
  `,
  styles: `
    .insignia {
      display: inline-block;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 650;
      white-space: nowrap;
      border: 1px solid currentcolor;
    }
    .insignia--exito {
      color: var(--exito);
      background: var(--exito-fondo);
    }
    .insignia--aviso {
      color: var(--aviso);
      background: var(--aviso-fondo);
    }
    .insignia--peligro {
      color: var(--peligro);
      background: var(--peligro-fondo);
    }
    .insignia--info {
      color: var(--info);
      background: var(--info-fondo);
    }
    .insignia--neutra {
      color: var(--texto-suave);
      background: var(--superficie-hundida);
    }
  `,
})
export class InsigniaEstadoComponent {
  readonly estado = input.required<EstadoCita>();

  readonly presentacion = computed<Presentacion>(
    () => PRESENTACION[this.estado()] ?? PRESENTACION.PENDING,
  );
}
