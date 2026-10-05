/**
 * Panel: el arranque del turno.
 *
 * Qué estaba mal
 * --------------
 * La versión anterior abría con cuatro cifras —«citas del periodo: 128»— y una
 * barra por estado. Todo cierto y nada accionable: a las ocho de la mañana, con
 * la sala llenándose, nadie necesita un recuento del mes. Necesita saber **qué
 * se rompe hoy si nadie lo toca**.
 *
 * El orden de la pantalla es el orden de utilidad:
 *
 * 1. **La cola de trabajo.** Lo que tiene plazo: un turno bloqueado que
 *    caduca, una oferta de lista de espera que nadie comunicó, citas sin
 *    confirmar. Es el mismo componente que ocupa el panel derecho de la
 *    agenda, a propósito: la misma pregunta debe dar la misma respuesta en las
 *    dos pantallas.
 * 2. **La carga de hoy por profesional.** Minutos de consulta comprometidos,
 *    no número de citas: una primera consulta y un control no cargan igual.
 * 3. **Las cifras del periodo**, al final, como contexto. La inasistencia va
 *    con su variación respecto al periodo anterior, porque un 8 % no dice nada
 *    sin saber si sube o baja.
 *
 * Lo que esta pantalla NO afirma
 * ------------------------------
 * No hay porcentaje de ocupación de la jornada. Calcularlo exige el horario de
 * atención de cada profesional, y hoy ninguna API lo expone. Un porcentaje con
 * un denominador inventado es peor que no tenerlo: se toman decisiones de
 * contratación con él.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ColaTrabajoComponent } from '../../compartido/cola-trabajo.component';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { ApiService } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import {
  OperacionesService,
  type EntradaEspera,
  type Pagina,
  type ResumenPanel,
} from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Cita, Profesional } from '../../nucleo/modelos/dominio';
import { derivarPendientes, type TareaPendiente } from '../../nucleo/utilidades/pendientes';
import { cargaPorProfesional, duracionLegible } from '../../nucleo/utilidades/secuencia-dia';
import { hoyEnZona, rangoDelDia, sumarDias } from '../../nucleo/utilidades/fechas';

/** Estados en el orden en que interesan, con su tono semántico. */
const ESTADOS: readonly { codigo: string; etiqueta: string; clase: string }[] = [
  { codigo: 'CONFIRMED', etiqueta: 'Confirmadas', clase: 'exito' },
  { codigo: 'RESCHEDULED', etiqueta: 'Reprogramadas', clase: 'info' },
  { codigo: 'COMPLETED', etiqueta: 'Atendidas', clase: 'neutra' },
  { codigo: 'PENDING', etiqueta: 'Pendientes', clase: 'neutra' },
  { codigo: 'HELD', etiqueta: 'Bloqueadas', clase: 'aviso' },
  { codigo: 'CANCELLED', etiqueta: 'Canceladas', clase: 'peligro' },
  { codigo: 'NO_SHOW', etiqueta: 'No asistió', clase: 'peligro' },
];

const DIAS_POR_PERIODO: Record<string, number> = { hoy: 1, '7': 7, '30': 30 };

