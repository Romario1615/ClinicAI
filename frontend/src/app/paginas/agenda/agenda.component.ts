/**
 * Pantalla de agenda. Conectada al backend real.
 *
 * Lo que esta pantalla tiene que hacer bien
 * -----------------------------------------
 * **No puede perder una reserva por una doble pulsación.** Cada creación
 * lleva una clave de idempotencia generada al abrir el formulario, no al
 * enviarlo: si se generara al enviar, dos pulsaciones producirían dos claves
 * y con ellas dos citas. Con la clave fija, la segunda petición devuelve la
 * cita ya creada.
 *
 * **No puede mentir sobre la hora.** Todo se formatea con la zona de la sede,
 * nunca con la del equipo. Una hora mal en una agenda médica es un paciente
 * que llega cuando no le esperan.
 *
 * **Tiene que explicar la ausencia de turnos.** «No hay disponibilidad» deja a
 * quien atiende sin saber si insistir otro día o llamar por teléfono. El
 * backend devuelve el recuento por motivo y aquí se muestra.
 *
 * **Tiene que distinguir el turno ocupado del error.** Un 409 al reservar no
 * es un fallo del sistema: es la carrera resuelta por la restricción de
 * exclusión, y el mensaje correcto es «ese turno acaba de ocuparse», no
 * «error inesperado».
 */
import {
  Component,
  DestroyRef,
  ElementRef,
  afterRenderEffect,
  computed,
  inject,
  signal,
  viewChild,
  ChangeDetectionStrategy,
} from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Subject, catchError, forkJoin, map, of, switchMap, type Observable } from 'rxjs';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import { ColaTrabajoComponent } from '../../compartido/cola-trabajo.component';
import { FichaPacienteComponent } from '../../compartido/ficha-paciente.component';
import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { InsigniaEstadoComponent } from '../../compartido/insignia-estado.component';
import { IconoComponent } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { PestanasComponent, type OpcionPestana } from '../../compartido/pestanas.component';
import { ReprogramarCitaComponent } from './reprogramar-cita.component';
import { AccionesRecorridoComponent } from './acciones-recorrido.component';
import { ProlongacionesPendientesComponent } from './prolongaciones-pendientes.component';
import {
  CalendarioAgendaComponent,
  rangoVista,
  type VistaCalendario,
} from './calendario-agenda.component';
import {
  ApiService,
  FalloApi,
  type FrecuenciaSerieCitas,
} from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import {
  OperacionesService,
  type EntradaEspera,
  type Pagina,
} from '../../nucleo/servicios/operaciones.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import {
  cargaPorProfesional,
  construirSecuencia,
  duracionLegible,
  minutosEntre,
  type FilaDia,
} from '../../nucleo/utilidades/secuencia-dia';
import { derivarPendientes, type TareaPendiente } from '../../nucleo/utilidades/pendientes';
import type {
  Cita,
  Consultorio,
  Disponibilidad,
  Especialidad,
  Paciente,
  Profesional,
  Sede,
  Servicio,
  TurnoDisponible,
} from '../../nucleo/modelos/dominio';
import {
  formatearFechaLarga,
  formatearHora,
  hoyEnZona,
  instanteLocal,
  rangoDelDia,
  sumarDias,
} from '../../nucleo/utilidades/fechas';

/**
 * Resultado de cargar un dia: o los datos, o el fallo ya traducido.
 *
 * El fallo viaja como valor y no como error del observable porque con
 * `switchMap` un error propagado termina la suscripcion, y la pantalla dejaria
 * de recargarse para siempre tras el primer 500.
 */
type CargaDelDia =
  | { readonly citas: readonly Cita[]; readonly disponibilidad: Disponibilidad | null }
  | { readonly fallo: FalloApi };

/**
 * Estados que cuentan como sala ocupada en la interfaz.
 *
 * La base de datos bloquea con `HELD`, `CONFIRMED` y `RESCHEDULED`. Aqui se
 * suma `PENDING` a proposito: una cita pendiente en un sillon todavia no lo
 * bloquea, pero ofrecerlo a otra persona produce un 409 en cuanto la primera
 * se confirme. Es mas prudente que la restriccion, nunca menos.
 */
const ESTADOS_QUE_OCUPAN_SALA: ReadonlySet<string> = new Set([
  'PENDING',
  'HELD',
  'CONFIRMED',
  'RESCHEDULED',
]);

/** Ventana del tablero de consultorios, en minutos desde medianoche local. */
const TABLERO_DESDE = 7 * 60;
const TABLERO_HASTA = 21 * 60;

const TIPOS_CONSULTORIO: Record<string, string> = {
  CONSULTA: 'Consulta',
  PROCEDIMIENTOS: 'Procedimientos',
  IMAGEN: 'Imagen',
  LABORATORIO: 'Laboratorio',
  OTRO: 'Otro',
};

/** Ocupacion de un consultorio en el dia mostrado. */
export interface OcupacionConsultorio {
  readonly consultorio: Consultorio;
  readonly tipo: string;
  readonly citas: readonly Cita[];
  readonly ocupadoAhora: Cita | null;
  readonly proxima: Cita | null;
  /** Bloques del dia en porcentaje de la ventana del tablero. */
  readonly bloques: readonly {
    readonly izquierda: number;
    readonly ancho: number;
    readonly cita: Cita;
  }[];
}

/** Traducción de los motivos por los que un hueco no se ofrece. */
const MOTIVOS: Record<string, string> = {
  FUERA_DE_HORARIO: 'fuera del horario de atención',
  DESCANSO: 'en horario de descanso',
  FERIADO: 'día feriado',
  BLOQUEO: 'el profesional no atiende (vacaciones, ausencia o capacitación)',
  OCUPADO: 'ya reservado',
  ANTELACION_INSUFICIENTE: 'demasiado próximo para reservar',
  PASADO: 'ya pasó',
  GRANULARIDAD_INCOMPATIBLE: 'el hueco no encaja con la duración del servicio',
};

const CLAVE_VISTA = 'agenda.vista';

/**
 * Ancho de ventana a partir del cual lo pendiente cabe en una columna fija a
 * la derecha del calendario. Por debajo, el calendario necesita todo el ancho
 * (siete días o varias columnas de profesionales) y lo pendiente se abre en
 * una ventana desde la cabecera.
 */
const CONSULTA_LATERAL_FIJO = '(min-width: 1200px)';

/** Vista recordada; si no hay o no se puede leer, el calendario del día. */
function leerVista(): VistaCalendario | 'lista' {
  try {
    const valor = localStorage.getItem(CLAVE_VISTA);
    return valor === 'semana' || valor === 'mes' || valor === 'lista' ? valor : 'dia';
  } catch {
    return 'dia';
  }
}

