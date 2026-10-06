/**
 * Recorrido del paciente: todo lo que pasó en la clínica, en orden.
 *
 * Cuándo llegó, en qué consultorio estuvo, quién le atendió, si le derivaron,
 * si la atención se alargó y cuándo salió. Agrupado por día, del más reciente
 * al más antiguo. Sin datos clínicos: lo ve recepción y queda auditado.
 */
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';

import { RecorridoService, type PasoRecorrido } from '../nucleo/servicios/recorrido.service';
import { formatearFechaLarga, formatearHora } from '../nucleo/utilidades/fechas';

interface Dia {
  readonly fecha: string;
  readonly pasos: readonly PasoRecorrido[];
}

const TONOS: Record<string, string> = {
  LLEGADA: 'llegada',
  INGRESO_CONSULTORIO: 'lugar',
  ATENCION_INICIADA: 'atencion',
  DERIVACION_INTERNA: 'derivacion',
  DERIVADA_DESDE: 'derivacion',
  PROLONGACION_SOLICITADA: 'tiempo',
  PROLONGACION_APLICADA: 'tiempo',
  PROLONGACION_RECHAZADA: 'tiempo',
  COMPLETADA: 'fin',
  SALIDA: 'fin',
  CANCELADA: 'alerta',
  INASISTENCIA: 'alerta',
};

@Component({
  selector: 'app-recorrido-paciente',
  standalone: true,
  template: `
    @if (cargando()) {
      <p role="status">Cargando el recorrido…</p>
    } @else if (error()) {
      <p class="campo__error" role="alert">{{ error() }}</p>
    } @else if (dias().length === 0) {
      <p class="nada">Aún no hay movimientos registrados de este paciente.</p>
    } @else {
      @for (dia of dias(); track dia.fecha) {
        <h4 class="dia">{{ dia.fecha }}</h4>
        <ol class="linea">
          @for (paso of dia.pasos; track $index) {
            <li class="paso" [attr.data-tono]="tono(paso.evento)">
              <span class="paso__hora numerico">{{ hora(paso.ocurrido_en) }}</span>
              <div class="paso__cuerpo">
                <strong>{{ paso.titulo }}</strong>
                @if (paso.detalle) { <span class="paso__detalle">{{ paso.detalle }}</span> }
                <small>
                  {{ detalle(paso.servicio, paso.profesional, paso.consultorio, paso.sede) }}
                  @if (paso.registrado_por) { · registró {{ paso.registrado_por }} }
                </small>
              </div>
            </li>
          }
        </ol>
      }
    }
  `,
  styles: `
    .nada { color: var(--texto-suave); }
    .dia { margin: var(--espacio-4) 0 var(--espacio-2); font-size: 0.8rem; letter-spacing: 0.05em;
      text-transform: uppercase; color: var(--texto-suave); }
    .dia:first-child { margin-top: 0; }
    .linea { margin: 0; padding: 0; list-style: none; border-left: 2px solid var(--borde); }
    .paso { position: relative; display: grid; grid-template-columns: 52px 1fr; gap: var(--espacio-2);
      padding: var(--espacio-2) 0 var(--espacio-2) var(--espacio-3); }
    .paso::before { content: ''; position: absolute; left: -6px; top: 14px; width: 10px; height: 10px;
      border-radius: 50%; background: var(--texto-suave); }
    .paso[data-tono='llegada']::before { background: #3b82c4; }
    .paso[data-tono='lugar']::before { background: #7c5cc4; }
    .paso[data-tono='atencion']::before, .paso[data-tono='fin']::before { background: var(--acento); }
    .paso[data-tono='derivacion']::before { background: #c9821b; }
    .paso[data-tono='tiempo']::before { background: #b8a018; }
    .paso[data-tono='alerta']::before { background: var(--peligro); }
    .paso__hora { color: var(--texto-suave); font-size: 0.85rem; padding-top: 2px; }
    .paso__cuerpo { display: grid; gap: 2px; }
    .paso__detalle { font-size: 0.9rem; }
    .paso__cuerpo small { color: var(--texto-suave); }
  `,
})
export class RecorridoPacienteComponent implements OnInit {
  private readonly servicio = inject(RecorridoService);

  readonly pacienteId = input.required<string>();
  readonly zona = input('America/Guayaquil');

  protected readonly pasos = signal<readonly PasoRecorrido[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');

  protected readonly dias = computed<readonly Dia[]>(() => {
    const porDia = new Map<string, PasoRecorrido[]>();
    for (const paso of this.pasos()) {
      const fecha = formatearFechaLarga(paso.ocurrido_en, this.zona());
      porDia.set(fecha, [...(porDia.get(fecha) ?? []), paso]);
    }
    return [...porDia].map(([fecha, pasos]) => ({ fecha, pasos })).reverse();
  });

  ngOnInit(): void {
    this.servicio.recorrido(this.pacienteId()).subscribe({
      next: (pasos) => {
        this.pasos.set(pasos);
        this.cargando.set(false);
      },
      error: (fallo: Error) => {
        this.error.set(fallo.message);
        this.cargando.set(false);
      },
    });
  }

  protected hora(instante: string): string {
    return formatearHora(instante, this.zona());
  }

  protected detalle(...partes: (string | null | undefined)[]): string {
    return partes.filter((parte): parte is string => Boolean(parte)).join(' · ');
  }

  protected tono(evento: string): string {
    return TONOS[evento] ?? 'neutro';
  }
}