@Component({
  selector: 'app-panel',
  standalone: true,
  imports: [FormsModule, RouterLink, ColaTrabajoComponent],
  template: `
    <div class="cabecera-pagina">
      <div>
        <p class="ceja">GESTIÓN CLÍNICA</p>
        <h1>Panel de seguimiento</h1>
        <p class="panel__contexto">{{ hoyLegible() }} · horario de {{ zona() }}</p>
      </div>
      <a class="boton boton--principal" routerLink="/agenda">Abrir agenda</a>
    </div>

    @if (error()) {
      <p class="aviso-error" role="alert">{{ error() }}</p>
    }

    <!-- ============ 1. Lo que tiene plazo ============ -->
    @if (sesion.tienePermiso(PERMISOS.agendaLeer)) {
      <section class="bloque">
        <div class="bloque__cabecera">
          <h2>Lo primero</h2>
          <span class="bloque__linea" aria-hidden="true"></span>
          <span class="bloque__cuenta numerico">
            {{ pendientes().length }} tarea(s) con plazo
          </span>
        </div>
        @if (cargandoHoy()) {
          <p role="status">Consultando el día…</p>
        } @else {
          <app-cola-trabajo
            [tareas]="pendientes()"
            [rejilla]="true"
            (actuar)="irALaAgenda()"
            (localizar)="irALaAgenda()"
          />
        }
      </section>

      <!-- ============ 2. La carga de hoy ============ -->
      <section class="bloque">
        <div class="bloque__cabecera">
          <h2>Carga de hoy</h2>
          <span class="bloque__linea" aria-hidden="true"></span>
        </div>
        <div class="tarjeta">
          <p class="campo__ayuda carga__nota">
            Minutos de consulta comprometidos, no número de citas: una primera consulta ocupa
            el doble que un control. No se muestra porcentaje de ocupación porque haría falta
            el horario de cada profesional, que todavía no expone ninguna API.
          </p>
          @if (carga().length === 0) {
            <p class="carga__vacio">Sin citas hoy en su ámbito.</p>
          } @else {
            <ul class="carga">
              @for (fila of carga(); track fila.id) {
                <li class="carga__fila">
                  <span class="carga__nombre">{{ fila.nombre }}</span>
                  <span class="carga__pista" [attr.title]="fila.nombre + ': ' + fila.legible">
                    <span class="carga__barra" [style.width.%]="fila.porcentaje"></span>
                  </span>
                  <span class="carga__valor numerico">{{ fila.legible }}</span>
                </li>
              }
            </ul>
          }
        </div>
      </section>
    }

    <!-- ============ 3. Las cifras, como contexto ============ -->
    @if (sesion.tienePermiso(PERMISOS.metricasLeer)) {
      <section class="bloque">
        <div class="bloque__cabecera">
          <h2>Cifras del periodo</h2>
          <span class="bloque__linea" aria-hidden="true"></span>
          <div class="periodos" role="group" aria-label="Periodo">
            @for (opcion of opciones; track opcion.clave) {
              <button
                type="button"
                class="periodos__boton"
                [class.periodos__boton--activo]="periodo() === opcion.clave"
                [attr.aria-pressed]="periodo() === opcion.clave"
                (click)="cambiarPeriodo(opcion.clave)"
              >
                {{ opcion.etiqueta }}
              </button>
            }
          </div>
        </div>

        @if (cargandoResumen()) {
          <p role="status">Consultando actividad…</p>
        } @else if (resumen()) {
          @let r = resumen()!;
          <div class="rejilla">
            <article class="tarjeta inasistencia">
              <p class="inasistencia__titulo">Inasistencia</p>
              <p class="inasistencia__valor">
                <strong class="numerico">{{ inasistencia().valor }}</strong>
                @if (inasistencia().delta !== null) {
                  <span
                    class="insignia"
                    [class.insignia--peligro]="inasistencia().sube"
                    [class.insignia--exito]="!inasistencia().sube"
                  >
                    {{ inasistencia().sube ? '▲' : '▼' }} {{ inasistencia().delta }} pt
                  </span>
                }
              </p>
              <p class="inasistencia__lectura">{{ inasistencia().lectura }}</p>
            </article>

            <article class="tarjeta">
              <p class="cifra__titulo">Citas del periodo</p>
              <strong class="cifra numerico">{{ r.total_citas }}</strong>
              <p class="campo__ayuda">{{ r.pacientes }} paciente(s) distintos</p>
            </article>

            <article class="tarjeta">
              <p class="cifra__titulo">Sala de espera</p>
              <strong class="cifra numerico">{{ r.espera.personas_en_espera }}</strong>
              <p class="campo__ayuda">paciente(s) esperando en el periodo</p>
              <p class="campo__ayuda">
                Espera media hasta iniciar:
                @if (r.espera.promedio_minutos === null) {
                  sin atenciones iniciadas
                } @else {
                  {{ r.espera.promedio_minutos }} min
                }
              </p>
              @if (r.espera.espera_mayor_15_minutos > 0) {
                <p class="carga__demora" role="status">
                  {{ r.espera.espera_mayor_15_minutos }} supera 15 minutos
                </p>
              }
            </article>

            @if (r.pagos; as pagos) {
              <article class="tarjeta">
                <p class="cifra__titulo">Pagos de esas citas</p>
                <ul class="pagos">
                  @for (par of pagosLegibles(pagos); track par.estado) {
                    <li>
                      <span>{{ par.estado }}</span>
                      <span class="numerico">{{ par.importe }}</span>
                    </li>
                  }
                </ul>
              </article>
            }
          </div>

          <div class="tarjeta estados">
            <p class="cifra__titulo">Reparto por estado</p>
            @for (estado of estadosConDatos(); track estado.codigo) {
              <div class="estados__fila">
                <span class="insignia" [class]="'insignia--' + estado.clase">
                  {{ estado.etiqueta }}
                </span>
                <span class="estados__pista">
                  <span
                    class="estados__barra"
                    [class]="'estados__barra--' + estado.clase"
                    [style.width.%]="estado.porcentaje"
                  ></span>
                </span>
                <span class="numerico estados__valor">{{ estado.cantidad }}</span>
              </div>
            }
          </div>
        }
      </section>
    } @else {
      <div class="tarjeta">
        <h2>Su espacio de trabajo</h2>
        <p>Use el menú para acceder a las gestiones habilitadas para su rol.</p>
      </div>
    }

    @if (sesion.tienePermiso(PERMISOS.metricasLeer)) {
      <section class="bloque seguimiento" aria-labelledby="seguimiento-inteligente">
        <div class="bloque__cabecera">
          <h2 id="seguimiento-inteligente">Seguimiento inteligente</h2>
          <span class="bloque__linea" aria-hidden="true"></span>
          <span class="seguimiento__metodo">Señales basadas en actividad real</span>
          @if (sesion.tienePermiso(PERMISOS.configuracionEscribir)) {
            <button class="boton boton--pequeno" type="button" (click)="generarAnalisisIA()" [disabled]="analizandoIA()">
              {{ analizandoIA() ? 'Analizando…' : 'Analizar con IA' }}
            </button>
          }
        </div>
        @if (errorIA()) { <p class="aviso-error" role="alert">{{ errorIA() }}</p> }
        @if (analisisIA()) { <article class="tarjeta analisis-ia"><p class="ceja">ANÁLISIS OPERATIVO · {{ periodo() === 'hoy' ? 'HOY' : periodo() + ' DÍAS' }}</p><p>{{ analisisIA() }}</p></article> }
        <div class="seguimiento__rejilla">
          @for (senal of senalesSeguimiento(); track senal.titulo) {
            <article class="tarjeta seguimiento__senal" [class.seguimiento__senal--alerta]="senal.alerta">
              <span class="seguimiento__punto" aria-hidden="true"></span>
              <div><h3>{{ senal.titulo }}</h3><p>{{ senal.detalle }}</p></div>
            </article>
          }
        </div>
        <p class="seguimiento__nota">Estas señales usan reglas transparentes sobre agenda y cobros; no generan diagnósticos ni predicciones clínicas.</p>
      </section>
    }
  `,
  styles: `
    .cabecera-pagina {
      position: relative;
      min-height: 138px;
      padding: var(--espacio-5) var(--espacio-6);
      overflow: hidden;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background-image:
        linear-gradient(90deg, rgb(255 255 255 / 96%) 0%, rgb(255 255 255 / 87%) 48%, rgb(255 255 255 / 22%) 100%),
        url('/images/inicio-coordinacion.png');
      background-position: center, center 58%;
      background-size: cover;
    }

    .cabecera-pagina > div,
    .cabecera-pagina > a {
      position: relative;
      z-index: 1;
    }

    @media (max-width: 600px) {
      .cabecera-pagina {
        min-height: 132px;
        padding: var(--espacio-4);
        background-position: center, 68% center;
      }
    }

    .panel__contexto {
      margin: 2px 0 0;
      color: var(--texto-suave);
      font-size: 0.9rem;
    }

    .bloque {
      margin-top: var(--espacio-5);
    }

    .seguimiento__metodo { color:var(--texto-tenue); font-size:.78rem; }
    .seguimiento__rejilla { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:var(--espacio-3); }
    .seguimiento__senal { display:flex; align-items:flex-start; gap:var(--espacio-3); padding:var(--espacio-4); }
    .seguimiento__senal h3 { margin:0; font-size:.98rem; }
    .seguimiento__senal p { margin:var(--espacio-1) 0 0; color:var(--texto-suave); font-size:.9rem; }
    .seguimiento__punto { flex:0 0 10px; width:10px; height:10px; margin-top:5px; border-radius:50%; background:var(--exito); }
    .seguimiento__senal--alerta .seguimiento__punto { background:var(--aviso); }
    .seguimiento__nota { margin:var(--espacio-2) 0 0; color:var(--texto-tenue); font-size:.8rem; }
    .analisis-ia { margin:0 0 var(--espacio-3); padding:var(--espacio-4); border-color:var(--acento); white-space:pre-line; }
    .analisis-ia p:last-child { margin-bottom:0; }
    @media (max-width:700px) { .seguimiento__rejilla { grid-template-columns:1fr; } }

    .bloque__cabecera {
      display: flex;
      align-items: center;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-3);

      h2 {
        margin: 0;
        font-size: 0.85rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: var(--texto-suave);
      }
    }

    .bloque__linea {
      flex: 1 1 auto;
      height: 1px;
      background: var(--borde);
    }

    .bloque__cuenta {
      color: var(--texto-tenue);
      font-size: 0.85rem;
    }

    /* --- Selector de periodo --- */
    .periodos {
      display: flex;
      gap: var(--espacio-1);
      padding: 3px;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
    }

    .periodos__boton {
      min-height: 34px;
      padding: 0 var(--espacio-3);
      border: 0;
      border-radius: var(--radio-pequeno);
      background: transparent;
      color: var(--texto-suave);
      font-weight: 600;
      font-size: 0.9rem;
      cursor: pointer;
    }

    .periodos__boton--activo {
      background: var(--acento);
      color: var(--acento-texto);
    }

    /* --- Carga por profesional --- */
    .carga {
      list-style: none;
      margin: var(--espacio-3) 0 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
    }

    .carga__fila {
      display: grid;
      grid-template-columns: minmax(120px, 200px) minmax(0, 1fr) 76px;
      gap: var(--espacio-3);
      align-items: center;
    }

    .carga__nombre {
      font-size: 0.92rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .carga__pista {
      height: 10px;
      border-radius: 0 999px 999px 0;
      background: var(--superficie-hundida);
      overflow: hidden;
    }

    /* Un solo tono: esto mide magnitud, no identidad. Categorías distintas
       pedirían colores distintos; aquí todas las filas son lo mismo. */
    .carga__barra {
      display: block;
      height: 10px;
      border-radius: 0 4px 4px 0;
      background: var(--acento);
    }

    .carga__valor {
      text-align: right;
      font-weight: 600;
      font-size: 0.9rem;
    }

    .carga__nota,
    .carga__vacio {
      margin: 0;
    }

    .carga__demora {
      margin: var(--espacio-2) 0 0;
      color: var(--aviso);
      font-weight: 650;
    }

    /* --- Cifras --- */
    .cifra {
      display: block;
      font-size: 2.1rem;
      font-weight: 650;
      letter-spacing: -0.02em;
      line-height: 1.1;
    }

    .cifra__titulo,
    .inasistencia__titulo {
      margin: 0 0 var(--espacio-1);
      font-size: 0.85rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--texto-suave);
    }

    .inasistencia__valor {
      display: flex;
      align-items: center;
      gap: var(--espacio-3);
      margin: 0;

      strong {
        font-size: 2.1rem;
        font-weight: 650;
        letter-spacing: -0.02em;
      }
    }

    .inasistencia__lectura {
      margin: var(--espacio-2) 0 0;
      color: var(--texto-suave);
      font-size: 0.88rem;
    }

    .insignia {
      display: inline-block;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid currentcolor;
      font-size: 0.8rem;
      font-weight: 650;
      white-space: nowrap;
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

    .pagos {
      list-style: none;
      margin: 0;
      padding: 0;

      li {
        display: flex;
        justify-content: space-between;
        gap: var(--espacio-3);
        padding: var(--espacio-1) 0;
        border-bottom: 1px solid var(--superficie-hundida);
        font-size: 0.92rem;
      }
    }

    /* --- Reparto por estado --- */
    .estados {
      margin-top: var(--espacio-4);
    }

    .estados__fila {
      display: grid;
      grid-template-columns: 140px minmax(0, 1fr) 48px;
      gap: var(--espacio-3);
      align-items: center;
      padding: var(--espacio-1) 0;
    }

    .estados__pista {
      height: 8px;
      border-radius: 0 999px 999px 0;
      background: var(--superficie-hundida);
      overflow: hidden;
    }

    .estados__barra {
      display: block;
      height: 8px;
      border-radius: 0 4px 4px 0;
      background: var(--texto-tenue);
    }

    .estados__barra--exito {
      background: var(--exito);
    }
    .estados__barra--aviso {
      background: var(--aviso);
    }
    .estados__barra--peligro {
      background: var(--peligro);
    }
    .estados__barra--info {
      background: var(--info);
    }

    .estados__valor {
      text-align: right;
      font-weight: 600;
      font-size: 0.9rem;
    }
  `,
})
export class PanelComponent {
  private readonly operaciones = inject(OperacionesService);
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  protected readonly sesion = inject(SesionService);
  protected readonly PERMISOS = PERMISOS;

