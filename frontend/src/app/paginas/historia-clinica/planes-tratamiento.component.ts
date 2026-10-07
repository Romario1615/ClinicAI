import { Component, computed, effect, inject, input, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FotosClinicasComponent } from '../../compartido/fotos-clinicas.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../nucleo/servicios/api.service';
import { CatalogoService, type ClinicaCatalogo } from '../../nucleo/servicios/catalogo.service';
import type {
  HallazgoResultante,
  PlantillaPlan,
  PlanTratamiento,
  PlanTratamientoNuevo,
  ProcedimientoPlan,
  ProcedimientoPlanNuevo,
} from '../../nucleo/servicios/api.service';
import { esSinAccesoClinico, mensajeFalloClinico } from '../../nucleo/utilidades/acceso-clinico';

/** Opciones del resultado al completar: por cara solo si el procedimiento tiene caras. */
const HALLAZGOS_CARA: readonly { valor: HallazgoResultante; texto: string }[] = [
  { valor: 'OBTURACION_RESINA', texto: 'Obturación de resina' },
  { valor: 'OBTURACION_AMALGAMA', texto: 'Obturación de amalgama' },
  { valor: 'SELLANTE', texto: 'Sellante' },
];
const HALLAZGOS_PIEZA: readonly { valor: HallazgoResultante; texto: string }[] = [
  { valor: 'CORONA', texto: 'Corona' },
  { valor: 'ENDODONCIA', texto: 'Endodoncia' },
  { valor: 'IMPLANTE', texto: 'Implante' },
  { valor: 'PROTESIS_FIJA', texto: 'Prótesis fija' },
  { valor: 'AUSENTE', texto: 'Extracción (pieza ausente)' },
];

/** Accion abierta sobre un plan o un procedimiento, con su formulario. */
type AccionAbierta =
  | { readonly tipo: 'aceptar'; readonly plan: PlanTratamiento }
  | { readonly tipo: 'cancelar-plan'; readonly plan: PlanTratamiento }
  | { readonly tipo: 'completar'; readonly procedimiento: ProcedimientoPlan }
  | { readonly tipo: 'atender-control'; readonly procedimiento: ProcedimientoPlan }
  | { readonly tipo: 'cancelar-procedimiento'; readonly procedimiento: ProcedimientoPlan };

@Component({
  selector: 'app-planes-tratamiento',
  standalone: true,
  imports: [DatePipe, FormsModule, FotosClinicasComponent, VentanaFlotanteComponent],
  templateUrl: './planes-tratamiento.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './planes-tratamiento.component.scss',
})
export class PlanesTratamientoComponent {
  private readonly api = inject(ApiService);
  private readonly catalogo = inject(CatalogoService);
  private readonly router = inject(Router);
  private readonly sesion = inject(SesionService);

