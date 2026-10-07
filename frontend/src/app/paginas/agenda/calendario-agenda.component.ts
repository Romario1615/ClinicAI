/**
 * Agenda como calendario: día, semana y mes, con colores por estado.
 *
 * Qué resuelve
 * ------------
 * La lista del día responde «qué viene ahora», pero no «cómo está la semana»
 * ni «dónde hay hueco el jueves». El calendario lo responde de un vistazo:
 * cada cita es un bloque del color de su estado, con su leyenda a la vista.
 *
 * * **Día**: una columna por profesional, para ver a toda la sede a la vez.
 *   En la columna del profesional elegido aparecen los tramos libres; un
 *   clic en ellos abre la reserva, igual que en la lista.
 * * **Semana**: lunes a domingo del profesional elegido.
 * * **Mes**: cuántas citas tiene cada día; un clic abre ese día.
 *
 * Es un componente de presentación: no pide nada al API. Recibe las citas y
 * los huecos ya cargados y avisa con eventos de lo que se eligió; la agenda
 * decide qué hacer (abrir el panel de la cita, reservar, cambiar de día).
 *
 * Todas las horas se calculan en la zona de la sede, nunca en la del equipo.
 *
 * Cómo ocupa la pantalla
 * ----------------------
 * En escritorio llena el alto que le da la agenda y desplaza dentro: las
 * horas (y, si no caben, los días o los profesionales) se mueven en su marco
 * con la cabecera de columnas y la columna de horas pegadas. La leyenda solo
 * enumera los estados que hay en pantalla: nueve muestras para dos citas eran
 * dos líneas de alto robadas a las horas.
 */
import {
  Component,
  DestroyRef,
  ElementRef,
  afterRenderEffect,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
  ChangeDetectionStrategy,
} from '@angular/core';

import type { Cita, Profesional } from '../../nucleo/modelos/dominio';
import type { FilaDia } from '../../nucleo/utilidades/secuencia-dia';
import { hoyEnZona, sumarDias } from '../../nucleo/utilidades/fechas';
import { FotoPersonaComponent } from '../../compartido/foto-persona.component';

export type VistaCalendario = 'dia' | 'semana' | 'mes';

/** Estado visual: el de la cita, afinado con la llegada y la atención. */
export type EstadoVisual =
  | 'PENDING'
  | 'HELD'
  | 'CONFIRMED'
  | 'RESCHEDULED'
  | 'EN_SALA'
  | 'EN_ATENCION'
  | 'COMPLETED'
  | 'NO_SHOW'
  | 'CANCELLED';

export const LEYENDA: readonly { estado: EstadoVisual; etiqueta: string }[] = [
  { estado: 'PENDING', etiqueta: 'Pendiente' },
  { estado: 'HELD', etiqueta: 'Apartada sin confirmar' },
  { estado: 'CONFIRMED', etiqueta: 'Confirmada' },
  { estado: 'RESCHEDULED', etiqueta: 'Reprogramada' },
  { estado: 'EN_SALA', etiqueta: 'En sala de espera' },
  { estado: 'EN_ATENCION', etiqueta: 'En atención' },
  { estado: 'COMPLETED', etiqueta: 'Atendida' },
  { estado: 'NO_SHOW', etiqueta: 'No asistió' },
  { estado: 'CANCELLED', etiqueta: 'Cancelada' },
];

const ETIQUETA = new Map(LEYENDA.map((item) => [item.estado, item.etiqueta]));

export function estadoVisual(cita: Cita): EstadoVisual {
  if (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED' || cita.estado === 'PENDING') {
    if (cita.atencion_iniciada_en) return 'EN_ATENCION';
    if (cita.llegada_en) return 'EN_SALA';
  }
  return cita.estado as EstadoVisual;
}

/** Fecha local (`AAAA-MM-DD`) y minutos desde medianoche en la zona dada. */
export function partesLocales(instanteIso: string, zona: string): { fecha: string; minutos: number } {
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: zona,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(new Date(instanteIso))
      .map((parte) => [parte.type, parte.value]),
  );
  const hora = partes['hour'] === '24' ? 0 : Number(partes['hour']);
  return {
    fecha: `${partes['year']}-${partes['month']}-${partes['day']}`,
    minutos: hora * 60 + Number(partes['minute']),
  };
}

/** Lunes de la semana de una fecha `AAAA-MM-DD`. */
export function lunesDe(fecha: string): string {
  const dia = new Date(`${fecha}T00:00:00Z`).getUTCDay();
  return sumarDias(fecha, -((dia + 6) % 7));
}

