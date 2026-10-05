/**
 * «Antes de entrar»: lo que el profesional tiene que saber del paciente.
 *
 * Alergias primero y en rojo si son graves; después la medicación confirmada
 * con cómo la está tomando, las últimas notas y los planes en curso. Todo es
 * dato de la historia, sin interpretación.
 *
 * «Redactar con IA local» convierte ese resumen en un párrafo con un modelo
 * que corre en el servidor de la clínica. No se guarda y lleva su aviso: es
 * una ayuda de lectura, no una conclusión clínica.
 */
import { Component, effect, inject, input, signal, untracked } from '@angular/core';
import { DatePipe, LowerCasePipe } from '@angular/common';

import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { FalloApi } from '../../nucleo/servicios/api.service';

export interface ResumenClinico {
  readonly edad: number | null;
  readonly sexo: string | null;
  readonly alergias: readonly { sustancia: string; reaccion: string | null; severidad: string }[];
  readonly antecedentes: readonly { categoria: string; descripcion: string }[];
  readonly medicacion_activa: readonly {
    nombre: string;
    concentracion: string | null;
    dosis: string;
    via: string;
    cuando_sea_necesario: boolean;
    frecuencia_horas: number | null;
    duracion_dias: number | null;
    instrucciones: string | null;
    desde: string | null;
  }[];
  readonly adherencia: { dias: number; tomadas: number; omitidas: number; sin_registrar: number };
  readonly ultimas_notas: readonly {
    fecha: string;
    tipo: string;
    motivo_consulta: string | null;
    analisis: string | null;
    plan: string | null;
  }[];
  readonly planes: readonly { titulo: string; estado: string; procedimientos_pendientes: number }[];
  readonly ultima_atencion: string | null;
  readonly proxima_cita: string | null;
  readonly redaccion_disponible: boolean;
}

@Component({
  selector: 'app-resumen-clinico',
  standalone: true,
  imports: [DatePipe, LowerCasePipe],
  template: `
    <section class="resumen" aria-labelledby="titulo-resumen">
      <header class="resumen__cabecera">
        <div>
          <p class="ceja">ANTES DE ENTRAR</p>
          <h3 id="titulo-resumen">Resumen para la consulta</h3>
        </div>
        @if (datos()?.redaccion_disponible) {
          <button type="button" class="boton boton--pequeno" [disabled]="redactando()" (click)="redactar()">
            {{ redactando() ? 'Redactando…' : 'Redactar con IA local' }}
          </button>
        }
      </header>

      @if (cargando()) {
        <p class="resumen__nada" role="status">Cargando el resumen…</p>
      } @else if (error()) {
        <p class="resumen__aviso" role="alert">{{ error() }}</p>
      } @else if (datos()) {
        @let d = datos()!;
        @if (redaccion(); as r) {
          <div class="redaccion" role="note">
            <p class="redaccion__texto">{{ r.texto }}</p>
            <p class="redaccion__aviso">{{ r.aviso }} Modelo: {{ r.modelo }}.</p>
          </div>
        }
        @if (errorRedaccion()) { <p class="resumen__aviso" role="alert">{{ errorRedaccion() }}</p> }

        <div class="rejilla">
          <div class="bloque" [class.bloque--alerta]="hayAlergiaGrave()">
            <h4>Alergias</h4>
            @for (a of d.alergias; track a.sustancia) {
              <p><strong>{{ a.sustancia }}</strong> · {{ severidad(a.severidad) }}@if (a.reaccion) { · {{ a.reaccion }} }</p>
            } @empty { <p class="resumen__nada">Sin alergias registradas.</p> }
          </div>

          <div class="bloque">
            <h4>Medicación activa</h4>
            @for (m of d.medicacion_activa; track m.nombre + m.dosis) {
              <p>
                <strong>{{ m.nombre }}@if (m.concentracion) { {{ m.concentracion }} }</strong> · {{ m.dosis }} · {{ m.via | lowercase }}
                · {{ m.cuando_sea_necesario ? 'cuando sea necesario' : m.frecuencia_horas ? 'cada ' + m.frecuencia_horas + ' h' : 'pauta sin frecuencia' }}
                @if (m.duracion_dias) { · {{ m.duracion_dias }} días }
              </p>
            } @empty { <p class="resumen__nada">Sin medicación confirmada.</p> }
            <p class="adherencia">
              Últimos {{ d.adherencia.dias }} días:
              <strong class="numerico">{{ d.adherencia.tomadas }}</strong> tomadas ·
              <strong class="numerico" [class.alerta]="d.adherencia.omitidas > 0">{{ d.adherencia.omitidas }}</strong> omitidas ·
              <strong class="numerico">{{ d.adherencia.sin_registrar }}</strong> sin registrar
            </p>
          </div>

          <div class="bloque">
            <h4>Evolución reciente</h4>
            @for (n of d.ultimas_notas; track n.fecha) {
              <p>
                <span class="numerico">{{ n.fecha | date: 'dd/MM/yy' }}</span> ·
                <strong>{{ n.motivo_consulta || 'Sin motivo registrado' }}</strong>
                @if (n.plan) { <br /><span class="tenue">Plan: {{ n.plan }}</span> }
              </p>
            } @empty { <p class="resumen__nada">Sin notas.</p> }
          </div>

          <div class="bloque">
            <h4>Tratamiento y citas</h4>
            @for (p of d.planes; track p.titulo) {
              <p><strong>{{ p.titulo }}</strong> · {{ estadoPlan(p.estado) }} · {{ p.procedimientos_pendientes }} procedimiento(s) pendiente(s)</p>
            } @empty { <p class="resumen__nada">Sin planes en curso.</p> }
            <p class="tenue">
              Última atención: {{ d.ultima_atencion ? (d.ultima_atencion | date: 'dd/MM/yy') : 'sin registro' }} ·
              Próxima cita: {{ d.proxima_cita ? (d.proxima_cita | date: 'dd/MM/yy HH:mm') : 'sin agendar' }}
            </p>
            @if (d.antecedentes.length) {
              <h4 class="sub">Antecedentes</h4>
              @for (a of d.antecedentes; track a.descripcion) { <p><span class="tenue">{{ a.categoria | lowercase }}:</span> {{ a.descripcion }}</p> }
            }
          </div>
        </div>
      }
    </section>
  `,
  styles: `
    .resumen { display: grid; gap: var(--espacio-3); padding: var(--espacio-4); border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie-elevada); }
    .resumen__cabecera { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--espacio-3); }
    .resumen__cabecera h3 { margin: 0; font-size: 1.05rem; }
    .ceja { margin: 0; color: var(--acento); font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; }
    .resumen__nada { margin: 0; color: var(--texto-tenue); font-size: 0.88rem; }
    .resumen__aviso { margin: 0; color: var(--aviso); font-size: 0.88rem; }
    .rejilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--espacio-3); }
    .bloque { padding: var(--espacio-3); border-radius: var(--radio); background: var(--superficie); border: 1px solid var(--superficie-hundida); }
    .bloque h4 { margin: 0 0 var(--espacio-2); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--texto-suave); }
    .bloque h4.sub { margin-top: var(--espacio-3); }
    .bloque p { margin: 0 0 var(--espacio-1); font-size: 0.88rem; }
    .bloque--alerta { border-color: color-mix(in srgb, var(--peligro) 45%, transparent); background: var(--peligro-fondo); }
    .bloque--alerta h4 { color: var(--peligro); }
    .adherencia { margin-top: var(--espacio-2) !important; color: var(--texto-suave); }
    .alerta { color: var(--aviso); }
    .tenue { color: var(--texto-suave); }
    .redaccion { padding: var(--espacio-3); border-radius: var(--radio); background: var(--acento-suave); }
    .redaccion__texto { margin: 0 0 var(--espacio-2); white-space: pre-line; }
    .redaccion__aviso { margin: 0; font-size: 0.78rem; color: var(--texto-suave); }
  `,
})
export class ResumenClinicoComponent {
  private readonly api = inject(OperacionesService);
  readonly pacienteId = input.required<string>();