@Component({
  selector: 'app-agenda',
  standalone: true,
  imports: [
    FormsModule,
    NgTemplateOutlet,
    PestanasComponent,
    CargandoComponent,
    ErrorComponent,
    VacioComponent,
    ColaTrabajoComponent,
    FichaPacienteComponent,
    InsigniaEstadoComponent,
    IconoComponent,
    ReprogramarCitaComponent,
    VentanaFlotanteComponent,
    CalendarioAgendaComponent,
    SelectorPacienteComponent,
    AccionesRecorridoComponent,
    ProlongacionesPendientesComponent,
  ],
  templateUrl: './agenda.component.html',
  // Pantalla de trabajo: en escritorio ocupa el alto disponible y solo
  // desplazan, cada uno en su marco, el calendario y las listas.
  host: { class: 'pantalla' },
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './agenda.component.scss',
})
export class AgendaComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  private readonly operaciones = inject(OperacionesService);
  protected readonly sesion = inject(SesionService);
  /**
   * Paciente que llega preseleccionado (por ejemplo, desde un plan de
   * tratamiento con una fase por agendar). Solo rellena el formulario de
   * reserva: el hueco lo sigue eligiendo quien agenda.
   */
  private readonly ruta = inject(ActivatedRoute);
  private citaSolicitada = this.ruta.snapshot.queryParamMap.get('cita');
  private solicitudCitaContexto = 0;
  protected readonly pacienteSugerido = signal<string | null>(
    inject(ActivatedRoute).snapshot.queryParamMap.get('paciente'),
  );
  /** Procedimiento seleccionado desde un plan aceptado; el servidor valida el vínculo. */
  protected readonly procedimientoPlanSugerido = signal<string | null>(
    inject(ActivatedRoute).snapshot.queryParamMap.get('procedimiento_plan'),
  );

  // --- Catálogo ---
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly especialidades = signal<readonly Especialidad[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly consultorios = signal<readonly Consultorio[]>([]);

  // --- Selección ---
  protected readonly sedeId = signal('');
  protected readonly especialidadId = signal('');
  protected readonly servicioId = signal('');
  protected readonly profesionalId = signal('');
  protected readonly fecha = signal('');
  /** Cómo se ve la agenda. Se recuerda por navegador: es preferencia de quien la usa. */
  protected readonly vista = signal<VistaCalendario | 'lista'>(leerVista());
  protected readonly vistas: readonly { valor: VistaCalendario | 'lista'; etiqueta: string }[] = [
    { valor: 'dia', etiqueta: 'Día' },
    { valor: 'semana', etiqueta: 'Semana' },
    { valor: 'mes', etiqueta: 'Mes' },
    { valor: 'lista', etiqueta: 'Lista' },
  ];
  /** Citas de la semana o del mes visibles (las del día van en `citasSede`). */
  protected readonly citasRango = signal<readonly Cita[]>([]);
  protected readonly cargandoRango = signal(false);
  private solicitudRango = 0;

  // --- Estado de carga ---
  protected readonly cargandoCatalogo = signal(true);
  protected readonly cargandoAgenda = signal(false);
  protected readonly errorCatalogo = signal<FalloApi | null>(null);
  protected readonly errorAgenda = signal<FalloApi | null>(null);
  protected readonly exportando = signal(false);
  protected readonly errorExportacion = signal('');

  // --- Datos ---
  protected readonly citas = signal<readonly Cita[]>([]);
  /**
   * Todas las citas de la sede en el dia, sin filtrar por profesional.
   *
   * La ocupacion de una sala no depende de quien este elegido en el filtro:
   * un sillon lo puede tener otra persona, y ofrecerlo como libre por no
   * verla es como se produce el 409 al reservar.
   */
  protected readonly citasSede = signal<readonly Cita[]>([]);
  protected readonly disponibilidad = signal<Disponibilidad | null>(null);

  // --- Reserva ---
  protected readonly turnoElegido = signal<TurnoDisponible | null>(null);
  protected pacienteId = '';
  protected notas = '';
  protected serieRecurrente = false;
  protected frecuenciaSerie: FrecuenciaSerieCitas = 'SEMANAL';
  protected cantidadSerie = 4;
  /** Consultorio elegido para la reserva. Vacio: sin sala asignada. */
  protected readonly consultorioId = signal('');
  /**
   * Clave de idempotencia del formulario abierto.
   *
   * Se genera al ABRIR el formulario, no al enviarlo. Si se generara al
   * enviar, dos pulsaciones rápidas producirían dos claves distintas y con
   * ellas dos citas; con la clave fija, la segunda petición devuelve la cita
   * que creó la primera.
   */
  private claveIdempotencia = '';
  protected readonly reservando = signal(false);
  protected readonly errorReserva = signal<FalloApi | null>(null);
  protected readonly mensajeExito = signal('');

  // --- Cancelación ---
  protected readonly citaACancelar = signal<Cita | null>(null);
  protected motivoCancelacion = '';
  protected readonly citaAReprogramar = signal<Cita | null>(null);

  // --- Lo que se abre encima ---
  //
  // Pulsar una cita abre su detalle en una ventana lateral y pulsar un hueco
  // abre la reserva en una ventana centrada. El calendario no se mueve ni
  // pierde el sitio, y nunca hay dos de estas ventanas abiertas a la vez.
  protected readonly huecoElegido = signal<(FilaDia & { tipo: 'hueco' }) | null>(null);
  /**
   * La reserva se abrió con «Nueva cita» y ofrece todas las horas libres del
   * día, no solo las de un tramo.
   */
  protected readonly reservaDelDia = signal(false);
  protected readonly citaSeleccionada = signal<Cita | null>(null);
  /** Ficha lateral abierta, si hay alguna. */
  protected readonly pacienteEnFicha = signal<string | null>(null);
  /**
   * Las canceladas se ocultan por defecto: su turno ya aparece como libre, y
   * dos filas para la misma hora se leen como un error de la pantalla.
   */
  protected readonly verCanceladas = signal(false);
  /** Ofertas de lista de espera que nadie pudo comunicar. */
  protected readonly ofertasSinAvisar = signal<readonly EntradaEspera[]>([]);

  /**
   * Dónde se quedó la lista del día. La agenda recarga tras cada acción y la
   * lista se vuelve a pintar: sin esto, cada confirmación devolvería la vista
   * a primera hora.
   */
  private readonly listaDia = viewChild<ElementRef<HTMLElement>>('listaDia');
  private posicionLista = { fecha: '', arriba: 0 };

  /** Explica por qué «Nueva cita» no pudo abrir la reserva. */
  protected readonly avisoAgenda = signal('');

  // --- Columna lateral: lo pendiente y los consultorios ---
  private readonly consultaLateral =
    typeof matchMedia === 'function' ? matchMedia(CONSULTA_LATERAL_FIJO) : null;
  /** Hay ancho para tener lo pendiente siempre a la vista, junto al calendario. */
  protected readonly lateralFijo = signal(this.consultaLateral?.matches ?? true);
  /** Ventana con lo pendiente, cuando no hay columna lateral. */
  protected readonly lateralAbierto = signal(false);
  protected readonly pestanaLateral = signal('pendientes');
  protected readonly opcionesLateral = computed<readonly OpcionPestana[]>(() => [
    { clave: 'pendientes', etiqueta: 'Pendientes', cuenta: this.pendientes().length },
    { clave: 'consultorios', etiqueta: 'Consultorios' },
  ]);

  /** El día entero en una sola columna: citas y huecos, en orden de reloj. */
  protected readonly secuencia = computed(() =>
    construirSecuencia(this.citas(), this.turnos(), this.verCanceladas()),
  );

  protected readonly pendientes = computed<readonly TareaPendiente[]>(() =>
    derivarPendientes({
      citas: this.citas(),
      ofertasSinAvisar: this.ofertasSinAvisar(),
      ahora: new Date(),
      nombrePaciente: (id) => this.nombrePaciente(id),
    }),
  );

  /**
   * Lo que se puede afirmar del día sin inventar la capacidad.
   *
   * Cuántas citas hay y cuántos minutos de consulta ocupan es un hecho. El
   * porcentaje de ocupación de la jornada NO se muestra: haría falta el
   * horario de atención, que hoy no expone ninguna API, y un porcentaje con un
   * denominador supuesto es peor que ninguno.
   */
  protected readonly resumenDia = computed(() => {
    const vivas = this.citas().filter((cita) => cita.estado !== 'CANCELLED');
    const ocupados = [...cargaPorProfesional(vivas).values()].reduce((a, b) => a + b, 0);
    const libres = this.secuencia()
      .filter((fila): fila is FilaDia & { tipo: 'hueco' } => fila.tipo === 'hueco')
      .reduce((total, hueco) => total + minutosEntre(hueco.inicio, hueco.fin), 0);
    return {
      citas: vivas.length,
      ocupado: duracionLegible(ocupados),
      libre: duracionLegible(libres),
      tramosLibres: this.secuencia().filter((fila) => fila.tipo === 'hueco').length,
    };
  });

  /** El día elegido en palabras, para la reserva (en semana o mes no lo dice el título). */
  protected readonly fechaDia = computed(() => {
    const fecha = this.fecha();
    if (!fecha) {
      return '';
    }
    const texto = formatearFechaLarga(`${fecha}T12:00:00Z`, this.zona());
    return texto.charAt(0).toUpperCase() + texto.slice(1);
  });

  /** El día elegido en corto («mié 7 oct»), para el pie y los consultorios. */
  protected readonly diaCorto = computed(() => {
    const fecha = this.fecha();
    if (!fecha) {
      return '';
    }
    return new Intl.DateTimeFormat('es', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      timeZone: 'UTC',
    }).format(new Date(`${fecha}T12:00:00Z`));
  });

  protected readonly nombreSugerido = computed(() => {
    const id = this.pacienteSugerido();
    return id ? this.nombrePaciente(id) : '';
  });

  protected readonly zona = computed(
    () => this.sedes().find((sede) => sede.id === this.sedeId())?.zona_horaria ?? 'America/Guayaquil',
  );

  protected readonly puedeCrear = computed(() => this.sesion.tienePermiso(PERMISOS.citaCrear));
  protected get maximoCitasSerie(): number {
    return this.frecuenciaSerie === 'MENSUAL' ? 13 : 53;
  }
  protected get cantidadSerieValida(): boolean {
    return Number.isInteger(this.cantidadSerie)
      && this.cantidadSerie >= 2
      && this.cantidadSerie <= this.maximoCitasSerie;
  }
  protected readonly puedeCancelar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.citaCancelar),
  );
  protected readonly puedeCompletar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.citaCompletar),
  );
  protected readonly puedeInasistencia = computed(() =>
    this.sesion.tienePermiso(PERMISOS.citaInasistencia),
  );
  protected readonly puedeExportarReportes = computed(() =>
    this.sesion.tienePermiso(PERMISOS.reporteExportar),
  );

  protected readonly fechaLegible = computed(() => {
    const fecha = this.fecha();
    if (!fecha) {
      return '';
    }
    const vista = this.vista();
    if (vista === 'mes') {
      const texto = new Intl.DateTimeFormat('es', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(
        new Date(`${fecha}T12:00:00Z`),
      );
      return texto.charAt(0).toUpperCase() + texto.slice(1);
    }
    if (vista === 'semana') {
      const { desde, hasta } = rangoVista('semana', fecha);
      const corto = (dia: string) =>
        new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(
          new Date(`${dia}T12:00:00Z`),
        );
      return `Semana del ${corto(desde)} al ${corto(sumarDias(hasta, -1))}`;
    }
    // Sin el año cuando es el año en curso: la cabecera comparte línea con
    // las flechas y la acción principal, y el año no dice nada nuevo.
    const mismoAno = fecha.slice(0, 4) === hoyEnZona(this.zona()).slice(0, 4);
    const texto = new Intl.DateTimeFormat('es', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      ...(mismoAno ? {} : { year: 'numeric' as const }),
      timeZone: 'UTC',
    }).format(new Date(`${fecha}T12:00:00Z`));
    return texto.charAt(0).toUpperCase() + texto.slice(1);
  });

  /** Tramos libres del día para pintarlos en el calendario. */
  protected readonly huecosDia = computed(() =>
    this.secuencia().filter((fila): fila is FilaDia & { tipo: 'hueco' } => fila.tipo === 'hueco'),
  );

  protected readonly citasCalendario = computed(() =>
    this.vista() === 'dia' ? this.citasSede() : this.citasRango(),
  );

  protected readonly etiquetaPaciente = (id: string): string => this.nombrePaciente(id);
  protected readonly etiquetaServicio = (id: string): string => this.nombreServicio(id);

  /** Cierto cuando faltan datos para poder consultar la disponibilidad. */
  protected readonly seleccionIncompleta = computed(
    () => !this.sedeId() || !this.servicioId() || !this.profesionalId(),
  );

  /** Turnos ofrecibles del dia. Vacio mientras no haya consulta hecha. */
  protected readonly turnos = computed(() => this.disponibilidad()?.turnos ?? []);

  protected readonly hayTurnos = computed(() => this.turnos().length > 0);

  /** Motivos de ausencia de turnos, ya traducidos y ordenados. */
  protected readonly motivosSinTurno = computed(() => {
    const datos = this.disponibilidad();
    if (!datos) {
      return [];
    }
    return Object.entries(datos.motivos_sin_turno)
      .map(([clave, cantidad]) => ({
        motivo: MOTIVOS[clave] ?? clave.toLowerCase().replace(/_/g, ' '),
        cantidad,
      }))
      .sort((a, b) => b.cantidad - a.cantidad);
  });

  /**
   * Disparador de la carga del dia.
   *
   * Por que un `Subject` con `switchMap` y no una suscripcion por llamada
   * ------------------------------------------------------------------------
   * Cambiar sede, especialidad, servicio y profesional son cuatro cambios
   * seguidos, y recepcion los hace en menos de un segundo. Con una suscripcion
   * por llamada, las cuatro peticiones vuelan a la vez y **gana la que llega
   * ultima, no la ultima pedida**: la pantalla acaba mostrando las citas de una
   * combinacion de filtros que ya no esta seleccionada.
   *
   * No es teorico: se reprodujo mostrando cero citas en un dia que tenia
   * cuatro. `switchMap` cancela la peticion anterior, asi que solo se aplica la
   * respuesta de la seleccion vigente.
   */
  private readonly recargar = new Subject<void>();

  constructor() {
    this.ruta.queryParamMap.pipe(takeUntilDestroyed()).subscribe(parametros => {
      const cita = parametros.get('cita');
      if (cita === this.citaSolicitada) return;
      this.citaSolicitada = cita;
      this.solicitudCitaContexto++;
      this.pacienteSugerido.set(parametros.get('paciente'));
      this.procedimientoPlanSugerido.set(parametros.get('procedimiento_plan'));
      if (!this.cargandoCatalogo() && cita) this.cargarCitaContexto(cita);
    });
    const consulta = this.consultaLateral;
    if (consulta) {
      // Si la ventana del navegador se ensancha con lo pendiente abierto en
      // una ventana flotante, se cierra: pasa a verse en la columna fija.
      const alCambiar = (evento: MediaQueryListEvent): void => {
        this.lateralFijo.set(evento.matches);
        if (evento.matches) {
          this.lateralAbierto.set(false);
        }
      };
      consulta.addEventListener('change', alCambiar);
      inject(DestroyRef).onDestroy(() => consulta.removeEventListener('change', alCambiar));
    }
    afterRenderEffect(() => {
      const lista = this.listaDia()?.nativeElement;
      if (lista && this.posicionLista.fecha === this.fecha() && lista.scrollTop === 0) {
        lista.scrollTop = this.posicionLista.arriba;
      }
    });
    this.recargar
      .pipe(
        switchMap(() => this.peticionDelDia()),
        takeUntilDestroyed(),
      )
      .subscribe((resultado) => {
        this.cargandoAgenda.set(false);
        if ('fallo' in resultado) {
          this.errorAgenda.set(resultado.fallo);
          return;
        }
        this.citasSede.set(resultado.citas);
        const profesional = this.profesionalId();
        this.citas.set(
          profesional
            ? resultado.citas.filter((cita) => cita.profesional_id === profesional)
            : resultado.citas,
        );
        this.disponibilidad.set(resultado.disponibilidad);
      });
    this.cargarCatalogo();
  }

  /**
   * La peticion del dia: citas siempre, disponibilidad solo si se puede.
   *
   * Sin servicio ni profesional se puede mostrar la agenda del dia, pero no
   * calcular huecos: el motor necesita saber de que servicio y de quien.
   */
  private peticionDelDia(): Observable<CargaDelDia> {
    const { desde, hasta } = rangoDelDia(this.fecha(), this.zona());
    // Sin filtro de profesional: el tablero de consultorios necesita ver a
    // toda la sede. El filtro se aplica despues, en el cliente.
    const citas$ = this.api.citas({
      desde,
      hasta,
      sede_id: this.sedeId(),
      limite: 200,
    });

    const peticion$: Observable<CargaDelDia> = this.seleccionIncompleta()
      ? citas$.pipe(
          map(
            (pagina): CargaDelDia => ({ citas: pagina.elementos, disponibilidad: null }),
          ),
        )
      : forkJoin({
          citas: citas$,
          disponibilidad: this.api.disponibilidad({
            profesional_id: this.profesionalId(),
            servicio_id: this.servicioId(),
            sede_id: this.sedeId(),
            desde,
            hasta,
            // Se piden los motivos de descarte para poder explicar la ausencia
            // de turnos en lugar de decir «no hay disponibilidad».
            explicar: true,
          }),
        }).pipe(
          map(
            (datos): CargaDelDia => ({
              citas: datos.citas.elementos,
              disponibilidad: datos.disponibilidad,
            }),
          ),
        );

    return peticion$.pipe(
      catchError((fallo: unknown): Observable<CargaDelDia> => of({ fallo: this.aFallo(fallo) })),
    );
  }

  // ======================================================================
  //  Carga
  // ======================================================================
  protected cargarCatalogo(): void {
    this.cargandoCatalogo.set(true);
    this.errorCatalogo.set(null);

    forkJoin({
      sedes: this.catalogo.sedes(),
      especialidades: this.catalogo.especialidades(),
      servicios: this.catalogo.servicios(),
      profesionales: this.catalogo.profesionales(),
      pacientes: this.api.pacientes({ limite: 100 }),
    }).subscribe({
      next: (datos) => {
        this.sedes.set(datos.sedes);
        this.especialidades.set(datos.especialidades);
        this.servicios.set(datos.servicios);
        this.profesionales.set(datos.profesionales);
        this.pacientes.set(datos.pacientes.elementos);
        this.incluirPacienteSugerido();

        // Preselección con el primer valor de cada lista. Es lo que hace que
        // la pantalla sea útil al abrirla en lugar de pedir cuatro clics
        // antes de mostrar nada.
        const primeraSede = datos.sedes[0];
        if (primeraSede) {
          this.sedeId.set(primeraSede.id);
          this.fecha.set(hoyEnZona(primeraSede.zona_horaria));
        }
        const primerServicio = datos.servicios[0];
        if (primerServicio) {
          this.servicioId.set(primerServicio.id);
          this.especialidadId.set(primerServicio.especialidad_id);
        }
        const primerProfesional = datos.profesionales.find(
          (profesional) => profesional.especialidad_id === primerServicio?.especialidad_id,
        );
        if (primerProfesional) {
          this.profesionalId.set(primerProfesional.id);
        }

        this.cargandoCatalogo.set(false);
        this.cargarAgenda();
        if (this.citaSolicitada) this.cargarCitaContexto(this.citaSolicitada);
      },
      error: (fallo: unknown) => {
        this.cargandoCatalogo.set(false);
        this.errorCatalogo.set(this.aFallo(fallo));
      },
    });
  }

  private cargarCitaContexto(id: string): void {
    const solicitud = ++this.solicitudCitaContexto;
    this.api.cita(id).subscribe({
      next: cita => {
        if (solicitud !== this.solicitudCitaContexto) return;
        this.sedeId.set(cita.sede_id); this.profesionalId.set(cita.profesional_id);
        this.servicioId.set(cita.servicio_id);
        this.especialidadId.set(this.profesionales().find(p => p.id === cita.profesional_id)?.especialidad_id ?? '');
        const partes = new Intl.DateTimeFormat('en-CA', { timeZone: this.zona(), year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(cita.inicio));
        const parte = (tipo: string) => partes.find(p => p.type === tipo)?.value;
        this.fecha.set(`${parte('year')}-${parte('month')}-${parte('day')}`);
        this.cerrarFicha();
        this.cargarAgenda(); this.abrirCita(cita);
      },
      error: fallo => {
        if (solicitud === this.solicitudCitaContexto) this.errorAgenda.set(this.aFallo(fallo));
      },
    });
  }

  protected cargarAgenda(): void {
    if (!this.sedeId() || !this.fecha()) {
      return;
    }
    this.cargandoAgenda.set(true);
    this.errorAgenda.set(null);
    this.avisoAgenda.set('');
    this.cerrarPanel();
    this.cargarOfertasSinAvisar();
    this.cargarConsultorios();
    this.cargarRango();
    // El `switchMap` del constructor cancela la carga anterior: solo se aplica
    // la respuesta de la seleccion vigente.
    this.recargar.next();
  }

  /**
   * El paciente sugerido puede no estar entre los primeros cien del listado:
   * se pide su ficha administrativa para poder mostrarlo en el selector.
   */
  private incluirPacienteSugerido(): void {
    const sugerido = this.pacienteSugerido();
    if (!sugerido || this.pacientes().some((paciente) => paciente.id === sugerido)) {
      return;
    }
    this.api.paciente(sugerido).subscribe({
      next: (paciente) => this.pacientes.update((lista) => [paciente, ...lista]),
      // Fuera de ámbito o inexistente: se descarta la sugerencia.
      error: () => {
        this.pacienteSugerido.set(null);
        this.procedimientoPlanSugerido.set(null);
      },
    });
  }

  /**
   * Consultorios de la sede elegida.
   *
   * Un fallo aqui no rompe la agenda: sin la lista se sigue pudiendo
   * reservar, solo que sin sala asignada.
   */
  private cargarConsultorios(): void {
    const sede = this.sedeId();
    this.catalogo.consultorios(sede).subscribe({
      next: (lista) =>
        this.consultorios.set(lista.filter((consultorio) => consultorio.sede_id === sede)),
      error: () => this.consultorios.set([]),
    });
  }

  /** Tablero: cada sala con sus citas del dia, lo que pasa ahora y lo siguiente. */
  protected readonly tableroConsultorios = computed<readonly OcupacionConsultorio[]>(() => {
    const ahora = Date.now();
    const zona = this.zona();
    const ventana = TABLERO_HASTA - TABLERO_DESDE;
    return this.consultorios().map((consultorio) => {
      const citas = this.citasSede()
        .filter(
          (cita) =>
            cita.consultorio_id === consultorio.id &&
            (ESTADOS_QUE_OCUPAN_SALA.has(cita.estado) || cita.estado === 'COMPLETED'),
        )
        .sort((a, b) => a.inicio.localeCompare(b.inicio));
      const ocupadoAhora =
        citas.find((cita) => Date.parse(cita.inicio) <= ahora && ahora < Date.parse(cita.fin)) ??
        null;
      const proxima = citas.find((cita) => Date.parse(cita.inicio) > ahora) ?? null;
      const bloques = citas.map((cita) => {
        const inicio = Math.max(minutosLocales(cita.inicio, zona), TABLERO_DESDE);
        const fin = Math.min(minutosLocales(cita.fin, zona), TABLERO_HASTA);
        return {
          izquierda: ((inicio - TABLERO_DESDE) / ventana) * 100,
          ancho: Math.max(((fin - inicio) / ventana) * 100, 0.8),
          cita,
        };
      });
      return {
        consultorio,
        tipo: TIPOS_CONSULTORIO[consultorio.tipo] ?? consultorio.tipo,
        citas,
        ocupadoAhora,
        proxima,
        bloques,
      };
    });
  });

  /**
   * Cita que ocupa la sala durante el turno elegido, o `null` si esta libre.
   *
   * Se compara contra el bloque completo del turno (consulta mas
   * preparacion), que es el rango que la restriccion de exclusion evalua.
   */
  protected choqueConsultorio(consultorioId: string): Cita | null {
    const turno = this.turnoElegido();
    if (!turno) {
      return null;
    }
    const inicio = Date.parse(turno.inicio);
    const fin = Date.parse(turno.fin_bloque);
    return (
      this.citasSede().find(
        (cita) =>
          cita.consultorio_id === consultorioId &&
          ESTADOS_QUE_OCUPAN_SALA.has(cita.estado) &&
          Date.parse(cita.inicio) < fin &&
          inicio < Date.parse(cita.fin),
      ) ?? null
    );
  }

  protected elegirConsultorio(consultorioId: string): void {
    if (consultorioId && this.choqueConsultorio(consultorioId)) {
      return;
    }
    this.consultorioId.set(consultorioId);
  }

  protected nombreConsultorio(id: string | null): string {
    if (!id) {
      return 'Sin consultorio asignado';
    }
    return (
      this.consultorios().find((consultorio) => consultorio.id === id)?.nombre ?? 'Consultorio'
    );
  }

  /**
   * Ofertas de lista de espera que no se pudieron comunicar.
   *
   * Un fallo aquí **no** rompe la agenda: quien no tiene permiso de lista de
   * espera sigue necesitando ver su día. La cola de pendientes simplemente
   * queda sin esa entrada.
   */
  private cargarOfertasSinAvisar(): void {
    if (!this.sesion.tienePermiso(PERMISOS.listaEsperaGestionar)) {
      this.ofertasSinAvisar.set([]);
      return;
    }
    this.operaciones
      .leer<Pagina<EntradaEspera>>('/lista-espera/', { limite: 25, solo_sin_avisar: true })
      .subscribe({
        next: (pagina) => this.ofertasSinAvisar.set(pagina.elementos),
        error: () => this.ofertasSinAvisar.set([]),
      });
  }

  // ======================================================================
  //  Detalle y reserva
  // ======================================================================
  protected abrirHueco(fila: FilaDia): void {
    if (fila.tipo !== 'hueco' || !this.puedeCrear()) {
      return;
    }
    this.citaSeleccionada.set(null);
    this.reservaDelDia.set(false);
    this.huecoElegido.set(fila);
    this.serieRecurrente = false;
    this.frecuenciaSerie = 'SEMANAL';
    this.cantidadSerie = 4;
    const sugerido = this.pacienteSugerido();
    if (sugerido && !this.pacienteId) {
      this.pacienteId = sugerido;
    }
    // El tramo es un rango; la reserva necesita un punto. Se preselecciona el
    // primer arranque y se dejan los demás a un clic.
    this.elegirTurno(fila.turnos[0]);
  }

  /**
   * «Nueva cita»: la reserva con todas las horas libres del día elegido.
   *
   * Es la misma reserva que se abre al pulsar un hueco; solo cambia que se
   * ofrecen los arranques de todos los tramos libres. Si no se puede ofrecer
   * ninguno, se dice por qué en lugar de abrir un formulario vacío.
   */
  protected nuevaCita(): void {
    if (!this.puedeCrear()) {
      return;
    }
    if (this.seleccionIncompleta()) {
      this.avisoAgenda.set(
        'Elija servicio y profesional en los filtros para ver las horas libres y reservar.',
      );
      return;
    }
    const huecos = this.huecosDia();
    const primero = huecos[0];
    const ultimo = huecos[huecos.length - 1];
    if (!primero || !ultimo) {
      this.avisoAgenda.set(
        `No quedan horas libres el ${this.diaCorto()} con ${this.nombreProfesional(this.profesionalId())}. ` +
          'Pruebe otro día con las flechas, otro profesional, o anote al paciente en la lista de espera.',
      );
      return;
    }
    this.avisoAgenda.set('');
    this.abrirHueco({
      tipo: 'hueco',
      inicio: primero.inicio,
      fin: ultimo.fin,
      turnos: huecos.flatMap((hueco) => hueco.turnos),
    });
    this.reservaDelDia.set(true);
  }

  /** Paciente elegido en el buscador de la reserva. */
  protected elegirPacienteReserva(paciente: Paciente | null): void {
    if (!paciente) return;
    if (!this.pacientes().some((p) => p.id === paciente.id)) {
      this.pacientes.update((lista) => [...lista, paciente]);
    }
    this.pacienteId = paciente.id;
  }

  protected abrirCita(cita: Cita): void {
    this.huecoElegido.set(null);
    this.turnoElegido.set(null);
    this.citaSeleccionada.set(cita);
  }

  protected cerrarPanel(): void {
    this.huecoElegido.set(null);
    this.reservaDelDia.set(false);
    this.citaSeleccionada.set(null);
    this.turnoElegido.set(null);
    this.pacienteId = '';
    this.notas = '';
    this.serieRecurrente = false;
    this.frecuenciaSerie = 'SEMANAL';
    this.cantidadSerie = 4;
    this.consultorioId.set('');
    this.errorReserva.set(null);
  }

  protected readonly citaEnFicha = signal<string | null>(null);
  protected abrirFicha(pacienteId: string, citaId: string | null = null): void {
    this.citaEnFicha.set(citaId);
    this.pacienteEnFicha.set(pacienteId);
  }

  protected cerrarFicha(): void {
    this.pacienteEnFicha.set(null);
  }

  /** El botón principal de una tarea de la cola. */
  protected atenderTarea(tarea: TareaPendiente): void {
    // Con lo pendiente en una ventana, se cierra: lo que sigue (un aviso o el
    // detalle de la cita) tiene que verse.
    this.lateralAbierto.set(false);
    if (tarea.clase === 'llamar') {
      // La gestión de llamadas vive en la pantalla de lista de espera, que es
      // donde está el botón que marca la oferta como comunicada.
      this.mensajeExito.set(
        'Abra «Lista de espera» y filtre por «solo pendientes de llamar» para marcar la llamada.',
      );
      return;
    }
    const primera = this.citas().find((cita) => cita.id === tarea.citas[0]);
    if (!primera) {
      return;
    }
    if (tarea.citas.length === 1) {
      this.confirmarCita(primera);
      return;
    }
    this.abrirCita(primera);
  }

  /** Lleva la vista a la primera cita de la tarea, sin ejecutar nada. */
  protected localizarTarea(tarea: TareaPendiente): void {
    this.lateralAbierto.set(false);
    const primera = this.citas().find((cita) => cita.id === tarea.citas[0]);
    if (primera) {
      this.abrirCita(primera);
    }
  }

  protected recordarPosicionLista(): void {
    const lista = this.listaDia()?.nativeElement;
    if (lista) {
      this.posicionLista = { fecha: this.fecha(), arriba: lista.scrollTop };
    }
  }

  /** Duración de un tramo libre, en palabras. */
  protected duracionHueco(fila: FilaDia): string {
    return fila.tipo === 'hueco'
      ? duracionLegible(minutosEntre(fila.inicio, fila.fin))
      : '';
  }

  // ======================================================================
  //  Navegación
  // ======================================================================
  protected exportarResumen(): void {
    if (this.exportando() || !this.sedeId() || !this.fecha()) return;
    const vistaActual = this.vista();
    const vista: VistaCalendario = vistaActual === 'lista' ? 'dia' : vistaActual;
    const { desde, hasta } = rangoVista(vista, this.fecha());
    const desdeIso = instanteLocal(desde, '00:00', this.zona());
    const hastaIso = instanteLocal(hasta, '00:00', this.zona());
    this.exportando.set(true);
    this.errorExportacion.set('');
    this.api
      .exportarResumenAgenda({
        desde: desdeIso,
        hasta: hastaIso,
        sede_id: this.sedeId(),
        profesional_id: this.profesionalId() || undefined,
        servicio_id: this.servicioId() || undefined,
      })
      .subscribe({
        next: (archivo) => {
          const url = URL.createObjectURL(archivo);
          const enlace = document.createElement('a');
          enlace.href = url;
          enlace.download = `resumen-agenda-${desde}.csv`;
          enlace.click();
          enlace.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 1000);
          this.exportando.set(false);
        },
        error: (fallo: unknown) => {
          this.errorExportacion.set(this.aFallo(fallo).message);
          this.exportando.set(false);
        },
      });
  }

  /** Flechas: un día, una semana o un mes según la vista. */
  protected cambiarDia(pasos: number): void {
    const vista = this.vista();
    if (vista === 'mes') {
      this.fecha.update((actual) => {
        const fecha = new Date(`${actual.slice(0, 8)}01T00:00:00Z`);
        fecha.setUTCMonth(fecha.getUTCMonth() + pasos);
        return fecha.toISOString().slice(0, 10);
      });
    } else {
      this.fecha.update((actual) => sumarDias(actual, vista === 'semana' ? pasos * 7 : pasos));
    }
    this.cargarAgenda();
  }

  protected cambiarVista(vista: VistaCalendario | 'lista'): void {
    this.vista.set(vista);
    try {
      localStorage.setItem(CLAVE_VISTA, vista);
    } catch {
      // Sin almacenamiento (ventana privada) la vista simplemente no se recuerda.
    }
    this.cargarRango();
  }

  /** Clic en un día de la semana o del mes: se abre ese día. */
  protected elegirDia(fecha: string): void {
    this.fecha.set(fecha);
    this.vista.set('dia');
    this.cargarAgenda();
  }

  /**
   * Citas de la semana o del mes, de toda la sede. Se pagina porque el API
   * entrega como máximo 200 por petición y un mes con mucha actividad pasa.
   */
  private cargarRango(): void {
    const vista = this.vista();
    if ((vista !== 'semana' && vista !== 'mes') || !this.sedeId() || !this.fecha()) {
      return;
    }
    const solicitud = ++this.solicitudRango;
    const { desde, hasta } = rangoVista(vista, this.fecha());
    const filtro = {
      sede_id: this.sedeId(),
      desde: instanteLocal(desde, '00:00', this.zona()),
      hasta: instanteLocal(hasta, '00:00', this.zona()),
      limite: 200,
    };
    const acumuladas: Cita[] = [];
    this.cargandoRango.set(true);
    const pagina = (desplazamiento: number): void => {
      this.api.citas({ ...filtro, desplazamiento }).subscribe({
        next: (resultado) => {
          if (solicitud !== this.solicitudRango) return;
          acumuladas.push(...resultado.elementos);
          const siguiente = desplazamiento + resultado.elementos.length;
          if (resultado.elementos.length > 0 && siguiente < resultado.total && siguiente < 2000) {
            pagina(siguiente);
          } else {
            this.citasRango.set(acumuladas);
            this.cargandoRango.set(false);
          }
        },
        error: (fallo: unknown) => {
          if (solicitud !== this.solicitudRango) return;
          this.cargandoRango.set(false);
          this.errorAgenda.set(this.aFallo(fallo));
        },
      });
    };
    pagina(0);
  }

  protected irAHoy(): void {
    this.fecha.set(hoyEnZona(this.zona()));
    this.cargarAgenda();
  }

  protected alCambiarEspecialidad(): void {
    // Al cambiar de especialidad, el servicio y el profesional elegidos
    // pueden pertenecer a otra. Se reajustan en lugar de dejar una
    // combinación imposible que produciría una consulta sin turnos y ninguna
    // pista de por qué.
    const especialidad = this.especialidadId();
    const servicio = this.serviciosDeEspecialidad()[0];
    this.servicioId.set(servicio?.id ?? '');
    const profesional = this.profesionalesDeEspecialidad()[0];
    this.profesionalId.set(profesional?.id ?? '');
    if (!especialidad) {
      this.servicioId.set('');
      this.profesionalId.set('');
    }
    this.cargarAgenda();
  }

  protected serviciosDeEspecialidad(): readonly Servicio[] {
    const especialidad = this.especialidadId();
    if (!especialidad) {
      return this.servicios();
    }
    return this.servicios().filter((servicio) => servicio.especialidad_id === especialidad);
  }

  protected profesionalesDeEspecialidad(): readonly Profesional[] {
    const especialidad = this.especialidadId();
    if (!especialidad) {
      return this.profesionales();
    }
    return this.profesionales().filter(
      (profesional) => profesional.especialidad_id === especialidad,
    );
  }

  // ======================================================================
  //  Presentación
  // ======================================================================
  protected hora(instante: string): string {
    return formatearHora(instante, this.zona());
  }

  protected nombrePaciente(id: string): string {
    const paciente = this.pacientes().find((p) => p.id === id);
    return paciente ? `${paciente.nombre} ${paciente.apellido}` : 'Paciente';
  }

  protected nombreProfesional(id: string): string {
    const profesional = this.profesionales().find((p) => p.id === id);
    return profesional ? `${profesional.nombre} ${profesional.apellido}` : 'Profesional';
  }

  protected nombreServicio(id: string): string {
    return this.servicios().find((s) => s.id === id)?.nombre ?? 'Servicio';
  }

  // ======================================================================
  //  Reserva
  // ======================================================================
  protected elegirTurno(turno: TurnoDisponible): void {
    this.turnoElegido.set(turno);
    this.errorReserva.set(null);
    this.mensajeExito.set('');
    // Clave nueva por formulario abierto. Ver la nota del campo.
    this.claveIdempotencia = `reserva-${crypto.randomUUID()}`;
    // La sala elegida puede estar ocupada a la nueva hora.
    if (this.consultorioId() && this.choqueConsultorio(this.consultorioId())) {
      this.consultorioId.set('');
    }
  }

  protected cancelarReserva(): void {
    this.cerrarPanel();
  }

  protected confirmarReserva(): void {
    const turno = this.turnoElegido();
    if (!turno || !this.pacienteId || this.reservando()) {
      return;
    }

    this.reservando.set(true);
    this.errorReserva.set(null);

    const datos = {
      paciente_id: this.pacienteId,
      profesional_id: this.profesionalId(),
      servicio_id: this.servicioId(),
      sede_id: this.sedeId(),
      consultorio_id: this.consultorioId() || null,
      procedimiento_plan_id: this.procedimientoPlanSugerido(),
      inicio: turno.inicio,
      notas_recepcion: this.notas.trim() || null,
    };
    const esSerie = this.serieRecurrente;
    const cantidad = this.cantidadSerie;
    const frecuencia = this.frecuenciaSerie;
    const citas$: Observable<readonly Cita[]> = esSerie
      ? this.api
          .crearSerieCitas({ ...datos, frecuencia, cantidad }, this.claveIdempotencia)
          .pipe(map((respuesta) => respuesta.citas))
      : this.api.crearCita(datos, this.claveIdempotencia).pipe(map((cita) => [cita] as const));

    citas$.subscribe({
        next: (citas) => {
          this.reservando.set(false);
          const primera = citas[0];
          if (!primera) {
            this.errorReserva.set(
              new FalloApi('RESPUESTA_INVALIDA', 'La API no devolvió las citas creadas.', 500),
            );
            return;
          }
          this.mensajeExito.set(esSerie
            ? `Serie de ${cantidad} citas creada para ${this.nombrePaciente(primera.paciente_id)}. La primera es a las ${this.hora(primera.inicio)}.`
            : `Cita creada para ${this.nombrePaciente(primera.paciente_id)} a las ${this.hora(primera.inicio)}.`,
          );
          this.procedimientoPlanSugerido.set(null);
          this.cancelarReserva();
          this.cargarAgenda();
        },
        error: (fallo: unknown) => {
          this.reservando.set(false);
          this.errorReserva.set(this.aFallo(fallo));
          if (this.aFallo(fallo).estado === 409) {
            // El turno se ocupó entre la consulta y el intento. Se recarga
            // para que la lista deje de ofrecerlo: seguir mostrándolo haría
            // que se reintentara con el mismo resultado.
            this.cargarAgenda();
          }
        },
      });
  }

  /** Mensaje del error de reserva, adaptado al caso. */
  protected readonly mensajeErrorReserva = computed(() => {
    const fallo = this.errorReserva();
    if (!fallo) {
      return '';
    }
    if (fallo.estado === 409) {
      if (fallo.message.toLowerCase().includes('serie')) {
        return fallo.message;
      }
      // Un 409 no es un fallo del sistema: es la carrera resuelta por la
      // restricción de exclusión de PostgreSQL.
      if (fallo.message.toLowerCase().includes('consultorio')) {
        return 'Ese consultorio acaba de ocuparse en ese horario. Elija otro o reserve sin sala.';
      }
      return 'Ese turno acaba de ocuparse. La lista se ha actualizado; elija otro.';
    }
    return fallo.message;
  });

  // ======================================================================
  //  Transiciones de estado
  // ======================================================================
  protected pedirCancelacion(cita: Cita): void {
    // Una ventana cada vez: el detalle se cierra y la confirmación ocupa su
    // lugar, con el nombre y la hora a la vista.
    this.citaSeleccionada.set(null);
    this.citaACancelar.set(cita);
    this.motivoCancelacion = '';
  }

  protected descartarCancelacion(): void {
    this.citaACancelar.set(null);
    this.motivoCancelacion = '';
  }

  protected confirmarCancelacion(): void {
    const cita = this.citaACancelar();
    const motivo = this.motivoCancelacion.trim();
    // El motivo es obligatorio y lo exige también la base de datos. Sin él,
    // ante una reclamación no se puede explicar por qué un paciente no fue
    // atendido.
    if (!cita || motivo.length < 3) {
      return;
    }

    this.api.cancelarCita(cita.id, motivo).subscribe({
      next: () => {
        this.descartarCancelacion();
        this.mensajeExito.set('Cita cancelada.');
        this.cargarAgenda();
      },
      error: (fallo: unknown) => {
        this.descartarCancelacion();
        this.errorAgenda.set(this.aFallo(fallo));
      },
    });
  }

  protected abrirReprogramacion(cita: Cita): void {
    this.citaSeleccionada.set(null);
    this.citaAReprogramar.set(cita);
  }

  protected confirmarCita(cita: Cita): void {
    this.ejecutar(() => this.api.confirmarCita(cita.id), 'Cita confirmada.');
  }

  protected alReprogramar(cita: Cita): void {
    this.citaAReprogramar.set(null);
    this.fecha.set(new Intl.DateTimeFormat('en-CA', { timeZone: this.zona(), year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(cita.inicio)));
    this.mensajeExito.set('Cita reprogramada. El cambio quedó registrado en su historial.');
    this.cargarAgenda();
  }

  protected completarCita(cita: Cita): void {
    this.ejecutar(() => this.api.completarCita(cita.id), 'Cita marcada como atendida.');
  }

  protected marcarInasistencia(cita: Cita): void {
    this.ejecutar(
      () => this.api.marcarInasistencia(cita.id),
      'Registrada la inasistencia del paciente.',
    );
  }

  protected registrarLlegada(cita: Cita): void {
    this.ejecutar(() => this.api.registrarLlegadaCita(cita.id), 'Llegada registrada en la sala de espera.');
  }

  protected iniciarAtencion(cita: Cita): void {
    this.ejecutar(() => this.api.iniciarAtencionCita(cita.id), 'Atención iniciada.');
  }

  protected minutosEspera(cita: Cita): number | null {
    if (!cita.llegada_en) return null;
    const fin = cita.atencion_iniciada_en ? new Date(cita.atencion_iniciada_en) : new Date();
    return Math.max(0, Math.floor((fin.getTime() - new Date(cita.llegada_en).getTime()) / 60_000));
  }

  private ejecutar(accion: () => ReturnType<ApiService['confirmarCita']>, exito: string): void {
    this.errorAgenda.set(null);
    accion().subscribe({
      next: () => {
        this.mensajeExito.set(exito);
        this.cargarAgenda();
      },
      error: (fallo: unknown) => this.errorAgenda.set(this.aFallo(fallo)),
    });
  }

  /** Acciones posibles sobre una cita, según su estado. */
  protected accionesDe(cita: Cita): {
    confirmar: boolean;
    cancelar: boolean;
    reprogramar: boolean;
    registrarLlegada: boolean;
    iniciarAtencion: boolean;
    completar: boolean;
    inasistencia: boolean;
  } {
    const abierta = cita.estado === 'PENDING' || cita.estado === 'HELD';
    const viva = abierta || cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED';
    return {
      confirmar: abierta && this.puedeCrear(),
      cancelar: viva && this.puedeCancelar(),
      reprogramar: (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED') && this.sesion.tienePermiso(PERMISOS.citaReprogramar),
      registrarLlegada:
        (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED') &&
        !cita.llegada_en &&
        this.sesion.tienePermiso(PERMISOS.citaRegistrarLlegada),
      iniciarAtencion:
        (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED') &&
        Boolean(cita.llegada_en) &&
        !cita.atencion_iniciada_en &&
        this.sesion.tienePermiso(PERMISOS.citaIniciarAtencion),
      completar:
        (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED') && this.puedeCompletar(),
      inasistencia:
        (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED') &&
        this.puedeInasistencia(),
    };
  }

  private aFallo(error: unknown): FalloApi {
    return error instanceof FalloApi
      ? error
      : new FalloApi('ERROR_DESCONOCIDO', 'Ocurrió un error inesperado.', 0);
  }
}

/** Minutos desde la medianoche local de la sede. */
function minutosLocales(instanteIso: string, zona: string): number {
  const partes = new Intl.DateTimeFormat('en-GB', {
    timeZone: zona,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(instanteIso));
  const hora = Number(partes.find((parte) => parte.type === 'hour')?.value ?? 0);
  const minuto = Number(partes.find((parte) => parte.type === 'minute')?.value ?? 0);
  return hora * 60 + minuto;
}
