import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService, type ImagenPacienteApi } from '../nucleo/servicios/api.service';
import { PERMISOS } from '../nucleo/servicios/configuracion';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { esSinAccesoClinico, mensajeFalloClinico } from '../nucleo/utilidades/acceso-clinico';

const TIPOS = [
  { valor: 'RADIOGRAFIA_PERIAPICAL', etiqueta: 'Radiografía periapical' },
  { valor: 'RADIOGRAFIA_BITEWING', etiqueta: 'Radiografía bitewing' },
  { valor: 'RADIOGRAFIA_PANORAMICA', etiqueta: 'Radiografía panorámica' },
  { valor: 'RADIOGRAFIA_CEFALOMETRICA', etiqueta: 'Radiografía cefalométrica' },
  { valor: 'FOTO_INTRAORAL', etiqueta: 'Fotografía intraoral' },
  { valor: 'FOTO_EXTRAORAL', etiqueta: 'Fotografía extraoral' },
  { valor: 'OTRA', etiqueta: 'Otra imagen clínica' },
] as const;

@Component({
  selector: 'app-galeria-imagenes',
  standalone: true,
  host: { '(document:keydown.escape)': 'cerrarVisor()' },
  imports: [DatePipe, FormsModule],
  templateUrl: './galeria-imagenes.component.html',
  styleUrl: './galeria-imagenes.component.scss',
})
export class GaleriaImagenesComponent {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);
  private readonly destruir = inject(DestroyRef);
  private solicitud = 0;

  readonly pacienteId = input.required<string>();
  protected readonly tipos = TIPOS;
  protected readonly puedeCargar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.imagenClinicaCargar),
  );
  protected readonly imagenes = signal<readonly ImagenPacienteApi[]>([]);
  protected readonly urls = signal<ReadonlyMap<string, string>>(new Map());
  protected readonly cargando = signal(true);
  protected readonly subiendo = signal(false);
  protected readonly error = signal('');
  /** La carga devolvió el 404 de acceso clínico: no se ofrece cargar imágenes. */
  protected readonly sinAcceso = signal(false);
  protected readonly exito = signal('');

  protected tipo = 'FOTO_INTRAORAL';
  protected filtroTipo = '';
  protected filtroPieza = '';
  protected piezas = '';
  protected tomadaEn = '';
  protected descripcion = '';
  protected archivo: File | null = null;
  protected archivoNombre = '';

  constructor() {
    effect(() => {
      const pacienteId = this.pacienteId();
      untracked(() => this.cargar(pacienteId));
    });
    this.destruir.onDestroy(() => this.liberarUrls());
  }

  protected cargar(pacienteId: string): void {
    const solicitud = ++this.solicitud;
    this.cargando.set(true);
    this.error.set('');
    this.sinAcceso.set(false);
    this.visor.set(null);
    this.comparacion.set([]);
    this.liberarUrls();
    const pieza = Number(this.filtroPieza);
    this.api
      .imagenesClinicas(pacienteId, {
        tipo: this.filtroTipo || undefined,
        pieza: Number.isInteger(pieza) && pieza > 0 ? pieza : undefined,
      })
      .subscribe({
        next: (imagenes) => {
          if (solicitud !== this.solicitud) return;
          this.imagenes.set(imagenes);
          this.cargando.set(false);
          for (const imagen of imagenes) this.cargarVista(imagen, solicitud);
        },
        error: (fallo: unknown) => {
          if (solicitud !== this.solicitud) return;
          this.sinAcceso.set(esSinAccesoClinico(fallo));
          this.error.set(this.mensaje(fallo));
          this.cargando.set(false);
        },
      });
  }

  protected seleccionarArchivo(evento: Event): void {
    const control = evento.target as HTMLInputElement;
    this.archivo = control.files?.item(0) ?? null;
    this.archivoNombre = this.archivo?.name ?? '';
  }

  protected subir(): void {
    if (!this.archivo || this.subiendo()) return;
    const piezas = this.piezas
      .split(/[ ,;]+/)
      .map((valor) => Number(valor.trim()))
      .filter((valor) => Number.isInteger(valor) && valor > 0);
    this.subiendo.set(true);
    this.error.set('');
    this.exito.set('');
    this.api
      .subirImagenClinica(this.pacienteId(), this.archivo, {
        tipo: this.tipo as Exclude<ImagenPacienteApi['tipo'], 'PERFIL'>,
        piezas,
        tomada_en: this.tomadaEn || null,
        descripcion: this.descripcion.trim() || null,
      })
      .subscribe({
        next: (imagen) => {
          this.subiendo.set(false);
          this.archivo = null;
          this.archivoNombre = '';
          this.piezas = '';
          this.tomadaEn = '';
          this.descripcion = '';
          this.exito.set(
            imagen.antivirus === 'LIMPIO'
              ? 'Imagen cargada, saneada y revisada por antivirus.'
              : 'Imagen cargada y cifrada. Antivirus no disponible en este entorno de desarrollo.',
          );
          this.cargar(this.pacienteId());
        },
        error: (fallo: unknown) => {
          this.error.set(this.mensaje(fallo));
          this.subiendo.set(false);
        },
      });
  }

  // ======================================================================
  //  Visor y comparacion
  // ======================================================================
  /** Imagenes abiertas en el visor: una, o dos para comparar. */
  protected readonly visor = signal<readonly string[] | null>(null);
  protected readonly zoom = signal(1);
  protected readonly porcentajeZoom = computed(() => `${Math.round(this.zoom() * 100)} %`);
  protected readonly transformacion = computed(() => `scale(${this.zoom()})`);
  /** Seleccion para comparar, como maximo dos. */
  protected readonly comparacion = signal<readonly string[]>([]);

  protected abrirVisor(ids: readonly string[]): void {
    this.zoom.set(1);
    this.visor.set(ids);
  }

  protected cerrarVisor(): void {
    this.visor.set(null);
  }

  protected cambiarZoom(paso: number): void {
    this.zoom.update((actual) => Math.min(4, Math.max(0.5, actual + paso)));
  }

  protected enComparacion(id: string): boolean {
    return this.comparacion().includes(id);
  }

  protected alternarComparacion(id: string): void {
    this.comparacion.update((actual) =>
      actual.includes(id) ? actual.filter((otro) => otro !== id) : [...actual, id].slice(-2),
    );
  }

  /** Las dos elegidas, la mas antigua primero («antes»). */
  protected ordenComparacion(): readonly string[] {
    const fecha = (id: string): string => {
      const imagen = this.imagenPorId(id);
      return imagen?.tomada_en ?? imagen?.creado_en ?? '';
    };
    return [...this.comparacion()].sort((a, b) => fecha(a).localeCompare(fecha(b)));
  }

  protected imagenPorId(id: string): ImagenPacienteApi | undefined {
    return this.imagenes().find((imagen) => imagen.id === id);
  }

  protected leyendaVisor(id: string, doble: boolean, primero: boolean): string {
    const imagen = this.imagenPorId(id);
    const partes = [
      doble ? (primero ? 'Antes' : 'Después') : '',
      this.etiquetaTipo(imagen?.tipo ?? ''),
      imagen?.tomada_en ? `tomada ${imagen.tomada_en}` : '',
      imagen?.piezas.length ? `pieza(s) ${imagen.piezas.join(', ')}` : '',
    ];
    return partes.filter(Boolean).join(' · ');
  }

  protected etiquetaTipo(tipo: string): string {
    return TIPOS.find((opcion) => opcion.valor === tipo)?.etiqueta ?? tipo;
  }

  protected url(id: string): string | null {
    return this.urls().get(id) ?? null;
  }

  protected formatearBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private cargarVista(imagen: ImagenPacienteApi, solicitud: number): void {
    this.api.contenidoImagen(imagen.id).subscribe({
      next: (blob) => {
        if (solicitud !== this.solicitud) return;
        const url = URL.createObjectURL(blob);
        this.urls.update((actual) => new Map(actual).set(imagen.id, url));
      },
      error: () => undefined,
    });
  }

  private liberarUrls(): void {
    for (const url of this.urls().values()) URL.revokeObjectURL(url);
    this.urls.set(new Map());
  }

  private mensaje(fallo: unknown): string {
    return mensajeFalloClinico(fallo, 'No se pudo completar la operación de imágenes.');
  }
}