/** Primer y último día (exclusivo) que pinta la vista, en fechas locales. */
export function rangoVista(vista: VistaCalendario, fecha: string): { desde: string; hasta: string } {
  if (vista === 'dia') return { desde: fecha, hasta: sumarDias(fecha, 1) };
  if (vista === 'semana') {
    const lunes = lunesDe(fecha);
    return { desde: lunes, hasta: sumarDias(lunes, 7) };
  }
  const primero = `${fecha.slice(0, 8)}01`;
  const lunes = lunesDe(primero);
  return { desde: lunes, hasta: sumarDias(lunes, 42) };
}

const NOMBRES_DIA = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

/**
 * Dónde se quedó el marco de horas, por vista y fecha.
 *
 * La agenda vuelve a pintar el calendario cada vez que recarga (después de
 * confirmar, cancelar o reservar). Sin esta memoria, quien trabajaba a las
 * 17:00 volvería a ver las 07:00 tras cada acción y tendría que buscar otra
 * vez su sitio. Vive fuera del componente a propósito: el componente se
 * destruye y se crea de nuevo en cada recarga.
 */
const POSICIONES = new Map<string, number>();
const ALTO_HORA = 56;
const MINUTO = ALTO_HORA / 60;

interface Bloque {
  readonly clave: string;
  readonly cita: Cita | null;
  readonly hueco: (FilaDia & { tipo: 'hueco' }) | null;
  readonly estado: EstadoVisual | 'LIBRE';
  readonly arriba: number;
  readonly alto: number;
  readonly izquierda: number;
  readonly ancho: number;
  readonly horaTexto: string;
  readonly inicioTexto: string;
  readonly titulo: string;
  readonly detalle: string;
}

interface Columna {
  readonly clave: string;
  readonly titulo: string;
  readonly subtitulo: string;
  readonly hoy: boolean;
  readonly fecha: string;
  readonly bloques: readonly Bloque[];
}

