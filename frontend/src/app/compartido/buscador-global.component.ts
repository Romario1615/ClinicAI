/**
 * Buscador de la cabecera: encuentra un paciente y abre su ficha flotando.
 *
 * Qué problema resuelve
 * ---------------------
 * Antes, saber algo de un paciente exigía ir a «Pacientes», buscarlo, y volver
 * a donde se estaba. Con el teléfono sonando eso significa que no se consulta.
 * Aquí se escribe el apellido desde cualquier pantalla y la ficha se abre
 * **encima**, sin navegar: al cerrarla todo sigue donde estaba.
 *
 * Por qué busca al enviar y no en cada tecla
 * ------------------------------------------
 * Cada consulta de pacientes queda registrada en la auditoría. Buscar en cada
 * pulsación generaría diez entradas de auditoría por búsqueda y ruido que
 * después impide investigar un acceso de verdad.
 *
 * Qué se envía
 * ------------
 * Si el término son solo dígitos se busca por documento; si no, por nombre o
 * apellido (`filtroBusquedaPaciente`). Eso importa porque el backend ignora un
 * término que no encaja y devolvería cero resultados sin decir por qué.
 */
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FichaPacienteComponent } from './ficha-paciente.component';
import { FotoPerfilComponent } from './foto-perfil.component';
import { IconoComponent } from './icono.component';
import { VentanaFlotanteComponent } from './ventana-flotante.component';
import { ApiService, filtroBusquedaPaciente } from '../nucleo/servicios/api.service';
import { PERMISOS } from '../nucleo/servicios/configuracion';
import { SesionService } from '../nucleo/servicios/sesion.service';
import type { Paciente } from '../nucleo/modelos/dominio';

