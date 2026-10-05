/**
 * Lista de espera.
 *
 * Qué cambia respecto a la versión anterior
 * -----------------------------------------
 * El formulario de alta ocupaba la mitad superior de la pantalla, siempre, y
 * la lista —que es el trabajo— quedaba debajo. Se usa una vez por turno y
 * estorbaba todo el rato. Ahora se abre en una **ventana flotante** desde un
 * botón, y la pantalla es lo que tiene que ser: la cola de gente esperando.
 *
 * Las acciones de cada entrada también se movieron a una ventana. Antes cada
 * fila llevaba hasta tres botones —aceptar, rechazar, retirar— y con quince
 * entradas eran cuarenta y cinco objetos pulsables, tres de ellos
 * irreversibles, a un clic de distancia.
 *
 * Lo primero de la pantalla es la llamada pendiente
 * ------------------------------------------------
 * Una oferta sin avisar retiene un turno del que el paciente **no sabe nada**:
 * no tiene consentimiento para mensajes automáticos. Si nadie llama antes de
 * que venza, el hueco vuelve a la cola y la ausencia cuenta contra él. Eso va
 * arriba y con su plazo, no mezclado entre las demás filas.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { IconoComponent } from '../../compartido/icono.component';
import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { FichaPacienteComponent } from '../../compartido/ficha-paciente.component';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PendientesService } from '../../nucleo/servicios/pendientes.service';
import {
  OperacionesService,
  type EntradaEspera,
  type Pagina,
} from '../../nucleo/servicios/operaciones.service';
import type { Cita, Paciente, PaginaCitas, Profesional, Sede, Servicio } from '../../nucleo/modelos/dominio';
import { formatearFechaHora } from '../../nucleo/utilidades/fechas';

/** Traducción de los estados de una entrada. El código sigue en inglés. */
const ESTADOS: Record<string, { etiqueta: string; clase: string }> = {
  ACTIVA: { etiqueta: 'En espera', clase: 'neutra' },
  OFERTADA: { etiqueta: 'Con oferta', clase: 'info' },
  ACEPTADA: { etiqueta: 'Aceptada', clase: 'exito' },
  RECHAZADA: { etiqueta: 'Rechazada', clase: 'peligro' },
  EXPIRADA: { etiqueta: 'Expirada', clase: 'peligro' },
  CANCELADA: { etiqueta: 'Retirada', clase: 'neutra' },
  CUMPLIDA: { etiqueta: 'Con cita', clase: 'exito' },
};

const POR_PAGINA = 25;
const DIAS_SEMANA = [
  { id: 0, nombre: 'Lunes' }, { id: 1, nombre: 'Martes' },
  { id: 2, nombre: 'Miércoles' }, { id: 3, nombre: 'Jueves' },
  { id: 4, nombre: 'Viernes' }, { id: 5, nombre: 'Sábado' },
  { id: 6, nombre: 'Domingo' },
] as const;