  readonly pacienteId = input.required<string>();
  readonly nombrePaciente = input.required<string>();
  readonly puedeEditar = input(false);
  protected readonly puedeLeerSensible = computed(() =>
    this.sesion.tienePermiso(PERMISOS.historiaLeerSensible),
  );
  protected readonly puedeAgendar = computed(() => this.sesion.tienePermiso(PERMISOS.citaCrear));
  protected readonly puedeVerFotos = computed(() =>
    this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer),
  );
  /** Procedimiento cuyas fotos (antes, durante, después) están desplegadas. */
  protected readonly fotosDe = signal<string | null>(null);
  protected readonly planes = signal<readonly PlanTratamiento[]>([]);
  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal('');
  /** La carga devolvió el 404 de acceso clínico: no se ofrece crear nada. */
  protected readonly sinAcceso = signal(false);
  protected readonly exito = signal('');
  protected readonly presupuestoCargando = signal(false);
  protected readonly presupuestoError = signal('');
  protected readonly presupuestoSeleccionado = signal<{
    readonly plan: PlanTratamiento;
    readonly clinica: ClinicaCatalogo;
  } | null>(null);
  protected readonly mostrarFormulario = signal(false);
  protected readonly procedimientos = signal<readonly ProcedimientoPlanNuevo[]>([]);
  protected readonly hoyIso = new Date().toISOString();
  protected readonly total = computed(() =>
    this.procedimientos().reduce((suma, item) => suma + Number(item.precio), 0),
  );

  /** Formulario de accion abierto (aceptar, completar, cancelar). */
  protected readonly accion = signal<AccionAbierta | null>(null);
  protected referenciaAceptacion = '';
  protected motivoCancelacion = '';
  protected hallazgo: HallazgoResultante | '' = '';
  protected controlRecomendadoEn = '';
  protected notaControl = '';
  protected readonly hallazgosCara = HALLAZGOS_CARA;
  protected readonly hallazgosPieza = HALLAZGOS_PIEZA;

  /** Plantillas de la clínica. Se cargan al abrir el borrador por primera vez. */
  protected readonly plantillas = signal<readonly PlantillaPlan[] | null>(null);
  protected plantillaId = '';

  protected titulo = '';
  protected observaciones = '';
  protected nivelSensibilidad: 'N2' | 'N3' = 'N2';
  protected descripcionProcedimiento = '';
  protected fase = 1;
  protected pieza: string | number = '';
  protected caras = '';
  protected precio = '0.00';
  private solicitud = 0;
  private solicitudPresupuesto = 0;

  constructor() {
    effect(() => this.cargar(this.pacienteId()));
  }

  protected cargar(pacienteId: string): void {
    const solicitud = ++this.solicitud;
    this.cargando.set(true);
    this.error.set('');
    this.sinAcceso.set(false);
    this.api.planesTratamiento(pacienteId).subscribe({
      next: (planes) => {
        if (solicitud !== this.solicitud) return;
        this.planes.set(planes);
        this.cargando.set(false);
      },
      error: (fallo: unknown) => {
        if (solicitud !== this.solicitud) return;
        this.sinAcceso.set(esSinAccesoClinico(fallo));
        this.error.set(this.mensaje(fallo));
        this.cargando.set(false);
      },
    });
  }

  protected agregarProcedimiento(): void {
    const descripcion = this.descripcionProcedimiento.trim();
    const importe = Number(this.precio);
    const piezaTexto = String(this.pieza ?? '').trim();
    const pieza = piezaTexto ? Number(piezaTexto) : null;
    // Se aceptan «O, V», «O V» u «OV»: el ejemplo del campo lleva comas.
    const carasTexto = this.caras.toUpperCase().replace(/[\s,;]/g, '');
    const caras = carasTexto ? [...new Set(carasTexto)].join('') : null;
    if (descripcion.length < 3) {
      this.error.set('Describe el procedimiento con al menos 3 caracteres.');
      return;
    }
    if (!Number.isFinite(importe) || importe < 0) {
      this.error.set('El precio debe ser un importe válido igual o mayor que cero.');
      return;
    }
    if (pieza !== null && (!Number.isInteger(pieza) || pieza < 11 || pieza > 85)) {
      this.error.set('La pieza dental debe usar notación FDI.');
      return;
    }
    if (caras && !/^[OMDVL]+$/.test(caras)) {
      this.error.set('Usa caras FDI: O, M, D, V o L.');
      return;
    }
    const nuevas = [...this.procedimientos()];
    this.procedimientos.set([
      ...nuevas,
      {
        fase: this.fase,
        orden: nuevas.filter((item) => item.fase === this.fase).length + 1,
        pieza,
        caras,
        descripcion,
        precio: importe.toFixed(2),
      },
    ]);
    this.descripcionProcedimiento = '';
    this.pieza = '';
    this.caras = '';
    this.precio = '0.00';
    this.error.set('');
  }

  protected quitarProcedimiento(indice: number): void {
    this.procedimientos.update((lista) =>
      lista
        .filter((_, posicion) => posicion !== indice)
        .map((item) => ({
          ...item,
          orden: lista
            .filter((otro, posicion) => otro.fase === item.fase && posicion !== indice)
            .findIndex((otro) => otro === item) + 1,
        })),
    );
  }

  protected guardarBorrador(): void {
    if (this.guardando() || !this.procedimientos().length) return;
    const datos: PlanTratamientoNuevo = {
      titulo: this.titulo.trim(),
      moneda: 'USD',
      observaciones: this.observaciones.trim() || null,
      nivel_sensibilidad: this.nivelSensibilidad,
      procedimientos: this.procedimientos(),
    };
    this.guardando.set(true);
    this.error.set('');
    this.exito.set('');
    this.api.crearPlanTratamiento(this.pacienteId(), datos).subscribe({
      next: (plan) => {
        this.planes.update((planes) => [plan, ...planes]);
        this.reiniciarFormulario();
        this.exito.set('Borrador guardado. Revísalo antes de proponerlo al paciente.');
        this.guardando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(this.mensaje(fallo));
        this.guardando.set(false);
      },
    });
  }

  protected proponer(plan: PlanTratamiento): void {
    if (this.guardando()) return;
    this.guardando.set(true);
    this.error.set('');
    this.api.proponerPlanTratamiento(plan.id).subscribe({
      next: (actualizado) => {
        this.planes.update((planes) =>
          planes.map((actual) => (actual.id === actualizado.id ? actualizado : actual)),
        );
        this.exito.set(
          'Plan propuesto. Cuando el paciente firme el documento, registre aquí la aceptación.',
        );
        this.guardando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(this.mensaje(fallo));
        this.guardando.set(false);
      },
    });
  }

  // ======================================================================
  //  Aceptacion, ejecucion y cancelacion
  // ======================================================================
  protected abrirAccion(accion: AccionAbierta): void {
    this.accion.set(accion);
    this.referenciaAceptacion = '';
    this.motivoCancelacion = '';
    this.hallazgo = '';
    this.controlRecomendadoEn = '';
    this.notaControl = '';
    this.error.set('');
    this.exito.set('');
  }

  /** La accion abierta, si pertenece a este plan o a uno de sus procedimientos. */
  protected accionEnPlan(plan: PlanTratamiento): AccionAbierta | null {
    const accion = this.accion();
    if (!accion) return null;
    if (accion.tipo === 'aceptar' || accion.tipo === 'cancelar-plan') {
      return accion.plan.id === plan.id ? accion : null;
    }
    return plan.procedimientos.some((item) => item.id === accion.procedimiento.id) ? accion : null;
  }

  protected cerrarAccion(): void {
    this.accion.set(null);
  }

  /** Hallazgos que tienen sentido para un procedimiento concreto. */
  protected hallazgosDe(procedimiento: ProcedimientoPlan): readonly {
    valor: HallazgoResultante;
    texto: string;
  }[] {
    if (procedimiento.pieza === null) {
      return [];
    }
    return procedimiento.caras ? [...HALLAZGOS_CARA, ...HALLAZGOS_PIEZA] : HALLAZGOS_PIEZA;
  }

  protected confirmarAccion(): void {
    const accion = this.accion();
    if (!accion || this.guardando()) return;
    let peticion;
    let mensaje: string;
    switch (accion.tipo) {
      case 'aceptar': {
        const referencia = this.referenciaAceptacion.trim();
        if (referencia.length < 3) {
          this.error.set('Indique la referencia del documento firmado por el paciente.');
          return;
        }
        peticion = this.api.aceptarPlanTratamiento(accion.plan.id, referencia);
        mensaje = 'Aceptación registrada con su constancia. Ya se pueden completar procedimientos.';
        break;
      }
      case 'cancelar-plan':
      case 'cancelar-procedimiento': {
        const motivo = this.motivoCancelacion.trim();
        if (motivo.length < 5) {
          this.error.set('Indique el motivo de la cancelación.');
          return;
        }
        peticion =
          accion.tipo === 'cancelar-plan'
            ? this.api.cancelarPlanTratamiento(accion.plan.id, motivo)
            : this.api.cancelarProcedimiento(accion.procedimiento.id, motivo);
        mensaje =
          accion.tipo === 'cancelar-plan'
            ? 'Plan cancelado. Lo ya realizado se conserva.'
            : 'Procedimiento cancelado.';
        break;
      }
      case 'completar':
        peticion = this.api.completarProcedimiento(
          accion.procedimiento.id,
          this.hallazgo || null,
          this.controlRecomendadoEn || null,
        );
        mensaje = this.hallazgo
          ? 'Procedimiento completado. El odontograma tiene una versión nueva con el resultado.'
          : 'Procedimiento completado.';
        if (this.controlRecomendadoEn) mensaje += ' El control quedó programado en el plan.';
        break;
      case 'atender-control':
        peticion = this.api.atenderControlTratamiento(
          accion.procedimiento.id,
          this.notaControl.trim() || null,
        );
        mensaje = 'Control posterior registrado en la historia clínica.';
        break;
    }
    this.guardando.set(true);
    this.error.set('');
    peticion.subscribe({
      next: (actualizado) => {
        this.planes.update((planes) =>
          planes.map((actual) => (actual.id === actualizado.id ? actualizado : actual)),
        );
        this.accion.set(null);
        this.exito.set(mensaje);
        this.guardando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(this.mensaje(fallo));
        this.guardando.set(false);
      },
    });
  }

  /** Primera fase con procedimientos pendientes, o `null` si no queda ninguna. */
  protected siguienteFase(plan: PlanTratamiento): number | null {
    const pendientes = plan.procedimientos
      .filter((item) => item.estado === 'PENDIENTE')
      .map((item) => item.fase);
    return pendientes.length ? Math.min(...pendientes) : null;
  }

  /**
   * Abre la agenda con el paciente preseleccionado. No crea la cita: quien
   * agenda elige el hueco, igual que en cualquier otra reserva.
   */
  protected procedimientosSiguienteFase(plan: PlanTratamiento): readonly ProcedimientoPlan[] {
    const fase = this.siguienteFase(plan);
    return fase === null
      ? []
      : plan.procedimientos.filter(
          (item) =>
            item.fase === fase && item.estado === 'PENDIENTE' && item.cita_id === null,
        );
  }

  protected agendarProcedimiento(plan: PlanTratamiento, procedimiento: ProcedimientoPlan): void {
    void this.router.navigate(['/agenda'], {
      queryParams: {
        paciente: plan.paciente_id,
        procedimiento_plan: procedimiento.id,
      },
    });
  }

  protected etiquetaEstado(estado: string): string {
    return (
      {
        BORRADOR: 'Pendiente de revisión',
        PROPUESTO: 'Propuesto al paciente',
        ACEPTADO: 'Aceptado · en curso',
        COMPLETADO: 'Completado',
        CANCELADO: 'Cancelado',
        PENDIENTE: 'Pendiente',
      } as Record<string, string>
    )[estado] ?? estado;
  }

  protected abrirFormulario(): void {
    this.mostrarFormulario.set(true);
    if (this.mostrarFormulario() && this.plantillas() === null) {
      this.api.plantillasPlan().subscribe({
        next: (lista) => this.plantillas.set(lista),
        error: () => this.plantillas.set([]),
      });
    }
  }

  protected cerrarFormulario(): void {
    if (!this.guardando()) this.reiniciarFormulario();
  }

  /** Copia los procedimientos de la plantilla al borrador. El borrador se puede ajustar. */
  protected usarPlantilla(id: string): void {
    const plantilla = this.plantillas()?.find((p) => p.id === id);
    if (!plantilla) return;
    this.procedimientos.set(plantilla.procedimientos.map((item) => ({ ...item })));
    if (!this.titulo.trim()) this.titulo = plantilla.nombre;
    this.exito.set(`Plantilla «${plantilla.nombre}» cargada. Ajuste piezas e importes si hace falta.`);
  }

  protected guardarComoPlantilla(): void {
    const nombre = this.titulo.trim();
    if (nombre.length < 3 || !this.procedimientos().length || this.guardando()) {
      this.error.set('Ponga un título y al menos un procedimiento para guardar la plantilla.');
      return;
    }
    this.guardando.set(true);
    this.api
      .crearPlantillaPlan({
        nombre,
        descripcion: this.observaciones.trim() || null,
        // Sin pieza ni caras: una plantilla vale para cualquier paciente.
        procedimientos: this.procedimientos().map((item) => ({ ...item, pieza: null, caras: null })),
      })
      .subscribe({
        next: (plantilla) => {
          this.guardando.set(false);
          this.plantillas.update((lista) => [...(lista ?? []), plantilla]);
          this.exito.set(`Plantilla «${plantilla.nombre}» guardada para toda la clínica.`);
        },
        error: (fallo: unknown) => {
          this.guardando.set(false);
          this.error.set(this.mensaje(fallo));
        },
      });
  }

  protected reiniciarFormulario(): void {
    this.mostrarFormulario.set(false);
    this.titulo = '';
    this.observaciones = '';
    this.nivelSensibilidad = 'N2';
    this.procedimientos.set([]);
    this.descripcionProcedimiento = '';
    this.pieza = '';
    this.caras = '';
    this.precio = '0.00';
    this.fase = 1;
  }

  protected dinero(valor: string): string {
    return new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' }).format(Number(valor));
  }

  protected fechaMinimaControl(): string {
    const hoy = new Date();
    const mes = String(hoy.getMonth() + 1).padStart(2, '0');
    const dia = String(hoy.getDate()).padStart(2, '0');
    return `${hoy.getFullYear()}-${mes}-${dia}`;
  }

  protected totalPlan(plan: PlanTratamiento): string {
    return plan.procedimientos
      .reduce((suma, item) => suma + Number(item.precio), 0)
      .toFixed(2);
  }

  protected fechaPresupuesto(fecha: string | null, zona: string): string {
    if (!fecha || Number.isNaN(Date.parse(fecha))) return 'Sin fecha registrada';
    return new Intl.DateTimeFormat('es-EC', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: zona,
    }).format(new Date(fecha));
  }

  /** Carga solo datos públicos de la clínica para imprimir una copia del plan propuesto. */
  protected prepararPresupuesto(plan: PlanTratamiento): void {
    if (plan.estado !== 'PROPUESTO' && plan.estado !== 'ACEPTADO') return;
    const solicitud = ++this.solicitudPresupuesto;
    this.presupuestoSeleccionado.set(null);
    this.presupuestoError.set('');
    this.presupuestoCargando.set(true);
    this.catalogo.clinica().subscribe({
      next: (clinica) => {
        if (solicitud !== this.solicitudPresupuesto) return;
        this.presupuestoSeleccionado.set({ plan, clinica });
        this.presupuestoCargando.set(false);
      },
      error: () => {
        if (solicitud !== this.solicitudPresupuesto) return;
        this.presupuestoError.set('No se pudo cargar la información de la clínica para el presupuesto.');
        this.presupuestoCargando.set(false);
      },
    });
  }

  protected imprimirPresupuesto(): void {
    if (!this.presupuestoSeleccionado()) return;
    document.body.classList.add('imprimiendo-presupuesto');
    try {
      window.print();
    } finally {
      document.body.classList.remove('imprimiendo-presupuesto');
    }
  }

  protected cerrarPresupuesto(): void {
    this.solicitudPresupuesto += 1;
    this.presupuestoCargando.set(false);
    this.presupuestoError.set('');
    this.presupuestoSeleccionado.set(null);
  }

  private mensaje(fallo: unknown): string {
    return mensajeFalloClinico(fallo, 'No se pudo completar la operación del plan. Inténtalo de nuevo.');
  }
}