@Component({
  selector: 'app-buscador-global',
  standalone: true,
  imports: [
    FormsModule,
    IconoComponent,
    VentanaFlotanteComponent,
    FichaPacienteComponent,
    FotoPerfilComponent,
  ],
  template: `
    @if (sesion.tienePermiso(PERMISOS.pacienteLeer)) {
      <form class="buscador" (ngSubmit)="buscar()" role="search">
        <label class="buscador__campo">
          <span class="solo-lectores">Buscar paciente por nombre, apellido o documento</span>
          <app-icono nombre="buscar" [tamano]="16" />
          <input
            type="search"
            name="termino"
            autocomplete="off"
            placeholder="Buscar paciente…"
            [(ngModel)]="termino"
            (ngModelChange)="alEscribir()"
          />
        </label>
        <button type="submit" class="boton boton--pequeno" [disabled]="buscando()">Buscar</button>
      </form>

      @if (abierto()) {
        <div class="buscador__resultados" role="region" aria-label="Resultados de la búsqueda">
          @if (buscando()) {
            <p class="buscador__nota" role="status">Buscando…</p>
          } @else if (error()) {
            <p class="buscador__nota buscador__nota--error" role="alert">{{ error() }}</p>
          } @else if (resultados().length === 0) {
            <p class="buscador__nota">
              Sin coincidencias para «{{ ultimoTermino() }}».
              @if (soloDigitos()) {
                <span>Se buscó por número de documento.</span>
              } @else {
                <span>Se buscó por nombre y apellido.</span>
              }
            </p>
          } @else {
            <ul class="buscador__lista">
              @for (paciente of resultados(); track paciente.id) {
                <li>
                  <button type="button" class="buscador__opcion" (click)="abrirFicha(paciente)">
                    <!-- La foto distingue a dos personas con el mismo nombre en el
                         mostrador. Es N1: la ve quien ya puede ver la ficha. -->
                    <app-foto-perfil
                      [pacienteId]="paciente.id"
                      [nombre]="paciente.nombre + ' ' + paciente.apellido"
                      [iniciales]="paciente.nombre.charAt(0) + paciente.apellido.charAt(0)"
                      [tamano]="32"
                    />
                    <span class="buscador__texto">
                      <span class="buscador__nombre">
                        {{ paciente.apellido }}, {{ paciente.nombre }}
                      </span>
                      <span class="buscador__doc numerico">{{ paciente.numero_documento }}</span>
                    </span>
                  </button>
                </li>
              }
            </ul>
          }
          <button type="button" class="boton boton--plano boton--pequeno" (click)="cerrar()">
            Cerrar resultados
          </button>
        </div>
      }

      <!-- La ficha flota: la pantalla de detrás no se mueve ni pierde el sitio. -->
      @if (pacienteElegido(); as elegido) {
        <app-ventana-flotante
          ceja="Ficha del paciente"
          [titulo]="elegido.apellido + ', ' + elegido.nombre"
          forma="centrada"
          [anchoMaximo]="1180"
          [altoCompleto]="true"
          (cerrar)="pacienteElegido.set(null)"
        >
          <app-ficha-paciente [pacienteId]="elegido.id" [sinCabecera]="true" />
        </app-ventana-flotante>
      }
    }
  `,
  styles: `
    :host {
      display: contents;
    }

    .buscador {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
    }

    @media (max-width: 540px) {
      .buscador {
        flex: 1 1 100%;
        min-width: 0;
        order: 5;
      }

      .buscador__campo {
        flex: 1;
        min-width: 0;
      }

      .buscador__campo input {
        width: 100%;
        min-width: 0;
      }
    }

    .buscador__campo {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      min-height: 38px;
      padding: 0 var(--espacio-3);
      border: 1px solid var(--borde);
      border-radius: 999px;
      background: var(--superficie);
      color: var(--texto-tenue);
    }

    .buscador__campo:focus-within {
      border-color: var(--acento);
      background: var(--superficie-elevada);
    }

    .buscador__campo input {
      width: 190px;
      border: 0;
      background: transparent;
      color: var(--texto);
      font-size: 0.92rem;
    }

    .buscador__campo input:focus {
      outline: none;
    }

    .buscador__resultados {
      position: absolute;
      top: 52px;
      left: 220px;
      z-index: 30;
      width: min(420px, calc(100vw - 32px));
      padding: var(--espacio-3);
      border: 1px solid var(--borde);
      border-radius: var(--radio);
      background: var(--superficie-elevada);
      box-shadow: var(--sombra-2);
    }

    .buscador__lista {
      list-style: none;
      margin: 0 0 var(--espacio-2);
      padding: 0;
      max-height: 320px;
      overflow-y: auto;
    }

    .buscador__lista button {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--espacio-3);
      width: 100%;
      min-height: var(--toque-minimo);
      padding: var(--espacio-2) var(--espacio-3);
      border: 0;
      border-radius: var(--radio-pequeno);
      background: transparent;
      text-align: left;
      cursor: pointer;
    }

    .buscador__lista button:hover {
      background: var(--acento-suave);
    }

    .buscador__nombre {
      font-weight: 600;
    }

    .buscador__lista .buscador__opcion {
      align-items: center;
      justify-content: flex-start;
    }

    .buscador__texto {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    .buscador__doc {
      color: var(--texto-tenue);
      font-size: 0.85rem;
    }

    .buscador__nota {
      margin: 0 0 var(--espacio-2);
      color: var(--texto-suave);
      font-size: 0.9rem;
    }

    .buscador__nota--error {
      color: var(--peligro);
    }

    @media (max-width: 980px) {
      .buscador__campo input {
        width: 120px;
      }
    }

    @media (max-width: 720px) {
      .buscador {
        display: none;
      }
    }
  `,
})
export class BuscadorGlobalComponent {
  private readonly api = inject(ApiService);
  protected readonly sesion = inject(SesionService);
  protected readonly PERMISOS = PERMISOS;

  protected termino = '';
  protected readonly ultimoTermino = signal('');
  protected readonly resultados = signal<readonly Paciente[]>([]);
  protected readonly buscando = signal(false);
  protected readonly abierto = signal(false);
  protected readonly error = signal('');
  protected readonly pacienteElegido = signal<Paciente | null>(null);

  protected readonly soloDigitos = computed(() => /^\d+$/.test(this.ultimoTermino().trim()));

  protected alEscribir(): void {
    // Al vaciar el campo se cierra el panel: dejar resultados de una búsqueda
    // anterior sobre un campo vacío se lee como si fueran de la actual.
    if (!this.termino.trim()) {
      this.abierto.set(false);
      this.resultados.set([]);
    }
  }

  protected buscar(): void {
    const limpio = this.termino.trim();
    if (!limpio || this.buscando()) {
      return;
    }
    this.buscando.set(true);
    this.abierto.set(true);
    this.error.set('');
    this.ultimoTermino.set(limpio);

    this.api.pacientes({ ...filtroBusquedaPaciente(limpio), limite: 20 }).subscribe({
      next: (pagina) => {
        this.resultados.set(pagina.elementos);
        this.buscando.set(false);
      },
      error: () => {
        this.resultados.set([]);
        this.error.set('No se pudo buscar. Inténtelo de nuevo.');
        this.buscando.set(false);
      },
    });
  }

  protected abrirFicha(paciente: Paciente): void {
    this.pacienteElegido.set(paciente);
    this.abierto.set(false);
  }

  protected cerrar(): void {
    this.abierto.set(false);
  }
}
