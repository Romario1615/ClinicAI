/**
 * Asistente interno del personal.
 *
 * Responde con la agenda, quién sigue, el resumen de la historia del paciente
 * elegido y los documentos aprobados de la clínica; y redacta borradores de
 * conocimiento y de promociones para que alguien los apruebe. No toma
 * decisiones clínicas. Todo con los permisos de quien escribe, comprobados y
 * auditados en el servidor.
 */
import { Component, ElementRef, OnInit, inject, signal, viewChild, ChangeDetectionStrategy } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { CONFIGURACION } from '../../nucleo/servicios/configuracion';
import type { Paciente } from '../../nucleo/modelos/dominio';
import { SelectorPacienteComponent } from '../../compartido/selector-paciente.component';
import { IconoComponent } from '../../compartido/icono.component';

export interface ElementoAsistente {
  readonly titulo: string;
  readonly detalle: string | null;
  readonly enlace: string | null;
}

export interface RespuestaAsistente {
  readonly intencion: string;
  readonly texto: string;
  readonly elementos: readonly ElementoAsistente[];
  readonly enlace: string | null;
  readonly sugerencias: readonly string[];
}

interface Turno {
  readonly autor: 'usted' | 'asistente';
  readonly texto: string;
  readonly elementos?: readonly ElementoAsistente[];
  readonly enlace?: string | null;
}