@Component({
  selector: 'app-calendario-agenda',
  standalone: true,
  imports: [FotoPersonaComponent],
  template: `
    @if (leyendaVisible().length > 0 || (vista() === 'dia' && huecos().length)) {
      <div class="leyenda" role="group" aria-label="Leyenda de colores">
        @for (item of leyendaVisible(); track item.estado) {
          <span class="leyenda__item"><i [class]="'muestra estado--' + item.estado"></i>{{ item.etiqueta }}</span>
        }
        @if (vista() === 'dia' && huecos().length) {
          <span class="leyenda__item"><i class="muestra estado--LIBRE"></i>Libre para reservar</span>
        }
      </div>
    }

    @if (vista() === 'mes') {
      <div class="mes" role="grid" aria-label="Calendario del mes">
        <div class="mes__cabecera" role="row">
          @for (nombre of nombresDia; track nombre) {
            <span role="columnheader">{{ nombre }}</span>
          }
        </div>
        <div class="mes__rejilla" #rejillaMes>
          @for (dia of diasMes(); track dia.fecha) {
            <button
              type="button"
              role="gridcell"
              class="mes__dia"
              [class.mes__dia--fuera]="!dia.delMes"
              [class.mes__dia--hoy]="dia.hoy"
              [class.mes__dia--elegido]="dia.fecha === fecha()"
              [attr.aria-label]="dia.etiqueta"
              (click)="diaElegido.emit(dia.fecha)"
            >
              <span class="mes__cabeza">
                <span class="mes__numero numerico">{{ dia.numero }}</span>
                @if (dia.citas.length > 0 && chipsPorDia() === 0) {
                  <span class="mes__cuenta numerico">
                    {{ dia.citas.length }}<span class="mes__cuenta-texto">&nbsp;{{ dia.citas.length === 1 ? 'cita' : 'citas' }}</span>
                  </span>
                }
              </span>
              @for (cita of dia.citas.slice(0, chipsPorDia()); track cita.id) {
                <span [class]="'chip estado--' + estado(cita)">
                  <span class="numerico">{{ dia.horas.get(cita.id) }}</span> {{ etiquetaPaciente()(cita.paciente_id) }}
                </span>
              }
              @if (chipsPorDia() > 0 && dia.citas.length > chipsPorDia()) {
                <span class="mes__mas">+{{ dia.citas.length - chipsPorDia() }} más</span>
              }
            </button>
          }
        </div>
      </div>
    } @else {
      <!-- Si no hay ninguna cita ni hueco que pulsar, el marco desplazable
           necesita su propio foco para que el teclado también lo recorra. -->
      <div
        #marco
        class="tiempo"
        (scroll)="recordarPosicion()"
        [style.--columnas]="columnas().length"
        [style.--ancho-min]="vista() === 'semana' ? '84px' : '160px'"
        [attr.tabindex]="vacio() && vista() === 'dia' ? 0 : null"
        [attr.role]="vacio() && vista() === 'dia' ? 'region' : null"
        [attr.aria-label]="vacio() && vista() === 'dia' ? 'Horas del día' : null"
      >
        <div class="tiempo__esquina"></div>
        @for (col of columnas(); track col.clave) {
          <div class="tiempo__titulo" [class.tiempo__titulo--hoy]="col.hoy">
            @if (vista() === 'semana') {
              <button type="button" class="tiempo__dia" (click)="diaElegido.emit(col.fecha)">
                <strong>{{ col.titulo }}</strong> <span class="numerico">{{ col.subtitulo }}</span>
              </button>
            } @else {
              <span class="tiempo__profesional" [attr.title]="col.titulo">
                <app-foto-persona [profesionalId]="col.clave" [nombre]="col.titulo" [tamano]="30" />
                <span class="tiempo__nombre">
                  <strong>{{ col.titulo }}</strong>
                  <span>{{ col.subtitulo }}</span>
                </span>
              </span>
            }
          </div>
        }

        <div class="tiempo__horas" [style.height.px]="altoTotal()">
          @for (h of horas(); track h.minutos) {
            <span class="numerico" [style.top.px]="h.arriba">{{ h.texto }}</span>
          }
        </div>
        @for (col of columnas(); track col.clave) {
          <div class="tiempo__columna" [class.tiempo__columna--hoy]="col.hoy" [style.height.px]="altoTotal()">
            @for (h of horas(); track h.minutos) {
              <span class="tiempo__linea" [style.top.px]="h.arriba"></span>
            }
            @if (col.hoy && ahora() !== null) {
              <span class="tiempo__ahora" [style.top.px]="ahora()" aria-hidden="true"></span>
            }
            @for (b of col.bloques; track b.clave) {
              <button
                type="button"
                [class]="'bloque estado--' + b.estado"
                [class.bloque--elegido]="b.cita && b.cita.id === citaSeleccionadaId()"
                [class.bloque--corto]="b.alto < 48"
                [style.top.px]="b.arriba"
                [style.height.px]="b.alto"
                [style.left.%]="b.izquierda"
                [style.width.%]="b.ancho"
                [disabled]="b.hueco !== null && !puedeReservar()"
                [attr.title]="b.horaTexto + ' · ' + b.titulo + ' · ' + b.detalle"
                [attr.aria-label]="b.horaTexto + ', ' + b.titulo + ', ' + b.detalle"
                (click)="elegirBloque(b)"
              >
                <span class="bloque__hora numerico">{{ b.alto < 48 ? b.inicioTexto : b.horaTexto }}</span>
                <span class="bloque__titulo">{{ b.titulo }}</span>
                <span class="bloque__detalle">{{ b.detalle }}</span>
              </button>
            }
          </div>
        }
      </div>
      @if (vacio()) {
        <p class="vacio">{{ vista() === 'dia' ? 'No hay citas este día.' : 'No hay citas esta semana.' }}</p>
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host {
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
      min-width: 0;
      --c-pending: #f4c95d;
      --c-held: #f59e42;
      --c-confirmed: #2a9d8f;
      --c-rescheduled: #8b6fd6;
      --c-en-sala: #38a3d6;
      --c-en-atencion: #3c5bd6;
      --c-completed: #3f9a5a;
      --c-no-show: #d0493c;
      --c-cancelled: #9aa5ad;
      --c-libre: #3f9a5a;
    }

    .leyenda {
      display: flex;
      flex: none;
      flex-wrap: wrap;
      gap: var(--espacio-1) var(--espacio-3);
      font-size: 0.78rem;
      color: var(--texto-suave);
    }
    .leyenda__item { display: inline-flex; align-items: center; gap: 6px; }
    .muestra { display: inline-block; width: 12px; height: 12px; border-radius: 3px; }

    /* ---- Colores por estado (bloques, chips y leyenda) ---- */
    .estado--PENDING { --c-fondo: color-mix(in srgb, var(--c-pending) 40%, #fff) ; --c-linea: var(--c-pending); }
    .estado--HELD { --c-fondo: color-mix(in srgb, var(--c-held) 34%, #fff) ; --c-linea: var(--c-held); }
    .estado--CONFIRMED { --c-fondo: color-mix(in srgb, var(--c-confirmed) 34%, #fff) ; --c-linea: var(--c-confirmed); }
    .estado--RESCHEDULED { --c-fondo: color-mix(in srgb, var(--c-rescheduled) 32%, #fff) ; --c-linea: var(--c-rescheduled); }
    .estado--EN_SALA { --c-fondo: color-mix(in srgb, var(--c-en-sala) 34%, #fff) ; --c-linea: var(--c-en-sala); }
    .estado--EN_ATENCION { --c-fondo: color-mix(in srgb, var(--c-en-atencion) 32%, #fff) ; --c-linea: var(--c-en-atencion); }
    .estado--COMPLETED { --c-fondo: color-mix(in srgb, var(--c-completed) 32%, #fff) ; --c-linea: var(--c-completed); }
    .estado--NO_SHOW { --c-fondo: color-mix(in srgb, var(--c-no-show) 30%, #fff) ; --c-linea: var(--c-no-show); }
    .estado--CANCELLED { --c-fondo: #f1f3f4 ; --c-linea: var(--c-cancelled); }
    .estado--LIBRE { --c-fondo: color-mix(in srgb, var(--c-libre) 8%, #fff) ; --c-linea: var(--c-libre); }
    .muestra { background: var(--c-fondo); border: 2px solid var(--c-linea); }
    .muestra.estado--HELD, .muestra.estado--LIBRE { border-style: dashed; }

    /* ---- Rejilla de día y semana ---- */
    /* Marco con desplazamiento propio en los dos ejes: la fila de títulos
       queda pegada arriba y la columna de horas pegada a la izquierda. */
    .tiempo {
      display: grid;
      grid-template-columns: 56px repeat(var(--columnas), minmax(var(--ancho-min, 140px), 1fr));
      align-content: start;
      overflow: auto;
      overscroll-behavior: contain;
      scrollbar-width: thin;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
    }
    .tiempo:focus-visible { outline: 3px solid var(--acento); outline-offset: 2px; }
    .tiempo__esquina, .tiempo__titulo {
      position: sticky;
      top: 0;
      z-index: 2;
      background: var(--superficie);
      border-bottom: 1px solid var(--borde);
    }
    .tiempo__esquina { left: 0; z-index: 4; }
    .tiempo__titulo {
      display: grid;
      gap: 2px;
      padding: var(--espacio-2);
      border-left: 1px solid var(--borde);
      text-align: center;
      font-size: 0.85rem;
    }
    .tiempo__titulo span { color: var(--texto-suave); font-size: 0.75rem; }
    .tiempo__profesional { display: inline-flex; align-items: center; gap: 8px; justify-content: center; min-width: 0; max-width: 100%; text-align: left; }
    .tiempo__nombre { display: grid; min-width: 0; }
    /* Un nombre largo se acorta con puntos suspensivos; completo en el título. */
    .tiempo__nombre > * { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .tiempo__profesional strong { color: var(--texto); font-size: 0.85rem; }
    .tiempo__titulo--hoy { background: var(--acento-suave); color: var(--acento-fuerte); }
    .tiempo__dia { display: inline-flex; gap: 4px; align-items: baseline; border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; border-radius: 6px; padding: 2px; }
    .tiempo__dia:hover { background: var(--superficie-hundida); }
    .tiempo__dia:focus-visible { outline: 3px solid var(--acento); }
    .tiempo__horas { position: sticky; left: 0; z-index: 2; background: var(--superficie-elevada); }
    .tiempo__horas span {
      position: absolute;
      right: 6px;
      transform: translateY(-50%);
      font-size: 0.7rem;
      color: var(--texto-tenue);
    }
    .tiempo__horas span:first-child { transform: none; }
    /* Cada columna aísla sus capas: una cita elegida (z-index 3) no puede
       pintarse encima de la fila de títulos pegada al desplazar. */
    .tiempo__columna { position: relative; isolation: isolate; border-left: 1px solid var(--borde); }
    .tiempo__columna--hoy { background: color-mix(in srgb, var(--acento) 4%, transparent); }
    .tiempo__linea { position: absolute; left: 0; right: 0; border-top: 1px solid var(--superficie-hundida); }
    .tiempo__ahora { position: absolute; left: 0; right: 0; z-index: 1; pointer-events: none; border-top: 2px solid var(--peligro); }
    .tiempo__ahora::before {
      content: '';
      position: absolute;
      left: -5px;
      top: -6px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--peligro);
    }

    .bloque {
      position: absolute;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 0;
      overflow: hidden;
      margin: 0 2px;
      padding: 3px 6px;
      border: 1px solid var(--c-linea);
      border-radius: 6px;
      background: var(--c-fondo);
      color: var(--texto);
      text-align: left;
      font-size: 0.75rem;
      line-height: 1.2;
      cursor: pointer;
      box-sizing: border-box;
    }
    .bloque:hover { filter: brightness(0.97); box-shadow: var(--sombra-1); z-index: 3; }
    .bloque:focus-visible { outline: 3px solid var(--acento); outline-offset: 1px; z-index: 3; }
    .bloque--elegido { box-shadow: 0 0 0 2px var(--acento); z-index: 3; }
    .bloque.estado--HELD, .bloque.estado--LIBRE { border-style: dashed; border-width: 2px; }
    .bloque.estado--CANCELLED .bloque__titulo { text-decoration: line-through; color: var(--texto-suave); }
    .bloque.estado--LIBRE { color: #23683a; font-weight: 600; }
    .bloque:disabled { cursor: default; opacity: 0.7; }
    .bloque__hora { font-weight: 700; font-size: 0.7rem; }
    /* Un bloque de menos de ~45 min no cabe en tres lineas: hora y nombre en una. */
    .bloque--corto { flex-direction: row; align-items: center; gap: 6px; padding-block: 1px; }
    .bloque--corto .bloque__detalle { display: none; }
    .bloque__titulo { font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
    /* Texto principal y no el suave: sobre el fondo teñido de una cita
       confirmada, #48646a quedaba en 4,37:1 (axe lo detectó). El título se
       distingue por el peso, no por el color. */
    .bloque__detalle { color: var(--texto); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }

    .vacio { flex: none; margin: 0; color: var(--texto-suave); text-align: center; }

    /* ---- Mes ---- */
    .mes { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--borde); border-radius: var(--radio); overflow: hidden; background: var(--superficie-elevada); }
    .mes__cabecera { display: grid; flex: none; grid-template-columns: repeat(7, minmax(0, 1fr)); background: var(--superficie); border-bottom: 1px solid var(--borde); }
    .mes__cabecera span { padding: var(--espacio-2); text-align: center; font-size: 0.78rem; font-weight: 700; color: var(--texto-suave); }
    .mes__rejilla { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
    .mes__dia {
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-height: 104px;
      padding: 6px;
      border: 0;
      border-right: 1px solid var(--superficie-hundida);
      border-bottom: 1px solid var(--superficie-hundida);
      background: transparent;
      color: var(--texto);
      text-align: left;
      cursor: pointer;
      overflow: hidden;
    }
    .mes__dia:hover { background: var(--superficie); }
    .mes__dia:focus-visible { outline: 3px solid var(--acento); outline-offset: -3px; }
    .mes__dia--fuera { color: var(--texto-tenue); background: color-mix(in srgb, var(--superficie-hundida) 40%, transparent); }
    .mes__dia--elegido { box-shadow: inset 0 0 0 2px var(--acento); }
    .mes__cabeza { display: flex; flex: none; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 2px 4px; min-height: 24px; }
    .mes__numero { font-weight: 700; font-size: 0.85rem; }
    /* Sin sitio para nombres, la cifra del día: dice lo mismo que el mes de un
       vistazo y el clic abre el día con el detalle. */
    .mes__cuenta {
      padding: 1px 6px;
      border-radius: 999px;
      background: var(--acento-suave);
      color: var(--acento-fuerte);
      font-size: 0.7rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .mes__dia--hoy .mes__numero {
      display: inline-grid;
      place-items: center;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: var(--acento);
      color: var(--acento-texto, #fff);
    }
    .chip {
      display: block;
      flex: none;
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid var(--c-linea);
      background: var(--c-fondo);
      font-size: 0.7rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .chip.estado--CANCELLED { text-decoration: line-through; color: var(--texto-suave); }
    .mes__mas { flex: none; font-size: 0.7rem; color: var(--texto-suave); font-weight: 600; }

    /* Escritorio: el calendario llena el alto que le deja la agenda. Las
       horas desplazan dentro; las seis semanas del mes se reparten el alto y
       solo desplazan si no caben con un mínimo legible. */
    @media (min-width: 821px) and (min-height: 600px) {
      :host { flex: 1 1 0; min-height: 0; }
      .tiempo { flex: 1 1 0; min-height: 0; }
      .mes { flex: 1 1 0; }
      .mes__rejilla {
        flex: 1 1 0;
        min-height: 0;
        overflow-y: auto;
        overscroll-behavior: contain;
        scrollbar-width: thin;
        grid-auto-rows: minmax(44px, 1fr);
      }
      .mes__dia { min-height: 0; }
    }

    /* Teléfono y tableta vertical: el documento desplaza, pero las horas
       siguen en su marco para no perder la fila de profesionales de vista. */
    @media (max-width: 820px), (max-height: 599px) {
      .tiempo { max-height: 72vh; }
    }

    @media (max-width: 720px) {
      .mes__dia { min-height: 72px; }
      .mes__cuenta-texto { display: none; }
    }
  `,
})
export class CalendarioAgendaComponent {
  readonly vista = input<VistaCalendario>('dia');
  /** Fecha de referencia, `AAAA-MM-DD` en la zona de la sede. */
  readonly fecha = input.required<string>();
  readonly zona = input('America/Guayaquil');
  readonly citas = input<readonly Cita[]>([]);
  /** Tramos libres del profesional elegido, solo en la vista de día. */
  readonly huecos = input<readonly (FilaDia & { tipo: 'hueco' })[]>([]);
  readonly profesionales = input<readonly Profesional[]>([]);
  readonly profesionalId = input('');
  readonly citaSeleccionadaId = input<string | null>(null);
  readonly puedeReservar = input(false);
  readonly verCanceladas = input(false);
  readonly etiquetaPaciente = input<(id: string) => string>(() => 'Paciente');
  readonly etiquetaServicio = input<(id: string) => string>(() => '');

