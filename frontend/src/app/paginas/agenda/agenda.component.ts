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
import { Component, computed, inject, signal } from '@angular/core';
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
import { InsigniaEstadoComponent } from '../../compartido/insignia-estado.component';
import { ReprogramarCitaComponent } from './reprogramar-cita.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
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

@Component({
  selector: 'app-agenda',
  standalone: true,
  imports: [
    FormsModule,
    CargandoComponent,
    ErrorComponent,
    VacioComponent,
    ColaTrabajoComponent,
    FichaPacienteComponent,
    InsigniaEstadoComponent,
    ReprogramarCitaComponent,
  ],
  templateUrl: './agenda.component.html',
  styleUrl: './agenda.component.scss',
})
export class AgendaComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  private readonly operaciones = inject(OperacionesService);
  protected readonly sesion = inject(SesionService);

  // --- Catálogo ---
  protected readonly sedes = signal<readonly Sede[]>([]);
  protected readonly especialidades = signal<readonly Especialidad[]>([]);
  protected readonly servicios = signal<readonly Servicio[]>([]);
  protected readonly profesionales = signal<readonly Profesional[]>([]);
  protected readonly pacientes = signal<readonly Paciente[]>([]);

  // --- Selección ---
  protected readonly sedeId = signal('');
  protected readonly especialidadId = signal('');
  protected readonly servicioId = signal('');
  protected readonly profesionalId = signal('');
  protected readonly fecha = signal('');

  // --- Estado de carga ---
  protected readonly cargandoCatalogo = signal(true);
  protected readonly cargandoAgenda = signal(false);
  protected readonly errorCatalogo = signal<FalloApi | null>(null);
  protected readonly errorAgenda = signal<FalloApi | null>(null);

  // --- Datos ---
  protected readonly citas = signal<readonly Cita[]>([]);
  protected readonly disponibilidad = signal<Disponibilidad | null>(null);

  // --- Reserva ---
  protected readonly turnoElegido = signal<TurnoDisponible | null>(null);
  protected pacienteId = '';
  protected notas = '';
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

  // --- Panel contextual ---
  //
  // La columna derecha hace tres trabajos y nunca dos a la vez: la cola de
  // pendientes mientras no hay nada elegido, el formulario de reserva al
  // pulsar un hueco, y el detalle al pulsar una cita. Eso es lo que permite
  // quitar la columna de cinco botones por fila que tenía la tabla.
  protected readonly huecoElegido = signal<(FilaDia & { tipo: 'hueco' }) | null>(null);
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

  protected readonly panelActivo = computed<'atencion' | 'reservar' | 'cita'>(() => {
    if (this.huecoElegido()) {
      return 'reservar';
    }
    return this.citaSeleccionada() ? 'cita' : 'atencion';
  });

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

  protected readonly zona = computed(
    () => this.sedes().find((sede) => sede.id === this.sedeId())?.zona_horaria ?? 'America/Guayaquil',
  );

  protected readonly puedeCrear = computed(() => this.sesion.tienePermiso(PERMISOS.citaCrear));
  protected readonly puedeCancelar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.citaCancelar),
  );
  protected readonly puedeCompletar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.citaCompletar),
  );
  protected readonly puedeInasistencia = computed(() =>
    this.sesion.tienePermiso(PERMISOS.citaInasistencia),
  );

  protected readonly fechaLegible = computed(() => {
    const fecha = this.fecha();
    if (!fecha) {
      return '';
    }
    return formatearFechaLarga(`${fecha}T12:00:00Z`, this.zona());
  });

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
        this.citas.set(resultado.citas);
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
    const citas$ = this.api.citas({
      desde,
      hasta,
      sede_id: this.sedeId(),
      profesional_id: this.profesionalId() || undefined,
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
      },
      error: (fallo: unknown) => {
        this.cargandoCatalogo.set(false);
        this.errorCatalogo.set(this.aFallo(fallo));
      },
    });
  }

  protected cargarAgenda(): void {
    if (!this.sedeId() || !this.fecha()) {
      return;
    }
    this.cargandoAgenda.set(true);
    this.errorAgenda.set(null);
    this.cerrarPanel();
    this.cargarOfertasSinAvisar();
    // El `switchMap` del constructor cancela la carga anterior: solo se aplica
    // la respuesta de la seleccion vigente.
    this.recargar.next();
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
  //  Panel contextual
  // ======================================================================
  protected abrirHueco(fila: FilaDia): void {
    if (fila.tipo !== 'hueco' || !this.puedeCrear()) {
      return;
    }
    this.citaSeleccionada.set(null);
    this.huecoElegido.set(fila);
    // El tramo es un rango; la reserva necesita un punto. Se preselecciona el
    // primer arranque y se dejan los demás a un clic.
    this.elegirTurno(fila.turnos[0]);
  }

  protected abrirCita(cita: Cita): void {
    this.huecoElegido.set(null);
    this.turnoElegido.set(null);
    this.citaSeleccionada.set(cita);
  }

  protected cerrarPanel(): void {
    this.huecoElegido.set(null);
    this.citaSeleccionada.set(null);
    this.turnoElegido.set(null);
    this.pacienteId = '';
    this.notas = '';
    this.errorReserva.set(null);
  }

  protected abrirFicha(pacienteId: string): void {
    this.pacienteEnFicha.set(pacienteId);
  }

  protected cerrarFicha(): void {
    this.pacienteEnFicha.set(null);
  }

  /** El botón principal de una tarea de la cola. */
  protected atenderTarea(tarea: TareaPendiente): void {
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
    const primera = this.citas().find((cita) => cita.id === tarea.citas[0]);
    if (primera) {
      this.abrirCita(primera);
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
  protected cambiarDia(dias: number): void {
    this.fecha.update((actual) => sumarDias(actual, dias));
    this.cargarAgenda();
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

    this.api
      .crearCita(
        {
          paciente_id: this.pacienteId,
          profesional_id: this.profesionalId(),
          servicio_id: this.servicioId(),
          sede_id: this.sedeId(),
          inicio: turno.inicio,
          notas_recepcion: this.notas.trim() || null,
        },
        this.claveIdempotencia,
      )
      .subscribe({
        next: (cita) => {
          this.reservando.set(false);
          this.mensajeExito.set(
            `Cita creada para ${this.nombrePaciente(cita.paciente_id)} a las ${this.hora(cita.inicio)}.`,
          );
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
      // Un 409 no es un fallo del sistema: es la carrera resuelta por la
      // restricción de exclusión de PostgreSQL.
      return 'Ese turno acaba de ocuparse. La lista se ha actualizado; elija otro.';
    }
    return fallo.message;
  });

  // ======================================================================
  //  Transiciones de estado
  // ======================================================================
  protected pedirCancelacion(cita: Cita): void {
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
    completar: boolean;
    inasistencia: boolean;
  } {
    const abierta = cita.estado === 'PENDING' || cita.estado === 'HELD';
    const viva = abierta || cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED';
    return {
      confirmar: abierta && this.puedeCrear(),
      cancelar: viva && this.puedeCancelar(),
      reprogramar: (cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED') && this.sesion.tienePermiso(PERMISOS.citaReprogramar),
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