@Component({
  selector: 'app-lista-espera',
  standalone: true,
  imports: [
    FormsModule,
    IconoComponent,
    SelectorPacienteComponent,
    VentanaFlotanteComponent,
    FichaPacienteComponent,
  ],
  template: `
    <div class="cabecera-pagina">
      <div>
        <p class="ceja">LISTA DE ESPERA</p>
        <h1>Quién espera un hueco</h1>
        <p class="pagina__nota">
          Una cancelación genera una oferta para una persona a la vez, con plazo para responder.
        </p>
      </div>
      <img class="modulo-cabecera__imagen" src="/images/lista-espera.png" alt="" aria-hidden="true" loading="lazy" />
      <div class="acciones">
        <button type="button" class="boton" (click)="cargar()" [disabled]="cargando()">
          Actualizar
        </button>
        <button type="button" class="boton boton--principal" (click)="abrirAlta()">
          <app-icono nombre="mas" [tamano]="17" />
          Anotar a un paciente
        </button>
      </div>
    </div>

    @if (error()) {
      <p class="aviso-error" role="alert">{{ error() }}</p>
    }
    @if (aviso()) {
      <p class="exito" role="status">{{ aviso() }}</p>
    }

    <!-- Lo único de esta pantalla que hay que hacer ahora. -->
    @if (sinAvisar().length > 0 && !soloSinAvisar()) {
      <div class="aviso-llamar">
        <p class="llamar__titulo">
          <app-icono nombre="telefono" [tamano]="18" />
          <strong>{{ sinAvisar().length }} paciente(s) esperan una llamada.</strong>
        </p>
        <p class="llamar__detalle">
          Tienen un turno reservado del que no se les pudo avisar por mensaje. Si nadie llama
          antes de que venza, el hueco vuelve a la cola.
        </p>
        <div class="acciones">
          <button type="button" class="boton boton--pequeno" (click)="alternarPendientes(true)">
            Ver solo esos
          </button>
        </div>
      </div>
    }

    <div class="barra-lista">
      <h2 class="barra-lista__titulo">
        Entradas <span class="numerico">· {{ total() }}</span>
      </h2>
      <label class="campo campo--en-linea">
        <input
          type="checkbox"
          name="pendientes"
          [ngModel]="soloSinAvisar()"
          (ngModelChange)="alternarPendientes($event)"
        />
        <span>Solo pendientes de llamar</span>
      </label>
    </div>

    @if (cargando()) {
      <p role="status">Consultando lista…</p>
    } @else if (entradas().length === 0) {
      <div class="tarjeta">
        <p class="vacio__titulo">
          @if (soloSinAvisar()) {
            Nadie está esperando una llamada.
          } @else {
            Todavía no hay pacientes en lista de espera.
          }
        </p>
        <p class="campo__ayuda">
          @if (soloSinAvisar()) {
            Quite el filtro para ver la cola completa.
          } @else {
            Cuando alguien no encuentre hueco, anótelo aquí y recibirá el primero que se libere.
          }
        </p>
      </div>
    } @else {
      <ul class="cola-espera">
        @for (entrada of entradas(); track entrada.id) {
          <li>
            <button
              type="button"
              class="fila-espera"
              [class.fila-espera--llamar]="entrada.oferta_avisada === false"
              (click)="abrirDetalle(entrada)"
            >
              <span class="fila-espera__quien">
                <span class="fila-espera__nombre">{{ nombre(entrada.paciente_id) }}</span>
                <span class="fila-espera__servicio">
                  {{ nombreServicio(entrada.servicio_id) }} ·
                  {{ entrada.horas_antelacion_minima }} h de antelación mínima
                </span>
              </span>

              @if (entrada.oferta_id) {
                <span class="fila-espera__oferta numerico">
                  Turno: {{ fecha(entrada.oferta_inicio) }}
                </span>
              }
              @if (entrada.oferta_avisada === false) {
                <span class="marca-llamar">
                  <app-icono nombre="telefono" [tamano]="13" />
                  hay que llamar
                </span>
              }
              <span class="insignia" [class]="'insignia--' + presentacion(entrada.estado).clase">
                {{ presentacion(entrada.estado).etiqueta }}
              </span>
            </button>
          </li>
        }
      </ul>

      <div class="acciones paginacion">
        <button
          type="button"
          class="boton"
          (click)="mover(-1)"
          [disabled]="pagina() === 0 || cargando()"
        >
          <app-icono nombre="anterior" [tamano]="16" />
          Anterior
        </button>
        <span class="paginacion__posicion numerico">
          Página {{ pagina() + 1 }} de {{ paginas() }}
        </span>
        <button
          type="button"
          class="boton"
          (click)="mover(1)"
          [disabled]="(pagina() + 1) * 25 >= total() || cargando()"
        >
          Siguiente
          <app-icono nombre="siguiente" [tamano]="16" />
        </button>
      </div>
    }

    <!-- ============ Alta: ventana flotante ============ -->
    @if (altaAbierta()) {
      <app-ventana-flotante
        ceja="Lista de espera"
        titulo="Anotar a un paciente"
        forma="centrada"
        [anchoMaximo]="560"
        [cierraAlPulsarFuera]="false"
        (cerrar)="cerrarAlta()"
      >
        <app-selector-paciente (seleccion)="seleccionarPaciente($event)" />

        @if (citasPrevias().length > 0) {
          <label class="campo campo--cita-previa">
            <span class="campo__etiqueta">Cita actual que desea cambiar (opcional)</span>
            <select class="campo__control" name="citaPrevia" [ngModel]="citaPreviaId()" (ngModelChange)="citaPreviaId.set($event)">
              <option value="">No tiene una cita que reemplazar</option>
              @for (cita of citasPrevias(); track cita.id) {
                <option [value]="cita.id">{{ fecha(cita.inicio) }} · {{ cita.estado === 'RESCHEDULED' ? 'Reprogramada' : 'Confirmada' }}</option>
              }
            </select>
            <span class="campo__ayuda">Al aceptar una oferta, esta cita se cancelará en la misma operación y su horario se ofrecerá a otra persona.</span>
          </label>
        } @else if (buscandoCitas()) {
          <p class="campo__ayuda" role="status">Buscando citas actuales del paciente…</p>
        }

        <div class="rejilla-alta">
          <label class="campo">
            <span class="campo__etiqueta">Sede</span>
            <select class="campo__control" name="sede" [ngModel]="sedeId()" (ngModelChange)="cambiarSede($event)" required>
              <option value="">Seleccione</option>
              @for (sede of sedes(); track sede.id) {
                <option [value]="sede.id">{{ sede.nombre }}</option>
              }
            </select>
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Servicio</span>
            <select class="campo__control" name="servicio" [ngModel]="servicioId()" (ngModelChange)="cambiarServicio($event)" required>
              <option value="">Seleccione</option>
              @for (servicio of servicios(); track servicio.id) {
                <option [value]="servicio.id">{{ servicio.nombre }}</option>
              }
            </select>
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Profesional (opcional)</span>
            <select class="campo__control" name="profesional" [ngModel]="profesionalId()" (ngModelChange)="profesionalId.set($event)">
              <option value="">Cualquier profesional</option>
              @for (profesional of profesionales(); track profesional.id) {
                <option [value]="profesional.id">{{ profesional.nombre }} {{ profesional.apellido }}</option>
              }
            </select>
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Disponible desde (opcional)</span>
            <input class="campo__control" type="date" name="disponibleDesde" [ngModel]="disponibleDesde()" (ngModelChange)="disponibleDesde.set($event)" />
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Disponible hasta (opcional)</span>
            <input class="campo__control" type="date" name="disponibleHasta" [ngModel]="disponibleHasta()" (ngModelChange)="disponibleHasta.set($event)" />
          </label>
          <label class="campo">
            <span class="campo__etiqueta">Antelación mínima (horas)</span>
            <input
              class="campo__control"
              type="number"
              name="antelacion"
              min="0"
              max="168"
              [(ngModel)]="antelacion"
            />
            <span class="campo__ayuda">
              No se le ofrecerá un hueco con menos aviso que este.
            </span>
          </label>
        </div>

        <fieldset class="preferencias-horario">
          <legend>Horarios aceptables (opcional)</legend>
          <p class="campo__ayuda">La hora se interpreta en la zona horaria de la sede.</p>
          <div class="dias-semana">
            @for (dia of diasSemanaCatalogo; track dia.id) {
              <label class="dia-semana">
                <input type="checkbox" [checked]="diasPreferidos().includes(dia.id)" (change)="alternarDia(dia.id, $any($event.target).checked)" />
                {{ dia.nombre }}
              </label>
            }
          </div>
          <div class="rejilla-alta">
            <label class="campo">
              <span class="campo__etiqueta">Desde las</span>
              <input class="campo__control" type="time" name="horaDesde" [ngModel]="horaDesde()" (ngModelChange)="horaDesde.set($event)" />
            </label>
            <label class="campo">
              <span class="campo__etiqueta">Hasta las</span>
              <input class="campo__control" type="time" name="horaHasta" [ngModel]="horaHasta()" (ngModelChange)="horaHasta.set($event)" />
            </label>
          </div>
          @if (!franjaCoherente()) {
            <p class="aviso-error" role="alert">Indique las dos horas y asegúrese de que la hora final sea posterior.</p>
          }
          @if (!fechasCoherentes()) {
            <p class="aviso-error" role="alert">La fecha final no puede ser anterior a la inicial.</p>
          }
        </fieldset>

        <div class="acciones acciones--final" pie>
          @if (faltaParaAnotar(); as falta) {
            <span class="campo__ayuda alta__falta" role="status">{{ falta }}</span>
          }
          <button type="button" class="boton" (click)="cerrarAlta()">Cancelar</button>
          <button
            type="button"
            class="boton boton--principal"
            [disabled]="!puedeAnotar() || ocupado()"
            (click)="anotar()"
          >
            {{ ocupado() ? 'Guardando…' : 'Añadir a la lista' }}
          </button>
        </div>
      </app-ventana-flotante>
    }

    <!-- ============ Detalle de una entrada: ventana flotante ============ -->
    @if (entradaElegida(); as entrada) {
      <app-ventana-flotante
        ceja="Entrada en espera"
        [titulo]="nombre(entrada.paciente_id)"
        forma="lateral"
        [anchoMaximo]="480"
        (cerrar)="entradaElegida.set(null)"
      >
        <dl class="detalle">
          <div>
            <dt>Estado</dt>
            <dd>
              <span class="insignia" [class]="'insignia--' + presentacion(entrada.estado).clase">
                {{ presentacion(entrada.estado).etiqueta }}
              </span>
            </dd>
          </div>
          <div>
            <dt>Servicio</dt>
            <dd>{{ nombreServicio(entrada.servicio_id) }}</dd>
          </div>
          <div>
            <dt>Antelación</dt>
            <dd class="numerico">{{ entrada.horas_antelacion_minima }} horas</dd>
          </div>
          @if (entrada.disponible_desde || entrada.disponible_hasta) {
            <div>
              <dt>Disponibilidad</dt>
              <dd>{{ entrada.disponible_desde || 'Sin fecha inicial' }} – {{ entrada.disponible_hasta || 'Sin fecha final' }}</dd>
            </div>
          }
          @if (entrada.preferencias; as preferencias) {
            <div>
              <dt>Días y horas</dt>
              <dd>{{ nombresDias(preferencias.dias_semana) }}{{ preferencias.hora_desde ? ' · ' + preferencias.hora_desde.slice(0, 5) + ' a ' + preferencias.hora_hasta?.slice(0, 5) : '' }}</dd>
            </div>
          }
          @if (entrada.cita_previa_id) {
            <div>
              <dt>Reagendamiento</dt>
              <dd>Al aceptar, se cancela la cita previa y su horario vuelve a la lista de espera.</dd>
            </div>
          }
          @if (entrada.oferta_id) {
            <div>
              <dt>Turno ofrecido</dt>
              <dd class="numerico">{{ fecha(entrada.oferta_inicio) }}</dd>
            </div>
            <div>
              <dt>Responder hasta</dt>
              <dd class="numerico">{{ fecha(entrada.oferta_expira_en) }}</dd>
            </div>
          }
        </dl>

        @if (entrada.oferta_avisada === false) {
          <div class="aviso-llamar">
            <p class="llamar__titulo">
              <app-icono nombre="telefono" [tamano]="18" />
              <strong>Este paciente no sabe nada de la oferta.</strong>
            </p>
            <p class="llamar__detalle">
              No tiene consentimiento para mensajes automáticos. Llámele antes de que venza, o el
              hueco vuelve a la cola y la ausencia contará contra él.
            </p>
          </div>
        }

        @if (entrada.oferta_id) {
          <div class="acciones acciones--separadas detalle__acciones">
            <button
              type="button"
              class="boton boton--principal"
              [disabled]="ocupado()"
              (click)="resolver(entrada, 'aceptar')"
            >
              {{ entrada.cita_previa_id ? 'Aceptar y cambiar la cita' : 'Aceptar la oferta' }}
            </button>
            <button
              type="button"
              class="boton"
              [disabled]="ocupado()"
              (click)="resolver(entrada, 'rechazar')"
            >
              Rechazar
            </button>
          </div>
        }
        @if (entrada.estado === 'ACTIVA' || entrada.estado === 'OFERTADA') {
          <div class="detalle__retirar">
            <button
              type="button"
              class="boton boton--peligro"
              [disabled]="ocupado()"
              (click)="resolver(entrada, 'cancelar')"
            >
              Retirar de la lista
            </button>
            <p class="campo__ayuda">
              Deja de recibir ofertas. No borra nada de su historial.
            </p>
          </div>
        }

        <div class="detalle__ficha">
          <button type="button" class="boton" (click)="fichaDe.set(entrada.paciente_id)">
            Ver la ficha completa del paciente
          </button>
        </div>
      </app-ventana-flotante>
    }

    @if (fichaDe(); as pacienteId) {
      <app-ventana-flotante
        ceja="Paciente"
        titulo="Ficha del paciente"
        forma="centrada"
        [anchoMaximo]="1180"
        [altoCompleto]="true"
        (cerrar)="fichaDe.set(null)"
      >
        <app-ficha-paciente [pacienteId]="pacienteId" [sinCabecera]="true" />
      </app-ventana-flotante>
    }
  `,
  styles: `
    .pagina__nota {
      margin: var(--espacio-1) 0 0;
      color: var(--texto-suave);
    }

    /* --- Aviso de llamada pendiente --- */
    .aviso-llamar {
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
    }

    .llamar__titulo {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      margin: 0;
    }

    .llamar__detalle {
      margin: 0;
      font-size: 0.92rem;
    }

    /* --- Barra de la lista --- */
    .barra-lista {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-4);
      flex-wrap: wrap;
      margin: var(--espacio-5) 0 var(--espacio-3);
    }

    .barra-lista__titulo {
      margin: 0;
    }

    /* --- La cola --- */
    .cola-espera {
      list-style: none;
      margin: 0;
      padding: 0;
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
      box-shadow: var(--sombra-1);
      overflow: hidden;
    }

    .fila-espera {
      display: flex;
      align-items: center;
      gap: var(--espacio-4);
      width: 100%;
      padding: var(--espacio-3) var(--espacio-4);
      border: 0;
      border-bottom: 1px solid var(--superficie-hundida);
      border-left: 3px solid transparent;
      background: var(--superficie-elevada);
      text-align: left;
      cursor: pointer;
      transition: background-color 120ms ease;
    }

    .fila-espera:hover {
      background: var(--acento-suave);
    }

    /* Quien espera una llamada se distingue por la barra y por la marca de
       texto, no solo por el tono. */
    .fila-espera--llamar {
      border-left-color: var(--aviso);
      background: var(--aviso-fondo);
    }

    .fila-espera--llamar:hover {
      background: var(--aviso-fondo);
    }

    .fila-espera__quien {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 1px;
    }

    .fila-espera__nombre {
      font-weight: 600;
    }

    .fila-espera__servicio {
      color: var(--texto-suave);
      font-size: 0.85rem;
    }

    .fila-espera__oferta {
      color: var(--texto-suave);
      font-size: 0.85rem;
      white-space: nowrap;
    }

    .marca-llamar {
      display: inline-flex;
      align-items: center;
      gap: var(--espacio-1);
      flex: 0 0 auto;
    }

    /* --- Paginación --- */
    .paginacion {
      margin-top: var(--espacio-4);
    }

    .paginacion__posicion {
      color: var(--texto-suave);
      font-size: 0.9rem;
    }

    /* --- Alta --- */
    .rejilla-alta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: var(--espacio-4);
      margin-top: var(--espacio-4);
    }

    .preferencias-horario {
      min-width: 0;
      margin: var(--espacio-4) 0 0;
      padding: var(--espacio-3);
      border: 1px solid var(--borde);
      border-radius: var(--radio-2);
    }

    .preferencias-horario legend { padding: 0 var(--espacio-1); font-weight: 650; }
    .campo--cita-previa { margin-top: var(--espacio-4); }
    .preferencias-horario > .campo__ayuda { margin-top: 0; }
    .dias-semana { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .dia-semana { display: inline-flex; align-items: center; gap: var(--espacio-1); min-height: var(--toque-minimo); }

    /* --- Detalle --- */
    .detalle {
      margin: 0 0 var(--espacio-4);
      display: flex;
      flex-direction: column;
      gap: var(--espacio-2);
    }

    .detalle div {
      display: flex;
      gap: var(--espacio-3);
      padding-bottom: var(--espacio-2);
      border-bottom: 1px solid var(--superficie-hundida);
    }

    .detalle dt {
      flex: 0 0 130px;
      color: var(--texto-tenue);
      font-size: 0.88rem;
    }

    .detalle dd {
      margin: 0;
      flex: 1 1 auto;
    }

    .detalle__acciones {
      margin-top: var(--espacio-4);
    }

    /* Lo irreversible va separado y abajo: no se pulsa por inercia. */
    .detalle__retirar {
      margin-top: var(--espacio-5);
      padding-top: var(--espacio-4);
      border-top: 1px solid var(--borde);
    }

    .detalle__retirar .campo__ayuda {
      margin-top: var(--espacio-2);
    }

    .alta__falta {
      margin-right: auto;
      align-self: center;
    }

    .detalle__ficha {
      margin-top: var(--espacio-5);
      padding-top: var(--espacio-4);
      border-top: 1px solid var(--borde);
    }



    .vacio__titulo {
      margin: 0 0 var(--espacio-1);
      font-weight: 600;
    }

    .insignia {
      display: inline-block;
      padding: 2px var(--espacio-2);
      border-radius: 999px;
      border: 1px solid currentcolor;
      font-size: 0.8rem;
      font-weight: 650;
      white-space: nowrap;
      flex: 0 0 auto;
    }

    .insignia--exito {
      color: var(--exito);
      background: var(--exito-fondo);
    }
    .insignia--info {
      color: var(--info);
      background: var(--info-fondo);
    }
    .insignia--peligro {
      color: var(--peligro);
      background: var(--peligro-fondo);
    }
    .insignia--neutra {
      color: var(--texto-suave);
      background: var(--superficie-hundida);
    }
  `,
})
export class ListaEsperaComponent {
  private readonly api = inject(OperacionesService);
  private readonly catalogo = inject(CatalogoService);
  private readonly pendientes = inject(PendientesService);

