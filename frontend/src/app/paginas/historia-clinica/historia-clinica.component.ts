/**
 * Historia clinica. Conectada al backend real.
 *
 * Lo que esta pantalla tiene que hacer bien
 * -----------------------------------------
 * **Tiene que degradar por rol, sin filtrar que existe lo que no se puede
 * ver.** Los permisos clinicos no van juntos: un asistente tiene `receta.leer`
 * y `adherencia.leer` pero **no** `historia_clinica.leer`. Esta pantalla le
 * muestra las recetas y le dice que las notas no estan a su alcance, en lugar
 * de enviar una peticion que devolvera 403 y pintar un error rojo como si algo
 * se hubiera roto.
 *
 * **No puede presentar una pauta «cuando sea necesario» como pauta fija.** Un
 * PRN no genera horarios, y confundirlos es un error de medicacion. Se marca
 * de forma explicita, no por omision del campo de frecuencia.
 *
 * **Tiene que enseñar que la historia no se borra.** Las versiones antiguas se
 * conservan con su autor, su fecha y el motivo del cambio. Si la interfaz solo
 * mostrara la version vigente, la garantia append-only existiria en la base y
 * no serviria de nada a quien tiene que auditarla.
 *
 * **Una receta suspendida sigue visible, con su motivo.** Ocultarla daria la
 * impresion de que nunca existio, y lo que se necesita saber es justo lo
 * contrario: que existio y por que se retiro.
 *
 * Lo que todavia no hace
 * ----------------------
 * Escribir notas, crear recetas, confirmarlas ni registrar tomas. Los
 * endpoints existen y estan probados. Escribir historia clinica desde una
 * interfaz a medio construir es la clase de cosa que no se hace con prisa:
 * queda para cuando la pantalla tenga su propio recorrido de revision.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import {
  CargandoComponent,
  ErrorComponent,
  VacioComponent,
} from '../../compartido/estados.component';
import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type {
  Medicamento,
  Nota,
  PacienteDetalle,
  Receta,
} from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { formatearFechaLarga, formatearHora } from '../../nucleo/utilidades/fechas';

/** Zona de presentacion. La real viene de la sede; esta es la de la clinica. */
const ZONA = 'America/Guayaquil';

/** Como se lee cada estado de receta, y que implica. */
const ESTADOS_RECETA: Record<string, { texto: string; tono: string; detalle: string }> = {
  BORRADOR: {
    texto: 'Borrador',
    tono: 'neutro',
    detalle: 'Sin confirmar. No genera recordatorios ni cuenta como indicacion vigente.',
  },
  CONFIRMADA: {
    texto: 'Confirmada',
    tono: 'exito',
    detalle: 'Confirmada por el profesional. Es la unica que genera calendario de tomas.',
  },
  SUSPENDIDA: {
    texto: 'Suspendida',
    tono: 'peligro',
    detalle: 'Retirada. Se conserva con su motivo: el historial no se borra.',
  },
};

const VIAS: Record<string, string> = {
  ORAL: 'via oral',
  TOPICA: 'via topica',
  INHALATORIA: 'via inhalatoria',
  OFTALMICA: 'via oftalmica',
  OTICA: 'via otica',
  NASAL: 'via nasal',
  RECTAL: 'via rectal',
  SUBCUTANEA: 'via subcutanea',
  INTRAMUSCULAR: 'via intramuscular',
  INTRAVENOSA: 'via intravenosa',
};

@Component({
  selector: 'app-historia-clinica',
  standalone: true,
  imports: [FormsModule, CargandoComponent, ErrorComponent, VacioComponent],
  templateUrl: './historia-clinica.component.html',
  styleUrl: './historia-clinica.component.scss',
})
export class HistoriaClinicaComponent {
  private readonly api = inject(ApiService);
  protected readonly sesion = inject(SesionService);

  // --- Seleccion de paciente ---
  protected termino = '';
  protected readonly pacientes = signal<readonly Paciente[]>([]);
  protected readonly cargandoPacientes = signal(true);
  protected readonly errorPacientes = signal<FalloApi | null>(null);
  protected readonly paciente = signal<PacienteDetalle | null>(null);

  // --- Historia ---
  protected readonly notas = signal<readonly Nota[]>([]);
  protected readonly recetas = signal<readonly Receta[]>([]);
  protected readonly incluirHistorico = signal(false);
  protected readonly cargandoHistoria = signal(false);
  protected readonly errorHistoria = signal<FalloApi | null>(null);
  /** Cierto cuando el backend nego las notas por permiso, no por un fallo. */
  protected readonly notasDenegadas = signal(false);

