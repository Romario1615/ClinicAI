/**
 * Consentimientos de comunicación de un paciente.
 *
 * Registrar un consentimiento es dejar constancia de que el paciente leyó y
 * aceptó **este** texto: por eso se muestra el texto completo y hay que marcar
 * la confirmación antes de registrar. El servidor guarda la versión y el hash
 * del texto exacto.
 *
 * Revocar no borra nada: el registro anterior queda para demostrar que hubo
 * consentimiento mientras se enviaron mensajes.
 */
import { Component, computed, effect, inject, input, signal, ChangeDetectionStrategy } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService, FalloApi } from '../nucleo/servicios/api.service';
import type {
  EstadoConsentimiento,
  TextoConsentimiento,
} from '../nucleo/servicios/api.service';
import { PERMISOS } from '../nucleo/servicios/configuracion';
import { SesionService } from '../nucleo/servicios/sesion.service';

@Component({
  selector: 'app-consentimientos-paciente',
  standalone: true,
  imports: [DatePipe, FormsModule],
  template: `
    <section class="consentimientos" aria-labelledby="titulo-consentimientos">
      <h3 id="titulo-consentimientos">Comunicaciones aceptadas</h3>
      @if (error()) {
        <p class="aviso-error" role="alert">{{ error() }}</p>
      }
      @for (estado of estados(); track estado.tipo) {
        <article class="consentimiento" [class.consentimiento--vigente]="estado.vigente">
          <div class="consentimiento__cabecera">
            <strong>{{ estado.titulo }}</strong>
            <span class="consentimiento__estado">
              {{ estado.vigente ? 'Aceptado' : estado.revocado_en ? 'Revocado' : 'No aceptado' }}
            </span>
          </div>
          @if (estado.vigente && estado.otorgado_en) {
            <p class="consentimiento__detalle">
              Desde {{ estado.otorgado_en | date: 'mediumDate' }} · versión {{ estado.version_texto }}
            </p>
          }
          @if (puedeGestionar()) {
            @if (abierto() === estado.tipo) {
              <blockquote class="consentimiento__texto">{{ texto(estado.tipo)?.texto }}</blockquote>
              <label class="campo--en-linea">
                <input type="checkbox" [(ngModel)]="confirmado" [name]="'confirmo-' + estado.tipo" />
                El paciente leyó y aceptó este texto
              </label>
              <div class="acciones">
                <button type="button" class="boton boton--pequeno" (click)="abierto.set(null)">Volver</button>
                <button type="button" class="boton boton--principal boton--pequeno" [disabled]="!confirmado || ocupado()" (click)="otorgar(estado.tipo)">
                  Registrar aceptación
                </button>
              </div>
            } @else if (estado.vigente) {
              <button type="button" class="boton boton--plano boton--pequeno" [disabled]="ocupado()" (click)="revocar(estado.tipo)">
                Registrar baja
              </button>
            } @else {
              <button type="button" class="boton boton--pequeno" (click)="abrir(estado.tipo)">
                Registrar aceptación…
              </button>
            }
          }
        </article>
      }
    </section>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: `
    .consentimientos { display: grid; gap: var(--espacio-2); margin-top: var(--espacio-4); }
    .consentimientos h3 { margin: 0 0 var(--espacio-1); }
    .consentimiento { display: grid; gap: var(--espacio-2); padding: var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio); }
    .consentimiento--vigente { border-color: var(--exito); box-shadow: inset 3px 0 0 var(--exito); }
    .consentimiento__cabecera { display: flex; justify-content: space-between; gap: var(--espacio-2); }
    .consentimiento__estado { font-size: .8rem; font-weight: 700; color: var(--texto-suave); }
    .consentimiento--vigente .consentimiento__estado { color: var(--exito); }
    .consentimiento__detalle { margin: 0; font-size: .82rem; color: var(--texto-suave); }
    .consentimiento__texto { margin: 0; padding: var(--espacio-2) var(--espacio-3); border: 1px solid var(--borde); border-radius: var(--radio-md); background: var(--superficie); font-size: .88rem; }
    .consentimiento .boton { justify-self: start; }
  `,
})
export class ConsentimientosPacienteComponent {
  private readonly api = inject(ApiService);
  private readonly sesion = inject(SesionService);

  readonly pacienteId = input.required<string>();

  protected readonly estados = signal<readonly EstadoConsentimiento[]>([]);
  protected readonly textos = signal<readonly TextoConsentimiento[]>([]);
  protected readonly abierto = signal<string | null>(null);
  protected readonly ocupado = signal(false);
  protected readonly error = signal('');
  protected confirmado = false;

  protected readonly puedeGestionar = computed(() =>
    this.sesion.tienePermiso(PERMISOS.consentimientoGestionar),
  );

  constructor() {
    effect(() => this.cargar(this.pacienteId()));
  }

  private cargar(pacienteId: string): void {
    this.api.consentimientos(pacienteId).subscribe({
      next: (estados) => this.estados.set(estados),
      error: (fallo: unknown) => this.error.set(this.mensaje(fallo)),
    });
  }

  protected texto(tipo: string): TextoConsentimiento | undefined {
    return this.textos().find((t) => t.tipo === tipo);
  }

  protected abrir(tipo: string): void {
    this.confirmado = false;
    this.error.set('');
    if (this.textos().length) {
      this.abierto.set(tipo);
      return;
    }
    this.api.textosConsentimiento().subscribe({
      next: (textos) => {
        this.textos.set(textos);
        this.abierto.set(tipo);
      },
      error: (fallo: unknown) => this.error.set(this.mensaje(fallo)),
    });
  }

  protected otorgar(tipo: string): void {
    const texto = this.texto(tipo);
    if (!texto || !this.confirmado) return;
    this.ocupado.set(true);
    this.api.otorgarConsentimiento(this.pacienteId(), tipo, texto.version).subscribe({
      next: (estado) => this.terminar(estado),
      error: (fallo: unknown) => this.fallar(fallo),
    });
  }

  protected revocar(tipo: string): void {
    this.ocupado.set(true);
    this.api.revocarConsentimiento(this.pacienteId(), tipo).subscribe({
      next: (estado) => this.terminar(estado),
      error: (fallo: unknown) => this.fallar(fallo),
    });
  }

  private terminar(estado: EstadoConsentimiento): void {
    this.ocupado.set(false);
    this.abierto.set(null);
    this.estados.update((lista) => lista.map((e) => (e.tipo === estado.tipo ? estado : e)));
  }

  private fallar(fallo: unknown): void {
    this.ocupado.set(false);
    this.error.set(this.mensaje(fallo));
  }

  private mensaje(fallo: unknown): string {
    return fallo instanceof FalloApi ? fallo.message : 'No se pudo registrar el consentimiento.';
  }
}