  protected readonly opciones = [
    { clave: 'hoy', etiqueta: 'Hoy' },
    { clave: '7', etiqueta: '7 días' },
    { clave: '30', etiqueta: '30 días' },
  ] as const;

  protected readonly periodo = signal<string>('hoy');
  protected readonly zona = signal('America/Guayaquil');

  protected readonly resumen = signal<ResumenPanel | null>(null);
  /** El mismo resumen del periodo anterior, solo para la variación. */
  protected readonly anterior = signal<ResumenPanel | null>(null);
  protected readonly citasHoy = signal<readonly Cita[]>([]);
  protected readonly ofertasSinAvisar = signal<readonly EntradaEspera[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);

  protected readonly cargandoResumen = signal(false);
  protected readonly cargandoHoy = signal(false);
  protected readonly error = signal('');
  protected readonly analisisIA = signal('');
  protected readonly errorIA = signal('');
  protected readonly analizandoIA = signal(false);

  protected readonly hoyLegible = computed(() =>
    new Intl.DateTimeFormat('es-EC', {
      timeZone: this.zona(),
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    }).format(new Date()),
  );

  protected readonly pendientes = computed<readonly TareaPendiente[]>(() =>
    derivarPendientes({
      citas: this.citasHoy(),
      ofertasSinAvisar: this.ofertasSinAvisar(),
      ahora: new Date(),
      nombrePaciente: (id) => `Paciente ${id.slice(0, 8)}`,
    }),
  );