  readonly citaElegida = output<Cita>();
  readonly huecoElegido = output<FilaDia & { tipo: 'hueco' }>();
  readonly diaElegido = output<string>();

  protected readonly nombresDia = NOMBRES_DIA;

  private readonly marco = viewChild<ElementRef<HTMLElement>>('marco');
  private readonly rejillaMes = viewChild<ElementRef<HTMLElement>>('rejillaMes');
  /**
   * Cuántas citas caben con nombre en una celda del mes. En escritorio las
   * seis semanas se reparten el alto disponible: en un portátil no caben tres
   * nombres por día, y tres nombres aplastados no se leen. Con menos sitio se
   * muestran menos, y sin sitio para ninguno, la cifra del día.
   */
  protected readonly chipsPorDia = signal(3);
  private observador: ResizeObserver | null = null;
  private observada: HTMLElement | null = null;
  /** Vista y fecha ya colocadas en el marco: solo se coloca al cambiar. */
  private colocada = '';

  constructor() {
    // Tras pintar una vista o un día nuevos, el marco de horas se coloca donde
    // se dejó o, la primera vez, cerca de lo que importa.
    afterRenderEffect(() => {
      const elemento = this.marco()?.nativeElement;
      const clave = `${this.vista()}|${this.fecha()}`;
      if (!elemento || clave === this.colocada) return;
      this.colocada = clave;
      elemento.scrollTop = POSICIONES.get(clave) ?? this.posicionInicial(elemento);
    });
    // El mes vuelve a calcular cuántos nombres caben cuando cambia su tamaño.
    afterRenderEffect(() => {
      const rejilla = this.rejillaMes()?.nativeElement ?? null;
      if (rejilla === this.observada) return;
      this.observador?.disconnect();
      this.observada = rejilla;
      if (!rejilla || typeof ResizeObserver !== 'function') return;
      this.observador = new ResizeObserver(() => this.ajustarChips(rejilla));
      this.observador.observe(rejilla);
    });
    inject(DestroyRef).onDestroy(() => this.observador?.disconnect());
  }

