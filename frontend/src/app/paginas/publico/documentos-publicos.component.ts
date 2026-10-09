import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { guardarPdf } from '../../nucleo/servicios/registros-paciente.service';

@Component({
  selector: 'app-documentos-publicos', standalone: true, imports: [FormsModule], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main class="pagina">
      <article class="tarjeta">
        <p class="marca">ClinicAI</p>
        <header>
          <h1>Su documento privado</h1>
          <p>Confirme su identidad para descargar el PDF que le preparó la clínica.</p>
        </header>
        <form #formulario="ngForm" (ngSubmit)="verificar()">
          @if (!usarDocumento) {
            <label class="campo">
              <span class="campo__etiqueta">Fecha de nacimiento</span>
              <input class="campo__control" type="date" name="fecha" [(ngModel)]="fecha" required [attr.aria-describedby]="error() ? 'mensaje-error' : null" />
            </label>
          } @else {
            <label class="campo">
              <span class="campo__etiqueta">Últimos 4 caracteres de su documento</span>
              <input class="campo__control" name="documento" [(ngModel)]="documento" required minlength="4" maxlength="4" autocomplete="off" [attr.aria-describedby]="error() ? 'mensaje-error' : null" />
            </label>
          }
          <button class="boton boton--plano alternar" type="button" (click)="cambiarMetodo()">{{ usarDocumento ? 'Usar fecha de nacimiento' : 'La clínica no tiene mi fecha de nacimiento' }}</button>
          @if (error()) { <p id="mensaje-error" class="mensaje mensaje--error" role="alert">{{ error() }}</p> }
          @if (aviso()) { <p class="mensaje mensaje--ok" role="status">{{ aviso() }}</p> }
          @if (ocupado()) { <p class="mensaje" role="status">Preparando la descarga…</p> }
          <button class="boton boton--principal descargar" type="submit" [disabled]="ocupado() || formulario.invalid">{{ ocupado() ? 'Preparando…' : 'Descargar PDF' }}</button>
        </form>
        <p class="nota">El enlace caduca y se bloquea después de cinco intentos incorrectos. Si necesita ayuda, contacte con su clínica.</p>
      </article>
    </main>`,
  styles: `
    :host { display: block; min-height: 100%; color: var(--texto); }
    .pagina { box-sizing: border-box; min-height: 100vh; display: grid; place-items: start center; padding: clamp(16px, 4vw, 40px); background: radial-gradient(ellipse at top, #d6f3f0, transparent 70%), var(--fondo); }
    .tarjeta { box-sizing: border-box; width: min(100%, 600px); min-width: 0; display: grid; gap: 20px; padding: clamp(20px, 5vw, 40px); border: 1px solid var(--borde); border-radius: 24px; background: var(--superficie-elevada); box-shadow: var(--sombra-2); overflow-wrap: anywhere; }
    .marca { margin: 0; font-size: 1.2rem; font-weight: 800; color: var(--acento); }
    h1 { margin: 0 0 8px; font-size: clamp(1.4rem, 3vw, 1.8rem); line-height: 1.25; }
    header p { margin: 0; line-height: 1.5; }
    form { display: grid; gap: 16px; }
    .campo { display: grid; gap: 8px; margin: 0; }
    .alternar { justify-self: start; max-width: 100%; text-align: left; white-space: normal; }
    .mensaje { margin: 0; line-height: 1.45; }
    .mensaje--error { padding: 12px 14px; border: 1px solid var(--peligro); border-radius: var(--radio); color: var(--peligro); background: var(--superficie); }
    .mensaje--ok { color: var(--texto); }
    .descargar { width: 100%; min-height: 48px; }
    .nota { margin: 0; color: var(--texto-suave); font-size: .9rem; line-height: 1.5; }
    :host :is(button, input):focus-visible { outline: 3px solid var(--acento); outline-offset: 3px; }
    @media (max-width: 480px) { .pagina { padding: 12px; } .tarjeta { border-radius: 16px; } }
  `,
})
export class DocumentosPublicosComponent {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';
  protected fecha = ''; protected documento = ''; protected usarDocumento = false;
  protected readonly ocupado = signal(false); protected readonly error = signal(''); protected readonly aviso = signal('');
  protected cambiarMetodo(): void { this.usarDocumento = !this.usarDocumento; this.error.set(''); }
  protected verificar(): void {
    if (this.ocupado()) return;
    if (this.usarDocumento ? this.documento.trim().length !== 4 : !this.fecha) {
      this.error.set(this.usarDocumento ? 'Escriba los 4 últimos caracteres de su documento.' : 'Indique su fecha de nacimiento.');
      return;
    }
    this.ocupado.set(true); this.error.set('');
    this.aviso.set('');
    this.http.post(`${this.config.urlApi}/publico/documentos/${encodeURIComponent(this.token)}/acceso`, this.usarDocumento ? { ultimos_digitos_documento: this.documento.trim() } : { fecha_nacimiento: this.fecha }, { responseType: 'blob' }).subscribe({
      next: pdf => { guardarPdf(pdf, 'ClinicAI-documento.pdf'); this.ocupado.set(false); this.aviso.set('Documento descargado.'); },
      error: (error: HttpErrorResponse) => {
        this.ocupado.set(false);
        this.error.set(error.status === 401
          ? 'Los datos no coinciden. Revise la información.'
          : error.status === 404 || error.status === 410
            ? 'Este enlace ha caducado o ya no está disponible. Solicite uno nuevo a su clínica.'
            : error.status === 409
              ? 'Este enlace se bloqueó tras varios intentos. Solicite uno nuevo a su clínica.'
              : 'No se pudo preparar el documento. Inténtelo de nuevo o contacte con su clínica.');
      },
    });
  }
}