  /** Carga de hoy, de más ocupado a menos. */
  protected readonly carga = computed(() => {
    const minutos = cargaPorProfesional(this.citasHoy());
    const mayor = Math.max(1, ...minutos.values());
    return [...minutos.entries()]
      .map(([id, valor]) => ({
        id,
        nombre: this.nombreProfesional(id),
        minutos: valor,
        legible: duracionLegible(valor),
        porcentaje: Math.round((valor / mayor) * 100),
      }))
      .sort((a, b) => b.minutos - a.minutos);
  });

  /**
   * Inasistencia del periodo, con su variación en puntos.
   *
   * Un 8 % no dice nada sin saber si sube o baja; la variación exige el
   * periodo anterior, así que se piden los dos.
   */
  protected readonly inasistencia = computed(() => {
    const actual = this.resumen();
    if (!actual || actual.total_citas === 0) {
      return { valor: '—', delta: null as string | null, sube: false, lectura: 'Sin citas en el periodo.' };
    }
    const tasa = ((actual.citas['NO_SHOW'] ?? 0) / actual.total_citas) * 100;
    const previo = this.anterior();
    if (!previo || previo.total_citas === 0) {
      return {
        valor: `${tasa.toFixed(1)} %`,
        delta: null,
        sube: false,
        lectura: 'Sin datos del periodo anterior para comparar.',
      };
    }
    const tasaPrevia = ((previo.citas['NO_SHOW'] ?? 0) / previo.total_citas) * 100;
    const diferencia = tasa - tasaPrevia;
    const sube = diferencia > 0;
    return {
      valor: `${tasa.toFixed(1)} %`,
      delta: Math.abs(diferencia).toFixed(1),
      sube,
      lectura: sube
        ? 'Sube respecto al periodo anterior. Las citas sin confirmar son el primer sitio donde mirar.'
        : 'Baja respecto al periodo anterior.',
    };
  });