  protected readonly paciente = signal<Paciente | null>(null);
  protected readonly citasPrevias = signal<readonly Cita[]>([]);
  protected readonly buscandoCitas = signal(false);
  protected readonly citaPreviaId = signal('');
  protected readonly sedeId = signal('');
  protected readonly servicioId = signal('');
  protected readonly profesionalId = signal('');
  protected readonly disponibleDesde = signal('');
  protected readonly disponibleHasta = signal('');
  protected readonly diasPreferidos = signal<number[]>([]);
  protected readonly horaDesde = signal('');
  protected readonly horaHasta = signal('');
  protected antelacion = 4;

  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly diasSemanaCatalogo = DIAS_SEMANA;
  protected readonly entradas = signal<readonly EntradaEspera[]>([]);
  protected readonly total = signal(0);
  protected readonly pagina = signal(0);
  protected readonly cargando = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected readonly aviso = signal('');
  protected readonly soloSinAvisar = signal(false);

  /** Ventanas flotantes abiertas. Nunca las dos a la vez. */
  protected readonly altaAbierta = signal(false);
  protected readonly entradaElegida = signal<EntradaEspera | null>(null);

  private nombres = signal<ReadonlyMap<string, string>>(new Map());
  private clave = crypto.randomUUID();
  private ultimoCuerpo = '';
  private solicitudCitasPrevias = 0;

