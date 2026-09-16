/**
 * La cola de trabajo del día, compartida por toda la aplicación.
 *
 * Por qué es un servicio y no cálculo de cada pantalla
 * ---------------------------------------------------
 * La misma pregunta —«¿qué se rompe hoy si nadie lo toca?»— aparece en tres
 * sitios: la insignia del menú, el bloque que abre el panel y la columna
 * derecha de la agenda. Calculada tres veces, un día divergen y quien mira el
 * menú ve un número que no cuadra con lo que hay dentro.
 *
 * El alcance es **hoy y toda la clínica** dentro del ámbito del usuario, no el
 * día que se esté mirando en la agenda. Una insignia que cambiara al navegar a
 * la semana que viene no sería un aviso, sería ruido.
 *
 * Degradación por permiso
 * -----------------------
 * Un usuario sin `lista_espera.gestionar` no puede leer las ofertas, y uno sin
 * `agenda.leer` no puede leer las citas. En ambos casos la cola queda con lo
 * que sí se puede ver, sin error: la pantalla que la usa sigue sirviendo.
 */
import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiService } from './api.service';
import { PERMISOS } from './configuracion';
import { OperacionesService, type EntradaEspera, type Pagina } from './operaciones.service';
import { SesionService } from './sesion.service';
import type { Cita } from '../modelos/dominio';
import { derivarPendientes, type TareaPendiente } from '../utilidades/pendientes';
import { hoyEnZona, rangoDelDia } from '../utilidades/fechas';

@Injectable({ providedIn: 'root' })
export class PendientesService {
  private readonly api = inject(ApiService);
  private readonly operaciones = inject(OperacionesService);
  private readonly sesion = inject(SesionService);

  private readonly citas = signal<readonly Cita[]>([]);
  private readonly ofertas = signal<readonly EntradaEspera[]>([]);
  private readonly nombres = signal<ReadonlyMap<string, string>>(new Map());

  readonly cargando = signal(false);

  /** Las tareas con plazo de hoy, ya ordenadas por urgencia. */
  readonly tareas = computed<readonly TareaPendiente[]>(() =>
    derivarPendientes({
      citas: this.citas(),
      ofertasSinAvisar: this.ofertas(),
      ahora: new Date(),
      nombrePaciente: (id) => this.nombres().get(id) ?? `Paciente ${id.slice(0, 8)}`,
    }),
  );

  /** Lo que muestra la insignia del menú. Cero significa cero, no «sin datos». */
  readonly cuenta = computed(() => this.tareas().length);

  /** Citas de hoy en el ámbito del usuario. Las usa el panel para la carga. */
  readonly citasDeHoy = this.citas.asReadonly();

  /**
   * Refresca la cola.
   *
   * Se llama al arrancar y después de cada acción que pueda cambiarla
   * (confirmar, cancelar, reservar). No se refresca por temporizador: un
   * reloj que recarga solo hace que el número baile mientras alguien lo lee.
   */
  cargar(zona = 'America/Guayaquil'): void {
    if (!this.sesion.tienePermiso(PERMISOS.agendaLeer)) {
      this.citas.set([]);
      this.ofertas.set([]);
      return;
    }

    this.cargando.set(true);
    const { desde, hasta } = rangoDelDia(hoyEnZona(zona), zona);

    this.api.citas({ desde, hasta, limite: 200 }).subscribe({
      next: (pagina) => {
        this.citas.set(pagina.elementos);
        this.cargando.set(false);
        this.resolverNombres(pagina.elementos);
      },
      error: () => {
        this.citas.set([]);
        this.cargando.set(false);
      },
    });

    if (this.sesion.tienePermiso(PERMISOS.listaEsperaGestionar)) {
      this.operaciones
        .leer<Pagina<EntradaEspera>>('/lista-espera/', { limite: 25, solo_sin_avisar: true })
        .subscribe({
          next: (pagina) => this.ofertas.set(pagina.elementos),
          error: () => this.ofertas.set([]),
        });
    }
  }

  /**
   * Nombres de los pacientes que aparecen en la cola.
   *
   * Solo se piden los que hacen falta —los de las citas con plazo—, no el
   * listado entero: la clínica de pruebas tiene doscientos pacientes y pedir
   * los cien primeros dejaba a la mitad mostrándose como «Paciente».
   */
  private resolverNombres(citas: readonly Cita[]): void {
    if (!this.sesion.tienePermiso(PERMISOS.pacienteLeer)) {
      return;
    }
    const interesan = new Set(
      citas
        .filter((cita) => cita.estado === 'HELD' || cita.estado === 'PENDING')
        .map((cita) => cita.paciente_id),
    );
    for (const id of interesan) {
      if (this.nombres().has(id)) {
        continue;
      }
      this.api.paciente(id).subscribe({
        next: (paciente) => {
          this.nombres.update((actual) => {
            const copia = new Map(actual);
            copia.set(id, `${paciente.nombre} ${paciente.apellido}`);
            return copia;
          });
        },
        // Sin permiso de ficha se queda el identificador recortado. Es peor
        // que un nombre y mejor que ocultar la tarea.
        error: () => undefined,
      });
    }
  }

  /** Nombre resuelto de un paciente, para quien ya tenga la cola cargada. */
  nombre(id: string): string {
    return this.nombres().get(id) ?? `Paciente ${id.slice(0, 8)}`;
  }
}