  /** Estados con al menos una cita, escalados contra el mayor. */
  protected readonly estadosConDatos = computed(() => {
    const datos = this.resumen();
    if (!datos) {
      return [];
    }
    const presentes = ESTADOS.map((estado) => ({
      ...estado,
      cantidad: datos.citas[estado.codigo] ?? 0,
    })).filter((estado) => estado.cantidad > 0);
    const mayor = Math.max(1, ...presentes.map((estado) => estado.cantidad));
    return presentes.map((estado) => ({
      ...estado,
      porcentaje: Math.round((estado.cantidad / mayor) * 100),
    }));
  });

  protected readonly senalesSeguimiento = computed(() => {
    const resumen = this.resumen();
    const abiertas = this.pendientes().length;
    const inasistencia = resumen?.total_citas
      ? ((resumen.citas['NO_SHOW'] ?? 0) / resumen.total_citas) * 100
      : null;
    const senales: { titulo: string; detalle: string; alerta: boolean }[] = [];
    senales.push(abiertas > 0
      ? { titulo: `${abiertas} tarea(s) requieren seguimiento`, detalle: 'Hay citas por confirmar, turnos que vencen u ofertas de espera sin comunicar en la jornada.', alerta: true }
      : { titulo: 'La cola de hoy está al día', detalle: 'No hay tareas operativas urgentes en la agenda consultada.', alerta: false });
    if (inasistencia !== null) {
      senales.push(inasistencia >= 10
        ? { titulo: 'Inasistencia sobre 10 %', detalle: `La tasa del periodo es ${inasistencia.toFixed(1)} %. Revise confirmaciones y los periodos comparables.`, alerta: true }
        : { titulo: 'Inasistencia bajo control', detalle: `La tasa del periodo es ${inasistencia.toFixed(1)} % sobre ${resumen!.total_citas} citas.`, alerta: false });
    } else {
      senales.push({ titulo: 'Aún no hay base para comparar', detalle: 'El periodo no contiene citas para calcular indicadores de asistencia.', alerta: false });
    }
    const esperando = resumen?.espera;
    if (esperando && esperando.personas_en_espera > 0) {
      senales.push({
        titulo: `${esperando.personas_en_espera} paciente(s) en sala de espera`,
        detalle: esperando.espera_mayor_15_minutos > 0
          ? `${esperando.espera_mayor_15_minutos} superan 15 minutos; revise la atención pendiente.`
          : 'La espera registrada todavía no supera 15 minutos.',
        alerta: esperando.espera_mayor_15_minutos > 0,
      });
    }
    const pendientesPago = Object.entries(resumen?.pagos ?? {}).find(([estado]) => ['PENDING', 'UNDER_REVIEW', 'PROOF_RECEIVED'].includes(estado));
    if (pendientesPago) {
      senales.push({ titulo: 'Cobros en seguimiento', detalle: `El estado ${pendientesPago[0]} suma ${pendientesPago[1]}.`, alerta: true });
    }
    return senales;
  });

