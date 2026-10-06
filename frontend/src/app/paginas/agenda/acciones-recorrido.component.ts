/**
 * Lo que pasa con el paciente mientras está en la clínica.
 *
 * Pasar a un consultorio, pedir más tiempo, derivar a otra área y registrar
 * la salida. Cada botón aparece solo si el rol puede usarlo y la cita está en
 * el momento adecuado (el paciente llegó, la atención empezó). El backend lo
 * vuelve a comprobar todo.
 */
import { Component, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import type { Cita, Consultorio } from '../../nucleo/modelos/dominio';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import {
  RecorridoService,
  type CitaAfectada,
  type OpcionDerivacion,
} from '../../nucleo/servicios/recorrido.service';
import { formatearHora } from '../../nucleo/utilidades/fechas';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

const MINUTOS = [10, 15, 20, 30, 45] as const;

interface GrupoDerivacion {
  readonly especialidad: string;
  readonly opciones: readonly OpcionDerivacion[];
}

@Component({
  selector: 'app-acciones-recorrido',
  standalone: true,
  imports: [FormsModule, RouterLink, VentanaFlotanteComponent],
  template: `
    @if (enClinica()) {
      <div class="recorrido" role="group" aria-label="El paciente en la clínica">
        @if (puedeMover()) {
          <div class="recorrido__fila">
            <label class="campo campo--linea">
              <span class="campo__etiqueta">Consultorio</span>
              <select class="campo__control" [(ngModel)]="consultorioId" name="consultorio-recorrido">
                <option value="">Elija…</option>
                @for (c of consultorios(); track c.id) { <option [value]="c.id">{{ c.nombre }}</option> }
              </select>
            </label>
            <button type="button" class="boton" [disabled]="!consultorioId || ocupado()" (click)="pasarAConsultorio()">
              Pasar a consultorio
            </button>
          </div>
        }
        @if (puedePedirTiempo()) {
          <div class="recorrido__fila">
            <label class="campo campo--linea">
              <span class="campo__etiqueta">Más tiempo</span>
              <select class="campo__control" [(ngModel)]="minutos" name="minutos-recorrido">
                @for (m of opcionesMinutos; track m) { <option [ngValue]="m">+{{ m }} min</option> }
              </select>
            </label>
            <button type="button" class="boton" [disabled]="ocupado()" (click)="pedirTiempo()">Pedir más tiempo</button>
          </div>
        }
        <div class="recorrido__fila">
          @if (puedeDerivar()) {
            <button type="button" class="boton" [disabled]="ocupado()" (click)="abrirDerivacion()">Derivar a otra área</button>
          }
          @if (puedeMover()) {
            <button type="button" class="boton boton--plano" [disabled]="ocupado()" (click)="registrarSalida()">Registrar salida</button>
          }
        </div>
        @if (aviso()) { <p class="recorrido__aviso" role="status">{{ aviso() }}</p> }
        @if (afectadas().length > 0) {
          <ul class="recorrido__afectadas">
            @for (a of afectadas(); track a.cita_id) {
              <li>{{ a.paciente }} · {{ hora(a.inicio) }}{{ a.llego ? ' · ya está en sala' : '' }}</li>
            }
          </ul>
        }
        @if (error()) { <p class="campo__error" role="alert">{{ error() }}</p> }
        @if (derivadaA()) {
          <p class="recorrido__aviso">
            Derivado. Escriba el motivo como
            <a [routerLink]="['/historia-clinica']" [queryParams]="{ paciente: cita().paciente_id }">nota de interconsulta en la historia</a>.
          </p>
        }
      </div>
    }

    @if (derivando()) {
      <app-ventana-flotante ceja="Derivación interna" titulo="¿A qué área lo envía?" forma="centrada" [anchoMaximo]="560" (cerrar)="derivando.set(false)">
        @if (cargandoOpciones()) {
          <p role="status">Buscando quién puede atenderle…</p>
        } @else if (grupos().length === 0) {
          <p>No hay otros profesionales con servicios en esta sede.</p>
        } @else {
          <p class="campo__ayuda">El paciente sigue en la clínica: la otra área lo recibe con la llegada ya registrada y podrá abrir su historia.</p>
          @for (grupo of grupos(); track grupo.especialidad) {
            <h3 class="derivar__grupo">{{ grupo.especialidad }}</h3>
            <ul class="derivar__lista">
              @for (o of grupo.opciones; track o.profesional_id + o.servicio_id) {
                <li class="derivar__opcion">
                  <span>
                    <strong>{{ o.profesional }}</strong>
                    <small>{{ o.servicio }} · {{ o.libre_ahora ? 'libre ahora' : o.proximo_turno ? 'libre a las ' + hora(o.proximo_turno) : 'sin hueco hoy' }}</small>
                  </span>
                  <button type="button" class="boton boton--pequeno" [disabled]="ocupado()" (click)="derivar(o)">
                    {{ o.libre_ahora || !o.proximo_turno ? 'Derivar ahora' : 'Derivar a las ' + hora(o.proximo_turno) }}
                  </button>
                </li>
              }
            </ul>
          }
        }
        @if (error()) { <p class="campo__error" role="alert">{{ error() }}</p> }
      </app-ventana-flotante>
    }
  `,
  styles: `
    .recorrido { display: grid; gap: var(--espacio-2); margin-top: var(--espacio-3); padding-top: var(--espacio-3);
      border-top: 1px dashed var(--borde); }
    .recorrido__fila { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--espacio-2); }
    .recorrido__fila .campo { flex: 1 1 140px; margin: 0; }
    .recorrido__aviso { margin: 0; color: var(--texto-suave); font-size: 0.85rem; }
    .recorrido__afectadas { margin: 0; padding-left: 1.2em; font-size: 0.85rem; }
    .derivar__grupo { margin: var(--espacio-3) 0 var(--espacio-2); font-size: 0.8rem; letter-spacing: 0.05em;
      text-transform: uppercase; color: var(--texto-suave); }
    .derivar__lista { display: grid; gap: var(--espacio-2); margin: 0; padding: 0; list-style: none; }
    .derivar__opcion { display: flex; align-items: center; justify-content: space-between; gap: var(--espacio-3);
      padding: var(--espacio-2) var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); }
    .derivar__opcion span { display: grid; }
    .derivar__opcion small { color: var(--texto-suave); }
  `,
})
export class AccionesRecorridoComponent {
  private readonly servicio = inject(RecorridoService);
  private readonly sesion = inject(SesionService);

  readonly cita = input.required<Cita>();
  readonly consultorios = input<readonly Consultorio[]>([]);
  readonly zona = input('America/Guayaquil');
  /** La cita cambió: lleva el mensaje para la persona; la agenda lo muestra y recarga. */
  readonly cambio = output<string>();

  protected readonly opcionesMinutos = MINUTOS;
  protected consultorioId = '';
  protected minutos = 15;

  protected readonly ocupado = signal(false);
  protected readonly aviso = signal('');
  protected readonly error = signal('');
  protected readonly afectadas = signal<readonly CitaAfectada[]>([]);
  protected readonly derivando = signal(false);
  protected readonly cargandoOpciones = signal(false);
  protected readonly opciones = signal<readonly OpcionDerivacion[]>([]);
  protected readonly derivadaA = signal(false);

  protected readonly enClinica = computed(() => {
    const c = this.cita();
    return Boolean(c.llegada_en) && (c.estado === 'CONFIRMED' || c.estado === 'RESCHEDULED');
  });
  protected readonly puedeMover = computed(() => this.sesion.tienePermiso('cita.registrar_llegada'));
  protected readonly puedePedirTiempo = computed(
    () => Boolean(this.cita().atencion_iniciada_en) && this.sesion.tienePermiso('cita.iniciar_atencion'),
  );
  protected readonly puedeDerivar = computed(
    () => this.sesion.tienePermiso('historia_clinica.escribir') && this.sesion.tienePermiso('cita.crear'),
  );
  protected readonly grupos = computed<readonly GrupoDerivacion[]>(() => {
    const porEspecialidad = new Map<string, OpcionDerivacion[]>();
    for (const opcion of this.opciones()) {
      porEspecialidad.set(opcion.especialidad, [...(porEspecialidad.get(opcion.especialidad) ?? []), opcion]);
    }
    return [...porEspecialidad].map(([especialidad, opciones]) => ({ especialidad, opciones }));
  });

  protected hora(instante: string): string {
    return formatearHora(instante, this.zona());
  }

  protected pasarAConsultorio(): void {
    this.correr(this.servicio.ingresoConsultorio(this.cita().id, this.consultorioId), () => {
      const nombre = this.consultorios().find((c) => c.id === this.consultorioId)?.nombre ?? 'el consultorio';
      return `Paciente en ${nombre}.`;
    });
  }

  protected registrarSalida(): void {
    this.correr(this.servicio.salida(this.cita().id), () => 'Salida registrada.');
  }

  protected pedirTiempo(): void {
    this.afectadas.set([]);
    this.ocupado.set(true);
    this.error.set('');
    this.servicio.pedirTiempo(this.cita().id, this.minutos).subscribe({
      next: (resultado) => {
        this.ocupado.set(false);
        if (resultado.aplicada) {
          const mensaje = `Atención alargada ${resultado.minutos} min; termina a las ${this.hora(resultado.fin)}.`;
          this.aviso.set(mensaje);
          this.cambio.emit(mensaje);
        } else {
          const afectados = resultado.conflictos.map((c) => c.paciente).join(', ');
          const mensaje = `Más tiempo pedido. Choca con ${afectados}: recepción decidirá cómo reorganizarlo.`;
          this.aviso.set(mensaje);
          this.afectadas.set(resultado.conflictos);
          this.cambio.emit(mensaje);
        }
      },
      error: (fallo: Error) => this.fallar(fallo),
    });
  }

  protected abrirDerivacion(): void {
    this.derivando.set(true);
    this.cargandoOpciones.set(true);
    this.error.set('');
    this.servicio.opcionesDerivacion(this.cita().id).subscribe({
      next: (opciones) => {
        this.opciones.set(opciones);
        this.cargandoOpciones.set(false);
      },
      error: (fallo: Error) => {
        this.cargandoOpciones.set(false);
        this.fallar(fallo);
      },
    });
  }

  protected derivar(opcion: OpcionDerivacion): void {
    const inicio = opcion.libre_ahora || !opcion.proximo_turno ? null : opcion.proximo_turno;
    this.correr(
      this.servicio.derivar(this.cita().id, { profesional_id: opcion.profesional_id, servicio_id: opcion.servicio_id, inicio }),
      () => {
        this.derivando.set(false);
        this.derivadaA.set(true);
        return `Derivado a ${opcion.profesional} (${opcion.especialidad}).`;
      },
    );
  }

  private correr(peticion: ReturnType<RecorridoService['salida']>, mensaje: () => string): void {
    this.ocupado.set(true);
    this.error.set('');
    peticion.subscribe({
      next: () => {
        this.ocupado.set(false);
        const texto = mensaje();
        this.aviso.set(texto);
        this.cambio.emit(texto);
      },
      error: (fallo: Error) => this.fallar(fallo),
    });
  }

  private fallar(fallo: Error): void {
    this.ocupado.set(false);
    this.error.set(fallo.message);
  }
}
