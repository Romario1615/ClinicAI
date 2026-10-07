/**
 * Automatizaciones: lo que ocurre solo, cuándo, y quién lo ve o interviene.
 *
 * Cada flujo se presenta como una frase completa: «Cuando ocurre X, el
 * sistema hace Y; lo ve Z y actúa W». Los flujos se agrupan por momento de la
 * atención (antes, el día, después, medicación, pagos, mensajes) para que se
 * lean en el orden en que le pasan al paciente.
 *
 * Apagar o encender pide un motivo: queda en la auditoría y en el historial de
 * la configuración. Los obligatorios no tienen interruptor y dicen por qué.
 */
import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { IconoComponent } from '../../compartido/icono.component';
import { OperacionesService } from '../../nucleo/servicios/operaciones.service';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';

export interface Automatizacion {
  readonly codigo: string;
  readonly nombre: string;
  readonly fase: string;
  readonly disparador: string;
  readonly accion: string;
  readonly canal: string;
  readonly quien_ve: readonly string[];
  readonly quien_interviene: readonly string[];
  readonly obligatorio: boolean;
  readonly nota: string | null;
  readonly activo: boolean;
  readonly ejecuciones_30_dias: number;
}

const FASES: readonly { clave: string; titulo: string; ayuda: string }[] = [
  { clave: 'ANTES_DE_LA_CITA', titulo: 'Antes de la cita', ayuda: 'Confirmar, recordar y llenar huecos.' },
  { clave: 'DIA_DE_LA_CITA', titulo: 'El día de la cita', ayuda: 'Llegada, sala de espera y agenda del profesional.' },
  { clave: 'DESPUES_DE_LA_CITA', titulo: 'Después de la consulta', ayuda: 'Indicaciones y seguimiento del tratamiento.' },
  { clave: 'MEDICACION', titulo: 'Medicación', ayuda: 'Alarmas de toma y alertas al equipo.' },
  { clave: 'PAGOS', titulo: 'Pagos', ayuda: 'Comprobantes y validación.' },
  { clave: 'MENSAJES', titulo: 'Mensajes', ayuda: 'Derivación a personas y campañas.' },
];

