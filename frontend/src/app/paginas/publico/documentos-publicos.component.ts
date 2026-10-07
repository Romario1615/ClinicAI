import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import { guardarPdf } from '../../nucleo/servicios/registros-paciente.service';

@Component({
  selector: 'app-documentos-publicos', standalone: true, imports: [FormsModule], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<main><article class="tarjeta"><p class="marca">ClinicAI</p><h1>Su documento privado</h1><p>Confirme su identidad para descargar el PDF que le preparó la clínica.</p><form #formulario="ngForm" (ngSubmit)="verificar()">
    @if (!usarDocumento) { <label class="campo">Fecha de nacimiento<input class="campo__control" type="date" name="fecha" [(ngModel)]="fecha" required /></label> } @else { <label class="campo">Últimos 4 caracteres de su documento<input class="campo__control" name="documento" [(ngModel)]="documento" required minlength="4" maxlength="4" autocomplete="off" /></label> }
    <button class="boton boton--plano" type="button" (click)="usarDocumento = !usarDocumento">{{ usarDocumento ? 'Usar fecha de nacimiento' : 'La clínica no tiene mi fecha de nacimiento' }}</button>
    @if (error()) { <p role="alert">{{ error() }}</p> }@if (aviso()) { <p role="status">{{ aviso() }}</p> }
    <button class="boton boton--principal" type="submit" [disabled]="ocupado() || formulario.invalid">{{ ocupado() ? 'Comprobando…' : 'Descargar PDF' }}</button></form><p class="nota">El enlace caduca y se bloquea después de cinco intentos incorrectos. Si necesita ayuda, contacte con su clínica.</p></article></main>`,
  styles: `main{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(ellipse at top,#d6f3f0,transparent 70%),var(--fondo)}article{width:min(100%,540px);padding:clamp(20px,5vw,36px);border:1px solid var(--borde);border-radius:28px;background:var(--superficie-elevada);backdrop-filter:blur(20px);box-shadow:var(--sombra-2)}.marca{font-size:1.3rem;font-weight:800;color:var(--acento)}h1{font-size:1.5rem}.campo,.boton{margin-top:16px}.nota{font-size:.8rem;color:var(--texto-suave);margin-top:24px}`,
})
export class DocumentosPublicosComponent {
  private readonly http = inject(HttpClient);
  private readonly config = inject(CONFIGURACION);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';
  protected fecha = ''; protected documento = ''; protected usarDocumento = false;
  protected readonly ocupado = signal(false); protected readonly error = signal(''); protected readonly aviso = signal('');
  protected verificar(): void {
    if (this.ocupado()) return;
    this.ocupado.set(true); this.error.set('');
    this.http.post(`${this.config.urlApi}/publico/documentos/${encodeURIComponent(this.token)}/acceso`, this.usarDocumento ? { ultimos_digitos_documento: this.documento } : { fecha_nacimiento: this.fecha }, { responseType: 'blob' }).subscribe({
      next: pdf => { guardarPdf(pdf, 'ClinicAI-documento.pdf'); this.ocupado.set(false); this.aviso.set('Documento descargado.'); },
      error: (error: HttpErrorResponse) => { this.ocupado.set(false); this.error.set(error.status === 401 ? 'Los datos no coinciden. Revise la información.' : 'El documento no está disponible. Solicite un enlace nuevo a la clínica.'); },
    });
  }
}
