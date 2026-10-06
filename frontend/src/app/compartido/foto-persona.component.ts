/**
 * Foto de una persona del equipo (cualquier rol) o de un profesional.
 *
 * Igual que la del paciente: llega por el API, se convierte en una URL de
 * objeto local y se revoca al destruir el componente. Sin foto se ven las
 * iniciales. Con `puedeEditar` ofrece «Subir foto» y «Tomar foto»; el
 * servidor decide si se puede (la propia persona o `usuario.editar`).
 *
 * Se identifica por `usuarioId` o, desde la agenda y las fichas, por
 * `profesionalId` (solo lectura: la foto es la de su usuario).
 */
import { Component, DestroyRef, effect, inject, input, output, signal, untracked } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';

import { CONFIGURACION } from '../nucleo/servicios/configuracion';
import { IconoComponent } from './icono.component';

@Component({
  selector: 'app-foto-persona',
  standalone: true,
  imports: [IconoComponent],
  template: `
    <span class="foto" [style.width.px]="tamano()" [style.height.px]="tamano()" [style.font-size.px]="tamano() * 0.36">
      @if (url(); as fuente) {
        <img [src]="fuente" [alt]="'Foto de ' + nombre()" />
      } @else {
        <span aria-hidden="true">{{ iniciales() }}</span>
      }
    </span>
    @if (puedeEditar() && usuarioId()) {
      <span class="acciones">
        <label class="boton boton--pequeno" [class.ocupado]="subiendo()">
          <input type="file" class="solo-lectores" accept="image/jpeg,image/png,image/webp"
                 [disabled]="subiendo()" (change)="subir($event)" />
          <app-icono nombre="subir" [tamano]="14" />
          {{ subiendo() ? 'Subiendo…' : url() ? 'Cambiar foto' : 'Subir foto' }}
        </label>
        <label class="boton boton--pequeno boton--plano" [class.ocupado]="subiendo()">
          <input type="file" class="solo-lectores" accept="image/jpeg,image/png,image/webp"
                 capture="user" [disabled]="subiendo()" (change)="subir($event)" />
          Tomar foto
        </label>
      </span>
    }
    @if (error()) { <span class="error" role="alert">{{ error() }}</span> }
  `,
  styles: `
    :host { display: inline-flex; flex-direction: column; align-items: center; gap: 6px; flex: 0 0 auto; }
    .foto { display: inline-grid; place-items: center; overflow: hidden; border-radius: 50%;
      background: var(--acento-suave); color: var(--acento-fuerte); font-weight: 700; text-transform: uppercase; }
    .foto img { width: 100%; height: 100%; object-fit: cover; }
    .acciones { display: flex; flex-wrap: wrap; justify-content: center; gap: 4px; }
    .acciones .boton { cursor: pointer; gap: 4px; }
    .acciones .boton:focus-within { outline: 3px solid var(--acento); outline-offset: 2px; }
    .ocupado { opacity: 0.6; cursor: progress; }
    .error { max-width: 200px; color: var(--peligro); font-size: 0.75rem; text-align: center; }
  `,
})
export class FotoPersonaComponent {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);

  readonly usuarioId = input<string | null>(null);
  readonly profesionalId = input<string | null>(null);
  readonly nombre = input('');
  readonly tamano = input(40);
  readonly puedeEditar = input(false);
  readonly actualizada = output<void>();

  protected readonly url = signal<string | null>(null);
  protected readonly subiendo = signal(false);
  protected readonly error = signal('');
  private solicitud = 0;

  constructor() {
    effect(() => {
      const usuario = this.usuarioId();
      const profesional = this.profesionalId();
      untracked(() => this.cargar(usuario, profesional));
    });
    inject(DestroyRef).onDestroy(() => this.liberar());
  }

  protected iniciales(): string {
    return this.nombre()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((parte) => parte.charAt(0))
      .join('');
  }

  private cargar(usuario: string | null, profesional: string | null): void {
    const ruta = usuario ? `/usuarios/${usuario}/foto` : profesional ? `/profesionales/${profesional}/foto` : null;
    const solicitud = ++this.solicitud;
    this.liberar();
    if (!ruta) return;
    this.http.get(this.configuracion.urlApi + ruta, { responseType: 'blob', observe: 'response' }).subscribe({
      next: (respuesta) => {
        if (solicitud !== this.solicitud || respuesta.status === 204 || !respuesta.body?.size) return;
        this.url.set(URL.createObjectURL(respuesta.body));
      },
      // Sin foto o sin acceso se ven las iniciales: no es un error para quien mira.
      error: () => undefined,
    });
  }

  protected subir(evento: Event): void {
    const campo = evento.target as HTMLInputElement;
    const archivo = campo.files?.item(0) ?? null;
    campo.value = '';
    const usuario = this.usuarioId();
    if (!archivo || !usuario) return;
    const formulario = new FormData();
    formulario.append('archivo', archivo, archivo.name);
    this.subiendo.set(true);
    this.error.set('');
    this.http.put(`${this.configuracion.urlApi}/usuarios/${usuario}/foto`, formulario).subscribe({
      next: () => {
        this.subiendo.set(false);
        this.cargar(usuario, null);
        this.actualizada.emit();
      },
      error: (fallo: HttpErrorResponse) => {
        this.subiendo.set(false);
        this.error.set((fallo.error as { mensaje?: string } | null)?.mensaje ?? 'No se pudo guardar la foto.');
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