@Component({
  selector: 'app-automatizaciones',
  standalone: true,
  imports: [FormsModule, VentanaFlotanteComponent, IconoComponent],
  template: `
    <header class="encabezado">
      <div class="encabezado__contenido">
        <p class="ceja"><app-icono nombre="automatizaciones" [tamano]="16" /> ADMINISTRACIÓN</p>
        <h1>Automatizaciones</h1>
        <p class="encabezado__sub">
          Lo que la plataforma hace sola en cada momento de la atención, y quién lo ve o interviene.
          Ningún mensaje automático incluye diagnóstico, medicamento ni motivo de consulta.
        </p>
      </div>
      <img class="encabezado__ilustracion" src="/images/automatizaciones-flujo-clinica.svg" alt="" aria-hidden="true" width="640" height="400" fetchpriority="low" />
    </header>

    @if (error()) { <p class="aviso-error" role="alert">{{ error() }}</p> }
    @if (aviso()) { <p class="exito" role="status">{{ aviso() }}</p> }

    @if (cargando()) {
      <p role="status" class="vacio">Cargando automatizaciones…</p>
    }

    @for (grupo of grupos(); track grupo.clave) {
      <section class="fase" [attr.aria-labelledby]="'fase-' + grupo.clave">
        <div class="fase__cabecera">
          <h2 [id]="'fase-' + grupo.clave">{{ grupo.titulo }}</h2>
          <span>{{ grupo.ayuda }}</span>
        </div>
        <div class="flujos">
          @for (flujo of grupo.flujos; track flujo.codigo) {
            <article class="flujo" [class.flujo--apagado]="!flujo.activo">
              <header class="flujo__cabecera">
                <h3>{{ flujo.nombre }}</h3>
                @if (flujo.obligatorio) {
                  <span class="insignia" title="No se puede apagar">Siempre activa</span>
                } @else if (puedeCambiar) {
                  <button
                    type="button"
                    class="interruptor"
                    role="switch"
                    [attr.aria-checked]="flujo.activo"
                    [attr.aria-label]="(flujo.activo ? 'Apagar ' : 'Encender ') + flujo.nombre"
                    (click)="pedirCambio(flujo)"
                  >
                    <span class="interruptor__pista"><span class="interruptor__bola"></span></span>
                    {{ flujo.activo ? 'Activa' : 'Apagada' }}
                  </button>
                } @else {
                  <span class="insignia">{{ flujo.activo ? 'Activa' : 'Apagada' }}</span>
                }
              </header>
              <dl class="flujo__frase">
                <div><dt>Cuando</dt><dd>{{ flujo.disparador }}</dd></div>
                <div><dt>Hace</dt><dd>{{ flujo.accion }}</dd></div>
              </dl>
              <div class="flujo__personas">
                <span class="flujo__canal">{{ flujo.canal }}</span>
                <span class="etiqueta-grupo">Lo ve</span>
                @for (quien of flujo.quien_ve; track quien) { <span class="chip">{{ quien }}</span> }
                <span class="etiqueta-grupo">Interviene</span>
                @for (quien of flujo.quien_interviene; track quien) { <span class="chip chip--accion">{{ quien }}</span> }
              </div>
              @if (flujo.nota) { <p class="flujo__nota">{{ flujo.nota }}</p> }
              <p class="flujo__cifra"><strong class="numerico">{{ flujo.ejecuciones_30_dias }}</strong> envíos en los últimos 30 días</p>
            </article>
          }
        </div>
      </section>
    }

    @if (cambio(); as flujo) {
      <app-ventana-flotante
        ceja="Automatización"
        [titulo]="(flujo.activo ? 'Apagar: ' : 'Encender: ') + flujo.nombre"
        forma="centrada"
        [anchoMaximo]="520"
        (cerrar)="cambio.set(null)"
      >
        <p>
          @if (flujo.activo) {
            Mientras esté apagada, esta automatización no enviará nada. Los envíos ya programados se mantienen.
          } @else {
            Desde ahora volverá a funcionar con los próximos disparadores.
          }
        </p>
        <label class="campo">
          <span class="campo__etiqueta">Motivo del cambio</span>
          <input class="campo__control" name="motivo" [(ngModel)]="motivo" required minlength="5" maxlength="300"
                 placeholder="Ej.: la clínica confirma por llamada" />
          <span class="campo__ayuda">Queda en la auditoría junto con su nombre.</span>
        </label>
        @if (errorCambio()) { <p class="aviso-error" role="alert">{{ errorCambio() }}</p> }
        <div class="acciones acciones--final" pie>
          <button class="boton" type="button" (click)="cambio.set(null)">Cancelar</button>
          <button class="boton boton--principal" type="button" [disabled]="ocupado()" (click)="confirmarCambio(flujo)">
            {{ flujo.activo ? 'Apagar' : 'Encender' }}
          </button>
        </div>
      </app-ventana-flotante>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: grid; gap: var(--espacio-5); }
    .ceja { margin: 0; color: var(--acento); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; }
    .encabezado { position: relative; isolation: isolate; display: flex; min-height: 220px; align-items: center; overflow: hidden; padding: clamp(20px, 3vw, 36px); border: 1px solid color-mix(in srgb, var(--acento) 14%, var(--borde)); border-radius: calc(var(--radio) + 4px); background: linear-gradient(105deg, var(--superficie-elevada) 0%, color-mix(in srgb, var(--superficie-elevada) 82%, #e0f7f4) 66%, #eaf9f7 100%); box-shadow: var(--sombra-1); }
    .encabezado::before { content: ''; position: absolute; z-index: -2; inset: -65%; background: radial-gradient(ellipse at 78% 48%, rgb(42 184 171 / 20%), transparent 34%), radial-gradient(ellipse at 92% 15%, rgb(246 199 102 / 13%), transparent 28%); animation: automatizaciones-ambiente 20s ease-in-out infinite alternate; }
    .encabezado::after { content: ''; position: absolute; z-index: -1; inset: 0; opacity: .26; pointer-events: none; background-image: radial-gradient(circle, #288f87 1.25px, transparent 1.7px), linear-gradient(115deg, transparent 48.9%, rgb(42 150 142 / 34%) 49.5%, rgb(42 150 142 / 34%) 50%, transparent 50.6%); background-size: 32px 32px, 180px 120px; background-position: 0 0, 0 0; mask-image: linear-gradient(100deg, transparent 18%, #000 100%); animation: automatizaciones-red 34s linear infinite; }
    .encabezado__contenido { position: relative; z-index: 1; width: min(58%, 54rem); }
    .encabezado h1 { margin: 2px 0 8px; font-size: clamp(1.8rem, 3vw, 2.45rem); }
    .encabezado__sub { margin: 0; color: var(--texto-suave); max-width: 52rem; line-height: 1.6; }
    .encabezado__ilustracion { position: absolute; z-index: 0; top: 50%; right: 0; width: min(58%, 780px); height: 145%; transform: translateY(-50%); object-fit: contain; object-position: right center; pointer-events: none; }
    @keyframes automatizaciones-ambiente { from { transform: translate3d(-1.5%, 1%, 0) scale(.97); opacity: .65; } to { transform: translate3d(1.5%, -1%, 0) scale(1.04); opacity: 1; } }
    @keyframes automatizaciones-red { from { background-position: 0 0, 0 0; } to { background-position: 96px 64px, 180px 120px; } }
    .vacio { color: var(--texto-suave); }
    .fase__cabecera { display: flex; align-items: baseline; gap: var(--espacio-3); flex-wrap: wrap; margin-bottom: var(--espacio-3); }
    .fase__cabecera h2 { margin: 0; font-size: 1.1rem; }
    .fase__cabecera span { color: var(--texto-suave); font-size: 0.88rem; }
    .flujos { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--espacio-3); }
    .flujo { display: grid; gap: var(--espacio-2); align-content: start; padding: var(--espacio-4);
      border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie-elevada); box-shadow: var(--sombra-1); }
    .flujo--apagado { background: var(--superficie); }
    .flujo--apagado .flujo__frase, .flujo--apagado .flujo__personas { opacity: 0.6; }
    .flujo__cabecera { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--espacio-3); }
    .flujo__cabecera h3 { margin: 0; font-size: 1rem; }
    .flujo__frase { margin: 0; display: grid; gap: var(--espacio-1); }
    .flujo__frase div { display: grid; grid-template-columns: 4.5rem 1fr; gap: var(--espacio-2); }
    .flujo__frase dt { color: var(--texto-tenue); font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding-top: 2px; }
    .flujo__frase dd { margin: 0; font-size: 0.9rem; }
    .flujo__personas { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
    .flujo__canal { padding: 2px 8px; border-radius: 6px; background: var(--superficie-hundida); font-size: 0.75rem; font-weight: 700; margin-right: var(--espacio-2); }
    .etiqueta-grupo { font-size: 0.72rem; color: var(--texto-tenue); font-weight: 700; margin-left: 4px; }
    .chip { padding: 2px 8px; border-radius: 999px; background: var(--acento-suave); color: var(--acento-fuerte); font-size: 0.75rem; font-weight: 600; }
    .chip--accion { background: color-mix(in srgb, var(--exito) 14%, transparent); color: var(--exito); }
    .flujo__nota { margin: 0; color: var(--texto-suave); font-size: 0.82rem; }
    .flujo__cifra { margin: 0; color: var(--texto-suave); font-size: 0.8rem; }
    .insignia { padding: 2px 8px; border-radius: 999px; background: var(--superficie-hundida); color: var(--texto-suave); font-size: 0.72rem; font-weight: 700; white-space: nowrap; }
    .interruptor { display: inline-flex; align-items: center; gap: 6px; border: 0; background: transparent; color: var(--texto-suave); font-size: 0.8rem; font-weight: 700; cursor: pointer; white-space: nowrap; }
    .interruptor:focus-visible { outline: 3px solid var(--acento); outline-offset: 2px; border-radius: 999px; }
    .interruptor__pista { position: relative; width: 36px; height: 20px; border-radius: 999px; background: var(--borde-fuerte); transition: background 140ms; }
    .interruptor__bola { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform 140ms; box-shadow: 0 1px 2px rgb(0 0 0 / 25%); }
    .interruptor[aria-checked='true'] { color: var(--exito); }
    .interruptor[aria-checked='true'] .interruptor__pista { background: var(--exito); }
    .interruptor[aria-checked='true'] .interruptor__bola { transform: translateX(16px); }
    @media (max-width: 760px) { .encabezado { min-height: 190px; align-items: flex-start; padding-bottom: 100px; } .encabezado__contenido { width: 100%; } .encabezado__ilustracion { top: auto; bottom: -50px; right: -10px; width: 76%; height: 155px; transform: none; opacity: .76; } }
    @media (max-width: 600px) { .flujos { grid-template-columns: 1fr; } .encabezado { padding-bottom: 76px; } .encabezado__ilustracion { bottom: -58px; width: 86%; height: 142px; opacity: .58; } }
    @media (prefers-reduced-motion: reduce) { .encabezado::before, .encabezado::after { animation: none; } }
  `,
})
export class AutomatizacionesComponent {
  private readonly api = inject(OperacionesService);
  protected readonly puedeCambiar = inject(SesionService).tienePermiso(PERMISOS.configuracionEscribir);