  protected readonly datos = signal<ResumenClinico | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal('');
  protected readonly redactando = signal(false);
  protected readonly errorRedaccion = signal('');
  protected readonly redaccion = signal<{ texto: string; modelo: string; aviso: string } | null>(null);

  constructor() {
    effect(() => {
      const id = this.pacienteId();
      untracked(() => this.cargar(id));
    });
  }

  private cargar(id: string): void {
    this.cargando.set(true);
    this.error.set('');
    this.redaccion.set(null);
    this.api.leer<ResumenClinico>(`/historia/pacientes/${id}/resumen-clinico`).subscribe({
      next: (datos) => {
        this.datos.set(datos);
        this.cargando.set(false);
      },
      error: (fallo: FalloApi) => {
        this.cargando.set(false);
        this.error.set(
          fallo.codigo === 'RELACION_ASISTENCIAL_REQUERIDA'
            ? 'Sin relación asistencial con este paciente: el resumen solo lo ve quien le atiende.'
            : fallo.message,
        );
      },
    });
  }

  protected redactar(): void {
    this.redactando.set(true);
    this.errorRedaccion.set('');
    this.api
      .guardar<{ texto: string; modelo: string; aviso: string }>(
        `/historia/pacientes/${this.pacienteId()}/resumen-clinico/redaccion`,
        {},
        crypto.randomUUID(),
      )
      .subscribe({
        next: (redaccion) => {
          this.redactando.set(false);
          this.redaccion.set(redaccion);
        },
        error: (fallo: FalloApi) => {
          this.redactando.set(false);
          this.errorRedaccion.set(fallo.message);
        },
      });
  }

  protected hayAlergiaGrave(): boolean {
    return (this.datos()?.alergias ?? []).some((a) => a.severidad === 'GRAVE' || a.severidad === 'ANAFILAXIA');
  }

  protected severidad(valor: string): string {
    return ({ LEVE: 'leve', MODERADA: 'moderada', GRAVE: 'grave', ANAFILAXIA: 'anafilaxia' } as Record<string, string>)[valor] ?? valor.toLowerCase();
  }

  protected estadoPlan(valor: string): string {
    return ({ BORRADOR: 'borrador', PROPUESTO: 'propuesto', ACEPTADO: 'en curso' } as Record<string, string>)[valor] ?? valor.toLowerCase();
  }
}
