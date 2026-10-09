/**
 * Página del paciente para leer sus indicaciones después de la consulta.
 *
 * Llega desde el enlace del WhatsApp. No hay sesión: antes de mostrar nada
 * pide la fecha de nacimiento (o, si la clínica no la tiene, los cuatro
 * últimos caracteres del documento). El servidor cuenta los intentos y
 * bloquea el enlace al quinto fallo. El contenido no se guarda en el
 * navegador: al recargar hay que volver a verificar.
 */
import { Component, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';

interface Medicamento {
  readonly nombre: string;
  readonly concentracion: string | null;
  readonly dosis: string;
  readonly via: string;
  readonly cuando_sea_necesario: boolean;
  readonly frecuencia_horas: number | null;
  readonly duracion_dias: number | null;
  readonly instrucciones: string | null;
}

export interface IndicacionPublica {
  readonly nombre_paciente: string;
  readonly clinica: string;
  readonly profesional: string;
  readonly fecha: string;
  readonly texto: string;
  readonly medicamentos: readonly Medicamento[];
}

@Component({
  selector: 'app-indicaciones-publicas',
  standalone: true,
  imports: [DatePipe, FormsModule],
  template: `
    <main class="pagina">
      <article class="tarjeta-publica">
        <p class="marca">ClinicAI</p>
        @if (indicacion(); as i) {
          <header>
            <p class="ceja">{{ i.clinica }}</p>
            <h1>Indicaciones para {{ i.nombre_paciente }}</h1>
            <p class="sub">{{ i.profesional }} · {{ i.fecha | date: 'd MMM y' }}</p>
          </header>
          <section>
            <h2>Qué hacer</h2>
            <p class="texto">{{ i.texto }}</p>
          </section>
          @if (i.medicamentos.length) {
            <section>
              <h2>Medicación indicada</h2>
              <ul class="medicamentos">
                @for (m of i.medicamentos; track $index) {
                  <li>
                    <strong>{{ m.nombre }}@if (m.concentracion) { {{ m.concentracion }} }</strong>
                    <span>
                      {{ m.dosis }} ·
                      {{ m.cuando_sea_necesario ? 'solo cuando sea necesario' : m.frecuencia_horas ? 'cada ' + m.frecuencia_horas + ' horas' : '' }}
                      @if (m.duracion_dias) { · durante {{ m.duracion_dias }} días }
                    </span>
                    @if (m.instrucciones) { <small>{{ m.instrucciones }}</small> }
                  </li>
                }
              </ul>
              <p class="nota">Si tiene dudas o una reacción, llame a la clínica. No cambie la dosis por su cuenta.</p>
            </section>
          }
          <div class="acciones">
            <button class="boton" type="button" (click)="imprimir()">Imprimir</button>
          </div>
        } @else {
          <header>
            <h1>Sus indicaciones</h1>
            <p class="sub">Para proteger su información, confirme que es usted.</p>
          </header>
          <form (ngSubmit)="verificar()" novalidate>
            @if (!usarDocumento()) {
              <label class="campo">
                <span class="campo__etiqueta">Fecha de nacimiento</span>
                <input class="campo__control" type="date" name="fecha" [(ngModel)]="fecha" required [attr.aria-describedby]="error() ? 'mensaje-error' : null" />
              </label>
            } @else {
              <label class="campo">
                <span class="campo__etiqueta">Últimos 4 caracteres de su documento</span>
                <input class="campo__control" name="documento" [(ngModel)]="documento" maxlength="4" required autocomplete="off" [attr.aria-describedby]="error() ? 'mensaje-error' : null" />
              </label>
            }
            <button class="enlace" type="button" (click)="usarDocumento.set(!usarDocumento())">
              {{ usarDocumento() ? 'Usar la fecha de nacimiento' : 'La clínica no tiene mi fecha de nacimiento' }}
            </button>
            @if (error()) { <p id="mensaje-error" class="aviso-error" role="alert">{{ error() }}</p> }
            @if (ocupado()) { <p class="aviso-carga" role="status">Comprobando sus datos…</p> }
            <button class="boton boton--principal" type="submit" [disabled]="ocupado() || bloqueado()">
              {{ ocupado() ? 'Comprobando…' : 'Ver mis indicaciones' }}
            </button>
          </form>
        }
      </article>
    </main>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    :host { display: block; min-height: 100%; color: var(--texto); }
    .pagina { box-sizing: border-box; min-height: 100vh; display: grid; place-items: start center; padding: clamp(16px, 4vw, 40px); background: var(--fondo); }
    .tarjeta-publica { box-sizing: border-box; width: min(100%, 680px); min-width: 0; display: grid; gap: var(--espacio-4); padding: clamp(20px, 4vw, 36px); border: 1px solid var(--borde); border-radius: var(--radio); background: var(--superficie-elevada); box-shadow: var(--sombra-2); overflow-wrap: anywhere; }
    .marca { margin: 0; font-weight: 800; color: var(--acento); }
    .ceja { margin: 0; color: var(--acento); font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; }
    h1 { margin: 2px 0; font-size: clamp(1.35rem, 3vw, 1.8rem); line-height: 1.25; }
    h2 { margin: 0 0 var(--espacio-2); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--texto-suave); }
    .sub { margin: 0; color: var(--texto-suave); }
    .texto { margin: 0; white-space: pre-line; font-size: 1.02rem; line-height: 1.55; }
    .medicamentos { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--espacio-2); }
    .medicamentos li { display: grid; gap: 2px; padding: var(--espacio-3); border-radius: var(--radio); background: var(--superficie); }
    .medicamentos small { color: var(--texto-suave); }
    .nota { margin: var(--espacio-2) 0 0; color: var(--texto-suave); font-size: 0.88rem; }
    form { display: grid; gap: var(--espacio-3); }
    form .campo { margin: 0; }
    .enlace { justify-self: start; max-width: 100%; border: 0; background: transparent; color: var(--acento); text-align: left; text-decoration: underline; cursor: pointer; padding: 4px 0; font: inherit; font-size: 0.95rem; }
    .aviso-error { margin: 0; padding: 12px 14px; border: 1px solid var(--peligro); border-radius: var(--radio); color: var(--peligro); background: var(--superficie); line-height: 1.45; }
    .aviso-carga { margin: 0; color: var(--texto); }
    .acciones { display: flex; justify-content: flex-end; }
    :host :is(button, input):focus-visible { outline: 3px solid var(--acento); outline-offset: 3px; }
    @media (max-width: 480px) { .pagina { padding: 12px; } .tarjeta-publica { gap: 20px; border-radius: 16px; } .acciones, .acciones .boton { width: 100%; } }
    @media print { .acciones, .marca { display: none; } .tarjeta-publica { box-shadow: none; border: 0; } }
  `,
})
export class IndicacionesPublicasComponent {
  private readonly http = inject(HttpClient);
  private readonly configuracion = inject(CONFIGURACION);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';

  protected readonly indicacion = signal<IndicacionPublica | null>(null);
  protected readonly usarDocumento = signal(false);
  protected readonly ocupado = signal(false);
  protected readonly bloqueado = signal(false);
  protected readonly error = signal('');
  protected fecha = '';
  protected documento = '';

  protected verificar(): void {
    if (this.ocupado() || this.bloqueado()) return;
    const cuerpo = this.usarDocumento()
      ? { ultimos_digitos_documento: this.documento.trim() }
      : { fecha_nacimiento: this.fecha || null };
    if (this.usarDocumento() ? this.documento.trim().length !== 4 : !this.fecha) {
      this.error.set(this.usarDocumento() ? 'Escriba los 4 últimos caracteres.' : 'Indique su fecha de nacimiento.');
      return;
    }
    this.ocupado.set(true);
    this.error.set('');
    this.http
      .post<IndicacionPublica>(`${this.configuracion.urlApi}/publico/indicaciones/${this.token}/acceso`, cuerpo)
      .subscribe({
        next: (indicacion) => {
          this.ocupado.set(false);
          this.indicacion.set(indicacion);
        },
        error: (fallo: HttpErrorResponse) => {
          this.ocupado.set(false);
          const cuerpoError = fallo.error as { mensaje?: string; codigo?: string; detalles?: { intentos_restantes?: number } } | null;
          const caducado = fallo.status === 404 || fallo.status === 410;
          if (cuerpoError?.codigo === 'ENLACE_BLOQUEADO' || caducado) this.bloqueado.set(true);
          const restantes = cuerpoError?.detalles?.intentos_restantes;
          this.error.set(
            (caducado
              ? 'Este enlace ha caducado. Solicite uno nuevo a su clínica.'
              : cuerpoError?.codigo === 'ENLACE_BLOQUEADO'
                ? 'Este enlace se bloqueó tras varios intentos. Solicite uno nuevo a su clínica.'
                : cuerpoError?.mensaje ?? 'No se pudo comprobar. Inténtelo de nuevo.') +
              (restantes !== undefined ? ` Le quedan ${restantes} intento(s).` : ''),
          );
        },
      });
  }

  protected imprimir(): void {
    window.print();
  }
}
