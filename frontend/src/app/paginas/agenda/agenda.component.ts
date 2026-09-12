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
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import { InsigniaEstadoComponent } from '../../compartido/insignia-estado.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
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
    InsigniaEstadoComponent,
  ],
  templateUrl: './agenda.component.html',
  styleUrl: './agenda.component.scss',
})
export class AgendaComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
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

  constructor() {
    this.cargarCatalogo();
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
    this.turnoElegido.set(null);

    const { desde, hasta } = rangoDelDia(this.fecha(), this.zona());

    const citas$ = this.api.citas({
      desde,
      hasta,
      sede_id: this.sedeId(),
      profesional_id: this.profesionalId() || undefined,
      limite: 200,
    });

    if (this.seleccionIncompleta()) {
      // Sin servicio ni profesional se puede mostrar la agenda del día, pero
      // no calcular disponibilidad: el motor necesita saber de qué servicio
      // y de quién.
      citas$.subscribe({
        next: (pagina) => {
          this.citas.set(pagina.elementos);
          this.disponibilidad.set(null);
          this.cargandoAgenda.set(false);
        },
        error: (fallo: unknown) => {
          this.cargandoAgenda.set(false);
          this.errorAgenda.set(this.aFallo(fallo));
        },
      });
      return;
    }

    forkJoin({
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
    }).subscribe({
      next: (datos) => {
        this.citas.set(datos.citas.elementos);
        this.disponibilidad.set(datos.disponibilidad);
        this.cargandoAgenda.set(false);
      },
      error: (fallo: unknown) => {
        this.cargandoAgenda.set(false);
        this.errorAgenda.set(this.aFallo(fallo));
      },
    });
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
    this.turnoElegido.set(null);
    this.pacienteId = '';
    this.notas = '';
    this.errorReserva.set(null);
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
    completar: boolean;
    inasistencia: boolean;
  } {
    const abierta = cita.estado === 'PENDING' || cita.estado === 'HELD';
    const viva = abierta || cita.estado === 'CONFIRMED' || cita.estado === 'RESCHEDULED';
    return {
      confirmar: abierta && this.puedeCrear(),
      cancelar: viva && this.puedeCancelar(),
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