  constructor() {
    this.catalogo.profesionales().subscribe({
      next: (lista) => this.profesionales.set(lista),
      error: () => this.profesionales.set([]),
    });
    this.cargar();
  }

  protected cambiarPeriodo(clave: string): void {
    this.periodo.set(clave);
    this.analisisIA.set('');
    this.cargarResumen();
  }

  protected generarAnalisisIA(): void {
    const dias = DIAS_POR_PERIODO[this.periodo()] ?? 1;
    const hoy = hoyEnZona(this.zona());
    const inicio = sumarDias(hoy, -(dias - 1));
    const desde = rangoDelDia(inicio, this.zona()).desde;
    const hasta = rangoDelDia(hoy, this.zona()).hasta;
    this.analizandoIA.set(true);
    this.errorIA.set('');
    this.analisisIA.set('');
    this.operaciones.analizar<{ analisis: string }>('/dashboard/analisis-ia', { desde, hasta }).subscribe({
      next: (resultado) => { this.analisisIA.set(resultado.analisis); this.analizandoIA.set(false); },
      error: (fallo: unknown) => { this.errorIA.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo generar el análisis.'); this.analizandoIA.set(false); },
    });
  }

  protected irALaAgenda(): void {
    // Las acciones sobre una cita viven en la agenda, que es donde se ve el
    // contexto del día. Este panel señala; no ejecuta.
    window.location.href = '/agenda';
  }

  private cargar(): void {
    this.cargarResumen();
    this.cargarHoy();
  }

  private cargarResumen(): void {
    if (!this.sesion.tienePermiso(PERMISOS.metricasLeer)) {
      return;
    }
    this.cargandoResumen.set(true);
    this.error.set('');

    const dias = DIAS_POR_PERIODO[this.periodo()] ?? 1;
    const hoy = hoyEnZona(this.zona());
    const inicio = sumarDias(hoy, -(dias - 1));
    const previoFin = sumarDias(inicio, -1);
    const previoInicio = sumarDias(previoFin, -(dias - 1));

    const actual = rangoDelDia(inicio, this.zona());
    const finActual = rangoDelDia(hoy, this.zona());
    const previo = rangoDelDia(previoInicio, this.zona());
    const finPrevio = rangoDelDia(previoFin, this.zona());

    this.operaciones
      .leer<ResumenPanel>('/dashboard/', { desde: actual.desde, hasta: finActual.hasta })
      .subscribe({
        next: (datos) => {
          this.resumen.set(datos);
          this.cargandoResumen.set(false);
        },
        error: (fallo: FalloApi) => {
          this.error.set(fallo.message);
          this.cargandoResumen.set(false);
        },
      });

    this.operaciones
      .leer<ResumenPanel>('/dashboard/', { desde: previo.desde, hasta: finPrevio.hasta })
      .subscribe({
        // Sin el periodo anterior la pantalla sigue sirviendo: se muestra la
        // tasa sin variación en lugar de un error.
        next: (datos) => this.anterior.set(datos),
        error: () => this.anterior.set(null),
      });
  }

  private cargarHoy(): void {
    if (!this.sesion.tienePermiso(PERMISOS.agendaLeer)) {
      return;
    }
    this.cargandoHoy.set(true);
    const { desde, hasta } = rangoDelDia(hoyEnZona(this.zona()), this.zona());

    this.api.citas({ desde, hasta, limite: 200 }).subscribe({
      next: (pagina) => {
        this.citasHoy.set(pagina.elementos);
        this.cargandoHoy.set(false);
      },
      error: () => this.cargandoHoy.set(false),
    });

    if (this.sesion.tienePermiso(PERMISOS.listaEsperaGestionar)) {
      this.operaciones
        .leer<Pagina<EntradaEspera>>('/lista-espera/', { limite: 25, solo_sin_avisar: true })
        .subscribe({
          next: (pagina) => this.ofertasSinAvisar.set(pagina.elementos),
          error: () => this.ofertasSinAvisar.set([]),
        });
    }
  }

  protected nombreProfesional(id: string): string {
    const profesional = this.profesionales().find((p) => p.id === id);
    return profesional ? `${profesional.nombre} ${profesional.apellido}` : `Profesional ${id.slice(0, 8)}`;
  }

  protected pagosLegibles(pagos: Record<string, string>): { estado: string; importe: string }[] {
    return Object.entries(pagos).map(([estado, importe]) => ({ estado, importe }));
  }
}
