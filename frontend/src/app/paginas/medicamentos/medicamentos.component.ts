/**
 * Medicacion y adherencia. Conectada al backend real.
 *
 * Por que es una pantalla distinta de la historia clinica
 * ------------------------------------------------------
 * Hasta ahora `/medicamentos` cargaba el mismo componente que
 * `/historia-clinica`: dos entradas de menu que abrian la misma pantalla. El
 * menu prometia una vista de medicacion y entregaba la historia entera.
 *
 * Lo que hace falta aqui no es el listado de recetas -- eso ya esta en la
 * historia -- sino el **calendario de tomas**: que toca hoy, que quedo sin
 * registrar y como va la adherencia.
 *
 * Lo que esta pantalla tiene que hacer bien
 * -----------------------------------------
 * **Una toma futura no se puede registrar.** Marcar como tomada una dosis que
 * todavia no toca produce un registro de adherencia falso, y ese registro es
 * lo que el profesional mira para decidir. El backend lo rechaza; la interfaz
 * no ofrece el boton siquiera, porque ofrecerlo y que falle es peor.
 *
 * **Una toma pasada sin registrar se distingue de una pendiente futura.** Las
 * dos estan en estado `PENDIENTE`, pero significan cosas opuestas: una es una
 * omision probable y la otra no ha llegado. Mostrarlas igual esconde
 * exactamente lo que hay que ver.
 *
 * **La adherencia se enuncia como recuento, no como juicio.** El backend
 * cuenta omisiones sobre esperadas; no concluye que el tratamiento falle ni
 * sugiere cambiarlo. La pantalla tampoco (CLAUDE.md, regla 5).
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import {
  ApiService,
  FalloApi,
  filtroBusquedaPaciente,
} from '../../nucleo/servicios/api.service';
import type { AlertaAdherencia, PacienteDetalle, Receta, Toma } from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { formatearFechaLarga, formatearHora } from '../../nucleo/utilidades/fechas';

const ZONA = 'America/Guayaquil';
const DIAS_VENTANA = 7;

/** Como se lee cada estado de una toma. */
const ESTADOS: Record<string, { texto: string; tono: string }> = {
  PENDIENTE: { texto: 'Pendiente', tono: 'neutro' },
  TOMADA: { texto: 'Tomada', tono: 'exito' },
  OMITIDA: { texto: 'Omitida', tono: 'peligro' },
  CANCELADA: { texto: 'Cancelada', tono: 'neutro' },
};

/** Una toma con lo que la interfaz necesita decidir sobre ella. */
export interface TomaPresentada {
  readonly toma: Toma;
  /** Cierto cuando su hora ya paso y sigue sin registrarse. */
  readonly vencida: boolean;
  /** Cierto cuando todavia no ha llegado su hora. */
  readonly futura: boolean;
}

@Component({
  selector: 'app-medicamentos',
  standalone: true,
  imports: [FormsModule, CargandoComponent, ErrorComponent, VacioComponent],
  templateUrl: './medicamentos.component.html',
  styleUrl: './medicamentos.component.scss',
})
export class MedicamentosComponent {
  private readonly api = inject(ApiService);
  protected readonly sesion = inject(SesionService);

  // --- Seleccion ---
  protected termino = '';
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly cargandoPacientes = signal(true);
  protected readonly errorPacientes = signal<FalloApi | null>(null);
  protected readonly paciente = signal<PacienteDetalle | null>(null);

  // --- Datos ---
  protected readonly tomas = signal<readonly Toma[]>([]);
  protected readonly recetas = signal<readonly Receta[]>([]);
  protected readonly alertas = signal<readonly AlertaAdherencia[]>([]);
  protected readonly atendiendoAlerta = signal<string | null>(null);
  protected readonly errorAlertas = signal<FalloApi | null>(null);
  protected readonly errorAtendiendoAlerta = signal<FalloApi | null>(null);
  protected readonly cargando = signal(false);
  protected readonly error = signal<FalloApi | null>(null);

  // --- Registro ---
  protected readonly registrando = signal<string | null>(null);
  protected readonly errorRegistro = signal<FalloApi | null>(null);

  /**
   * Instante de referencia para decidir que es pasado.
   *
   * Se fija al cargar y no en cada evaluacion: si se leyera el reloj en cada
   * comprobacion, una toma podria cambiar de «futura» a «vencida» entre que se
   * pinta la fila y se pulsa el boton.
   */
  private readonly ahora = signal(Date.now());

  protected readonly puedeRegistrar = computed(
    () =>
      this.sesion.tienePermiso(PERMISOS.adherenciaLeer) &&
      this.sesion.tienePermiso(PERMISOS.recetaLeer),
  );
  protected readonly hayPaciente = computed(() => this.paciente() !== null);
  protected readonly diasVentana = DIAS_VENTANA;

  /** Tomas clasificadas, en orden cronologico. */
  protected readonly presentadas = computed<readonly TomaPresentada[]>(() => {
    const referencia = this.ahora();
    return this.tomas().map((toma) => {
      const instante = new Date(toma.programada_en).getTime();
      const pendiente = toma.estado === 'PENDIENTE';
      return {
        toma,
        vencida: pendiente && instante <= referencia,
        futura: instante > referencia,
      };
    });
  });

