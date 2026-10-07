/**
 * Tira de fotos clínicas de una pieza o de un procedimiento del plan.
 *
 * Para qué sirve
 * --------------
 * Documentar el tratamiento donde se hace: al pie de una pieza del odontograma
 * o de un procedimiento del plan (antes, durante, después), sin ir a la
 * galería y escribir a mano el número de pieza.
 *
 * Las fotos pasan por el mismo camino que la galería: el backend sanea,
 * cifra y audita; aquí solo se piden por el API y se muestran con URLs de
 * objeto locales que se revocan al cambiar de filtro o destruir el componente.
 */
import {
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  ChangeDetectionStrategy
} from '@angular/core';
import { DatePipe } from '@angular/common';

import { ApiService, FalloApi, type ImagenPacienteApi } from '../nucleo/servicios/api.service';
import { PERMISOS } from '../nucleo/servicios/configuracion';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { IconoComponent } from './icono.component';

@Component({
  selector: 'app-fotos-clinicas',
  standalone: true,
  imports: [DatePipe, IconoComponent],
  template: `
    @if (puedeLeer()) {
      <div class="fotos">
        <div class="fotos__tira" role="list" [attr.aria-label]="etiqueta()">
          @for (imagen of imagenes(); track imagen.id) {
            <button
              type="button"
              role="listitem"
              class="fotos__miniatura"
              [class.fotos__miniatura--abierta]="abierta() === imagen.id"
              [attr.aria-label]="'Ver foto del ' + (imagen.tomada_en ?? imagen.creado_en | date: 'mediumDate')"
              (click)="alternar(imagen.id)"
            >
              @if (urls().get(imagen.id); as fuente) {
                <img [src]="fuente" alt="" />
              } @else {
                <span class="fotos__cargando" aria-hidden="true"></span>
              }
              <span class="fotos__fecha">{{ imagen.tomada_en ?? imagen.creado_en | date: 'dd/MM/yy' }}</span>
            </button>
          } @empty {
            @if (!cargando()) {
              <p class="fotos__vacio">{{ vacio() }}</p>
            }
          }
        </div>

        @if (abierta() && urls().get(abierta()!); as fuente) {
          <figure class="fotos__ampliada">
            <img [src]="fuente" [alt]="descripcionAbierta() || 'Foto clínica ampliada'" />
            @if (descripcionAbierta()) {
              <figcaption>{{ descripcionAbierta() }}</figcaption>
            }
          </figure>
        }

        @if (puedeCargar()) {
          <div class="fotos__acciones">
            <label class="boton boton--pequeno" [class.fotos__ocupado]="subiendo()">
              <input type="file" class="solo-lectores" accept="image/jpeg,image/png,image/webp"
                     [disabled]="subiendo()" (change)="subir($event)" />
              <app-icono nombre="subir" [tamano]="14" />
              {{ subiendo() ? 'Subiendo…' : 'Subir foto' }}
            </label>
            <label class="boton boton--pequeno boton--plano" [class.fotos__ocupado]="subiendo()">
              <input type="file" class="solo-lectores" accept="image/jpeg,image/png,image/webp"
                     capture="environment" [disabled]="subiendo()" (change)="subir($event)" />
              Tomar foto
            </label>
          </div>
        }
        @if (error()) {
          <p class="fotos__error" role="alert">{{ error() }}</p>
        }
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .fotos { display: grid; gap: var(--espacio-2); }
    .fotos__tira { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .fotos__miniatura {
      position: relative;
      width: 72px;
      height: 72px;
      padding: 0;
      border: 2px solid var(--borde);
      border-radius: var(--radio-2, 8px);
      overflow: hidden;
      background: var(--superficie-hundida, var(--acento-suave));
      cursor: zoom-in;
    }
    .fotos__miniatura--abierta { border-color: var(--acento); }
    .fotos__miniatura img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .fotos__fecha {
      position: absolute;
      inset: auto 0 0 0;
      padding: 1px 4px;
      font-size: 0.65rem;
      color: #fff;
      background: rgb(0 0 0 / 0.55);
    }
    .fotos__cargando { display: block; width: 100%; height: 100%; }
    .fotos__vacio { margin: 0; font-size: 0.85rem; color: var(--texto-suave); }
    .fotos__ampliada { margin: 0; }
    .fotos__ampliada img {
      max-width: 100%;
      max-height: 360px;
      border-radius: var(--radio-2, 8px);
      display: block;
    }
    .fotos__ampliada figcaption { font-size: 0.8rem; color: var(--texto-suave); margin-top: 4px; }
    .fotos__acciones { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .fotos__acciones .boton { cursor: pointer; gap: 4px; }
    .fotos__acciones .boton:focus-within { outline: 3px solid var(--acento); outline-offset: 2px; }
    .fotos__ocupado { opacity: 0.6; cursor: progress; }
    .fotos__error { margin: 0; font-size: 0.85rem; color: var(--peligro); }
  `,
})
export class FotosClinicasComponent {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);
  private solicitud = 0;

  readonly pacienteId = input.required<string>();
  /** Pieza FDI que documentan las fotos; se etiqueta al subir. */
  readonly pieza = input<number | null>(null);
  /** Procedimiento del plan al que se ligan las fotos. */
  readonly procedimientoId = input<string | null>(null);
  readonly etiqueta = input('Fotos clínicas');
  readonly vacio = input('Aún no hay fotos.');
  /** Avisa al padre tras cada carga correcta. */
  readonly cargada = output<ImagenPacienteApi>();

  protected readonly puedeLeer = computed(() => this.sesion.tienePermiso(PERMISOS.imagenClinicaLeer));
  protected readonly puedeCargar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.imagenClinicaCargar),
  );
  protected readonly imagenes = signal<readonly ImagenPacienteApi[]>([]);
  protected readonly urls = signal<ReadonlyMap<string, string>>(new Map());
  protected readonly abierta = signal<string | null>(null);
  protected readonly cargando = signal(false);
  protected readonly subiendo = signal(false);
  protected readonly error = signal('');
  protected readonly descripcionAbierta = computed(
    () => this.imagenes().find((imagen) => imagen.id === this.abierta())?.descripcion ?? '',
  );

  constructor() {
    effect(() => {
      const pacienteId = this.pacienteId();
      const pieza = this.pieza();
      const procedimientoId = this.procedimientoId();
      untracked(() => this.cargar(pacienteId, pieza, procedimientoId));
    });
    inject(DestroyRef).onDestroy(() => this.liberar());
  }

  protected alternar(id: string): void {
    this.abierta.update((actual) => (actual === id ? null : id));
  }

  protected subir(evento: Event): void {
    const campo = evento.target as HTMLInputElement;
    const archivo = campo.files?.item(0) ?? null;
    campo.value = '';
    if (!archivo || this.subiendo()) return;
    const pieza = this.pieza();
    this.subiendo.set(true);
    this.error.set('');
    this.api
      .subirImagenClinica(this.pacienteId(), archivo, {
        tipo: 'FOTO_INTRAORAL',
        piezas: pieza === null ? [] : [pieza],
        procedimiento_id: this.procedimientoId(),
      })
      .subscribe({
        next: (imagen) => {
          this.subiendo.set(false);
          this.cargada.emit(imagen);
          this.cargar(this.pacienteId(), this.pieza(), this.procedimientoId());
        },
        error: (fallo: unknown) => {
          this.subiendo.set(false);
          this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudo subir la foto.');
        },
      });
  }

  private cargar(pacienteId: string, pieza: number | null, procedimientoId: string | null): void {
    if (!this.puedeLeer()) return;
    const solicitud = ++this.solicitud;
    this.liberar();
    this.abierta.set(null);
    this.cargando.set(true);
    this.api
      .imagenesClinicas(pacienteId, {
        pieza: pieza ?? undefined,
        procedimiento_id: procedimientoId ?? undefined,
      })
      .subscribe({
        next: (imagenes) => {
          if (solicitud !== this.solicitud) return;
          this.imagenes.set(imagenes);
          this.cargando.set(false);
          for (const imagen of imagenes) this.cargarVista(imagen.id, solicitud);
        },
        error: (fallo: unknown) => {
          if (solicitud !== this.solicitud) return;
          this.cargando.set(false);
          this.error.set(fallo instanceof FalloApi ? fallo.message : 'No se pudieron cargar las fotos.');
        },
      });
  }

  private cargarVista(id: string, solicitud: number): void {
    this.api.contenidoImagen(id).subscribe({
      next: (blob) => {
        if (solicitud !== this.solicitud) return;
        const url = URL.createObjectURL(blob);
        this.urls.update((actual) => new Map(actual).set(id, url));
      },
      // Una miniatura que no carga deja el hueco; el resto sigue visible.
      error: () => undefined,
    });
  }

  private liberar(): void {
    for (const url of this.urls().values()) URL.revokeObjectURL(url);
    this.urls.set(new Map());
    this.imagenes.set([]);
  }
}