  protected readonly paginas = computed(() =>
    Math.max(1, Math.ceil(this.total() / POR_PAGINA)),
  );

  /** Entradas con un turno reservado del que el paciente no sabe nada. */
  protected readonly sinAvisar = computed(() =>
    this.entradas().filter((entrada) => entrada.oferta_avisada === false),
  );

  protected readonly puedeAnotar = computed(
    () => this.paciente() !== null && this.sedeId() !== '' && this.servicioId() !== '' &&
      this.franjaCoherente() && this.fechasCoherentes(),
  );

  /** Por qué el botón está apagado, dicho junto al botón. */
  protected readonly faltaParaAnotar = computed(() => {
    if (this.paciente() === null) return 'Elija primero al paciente.';
    if (!this.sedeId()) return 'Elija la sede.';
    if (!this.servicioId()) return 'Elija el servicio.';
    if (!this.franjaCoherente()) return 'Revise la franja horaria.';
    if (!this.fechasCoherentes()) return 'Revise las fechas.';
    return '';
  });

  protected readonly franjaCoherente = computed(() =>
    Boolean(this.horaDesde()) === Boolean(this.horaHasta()) &&
      (!this.horaDesde() || this.horaDesde() < this.horaHasta()),
  );

  protected readonly fechasCoherentes = computed(() =>
    !this.disponibleDesde() || !this.disponibleHasta() || this.disponibleHasta() >= this.disponibleDesde(),
  );