  /**
   * Tomas cuya hora ya paso y siguen sin registrar.
   *
   * Van arriba y separadas: son lo unico de esta pantalla sobre lo que hay
   * que actuar hoy.
   */
  protected readonly vencidas = computed(() => this.presentadas().filter((p) => p.vencida));

  /** Recuento por estado, para la barra de resumen. */
  protected readonly resumen = computed(() => {
    const cuenta = new Map<string, number>();
    for (const { toma } of this.presentadas()) {
      cuenta.set(toma.estado, (cuenta.get(toma.estado) ?? 0) + 1);
    }
    return [...cuenta.entries()].map(([estado, cantidad]) => ({
      estado,
      etiqueta: this.estado(estado).texto,
      tono: this.estado(estado).tono,
      cantidad,
    }));
  });

  constructor() {
    this.cargarPacientes();
  }

  // ======================================================================
  //  Pacientes
  // ======================================================================
  protected cargarPacientes(): void {
    this.cargandoPacientes.set(true);
    this.errorPacientes.set(null);

    const termino = this.termino.trim();
    this.api.pacientes({ ...filtroBusquedaPaciente(termino), limite: 50 }).subscribe({
      next: (pagina) => {
        this.pacientes.set(pagina.elementos);
        this.cargandoPacientes.set(false);
      },
      error: (fallo: FalloApi) => {
        this.errorPacientes.set(fallo);
        this.cargandoPacientes.set(false);
      },
    });
  }

  protected abrir(paciente: Paciente): void {
    this.cargando.set(true);
    this.error.set(null);
    this.tomas.set([]);
    this.recetas.set([]);
    this.alertas.set([]);
    this.errorAlertas.set(null);

    this.api.paciente(paciente.id).subscribe({
      next: (detalle) => {
        this.paciente.set(detalle);
        this.cargar();
      },
      error: (fallo: FalloApi) => {
        this.error.set(fallo);
        this.cargando.set(false);
      },
    });
  }

  protected cerrar(): void {
    this.paciente.set(null);
    this.tomas.set([]);
    this.recetas.set([]);
    this.alertas.set([]);
    this.errorAlertas.set(null);
    this.errorAtendiendoAlerta.set(null);
    this.error.set(null);
    this.errorRegistro.set(null);
  }

  // ======================================================================
  //  Medicacion
  // ======================================================================
  protected cargar(): void {
    const paciente = this.paciente();
    if (!paciente) {
      return;
    }
    this.cargando.set(true);
    this.error.set(null);
    this.ahora.set(Date.now());

    this.api.tomas(paciente.id, DIAS_VENTANA).subscribe({
      next: (tomas) => {
        this.tomas.set(tomas);
        this.cargando.set(false);
      },
      error: (fallo: FalloApi) => {
        this.error.set(fallo);
        this.cargando.set(false);
      },
    });
    if (this.sesion.tienePermiso(PERMISOS.adherenciaLeer)) {
      this.api.alertasAdherencia().subscribe({
        next: (alertas) => this.alertas.set(alertas.filter((alerta) => alerta.paciente_id === paciente.id)),
        error: (fallo: FalloApi) => this.errorAlertas.set(fallo),
      });
    }
  }

  protected atender(alerta: AlertaAdherencia): void {
    this.atendiendoAlerta.set(alerta.id);
    this.errorAtendiendoAlerta.set(null);
    this.api.atenderAlertaAdherencia(alerta.id).subscribe({
      next: () => {
        this.atendiendoAlerta.set(null);
        this.cargar();
      },
      error: (fallo: FalloApi) => {
        this.errorAtendiendoAlerta.set(fallo);
        this.atendiendoAlerta.set(null);
      },
    });
  }

  /**
   * Registra una toma como hecha u omitida.
   *
   * Se recarga la lista al terminar en lugar de mutar la fila en memoria: el
   * backend puede haber rechazado el registro por una razon que la interfaz no
   * conoce, y mostrar un estado que el servidor no tiene es peor que esperar
   * medio segundo.
   */
  protected registrar(toma: Toma, tomada: boolean): void {
    this.registrando.set(toma.id);
    this.errorRegistro.set(null);

    this.api.registrarToma(toma.id, tomada).subscribe({
      next: () => {
        this.registrando.set(null);
        this.cargar();
      },
      error: (fallo: FalloApi) => {
        this.errorRegistro.set(fallo);
        this.registrando.set(null);
      },
    });
  }

  // ======================================================================
  //  Presentacion
  // ======================================================================
  protected estado(clave: string): { texto: string; tono: string } {
    return ESTADOS[clave] ?? { texto: clave, tono: 'neutro' };
  }

  protected dia(valor: string): string {
    return formatearFechaLarga(valor, ZONA);
  }

  protected hora(valor: string): string {
    return formatearHora(valor, ZONA);
  }

  protected nombreCompleto(paciente: PacienteDetalle): string {
    return `${paciente.nombre} ${paciente.apellido}`;
  }
}