  /**
   * Alto de una celda menos su relleno (12), la cabecera con el número (24) y
   * la línea «+N más» (20); cada nombre ocupa 24. En escritorio el alto lo
   * fija la rejilla y no depende del contenido; fuera de él la celda crece
   * con lo que lleva, así que se toma su alto mínimo para no entrar en bucle.
   */
  private ajustarChips(rejilla: HTMLElement): void {
    const dia = rejilla.querySelector<HTMLElement>('.mes__dia');
    if (!dia) return;
    const escritorio =
      typeof matchMedia === 'function' && matchMedia('(min-width: 821px) and (min-height: 600px)').matches;
    const alto = escritorio ? dia.clientHeight : parseFloat(getComputedStyle(dia).minHeight) || 104;
    this.chipsPorDia.set(Math.max(0, Math.min(3, Math.floor((alto - 12 - 24 - 20) / 24))));
  }

  protected recordarPosicion(): void {
    const elemento = this.marco()?.nativeElement;
    if (elemento && this.colocada) POSICIONES.set(this.colocada, elemento.scrollTop);
  }

  /**
   * Primera posición del marco: una hora antes de ahora si se ve el día de
   * hoy; si no, un poco antes de la primera cita o hueco; si no hay nada, las
   * 08:00.
   *
   * La fila de títulos va pegada arriba y tapa lo que pasa por debajo. Para
   * que ninguna cita quede medio escondida bajo ella al abrir, si alguna cruza
   * esa franja se sube hasta el principio de esa cita.
   */
  private posicionInicial(elemento: HTMLElement): number {
    const { desde } = this.franja();
    const bloques = this.columnas().flatMap((col) => col.bloques);
    const conHoy = this.columnas().some((col) => col.hoy);
    let objetivo: number;
    const ahora = this.ahora();
    if (conHoy && ahora !== null) {
      objetivo = ahora - ALTO_HORA;
    } else if (bloques.length > 0) {
      objetivo = Math.min(...bloques.map((b) => b.arriba)) - ALTO_HORA / 2;
    } else {
      objetivo = (8 * 60 - desde) * MINUTO;
    }
    // A la hora en punto: la columna de horas empieza con su etiqueta entera.
    let arriba = Math.max(0, Math.floor(objetivo / ALTO_HORA) * ALTO_HORA);
    const alto = (elemento.querySelector('.tiempo__titulo') as HTMLElement | null)?.offsetHeight ?? 0;
    for (;;) {
      const tapada = bloques.filter((b) => b.arriba < arriba && b.arriba + b.alto > arriba - alto);
      if (tapada.length === 0) break;
      arriba = Math.max(0, Math.min(...tapada.map((b) => b.arriba)) - 1);
    }
    return arriba;
  }