  constructor() {
    forkJoin({ sedes: this.catalogo.sedes(), servicios: this.catalogo.servicios() }).subscribe({
      next: (resultado) => {
        this.sedes.set(resultado.sedes);
        this.servicios.set(resultado.servicios);
      },
      error: () => this.error.set('No se pudo cargar el catálogo.'),
    });
    this.cargar();
  }

  protected abrirAlta(): void {
    this.paciente.set(null);
    this.citasPrevias.set([]);
    this.citaPreviaId.set('');
    this.sedeId.set(this.sedes()[0]?.id ?? '');
    this.servicioId.set('');
    this.profesionalId.set('');
    this.profesionales.set([]);
    this.disponibleDesde.set('');
    this.disponibleHasta.set('');
    this.diasPreferidos.set([]);
    this.horaDesde.set('');
    this.horaHasta.set('');
    this.antelacion = 4;
    this.altaAbierta.set(true);
  }

  protected cerrarAlta(): void {
    this.altaAbierta.set(false);
  }

  /** Paciente cuya ficha completa está abierta encima del detalle. */
  protected readonly fichaDe = signal<string | null>(null);

  protected abrirDetalle(entrada: EntradaEspera): void {
    this.entradaElegida.set(entrada);
  }

  protected cambiarSede(sedeId: string): void {
    this.sedeId.set(sedeId);
    this.citaPreviaId.set('');
    this.cargarProfesionales();
    this.cargarCitasPrevias();
  }