  protected readonly flujos = signal<readonly Automatizacion[]>([]);
  protected readonly cargando = signal(true);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly errorCambio = signal('');
  protected readonly cambio = signal<Automatizacion | null>(null);
  protected motivo = '';

  protected readonly grupos = computed(() =>
    FASES.map((fase) => ({ ...fase, flujos: this.flujos().filter((f) => f.fase === fase.clave) })).filter(
      (grupo) => grupo.flujos.length > 0,
    ),
  );

  constructor() {
    this.api.leer<Automatizacion[]>('/automatizaciones').subscribe({
      next: (lista) => {
        this.flujos.set(lista);
        this.cargando.set(false);
      },
      error: (fallo: FalloApi) => {
        this.error.set(fallo.message);
        this.cargando.set(false);
      },
    });
  }

  protected pedirCambio(flujo: Automatizacion): void {
    this.motivo = '';
    this.errorCambio.set('');
    this.cambio.set(flujo);
  }

  protected confirmarCambio(flujo: Automatizacion): void {
    if (this.motivo.trim().length < 5) {
      this.errorCambio.set('Escriba el motivo (mínimo 5 caracteres).');
      return;
    }
    this.ocupado.set(true);
    this.api
      .guardar<Automatizacion>(
        `/automatizaciones/${flujo.codigo}`,
        { activo: !flujo.activo, motivo: this.motivo.trim() },
        crypto.randomUUID(),
        true,
      )
      .subscribe({
        next: (actualizada) => {
          this.ocupado.set(false);
          this.flujos.update((lista) => lista.map((f) => (f.codigo === actualizada.codigo ? actualizada : f)));
          this.cambio.set(null);
          this.aviso.set(`«${actualizada.nombre}» ${actualizada.activo ? 'encendida' : 'apagada'}.`);
        },
        error: (fallo: FalloApi) => {
          this.ocupado.set(false);
          this.errorCambio.set(fallo.message);
        },
      });
  }
}