  private readonly hoy = computed(() => hoyEnZona(this.zona()));

  /** Citas visibles con su fecha y minutos locales ya calculados. */
  private readonly locales = computed(() =>
    this.citas()
      .filter((cita) => this.verCanceladas() || cita.estado !== 'CANCELLED')
      .map((cita) => {
        const inicio = partesLocales(cita.inicio, this.zona());
        const fin = partesLocales(cita.fin, this.zona());
        const minutosFin = fin.fecha === inicio.fecha ? fin.minutos : 24 * 60;
        return { cita, fecha: inicio.fecha, desde: inicio.minutos, hasta: Math.max(minutosFin, inicio.minutos + 10) };
      }),
  );

  /** Franja horaria: 07:00 a 21:00, ampliada si alguna cita cae fuera. */
  private readonly franja = computed(() => {
    let desde = 7 * 60;
    let hasta = 21 * 60;
    for (const item of this.locales()) {
      desde = Math.min(desde, Math.floor(item.desde / 60) * 60);
      hasta = Math.max(hasta, Math.ceil(item.hasta / 60) * 60);
    }
    return { desde, hasta };
  });

  protected readonly altoTotal = computed(() => (this.franja().hasta - this.franja().desde) * MINUTO);

  protected readonly horas = computed(() => {
    const { desde, hasta } = this.franja();
    const lista: { minutos: number; arriba: number; texto: string }[] = [];
    for (let m = desde; m < hasta; m += 60) {
      lista.push({ minutos: m, arriba: (m - desde) * MINUTO, texto: `${String(m / 60).padStart(2, '0')}:00` });
    }
    return lista;
  });