  // --- Permisos ---
  // Se leen del principal, no se adivinan: el backend es la autoridad y
  // ocultar lo que no se puede pedir evita peticiones que van a dar 403.
  protected readonly puedeLeerNotas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaLeer),
  );
  protected readonly puedeLeerRecetas = computed(() =>
    this.sesion.tienePermiso(PERMISOS.recetaLeer),
  );

  protected readonly hayPaciente = computed(() => this.paciente() !== null);

  /** Notas agrupadas por su raiz, con la vigente primero. */
  protected readonly historias = computed(() => {
    const porRaiz = new Map<string, Nota[]>();
    for (const nota of this.notas()) {
      const grupo = porRaiz.get(nota.raiz_id) ?? [];
      grupo.push(nota);
      porRaiz.set(nota.raiz_id, grupo);
    }
    return [...porRaiz.values()]
      .map((versiones) => {
        const ordenadas = [...versiones].sort((a, b) => b.version - a.version);
        return {
          raizId: ordenadas[0].raiz_id,
          vigente: ordenadas.find((n) => n.vigente) ?? ordenadas[0],
          anteriores: ordenadas.filter((n) => !n.vigente),
        };
      })
      .sort(
        (a, b) =>
          new Date(b.vigente.creado_en).getTime() - new Date(a.vigente.creado_en).getTime(),
      );
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
    this.api.pacientes({ termino: termino || undefined, limite: 50 }).subscribe({
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
    this.cargandoHistoria.set(true);
    this.errorHistoria.set(null);
    this.notasDenegadas.set(false);
    this.notas.set([]);
    this.recetas.set([]);

    this.api.paciente(paciente.id).subscribe({
      next: (detalle) => {
        this.paciente.set(detalle);
        this.cargarHistoria();
      },
      error: (fallo: FalloApi) => {
        this.errorHistoria.set(fallo);
        this.cargandoHistoria.set(false);
      },
    });
  }

  protected cerrar(): void {
    this.paciente.set(null);
    this.notas.set([]);
    this.recetas.set([]);
    this.errorHistoria.set(null);
    this.notasDenegadas.set(false);
  }

  // ======================================================================
  //  Historia
  // ======================================================================
  /**
   * Carga notas y recetas a la vez.
   *
   * Cada rama absorbe su propio 403 en lugar de tumbar la carga entera: un
   * asistente puede ver las recetas y no las notas, y fallar del todo le
   * dejaria sin lo que si tiene derecho a consultar. Un 403 aqui no es un
   * error del sistema, es el control funcionando.
   */
  protected cargarHistoria(): void {
    const paciente = this.paciente();
    if (!paciente) {
      return;
    }

    this.cargandoHistoria.set(true);
    this.errorHistoria.set(null);

    forkJoin({
      notas: this.puedeLeerNotas()
        ? this.api.notas(paciente.id, this.incluirHistorico()).pipe(
            catchError((fallo: FalloApi) => {
              if (fallo.estado === 403) {
                this.notasDenegadas.set(true);
                return of([] as readonly Nota[]);
              }
              throw fallo;
            }),
          )
        : of([] as readonly Nota[]),
      recetas: this.puedeLeerRecetas()
        ? this.api
            .recetas(paciente.id)
            .pipe(catchError(() => of([] as readonly Receta[])))
        : of([] as readonly Receta[]),
    }).subscribe({
      next: (datos) => {
        this.notas.set(datos.notas);
        this.recetas.set(datos.recetas);
        this.cargandoHistoria.set(false);
      },
      error: (fallo: FalloApi) => {
        this.errorHistoria.set(fallo);
        this.cargandoHistoria.set(false);
      },
    });
  }

  protected alternarHistorico(): void {
    this.incluirHistorico.update((valor) => !valor);
    this.cargarHistoria();
  }

  // ======================================================================
  //  Presentacion
  // ======================================================================
  protected estadoReceta(clave: string): { texto: string; tono: string; detalle: string } {
    return (
      ESTADOS_RECETA[clave] ?? {
        texto: clave,
        tono: 'neutro',
        detalle: 'Estado desconocido.',
      }
    );
  }

  /**
   * Como se lee la pauta de un medicamento.
   *
   * El PRN se enuncia de forma explicita y nunca se le calcula una frecuencia.
   * Escribir «cada 8 horas» sobre algo que el paciente solo debe tomar si lo
   * necesita es convertir una indicacion a demanda en una pauta fija.
   */
  protected pauta(medicamento: Medicamento): string {
    if (medicamento.cuando_sea_necesario) {
      return 'Solo cuando sea necesario. Sin horario fijo.';
    }
    const partes: string[] = [];
    if (medicamento.frecuencia_horas) {
      partes.push(`cada ${medicamento.frecuencia_horas} h`);
    }
    if (medicamento.duracion_dias) {
      partes.push(`durante ${medicamento.duracion_dias} dias`);
    }
    return partes.length > 0 ? partes.join(', ') : 'Sin pauta registrada';
  }

  protected via(clave: string): string {
    return VIAS[clave] ?? clave.toLowerCase();
  }

  protected fecha(valor: string | null): string {
    if (!valor) {
      return '—';
    }
    return `${formatearFechaLarga(valor, ZONA)}, ${formatearHora(valor, ZONA)}`;
  }

  protected nombreCompleto(paciente: PacienteDetalle): string {
    return `${paciente.nombre} ${paciente.apellido}`;
  }
}
