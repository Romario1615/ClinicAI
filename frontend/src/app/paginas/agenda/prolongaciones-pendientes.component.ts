/**
 * Peticiones de más tiempo que esperan a recepción.
 *
 * Un profesional pidió alargar la atención y eso pisa al siguiente paciente.
 * El sistema propone a dónde moverlo (otro profesional libre o más tarde con
 * el mismo); recepción elige y confirma. Al paciente movido le llega un
 * WhatsApp genérico con la nueva hora. También se puede no aplicar la
 * prolongación, con motivo.
 */
import { Component, OnInit, inject, input, output, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SesionService } from '../../nucleo/servicios/sesion.service';
import {
  RecorridoService,
  type AlternativaTurno,
  type PeticionTiempo,
} from '../../nucleo/servicios/recorrido.service';
import { formatearHora, instanteLocal } from '../../nucleo/utilidades/fechas';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

@Component({
  selector: 'app-prolongaciones-pendientes',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent],
  template: `
    <!-- En la agenda este componente no ocupa caja propia («sin-caja»): el
         aviso es directamente una pieza fija de la pantalla y, sin
         peticiones, no deja ni un hueco vacío. -->
    @if (puedeResolver() && peticiones().length > 0) {
      <section class="pendientes pantalla__fijo" aria-labelledby="titulo-mas-tiempo">
        <h2 id="titulo-mas-tiempo">Peticiones de más tiempo</h2>
        <ul>
          @for (p of peticiones(); track p.cita_id) {
            <li class="pendientes__fila">
              <span>
                <strong>{{ p.profesional }}</strong> pide +{{ p.minutos }} min con {{ p.paciente }}.
                Afecta a {{ nombres(p) }}.
              </span>
              <button type="button" class="boton boton--principal boton--pequeno" (click)="abrir(p)">Decidir</button>
            </li>
          }
        </ul>
      </section>
    }

    @if (abierta(); as p) {
      <app-ventana-flotante ceja="Más tiempo" [titulo]="p.profesional + ' pide +' + p.minutos + ' min'" forma="centrada"
        [anchoMaximo]="600" [cierraAlPulsarFuera]="false" (cerrar)="cerrar()">
        <p class="campo__ayuda">
          La atención de {{ p.paciente }} terminaría a las {{ hora(sumar(p.fin_actual, p.minutos)) }}.
          Elija qué pasa con cada paciente afectado. Si prefiere, el profesional puede derivar al paciente en atención a otra área.
        </p>
        @for (afectada of p.conflictos; track afectada.cita_id) {
          <fieldset class="afectada">
            <legend>{{ afectada.paciente }} · {{ hora(afectada.inicio) }}{{ afectada.llego ? ' · ya está en sala' : '' }}</legend>
            @for (alt of afectada.alternativas; track alt.profesional_id + alt.inicio) {
              <label class="afectada__opcion">
                <input type="radio" [name]="'decision-' + afectada.cita_id" [checked]="elegida(afectada.cita_id) === alt"
                  (change)="elegir(afectada.cita_id, alt)" />
                {{ alt.mismo_profesional ? 'Más tarde con ' : 'Pasar a ' }}{{ alt.profesional }} a las {{ hora(alt.inicio) }}
              </label>
            } @empty {
              <p class="campo__ayuda">El sistema no encontró un hueco libre: elija otra hora a mano o no aplique la prolongación.</p>
            }
            <label class="afectada__opcion">
              <input type="radio" [name]="'decision-' + afectada.cita_id" [checked]="elegida(afectada.cita_id)?.profesional_id === ''"
                (change)="elegirManual(afectada.cita_id, manual[afectada.cita_id])" />
              Otra hora con el mismo profesional:
              <input type="datetime-local" class="campo__control afectada__hora" [name]="'hora-' + afectada.cita_id"
                [(ngModel)]="manual[afectada.cita_id]" (ngModelChange)="elegirManual(afectada.cita_id, $event)"
                [attr.aria-label]="'Nueva hora para ' + afectada.paciente" />
            </label>
          </fieldset>
        }
        <label class="campo">
          <span class="campo__etiqueta">Si no la aplica, ¿por qué?</span>
          <input class="campo__control" name="motivo-rechazo" [(ngModel)]="motivo" maxlength="300"
            placeholder="Ej.: el siguiente paciente ya está en sala" />
        </label>
        @if (error()) { <p class="campo__error" role="alert">{{ error() }}</p> }
        <div class="pie">
          <button type="button" class="boton" [disabled]="ocupado()" (click)="rechazar(p)">No aplicar</button>
          <button type="button" class="boton boton--principal" [disabled]="ocupado() || !completa(p)" (click)="aplicar(p)">
            Aplicar y avisar
          </button>
        </div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .pendientes { margin: 0; padding: var(--espacio-2) var(--espacio-4);
      border: 1px solid var(--aviso-borde, var(--borde)); border-left: 4px solid var(--aviso, #c98a1b);
      border-radius: var(--radio); background: var(--superficie); }
    .pendientes h2 { margin: 0 0 var(--espacio-1); font-size: 0.95rem; }
    .pendientes ul { display: grid; gap: var(--espacio-1); margin: 0; padding: 0; list-style: none; }
    .pendientes__fila { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--espacio-1) var(--espacio-3); }
    .pendientes__fila > span { flex: 1 1 18rem; min-width: 0; }
    .afectada { display: grid; gap: var(--espacio-2); margin: 0 0 var(--espacio-3); padding: var(--espacio-3);
      border: 1px solid var(--borde); border-radius: var(--radio); }
    .afectada legend { padding: 0 var(--espacio-1); font-weight: 600; }
    .afectada__opcion { display: flex; align-items: center; gap: var(--espacio-2); cursor: pointer; }
    .afectada__hora { width: auto; max-width: 220px; }
    .pie { display: flex; justify-content: flex-end; gap: var(--espacio-2); margin-top: var(--espacio-3); }
  `,
})
export class ProlongacionesPendientesComponent implements OnInit {
  private readonly servicio = inject(RecorridoService);
  private readonly sesion = inject(SesionService);

