/**
 * Foto de perfil del paciente, con iniciales de respaldo.
 *
 * Para qué sirve
 * --------------
 * Reconocer al paciente en el mostrador y no confundir a dos personas con el
 * mismo nombre. Es identificación (N1), no información clínica: la ve quien
 * puede ver la ficha administrativa y la cambia quien puede editarla.
 *
 * La imagen llega por el API, nunca por una URL pública: el backend la
 * descifra solo para una sesión con permiso. Aquí se convierte en una URL de
 * objeto local, que se revoca al destruir el componente para no dejar la foto
 * en memoria del navegador más tiempo del necesario.
 */
import { Component, DestroyRef, effect, inject, input, signal, untracked, ChangeDetectionStrategy } from '@angular/core';

import { ApiService, FalloApi } from '../nucleo/servicios/api.service';
import { IconoComponent } from './icono.component';

@Component({
  selector: 'app-foto-perfil',
  standalone: true,
  imports: [IconoComponent],
  template: `
    <span class="foto" [style.width.px]="tamano()" [style.height.px]="tamano()">
      @if (url(); as fuente) {
        <img [src]="fuente" [alt]="'Foto de ' + nombre()" />
      } @else {
        <span class="foto__iniciales" aria-hidden="true">{{ iniciales() }}</span>
      }
      @if (puedeEditar() && !conBotones()) {
        <label class="foto__cambiar" [class.foto__cambiar--ocupado]="subiendo()">
          <input
            type="file"
            class="solo-lectores"
            accept="image/jpeg,image/png,image/webp"
            [disabled]="subiendo()"
            (change)="subir($event)"
          />
          <app-icono nombre="subir" [tamano]="14" />
          <span class="solo-lectores">Cambiar la foto de {{ nombre() }}</span>
        </label>
      }
    </span>
    @if (puedeEditar() && conBotones()) {
      <!-- Botones con texto: en la ficha la acción debe verse sin buscarla.
           «Tomar foto» abre la cámara en tabletas y teléfonos. -->
      <span class="foto__acciones">
        <label class="boton boton--pequeno" [class.foto__cambiar--ocupado]="subiendo()">
          <input
            type="file"
            class="solo-lectores"
            accept="image/jpeg,image/png,image/webp"
            [disabled]="subiendo()"
            (change)="subir($event)"
          />
          <app-icono nombre="subir" [tamano]="14" />
          {{ subiendo() ? 'Subiendo…' : url() ? 'Cambiar foto' : 'Subir foto' }}
        </label>
        <label class="boton boton--pequeno boton--plano" [class.foto__cambiar--ocupado]="subiendo()">
          <input
            type="file"
            class="solo-lectores"
            accept="image/jpeg,image/png,image/webp"
            capture="user"
            [disabled]="subiendo()"
            (change)="subir($event)"
          />
          Tomar foto
        </label>
      </span>
    }
    @if (error()) {
      <span class="foto__error" role="alert">{{ error() }}</span>
    }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host {
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      flex: 0 0 auto;
    }
    .foto {
      position: relative;
      display: inline-grid;
      place-items: center;
      border-radius: 50%;
      background: var(--acento-suave);
      color: var(--acento-fuerte);
      font-weight: 700;
    }
    .foto img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      border-radius: 50%;
    }
    .foto__cambiar {
      position: absolute;
      right: -4px;
      bottom: -4px;
      display: inline-grid;
      place-items: center;
      width: 24px;
      height: 24px;
      border: 2px solid var(--superficie-elevada);
      border-radius: 50%;
      background: var(--acento);
      color: var(--acento-texto);
      cursor: pointer;
    }
    .foto__cambiar:focus-within {
      outline: 3px solid var(--acento);
      outline-offset: 2px;
    }
    .foto__cambiar--ocupado {
      opacity: 0.6;
      cursor: progress;
    }
    .foto__acciones {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 4px;
      margin-top: 4px;
    }
    .foto__acciones .boton {
      cursor: pointer;
      gap: 4px;
    }
    .foto__acciones .boton:focus-within {
      outline: 3px solid var(--acento);
      outline-offset: 2px;
    }
    .foto__error {
      max-width: 160px;
      font-size: 0.75rem;
      color: var(--peligro);
      text-align: center;
    }
  `,
})
export class FotoPerfilComponent {
  private readonly api = inject(ApiService);

  readonly pacienteId = input.required<string>();
  readonly nombre = input('');
  readonly iniciales = input('');
  readonly tamano = input(44);
  readonly puedeEditar = input(false);
  /** Muestra «Subir foto» y «Tomar foto» con texto en vez del distintivo. */
  readonly conBotones = input(false);

  protected readonly url = signal<string | null>(null);
  protected readonly subiendo = signal(false);
  protected readonly error = signal('');
  private solicitud = 0;

  constructor() {
    effect(() => {
      const pacienteId = this.pacienteId();
      untracked(() => this.cargar(pacienteId));
    });
    inject(DestroyRef).onDestroy(() => this.liberar());
  }

  private cargar(pacienteId: string): void {
    const solicitud = ++this.solicitud;
    this.liberar();
    this.api.fotoPerfil(pacienteId).subscribe({
      next: (foto) => {
        if (solicitud !== this.solicitud || !foto) return;
        this.api.contenidoImagen(foto.id).subscribe({
          next: (blob) => {
            if (solicitud !== this.solicitud) return;
            this.url.set(URL.createObjectURL(blob));
          },
          // Sin foto se ven las iniciales: no es un error para quien atiende.
          error: () => undefined,
        });
      },
      error: () => undefined,
    });
  }

  protected subir(evento: Event): void {
    const campo = evento.target as HTMLInputElement;
    const archivo = campo.files?.[0];
    campo.value = '';
    if (!archivo) return;
    this.subiendo.set(true);
    this.error.set('');
    this.api.subirFotoPerfil(this.pacienteId(), archivo).subscribe({
      next: () => {
        this.subiendo.set(false);
        this.cargar(this.pacienteId());
      },
      error: (fallo: unknown) => {
        this.subiendo.set(false);
        this.error.set(
          fallo instanceof FalloApi ? fallo.message : 'No se pudo actualizar la foto.',
        );
      },
    });
  }

  private liberar(): void {
    const actual = this.url();
    if (actual) {
      URL.revokeObjectURL(actual);
      this.url.set(null);
    }
  }
}