@Component({
  selector: 'app-asistente',
  standalone: true,
  imports: [FormsModule, RouterLink, SelectorPacienteComponent, IconoComponent],
  host: { class: 'pantalla' },
  template: `
    <header class="modulo-cabecera pantalla__fijo">
      <div class="modulo-cabecera__texto">
        <p class="ceja"><app-icono nombre="asistente-clinico" [tamano]="17" /> ASISTENTE DEL EQUIPO</p>
        <h1>Asistente</h1>
        <p>Pregunte por su agenda, el siguiente paciente o lo que dicen los documentos aprobados. También redacta borradores de conocimiento y de promociones.</p>
      </div>
    </header>

    <div class="asistente pantalla__columnas">
      <aside class="asistente__contexto" aria-label="Paciente de la conversación">
        <h2>Paciente</h2>
        @if (paciente(); as p) {
          <p class="elegido"><strong>{{ p.nombre }} {{ p.apellido }}</strong>
            <button type="button" class="boton boton--plano boton--pequeno" (click)="paciente.set(null)">Quitar</button>
          </p>
        } @else {
          <p class="campo__ayuda">Elíjalo para pedir su resumen. Solo verá lo que su relación asistencial permite.</p>
        }
        <app-selector-paciente (seleccion)="paciente.set($event)" />
        <p class="aviso">No toma decisiones clínicas: muestra lo registrado y lo aprobado.</p>
      </aside>

      <section class="asistente__chat" aria-label="Conversación con el asistente">
        <div class="mensajes desplazable" role="log" aria-live="polite" tabindex="0" #registro>
          @for (turno of turnos(); track $index) {
            <article class="mensaje" [class.mensaje--usted]="turno.autor === 'usted'">
              <p>{{ turno.texto }}</p>
              @if (turno.elementos?.length) {
                <ul class="elementos">
                  @for (e of turno.elementos; track $index) {
                    <li>
                      <strong>{{ e.titulo }}</strong>
                      @if (e.detalle) { <span>{{ e.detalle }}</span> }
                    </li>
                  }
                </ul>
              }
              @if (turno.enlace) { <a class="enlace" [routerLink]="ruta(turno.enlace)" [queryParams]="consulta(turno.enlace)">Abrir</a> }
            </article>
          } @empty {
            <p class="vacio">Empiece con una sugerencia o escriba su pregunta.</p>
          }
          @if (pensando()) { <p class="pensando" role="status">Buscando…</p> }
        </div>

        <div class="sugerencias">
          @for (s of sugerencias(); track s) {
            <button type="button" class="boton boton--pequeno" [disabled]="pensando()" (click)="usarSugerencia(s)">{{ s }}</button>
          }
        </div>

        <form class="compositor" (ngSubmit)="enviar()">
          <label class="campo">
            <span class="campo__etiqueta">Mensaje</span>
            <textarea class="campo__control" name="texto" rows="2" maxlength="1000" [(ngModel)]="texto"
              (keydown.enter)="alEnter($event)" placeholder="Ej.: ¿Quién sigue? · Agrega al conocimiento: …"></textarea>
          </label>
          <button class="boton boton--principal" type="submit" [disabled]="pensando() || !texto.trim()">Enviar</button>
        </form>
        @if (error()) { <p class="campo__error" role="alert">{{ error() }}</p> }
      </section>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .modulo-cabecera {
      position: relative;
      isolation: isolate;
      min-height: 170px;
      overflow: hidden;
      border-color: #165453;
      background-image:
        linear-gradient(90deg, rgb(5 35 39 / 94%) 0%, rgb(5 35 39 / 84%) 39%, rgb(5 35 39 / 25%) 100%),
        url('/images/asistente-clinico-banner.jpg');
      background-position: center, 50% 52%;
      background-size: cover;
      color: #fff;
      animation: asistente-fondo 30s ease-in-out infinite alternate;
    }
    .modulo-cabecera::after {
      position: absolute;
      z-index: 0;
      inset: -60% 8% -60% 48%;
      background: radial-gradient(ellipse, rgb(95 209 196 / 20%), transparent 67%);
      content: '';
      pointer-events: none;
      animation: asistente-halo 17s ease-in-out infinite alternate;
    }
    .modulo-cabecera__texto { position: relative; z-index: 1; max-width: 670px; }
    .modulo-cabecera .ceja { display: flex; align-items: center; gap: var(--espacio-2); color: #aaf4e9; }
    .modulo-cabecera h1 { color: #fff; }
    .modulo-cabecera p:last-child { color: #e0f0ef; }
    @keyframes asistente-fondo {
      from { background-position: center, 48% 52%; }
      to { background-position: center, 54% 52%; }
    }
    @keyframes asistente-halo {
      from { transform: translate3d(-2%, 0, 0) scale(.97); opacity: .55; }
      to { transform: translate3d(2%, 1%, 0) scale(1.04); opacity: .9; }
    }
    .asistente { --pantalla-columnas: minmax(220px, 300px) minmax(0, 1fr); gap: var(--espacio-4); align-items: start; }
    .asistente__contexto, .asistente__chat { padding: var(--espacio-4); border: 1px solid var(--borde);
      border-radius: var(--radio); background: var(--superficie); }
    .asistente__contexto h2 { margin: 0 0 var(--espacio-2); font-size: 1rem; }
    .elegido { display: flex; align-items: center; justify-content: space-between; gap: var(--espacio-2); }
    .aviso { margin: var(--espacio-3) 0 0; color: var(--texto-suave); font-size: 0.85rem; }
    .mensajes { display: grid; gap: var(--espacio-3); max-height: min(60vh, 560px); overflow-y: auto;
      padding-bottom: var(--espacio-2); }
    .mensaje { justify-self: start; max-width: 85%; padding: var(--espacio-3); border-radius: var(--radio);
      background: var(--acento-suave); }
    .mensaje--usted { justify-self: end; background: var(--superficie-elevada, #fff); border: 1px solid var(--borde); }
    .mensaje p { margin: 0; white-space: pre-wrap; }
    .elementos { display: grid; gap: var(--espacio-2); margin: var(--espacio-2) 0 0; padding: 0; list-style: none; }
    .elementos li { display: grid; gap: 2px; padding: var(--espacio-2); border-radius: var(--radio);
      background: rgb(255 255 255 / 70%); }
    .elementos span { color: var(--texto-suave); font-size: 0.9rem; }
    .enlace { display: inline-block; margin-top: var(--espacio-2); font-weight: 600; }
    .vacio, .pensando { color: var(--texto-suave); }
    .sugerencias { display: flex; flex-wrap: wrap; gap: 6px; margin: var(--espacio-3) 0; }
    .compositor { display: grid; grid-template-columns: 1fr auto; gap: var(--espacio-2); align-items: end; }
    .compositor .campo { margin: 0; }
    @media (max-width: 820px) {
      .modulo-cabecera { min-height: 160px; padding: var(--espacio-4); background-position: center, 61% center; }
      .asistente { grid-template-columns: 1fr; }
      .compositor { grid-template-columns: 1fr; }
    }
    @media (prefers-reduced-motion: reduce) {
      .modulo-cabecera, .modulo-cabecera::after { animation: none; }
    }
    /* Pantalla de trabajo: el historial llena el alto y desplaza; las
       sugerencias y el campo de escribir quedan siempre a la vista. */
    .asistente__chat { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
    .asistente__chat > :not(.mensajes) { flex: none; }
    @media (min-width: 821px) and (min-height: 600px) {
      .asistente { align-items: stretch; }
      .modulo-cabecera { min-height: 0; padding: var(--espacio-3) var(--espacio-5); }
      .modulo-cabecera h1 { margin: 0 0 2px; font-size: 1.45rem; }
      .modulo-cabecera p:last-child { font-size: .88rem; }
      .asistente__contexto { min-height: 0; overflow: auto; }
      .mensajes { max-height: none; align-content: start; }
    }
  `,
})
export class AsistenteComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly base = inject(CONFIGURACION).urlApi + '/asistente';
  private readonly registro = viewChild<ElementRef<HTMLElement>>('registro');

  protected readonly turnos = signal<readonly Turno[]>([]);
  protected readonly sugerencias = signal<readonly string[]>([]);
  protected readonly paciente = signal<Paciente | null>(null);
  protected readonly pensando = signal(false);
  protected readonly error = signal('');
  protected texto = '';

  ngOnInit(): void {
    this.http.get<readonly string[]>(`${this.base}/sugerencias`).subscribe({
      next: (lista) => this.sugerencias.set(lista),
      error: () => this.sugerencias.set([]),
    });
  }

  protected usarSugerencia(sugerencia: string): void {
    // Las que terminan en «…» piden completar el texto.
    if (sugerencia.endsWith('…')) {
      this.texto = sugerencia.replace('…', '');
      return;
    }
    this.texto = sugerencia;
    this.enviar();
  }

  protected alEnter(evento: Event): void {
    const teclado = evento as KeyboardEvent;
    if (!teclado.shiftKey) {
      teclado.preventDefault();
      this.enviar();
    }
  }

  protected enviar(): void {
    const texto = this.texto.trim();
    if (!texto || this.pensando()) return;
    this.texto = '';
    this.error.set('');
    this.turnos.update((t) => [...t, { autor: 'usted', texto }]);
    this.pensando.set(true);
    this.http
      .post<RespuestaAsistente>(`${this.base}/mensajes`, { texto, paciente_id: this.paciente()?.id ?? null })
      .subscribe({
        next: (respuesta) => {
          this.pensando.set(false);
          this.turnos.update((t) => [
            ...t,
            { autor: 'asistente', texto: respuesta.texto, elementos: respuesta.elementos, enlace: respuesta.enlace },
          ]);
          if (respuesta.sugerencias.length) this.sugerencias.set(respuesta.sugerencias);
          this.alFinal();
        },
        error: (fallo: HttpErrorResponse) => {
          this.pensando.set(false);
          this.error.set((fallo.error as { mensaje?: string } | null)?.mensaje ?? 'El asistente no pudo responder.');
        },
      });
  }

  protected ruta(enlace: string): string {
    return enlace.split('?')[0];
  }

  protected consulta(enlace: string): Record<string, string> {
    const [, query] = enlace.split('?');
    return Object.fromEntries(new URLSearchParams(query ?? ''));
  }

  private alFinal(): void {
    queueMicrotask(() => {
      const caja = this.registro()?.nativeElement;
      if (caja) caja.scrollTop = caja.scrollHeight;
    });
  }
}
