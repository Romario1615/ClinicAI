import { ChangeDetectionStrategy, Component, ElementRef, effect, input, model, output, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

/** Estructura común para los chats internos; cada pantalla proyecta sus mensajes y acciones. */
@Component({
  selector: 'app-chat-conversacional',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div #registro class="chat__mensajes desplazable" role="log" aria-live="polite" tabindex="0" [attr.aria-label]="etiqueta()">
      <ng-content select="[chat-mensaje]" />
    </div>
    <div class="chat__acciones"><ng-content select="[chat-acciones]" /></div>
    @if (sugerencias().length) {
      <div class="chat__sugerencias" aria-label="Sugerencias">
        @for (sugerencia of sugerencias(); track sugerencia) {
          <button type="button" class="boton boton--pequeno" [disabled]="ocupado() || deshabilitado()" (click)="elegir(sugerencia)">
            {{ sugerencia }}
          </button>
        }
      </div>
    }
    @if (error()) { <p class="chat__error" role="alert">{{ error() }}</p> }
    <form class="chat__compositor" (ngSubmit)="enviar.emit()">
      <label class="campo">
        <span class="campo__etiqueta">Mensaje</span>
        <textarea class="campo__control" name="mensaje" rows="2" maxlength="1000" [ngModel]="texto()" (ngModelChange)="texto.set($event)"
          [disabled]="ocupado() || deshabilitado()" (keydown.enter)="alEnter($event)" [placeholder]="placeholder()"></textarea>
      </label>
      <button class="boton boton--principal" type="submit" [disabled]="ocupado() || deshabilitado() || !texto().trim()">Enviar</button>
    </form>
  `,
  styles: `
    :host { display: flex; flex: 1 1 0; flex-direction: column; gap: var(--espacio-2); min-width: 0; min-height: 0; }
    .chat__mensajes { display: grid; flex: 1 1 0; align-content: start; gap: var(--espacio-3); min-width: 0; min-height: 0; overflow: auto; padding: var(--espacio-1); }
    .chat__acciones, .chat__sugerencias { flex: none; }
    .chat__sugerencias { display: flex; flex-wrap: wrap; gap: var(--espacio-2); }
    .chat__sugerencias .boton { min-height: 36px; font-size: .875rem; }
    .chat__error { flex: none; margin: 0; color: var(--peligro); }
    .chat__compositor { display: grid; flex: none; grid-template-columns: minmax(0, 1fr) auto; gap: var(--espacio-2); align-items: end; margin: 0; padding-top: var(--espacio-2); border-top: 1px solid var(--borde); }
    .chat__compositor .campo { min-width: 0; margin: 0; }
    .chat__compositor textarea { min-height: 56px; }
    @media (max-width: 600px) { .chat__compositor { grid-template-columns: minmax(0, 1fr); } }
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class ChatConversacionalComponent {
  readonly etiqueta = input('Conversación');
  readonly actualizacion = input(0);
  readonly sugerencias = input<readonly string[]>([]);
  readonly placeholder = input('Escriba un mensaje…');
  readonly ocupado = input(false);
  readonly deshabilitado = input(false);
  readonly error = input('');
  readonly texto = model('');
  readonly enviar = output<void>();
  readonly sugerencia = output<string>();
  private readonly registro = viewChild<ElementRef<HTMLElement>>('registro');

  constructor() {
    effect(() => {
      this.actualizacion();
      queueMicrotask(() => {
        const caja = this.registro()?.nativeElement;
        if (caja) caja.scrollTop = caja.scrollHeight;
      });
    });
  }

  protected alEnter(evento: Event): void {
    const teclado = evento as KeyboardEvent;
    if (!teclado.shiftKey) {
      teclado.preventDefault();
      this.enviar.emit();
    }
  }

  protected elegir(valor: string): void {
    this.texto.set(valor.endsWith('…') ? valor.replace('…', '') : valor);
    this.sugerencia.emit(valor);
  }
}