  protected cambiarServicio(servicioId: string): void {
    this.servicioId.set(servicioId);
    this.citaPreviaId.set('');
    this.cargarProfesionales();
    this.cargarCitasPrevias();
  }

  protected seleccionarPaciente(paciente: Paciente | null): void {
    this.paciente.set(paciente);
    this.citaPreviaId.set('');
    this.cargarCitasPrevias();
  }

  private cargarCitasPrevias(): void {
    const solicitud = ++this.solicitudCitasPrevias;
    const paciente = this.paciente();
    const sedeId = this.sedeId();
    const servicioId = this.servicioId();
    this.citasPrevias.set([]);
    if (!paciente || !sedeId || !servicioId) {
      this.buscandoCitas.set(false);
      return;
    }
    this.buscandoCitas.set(true);
    this.api.leer<PaginaCitas>('/agenda/citas', {
      paciente_id: paciente.id,
      sede_id: sedeId,
      desde: new Date().toISOString(),
      limite: 100,
    }).subscribe({
      next: (pagina) => {
        if (solicitud !== this.solicitudCitasPrevias) return;
        const citas = pagina.elementos.filter((cita) =>
          cita.servicio_id === servicioId &&
          ['CONFIRMED', 'RESCHEDULED'].includes(cita.estado) &&
          Date.parse(cita.inicio) > Date.now(),
        );
        this.citasPrevias.set(citas);
        this.buscandoCitas.set(false);
      },
      error: () => {
        if (solicitud !== this.solicitudCitasPrevias) return;
        this.buscandoCitas.set(false);
        this.error.set('No se pudieron consultar las citas actuales del paciente.');
      },
    });
  }

