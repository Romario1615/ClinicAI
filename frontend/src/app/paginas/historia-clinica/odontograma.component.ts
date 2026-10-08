/**
 * Odontograma interactivo.
 *
 * Cada pieza se dibuja con sus cinco caras clicables. Se elige un hallazgo en
 * la paleta («pincel») y se pinta sobre la cara o la pieza; con «Seleccionar»
 * solo se abre la pieza. Al abrir una pieza se abre, en una ventana lateral,
 * su ficha de registro (hallazgos, nota) y su historial: cambios por versión,
 * procedimientos del plan y fotos. Con un pincel activo el clic pinta y no
 * abre nada: abrir una ventana a cada pincelada impediría pintar seguido.
 *
 * Nada se guarda al pintar: los cambios quedan en un borrador y se guardan
 * juntos como una versión nueva, con motivo obligatorio. Las versiones son
 * inmutables en la base de datos; una versión antigua se consulta en solo
 * lectura.
 */
import { Component, computed, effect, inject, input, signal, viewChild, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../../nucleo/servicios/api.service';
import type {
  CaraOdontologica,
  ContenidoOdontograma,
  Denticion,
  EstadoPiezaOdontograma,
  HallazgoCara,
  HallazgoPieza,
  Odontograma,
  PlanTratamiento,
} from '../../nucleo/servicios/api.service';
import { PERMISOS } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { HistorialPiezaComponent } from './historial-pieza.component';
import { IconoComponent } from '../../compartido/icono.component';
import { VentanaFlotanteComponent } from '../../compartido/ventana-flotante.component';
import {
  CARAS,
  GRUPOS_FDI,
  HALLAZGOS_CARA,
  HALLAZGOS_PIEZA,
  PIEZA_VACIA,
  type Region,
  caraEnRegion,
  describirEstado,
  mismoEstado,
  nombreHallazgoCara,
} from './odontograma.vocabulario';
import { falloClinicoLegible } from '../../nucleo/utilidades/acceso-clinico';
import { CapturaFotosComponent, type FotoSeleccionada } from '../../compartido/captura-fotos.component';
import { FotosRegistroComponent } from '../../compartido/fotos-registro.component';
import { FotosRegistroService } from '../../nucleo/servicios/fotos-registro.service';

/** Herramienta activa de la paleta. */
export type Herramienta = 'SELECCIONAR' | 'BORRAR' | HallazgoCara | HallazgoPieza;

/** Regiones del dibujo de 40×40: cuatro trapecios y el cuadrado central. */
const REGIONES: readonly { region: Region; puntos: string }[] = [
  { region: 'arriba', puntos: '0,0 40,0 28,12 12,12' },
  { region: 'abajo', puntos: '12,28 28,28 40,40 0,40' },
  { region: 'izquierda', puntos: '0,0 12,12 12,28 0,40' },
  { region: 'derecha', puntos: '40,0 40,40 28,28 28,12' },
  { region: 'centro', puntos: '12,12 28,12 28,28 12,28' },
];

/** Movimiento de teclado entre las cinco superficies dibujadas. */
const REGION_POR_FLECHA: Readonly<Record<Region, Readonly<Record<string, Region>>>> = {
  arriba: { ArrowDown: 'centro', ArrowLeft: 'izquierda', ArrowRight: 'derecha' },
  abajo: { ArrowUp: 'centro', ArrowLeft: 'izquierda', ArrowRight: 'derecha' },
  izquierda: { ArrowRight: 'centro', ArrowUp: 'arriba', ArrowDown: 'abajo' },
  derecha: { ArrowLeft: 'centro', ArrowUp: 'arriba', ArrowDown: 'abajo' },
  centro: { ArrowUp: 'arriba', ArrowDown: 'abajo', ArrowLeft: 'izquierda', ArrowRight: 'derecha' },
};

const ES_HALLAZGO_CARA = new Set<string>(HALLAZGOS_CARA.map((h) => h.codigo));
const ES_HALLAZGO_PIEZA = new Set<string>(HALLAZGOS_PIEZA.map((h) => h.codigo));

@Component({
  selector: 'app-odontograma',
  standalone: true,
  imports: [CapturaFotosComponent, FotosRegistroComponent, FormsModule, DatePipe, NgTemplateOutlet, HistorialPiezaComponent, IconoComponent, VentanaFlotanteComponent],
  templateUrl: './odontograma.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './odontograma.component.scss',
})
export class OdontogramaComponent {
  readonly pacienteId = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);
  protected readonly operacionFotos = inject(FotosRegistroService).operacion<Odontograma>();
  protected fotos: readonly FotoSeleccionada[] = [];
  private readonly capturaFotos = viewChild(CapturaFotosComponent);
  protected readonly puedeLeerFotos = this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer);
  protected readonly puedeCargarFotos = this.sesion.tienePermiso(PERMISOS.imagenClinicaCargar);

  protected readonly puedeEditar = this.sesion.tienePermiso(PERMISOS.odontogramaEscribir);
  protected readonly puedeLeerSensible = this.sesion.tienePermiso(PERMISOS.historiaLeerSensible);
  private readonly puedeVerPlanes = this.sesion.tienePermiso(PERMISOS.planTratamientoLeer);
  protected readonly denticion = signal<Denticion>('PERMANENTE');
  protected readonly actual = signal<Odontograma | null>(null);
  protected readonly versiones = signal<readonly Odontograma[]>([]);
  protected readonly planes = signal<readonly PlanTratamiento[]>([]);
  protected readonly seleccionada = signal<number | null>(null);
  /** La ficha de la pieza seleccionada está abierta en su ventana. */
  protected readonly fichaPieza = signal(false);
  protected readonly herramienta = signal<Herramienta>('SELECCIONAR');
  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly motivo = signal('');
  protected readonly nivelSensibilidad = signal<'N2' | 'N3'>('N2');
  protected readonly error = signal<FalloApi | string | null>(null);
  protected readonly aviso = signal('');
  protected readonly borrador = signal<Record<string, EstadoPiezaOdontograma>>({});
  /** Hay algo que dibujar: terminó la carga y no falló sin datos previos. */
  protected readonly listo = computed(
    () => !this.cargando() && !(this.error() !== null && !this.actual() && this.versiones().length === 0),
  );
  protected readonly errorTexto = computed(() => {
    const error = this.error();
    return error instanceof Error ? error.message : error ?? '';
  });
  protected readonly conflicto = computed(() => {
    const error = this.error();
    return error instanceof FalloApi && error.estado === 409;
  });
  protected readonly grupos = computed(() => GRUPOS_FDI[this.denticion()]);
  protected readonly superiores = computed(() => this.grupos().slice(0, 2));
  protected readonly inferiores = computed(() => this.grupos().slice(2, 4));
  protected readonly caras = CARAS;
  protected readonly hallazgosPieza = HALLAZGOS_PIEZA;
  protected readonly hallazgosCara = HALLAZGOS_CARA;
  protected readonly regiones = REGIONES;
  protected readonly puedeGuardar = computed(
    () => this.puedeEditar && !this.guardando() && (this.actual()?.vigente ?? true),
  );
  protected readonly estadoSeleccionado = computed(() => {
    const codigo = this.seleccionada();
    return codigo === null ? PIEZA_VACIA : (this.borrador()[String(codigo)] ?? PIEZA_VACIA);
  });
  /** Piezas cuyo borrador difiere de la versión mostrada: cambios sin guardar. */
  protected readonly cambiadas = computed(() => {
    const base = this.actual()?.piezas ?? {};
    const borrador = this.borrador();
    const codigos = new Set([...Object.keys(base), ...Object.keys(borrador)]);
    return new Set(
      [...codigos].filter((codigo) => !mismoEstado(base[codigo], borrador[codigo])).map(Number),
    );
  });

  constructor() {
    effect(() => {
      const pacienteId = this.pacienteId();
      this.cargar(pacienteId);
      if (this.puedeVerPlanes) this.cargarPlanes(pacienteId);
    });
  }

  protected cargar(pacienteId = this.pacienteId()): void {
    this.cargando.set(true);
    this.error.set(null);
    this.aviso.set('');
    this.api.versionesOdontograma(pacienteId).subscribe({
      next: (versiones) => {
        this.versiones.set(versiones);
        const vigente = versiones.find((version) => version.vigente) ?? null;
        this.actual.set(vigente);
        this.nivelSensibilidad.set(vigente?.nivel_sensibilidad ?? 'N2');
        this.denticion.set(vigente?.denticion ?? 'PERMANENTE');
        this.borrador.set(vigente ? this.clonarPiezas(vigente.piezas) : {});
        this.cargando.set(false);
      },
      error: (fallo: FalloApi) => {
        this.error.set(falloClinicoLegible(fallo));
        this.cargando.set(false);
      },
    });
  }

  private cargarPlanes(pacienteId: string): void {
    this.api.planesTratamiento(pacienteId).subscribe({
      next: (planes) => this.planes.set(planes),
      // Sin planes el historial de la pieza muestra solo versiones y fotos.
      error: () => this.planes.set([]),
    });
  }

  protected seleccionarVersion(valor: string): void {
    if(this.guardando() || this.operacionFotos.guardado) return;
    const elegida = this.versiones().find((version) => version.version === Number(valor));
    if (!elegida) return;
    this.actual.set(elegida);
    this.nivelSensibilidad.set(elegida.nivel_sensibilidad);
    this.denticion.set(elegida.denticion);
    this.borrador.set(this.clonarPiezas(elegida.piezas));
    this.cerrarFicha();
    this.motivo.set('');
  }

  /** Selecciona una pieza y abre su ficha. */
  protected elegirPieza(codigo: number): void {
    this.seleccionada.set(codigo);
    this.fichaPieza.set(true);
  }

  protected cerrarFicha(): void {
    this.fichaPieza.set(false);
    this.seleccionada.set(null);
  }

  protected elegirHerramienta(herramienta: Herramienta): void {
    this.herramienta.set(herramienta);
  }

  /**
   * Clic sobre una cara del dibujo. Abre la pieza y, si hay un pincel activo
   * y se puede editar, aplica el hallazgo. Repetir el mismo hallazgo lo quita.
   */
  protected clicRegion(codigo: number, region: Region): void {
    this.seleccionada.set(codigo);
    const herramienta = this.herramienta();
    if (herramienta === 'SELECCIONAR' || !this.puedeGuardar()) {
      this.fichaPieza.set(true);
      return;
    }
    const estado = this.borrador()[String(codigo)] ?? PIEZA_VACIA;

    if (ES_HALLAZGO_PIEZA.has(herramienta)) {
      this.aplicarHallazgoPieza(codigo, herramienta as HallazgoPieza);
      return;
    }
    if (estado.pieza === 'AUSENTE') {
      this.error.set('La pieza está marcada como ausente: quite esa marca antes de pintar caras.');
      return;
    }
    const cara = caraEnRegion(codigo, region);
    const caras: Partial<Record<CaraOdontologica, HallazgoCara>> = { ...estado.caras };
    if (herramienta === 'BORRAR' || caras[cara] === herramienta) {
      delete caras[cara];
    } else if (ES_HALLAZGO_CARA.has(herramienta)) {
      caras[cara] = herramienta as HallazgoCara;
    }
    this.actualizarPiezaDe(codigo, { ...estado, caras });
  }

  /** Permite seleccionar una cara y aplicar la herramienta sin usar ratón. */
  protected teclaRegion(evento: KeyboardEvent, codigo: number, region: Region): void {
    if (evento.key === 'Enter' || evento.key === ' ') {
      evento.preventDefault();
      this.clicRegion(codigo, region);
      return;
    }
    if (!evento.key.startsWith('Arrow')) return;
    evento.preventDefault();
    const siguiente = REGION_POR_FLECHA[region][evento.key];
    if (!siguiente) return;
    const objetivo = (evento.currentTarget as SVGPolygonElement)
      .closest('.diente')
      ?.querySelector<SVGPolygonElement>(`[data-region="${siguiente}"]`);
    objetivo?.focus();
  }

  /** Clic sobre el número o el contorno: abre la pieza o aplica un hallazgo de pieza. */
  protected clicPieza(codigo: number): void {
    this.seleccionada.set(codigo);
    const herramienta = this.herramienta();
    if (herramienta === 'SELECCIONAR' || !this.puedeGuardar()) {
      this.fichaPieza.set(true);
    } else if (ES_HALLAZGO_PIEZA.has(herramienta)) {
      this.aplicarHallazgoPieza(codigo, herramienta as HallazgoPieza);
    } else if (herramienta === 'BORRAR') {
      const estado = this.borrador()[String(codigo)] ?? PIEZA_VACIA;
      this.actualizarPiezaDe(codigo, { ...estado, pieza: null });
    }
  }

  private aplicarHallazgoPieza(codigo: number, hallazgo: HallazgoPieza): void {
    const estado = this.borrador()[String(codigo)] ?? PIEZA_VACIA;
    const nuevo = estado.pieza === hallazgo ? null : hallazgo;
    this.actualizarPiezaDe(codigo, {
      ...estado,
      pieza: nuevo,
      caras: nuevo === 'AUSENTE' ? {} : estado.caras,
    });
  }

  protected cambiarDenticion(valor: string): void {
    if (valor !== 'PERMANENTE' && valor !== 'TEMPORAL' && valor !== 'MIXTA') return;
    if (this.actual()) return;
    this.denticion.set(valor);
    this.cerrarFicha();
  }

  protected cambiarHallazgoPieza(valor: string): void {
    const valido = HALLAZGOS_PIEZA.find((hallazgo) => hallazgo.codigo === valor)?.codigo ?? null;
    const estado = this.estadoSeleccionado();
    this.actualizarPieza({
      ...estado,
      pieza: valido,
      caras: valido === 'AUSENTE' ? {} : estado.caras,
    });
  }

  protected alternarCara(cara: CaraOdontologica, marcado: boolean): void {
    const estado = this.estadoSeleccionado();
    const caras = { ...estado.caras };
    if (marcado) {
      caras[cara] ??= 'CARIES';
    } else {
      delete caras[cara];
    }
    this.actualizarPieza({ ...estado, pieza: estado.pieza === 'AUSENTE' ? null : estado.pieza, caras });
  }

  protected cambiarHallazgoCara(cara: CaraOdontologica, valor: string): void {
    const hallazgo = HALLAZGOS_CARA.find((opcion) => opcion.codigo === valor)?.codigo;
    const caras = { ...this.estadoSeleccionado().caras };
    if (hallazgo) caras[cara] = hallazgo;
    else delete caras[cara];
    this.actualizarPieza({ ...this.estadoSeleccionado(), caras });
  }

  protected cambiarNota(valor: string): void {
    this.actualizarPieza({ ...this.estadoSeleccionado(), nota: valor || null });
  }

  /** Descarta los cambios sin guardar de la pieza abierta. */
  protected deshacerPieza(): void {
    const codigo = this.seleccionada();
    if (codigo === null) return;
    const original = this.actual()?.piezas[String(codigo)];
    this.borrador.update((actual) => {
      const copia = { ...actual };
      if (original) copia[String(codigo)] = { ...original, caras: { ...original.caras } };
      else delete copia[String(codigo)];
      return copia;
    });
  }

  protected guardar(): void {
    if (!this.puedeGuardar()) return;
    const contenido: ContenidoOdontograma = {
      denticion: this.denticion(),
      piezas: this.limpiarVacias(this.borrador()),
    };
    const actual = this.actual();
    if (actual && this.motivo().trim().length < 8) {
      this.error.set('Escriba el motivo del cambio (mínimo 8 caracteres).');
      return;
    }

    this.guardando.set(true);
    this.error.set(null);
    this.aviso.set('');
    const peticion = actual
      ? this.api.versionarOdontograma(
          this.pacienteId(),
          contenido,
          actual.version,
          this.motivo().trim(),
          this.nivelSensibilidad(),
        )
      : this.api.crearOdontograma(this.pacienteId(), contenido, this.nivelSensibilidad());
    this.operacionFotos.guardar('odontograma',peticion,this.fotos).subscribe({
      next: () => {
        this.fotos=[];
        this.capturaFotos()?.limpiar();
        this.operacionFotos.reiniciar();
        this.guardando.set(false);
        this.motivo.set('');
        // `cargar()` limpia el aviso al empezar: el aviso va después o no se ve.
        this.cargar();
        this.aviso.set('Odontograma guardado en una nueva versión.');
      },
      error: (fallo: FalloApi) => {
        this.guardando.set(false);
        this.error.set(fallo);
      },
    });
  }

  protected leyendaPieza(codigo: number): string {
    return describirEstado(this.borrador()[String(codigo)]).replace(
      'Sin hallazgos',
      'Sin hallazgos registrados',
    );
  }

  protected nombreHallazgo(codigo: HallazgoCara): string {
    return nombreHallazgoCara(codigo);
  }

  protected tieneHallazgoPieza(codigo: number): boolean {
    return Boolean(this.borrador()[String(codigo)]?.pieza);
  }

  /** Hallazgo de pieza (para dibujar su marca) o null. */
  protected hallazgoDePieza(codigo: number): HallazgoPieza | null {
    return this.borrador()[String(codigo)]?.pieza ?? null;
  }

  /** Clase de color de una región del dibujo. */
  protected claseRegion(codigo: number, region: Region): string {
    const hallazgo = this.borrador()[String(codigo)]?.caras[caraEnRegion(codigo, region)];
    return hallazgo ? `cara cara--${hallazgo.toLowerCase()}` : 'cara';
  }

  protected tituloRegion(codigo: number, region: Region): string {
    const cara = caraEnRegion(codigo, region);
    const nombre = CARAS.find((opcion) => opcion.codigo === cara)?.nombre ?? cara;
    const hallazgo = this.borrador()[String(codigo)]?.caras[cara];
    return `${codigo} · ${nombre}${hallazgo ? ': ' + nombreHallazgoCara(hallazgo) : ''}`;
  }

  protected tieneNota(codigo: number): boolean {
    return Boolean(this.borrador()[String(codigo)]?.nota);
  }

  private actualizarPieza(estado: EstadoPiezaOdontograma): void {
    const codigo = this.seleccionada();
    if (codigo === null) return;
    this.actualizarPiezaDe(codigo, estado);
  }

  private actualizarPiezaDe(codigo: number, estado: EstadoPiezaOdontograma): void {
    if (!this.puedeGuardar() || this.operacionFotos.guardado) return;
    this.borrador.update((actual) => ({ ...actual, [String(codigo)]: estado }));
    this.error.set(null);
    this.aviso.set('');
  }

  /** Una pieza sin hallazgos ni nota no viaja: el servidor la trata como sana. */
  private limpiarVacias(
    piezas: Readonly<Record<string, EstadoPiezaOdontograma>>,
  ): Record<string, EstadoPiezaOdontograma> {
    return Object.fromEntries(
      Object.entries(piezas).filter(
        ([, estado]) => estado.pieza || estado.nota || Object.keys(estado.caras).length,
      ),
    );
  }

  private clonarPiezas(
    piezas: Readonly<Record<string, EstadoPiezaOdontograma>>,
  ): Record<string, EstadoPiezaOdontograma> {
    return Object.fromEntries(
      Object.entries(piezas).map(([codigo, estado]) => [codigo, { ...estado, caras: { ...estado.caras } }]),
    );
  }
}