  /** Posición de la línea de «ahora», o null si cae fuera de la franja. */
  protected readonly ahora = computed(() => {
    const { minutos } = partesLocales(new Date().toISOString(), this.zona());
    const { desde, hasta } = this.franja();
    return minutos < desde || minutos > hasta ? null : (minutos - desde) * MINUTO;
  });

  protected readonly columnas = computed<readonly Columna[]>(() => {
    const fecha = this.fecha();
    if (this.vista() === 'semana') {
      const lunes = lunesDe(fecha);
      return Array.from({ length: 7 }, (_, i) => {
        const dia = sumarDias(lunes, i);
        const citas = this.locales().filter(
          (item) =>
            item.fecha === dia && (!this.profesionalId() || item.cita.profesional_id === this.profesionalId()),
        );
        return {
          clave: dia,
          titulo: NOMBRES_DIA[i],
          subtitulo: `${dia.slice(8, 10)}/${dia.slice(5, 7)}`,
          hoy: dia === this.hoy(),
          fecha: dia,
          bloques: this.colocar(citas, [], true),
        };
      });
    }
    // Día: una columna por profesional con citas, y siempre la del elegido.
    const delDia = this.locales().filter((item) => item.fecha === fecha);
    const ids = new Set(delDia.map((item) => item.cita.profesional_id));
    if (this.profesionalId()) ids.add(this.profesionalId());
    const nombres = new Map(this.profesionales().map((p) => [p.id, `${p.nombre} ${p.apellido}`]));
    const orden = [...ids].sort((a, b) => {
      if (a === this.profesionalId()) return -1;
      if (b === this.profesionalId()) return 1;
      return (nombres.get(a) ?? '').localeCompare(nombres.get(b) ?? '');
    });
    return orden.map((id) => ({
      clave: id,
      titulo: nombres.get(id) ?? 'Profesional',
      subtitulo: id === this.profesionalId() ? 'Profesional elegido' : `${delDia.filter((i) => i.cita.profesional_id === id).length} cita(s)`,
      hoy: fecha === this.hoy(),
      fecha,
      bloques: this.colocar(
        delDia.filter((item) => item.cita.profesional_id === id),
        id === this.profesionalId() ? this.huecos() : [],
        false,
      ),
    }));
  });

  protected readonly vacio = computed(() => this.columnas().every((col) => col.bloques.length === 0));

  /** Solo los estados que se ven en pantalla, en el orden de la leyenda completa. */
  protected readonly leyendaVisible = computed(() => {
    const presentes = new Set<string>();
    if (this.vista() === 'mes') {
      for (const dia of this.diasMes()) {
        for (const cita of dia.citas) presentes.add(estadoVisual(cita));
      }
    } else {
      for (const columna of this.columnas()) {
        for (const bloque of columna.bloques) presentes.add(bloque.estado);
      }
    }
    return LEYENDA.filter((item) => presentes.has(item.estado));
  });