  private cargarProfesionales(): void {
    this.profesionalId.set('');
    this.profesionales.set([]);
    const servicio = this.servicios().find((item) => item.id === this.servicioId());
    if (!servicio || !this.sedeId()) return;
    this.catalogo.profesionales({ sedeId: this.sedeId(), especialidadId: servicio.especialidad_id }).subscribe({
      next: (profesionales) => this.profesionales.set(profesionales),
      error: () => this.error.set('No se pudieron cargar los profesionales de la sede y el servicio.'),
    });
  }

  protected alternarDia(dia: number, activo: boolean): void {
    this.diasPreferidos.update((dias) => activo
      ? [...new Set([...dias, dia])].sort((a, b) => a - b)
      : dias.filter((actual) => actual !== dia));
  }

  protected nombresDias(dias: readonly number[]): string {
    const nombres = dias.map((dia) => DIAS_SEMANA.find((opcion) => opcion.id === dia)?.nombre)
      .filter((nombre) => nombre !== undefined);
    return nombres.join(', ');
  }

  protected alternarPendientes(valor: boolean): void {
    this.soloSinAvisar.set(valor);
    this.pagina.set(0);
    this.cargar();
  }

  protected cargar(): void {
    this.cargando.set(true);
    this.error.set('');
    this.api
      .leer<Pagina<EntradaEspera>>('/lista-espera/', {
        limite: POR_PAGINA,
        desplazamiento: this.pagina() * POR_PAGINA,
        solo_sin_avisar: this.soloSinAvisar(),
      })
      .subscribe({
        next: (resultado) => {
          this.entradas.set(resultado.elementos);
          this.total.set(resultado.total);
          this.cargando.set(false);
          this.resolverNombres(resultado.elementos);
        },
        error: (fallo: FalloApi) => {
          this.error.set(fallo.message);
          this.cargando.set(false);
        },
      });
  }