  readonly zona = input('America/Guayaquil');
  /** Avisa a la agenda para que recargue el día. */
  readonly resuelta = output<void>();

  protected readonly peticiones = signal<readonly PeticionTiempo[]>([]);
  protected readonly abierta = signal<PeticionTiempo | null>(null);
  protected readonly decisiones = signal<ReadonlyMap<string, AlternativaTurno>>(new Map());
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected motivo = '';
  /** Hora elegida a mano por paciente afectado (valor de datetime-local). */
  protected manual: Record<string, string> = {};

  protected puedeResolver(): boolean {
    return this.sesion.tienePermiso('cita.reprogramar');
  }

  ngOnInit(): void {
    this.cargar();
  }

  /** Vuelve a pedir las peticiones (la agenda lo llama al recargar). */
  cargar(): void {
    if (!this.puedeResolver()) return;
    this.servicio.pendientes().subscribe({
      next: (lista) => this.peticiones.set(lista),
      error: () => this.peticiones.set([]),
    });
  }

  protected nombres(p: PeticionTiempo): string {
    return p.conflictos.map((c) => c.paciente).join(', ') || 'nadie';
  }

  protected hora(instante: string): string {
    return formatearHora(instante, this.zona());
  }

  protected sumar(instante: string, minutos: number): string {
    return new Date(new Date(instante).getTime() + minutos * 60_000).toISOString();
  }

  protected abrir(p: PeticionTiempo): void {
    this.error.set('');
    this.motivo = '';
    this.manual = {};
    this.decisiones.set(new Map());
    this.servicio.opcionesTiempo(p.cita_id).subscribe({
      next: (detalle) => {
        this.abierta.set(detalle);
        // Por omisión, la primera alternativa de cada paciente.
        const iniciales = new Map<string, AlternativaTurno>();
        for (const c of detalle.conflictos) {
          if (c.alternativas[0]) iniciales.set(c.cita_id, c.alternativas[0]);
        }
        this.decisiones.set(iniciales);
      },
      error: (fallo: Error) => this.error.set(fallo.message),
    });
  }

  protected cerrar(): void {
    this.abierta.set(null);
  }

  protected elegida(citaId: string): AlternativaTurno | undefined {
    return this.decisiones().get(citaId);
  }

  protected elegir(citaId: string, alternativa: AlternativaTurno): void {
    const nuevas = new Map(this.decisiones());
    nuevas.set(citaId, alternativa);
    this.decisiones.set(nuevas);
  }

  protected elegirManual(citaId: string, valor: string | undefined): void {
    const nuevas = new Map(this.decisiones());
    if (!valor) {
      nuevas.delete(citaId);
    } else {
      const [fecha, hora] = valor.split('T');
      nuevas.set(citaId, {
        profesional_id: '',
        profesional: '',
        inicio: instanteLocal(fecha, hora, this.zona()),
        mismo_profesional: true,
      });
    }
    this.decisiones.set(nuevas);
  }

  protected completa(p: PeticionTiempo): boolean {
    return p.conflictos.every((c) => this.decisiones().has(c.cita_id));
  }

  protected aplicar(p: PeticionTiempo): void {
    const resoluciones = p.conflictos.map((c) => {
      const alt = this.decisiones().get(c.cita_id)!;
      return { cita_id: c.cita_id, inicio: alt.inicio, profesional_id: alt.mismo_profesional ? null : alt.profesional_id };
    });
    this.enviar(p, { aprobar: true, resoluciones });
  }

  protected rechazar(p: PeticionTiempo): void {
    if (this.motivo.trim().length < 3) {
      this.error.set('Indique por qué no se aplica la prolongación.');
      return;
    }
    this.enviar(p, { aprobar: false, motivo_rechazo: this.motivo.trim() });
  }

  private enviar(p: PeticionTiempo, cuerpo: Parameters<RecorridoService['resolver']>[1]): void {
    this.ocupado.set(true);
    this.error.set('');
    this.servicio.resolver(p.cita_id, cuerpo).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.abierta.set(null);
        this.cargar();
        this.resuelta.emit();
      },
      error: (fallo: Error) => {
        this.ocupado.set(false);
        this.error.set(fallo.message);
      },
    });
  }
}