  protected readonly diasMes = computed(() => {
    const fecha = this.fecha();
    const { desde } = rangoVista('mes', fecha);
    const mes = fecha.slice(0, 7);
    const porDia = new Map<string, Cita[]>();
    const horas = new Map<string, string>();
    for (const item of this.locales()) {
      if (this.profesionalId() && item.cita.profesional_id !== this.profesionalId()) continue;
      const lista = porDia.get(item.fecha) ?? [];
      lista.push(item.cita);
      porDia.set(item.fecha, lista);
      horas.set(item.cita.id, this.textoHora(item.desde));
    }
    return Array.from({ length: 42 }, (_, i) => {
      const dia = sumarDias(desde, i);
      const citas = (porDia.get(dia) ?? []).sort((a, b) => Date.parse(a.inicio) - Date.parse(b.inicio));
      return {
        fecha: dia,
        numero: Number(dia.slice(8, 10)),
        delMes: dia.startsWith(mes),
        hoy: dia === this.hoy(),
        citas,
        horas,
        etiqueta: `${dia.slice(8, 10)}/${dia.slice(5, 7)}: ${citas.length} cita(s)`,
      };
    });
  });

  protected estado(cita: Cita): EstadoVisual {
    return estadoVisual(cita);
  }

  protected elegirBloque(bloque: Bloque): void {
    if (bloque.cita) this.citaElegida.emit(bloque.cita);
    else if (bloque.hueco) this.huecoElegido.emit(bloque.hueco);
  }

  /**
   * Coloca bloques en una columna. Las citas que se solapan (dos sillones,
   * una cita y su reprogramación) se reparten el ancho en carriles para que
   * ninguna tape a otra.
   */
  private colocar(
    citas: readonly { cita: Cita; desde: number; hasta: number }[],
    huecos: readonly (FilaDia & { tipo: 'hueco' })[],
    conProfesional: boolean,
  ): Bloque[] {
    const inicioFranja = this.franja().desde;
    const nombres = new Map(this.profesionales().map((p) => [p.id, `${p.nombre} ${p.apellido}`]));
    const items = [
      ...citas.map((item) => ({ ...item, hueco: null as (FilaDia & { tipo: 'hueco' }) | null })),
      ...huecos.map((hueco) => ({
        cita: null as Cita | null,
        hueco,
        desde: partesLocales(hueco.inicio, this.zona()).minutos,
        hasta: partesLocales(hueco.fin, this.zona()).minutos,
      })),
    ].sort((a, b) => a.desde - b.desde || b.hasta - a.hasta);

    // Agrupa en racimos de solape y asigna carril dentro de cada racimo.
    const resultado: Bloque[] = [];
    let racimo: { item: (typeof items)[number]; carril: number }[] = [];
    let finRacimo = -1;
    const cerrar = () => {
      const carriles = Math.max(1, ...racimo.map((r) => r.carril + 1));
      for (const { item, carril } of racimo) {
        const cita = item.cita;
        const estado = cita ? estadoVisual(cita) : 'LIBRE';
        const alto = Math.max((item.hasta - item.desde) * MINUTO - 2, 20);
        resultado.push({
          clave: cita ? cita.id : `hueco-${item.hueco!.inicio}`,
          cita,
          hueco: item.hueco,
          estado,
          arriba: (item.desde - inicioFranja) * MINUTO + 1,
          alto,
          izquierda: (carril / carriles) * 100,
          ancho: 100 / carriles,
          horaTexto: `${this.textoHora(item.desde)}–${this.textoHora(item.hasta)}`,
          inicioTexto: this.textoHora(item.desde),
          titulo: cita ? this.etiquetaPaciente()(cita.paciente_id) : 'Libre',
          detalle: cita
            ? [
                ETIQUETA.get(estado as EstadoVisual) ?? '',
                this.etiquetaServicio()(cita.servicio_id),
                conProfesional ? (nombres.get(cita.profesional_id) ?? '') : '',
              ]
                .filter(Boolean)
                .join(' · ')
            : `${item.hueco!.turnos.length} turno(s) para reservar`,
        });
      }
      racimo = [];
    };
    for (const item of items) {
      if (racimo.length && item.desde >= finRacimo) cerrar();
      const ocupados = new Set(racimo.filter((r) => r.item.hasta > item.desde).map((r) => r.carril));
      let carril = 0;
      while (ocupados.has(carril)) carril += 1;
      racimo.push({ item, carril });
      finRacimo = Math.max(finRacimo, item.hasta);
    }
    if (racimo.length) cerrar();
    return resultado;
  }

  private textoHora(minutos: number): string {
    const m = Math.min(minutos, 24 * 60);
    return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  }
}