  private resolverNombres(entradas: readonly EntradaEspera[]): void {
    for (const id of new Set(entradas.map((entrada) => entrada.paciente_id))) {
      if (this.nombres().has(id)) {
        continue;
      }
      this.api.leer<Paciente>(`/pacientes/${id}`).subscribe({
        next: (paciente) =>
          this.nombres.update((actual) => {
            const copia = new Map(actual);
            copia.set(id, `${paciente.apellido}, ${paciente.nombre}`);
            return copia;
          }),
        // Sin permiso de ficha queda el identificador recortado: peor que un
        // nombre, mejor que ocultar la entrada.
        error: () => undefined,
      });
    }
  }

  protected nombre(id: string): string {
    return this.nombres().get(id) ?? `Paciente ${id.slice(0, 8)}`;
  }

  protected mover(saltos: number): void {
    this.pagina.update((actual) => actual + saltos);
    this.cargar();
  }

  protected anotar(): void {
    const servicio = this.servicios().find((s) => s.id === this.servicioId());
    const paciente = this.paciente();
    if (!servicio || !paciente) {
      return;
    }
    const dias = this.diasPreferidos();
    const preferencias = dias.length || this.horaDesde()
      ? {
          dias_semana: dias,
          ...(this.horaDesde() ? { hora_desde: this.horaDesde(), hora_hasta: this.horaHasta() } : {}),
        }
      : null;
    this.enviar('/lista-espera/', {
      paciente_id: paciente.id,
      sede_id: this.sedeId(),
      servicio_id: servicio.id,
      especialidad_id: servicio.especialidad_id,
      cita_previa_id: this.citaPreviaId() || null,
      profesional_id: this.profesionalId() || null,
      disponible_desde: this.disponibleDesde() || null,
      disponible_hasta: this.disponibleHasta() || null,
      preferencias,
      horas_antelacion_minima: this.antelacion,
    });
  }

  protected resolver(entrada: EntradaEspera, accion: string): void {
    this.enviar(`/lista-espera/${entrada.id}/resolver`, { accion });
  }

  private enviar(ruta: string, datos: unknown): void {
    if (this.ocupado()) {
      return;
    }
    // La clave se reutiliza mientras el cuerpo no cambie: dos pulsaciones del
    // mismo botón no crean dos entradas, pero corregir un dato y reenviar sí
    // manda una operación nueva.
    const cuerpo = JSON.stringify({ ruta, datos });
    if (cuerpo !== this.ultimoCuerpo) {
      this.clave = crypto.randomUUID();
    }
    this.ultimoCuerpo = cuerpo;

    this.ocupado.set(true);
    this.error.set('');
    this.aviso.set('');
    this.api.guardar<EntradaEspera>(ruta, datos, this.clave).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.aviso.set('Lista de espera actualizada.');
        this.altaAbierta.set(false);
        this.entradaElegida.set(null);
        this.cargar();
        // La insignia del menú cuenta las ofertas sin avisar: si esta acción
        // resolvió una, el número tiene que bajar.
        this.pendientes.cargar();
      },
      error: (fallo: FalloApi) => {
        this.cargar();
        this.error.set(fallo.message);
        this.ocupado.set(false);
        this.pendientes.cargar();
      },
    });
  }

  protected presentacion(estado: string): { etiqueta: string; clase: string } {
    return ESTADOS[estado] ?? { etiqueta: estado, clase: 'neutra' };
  }

  protected nombreServicio(id: string): string {
    return this.servicios().find((s) => s.id === id)?.nombre ?? 'Servicio';
  }

  protected fecha(instante: string | null): string {
    return instante ? formatearFechaHora(instante, 'America/Guayaquil') : '—';
  }
}
