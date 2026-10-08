/**
 * Ayuda y documentación: el manual de cada rol de la sesión.
 *
 * Cada persona ve el manual de **sus** roles, y de cada rol solo las tareas
 * que puede hacer hoy (lo decide el servidor con los permisos vigentes). Si
 * tiene varios roles, cada uno es una pestaña con su propio manual: mezclarlos
 * en uno solo es justo lo que la tarea 11.1 prohíbe.
 *
 * Las tareas se pueden filtrar por texto y cada una enlaza a la pantalla
 * donde se hace. La cabecera lleva el gráfico en movimiento de la clínica
 * conectada; es decorativo y queda quieto con movimiento reducido.
 */
import { Component, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';

import { CargandoComponent, ErrorComponent, VacioComponent } from '../../compartido/estados.component';
import { GraficoRedComponent } from '../../compartido/grafico-red.component';
import { IconoComponent } from '../../compartido/icono.component';
import { FalloApi } from '../../nucleo/servicios/api.service';
import { AyudaService, type Manual, type SeccionManual } from './ayuda.service';

/** Nombre visible de cada pantalla, igual que en la navegación. */
const PANTALLAS: Readonly<Record<string, string>> = {
  '/panel': 'Panel',
  '/plataforma/clinicas': 'Clínicas',
  '/usuarios': 'Usuarios y roles',
  '/agenda': 'Agenda',
  '/pacientes': 'Pacientes',
  '/lista-espera': 'Lista de espera',
  '/historia-clinica': 'Historia clínica',
  '/medicamentos': 'Medicamentos',
  '/conocimiento': 'Conocimiento',
  '/equipo': 'Equipo clínico',
  '/promociones': 'Promociones',
  '/catalogo': 'Catálogo',
  '/pagos': 'Pagos',
  '/gastos': 'Gastos y caja',
  '/conversaciones': 'Atención de mensajes',
  '/seguridad': 'Seguridad clínica',
  '/asistente': 'Asistente',
  '/automatizaciones': 'Automatizaciones',
  '/configuracion': 'Configuración',
};

/** Normaliza para buscar sin distinguir tildes ni mayúsculas. */
function normalizar(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

@Component({
  selector: 'app-ayuda',
  standalone: true,
  imports: [RouterLink, IconoComponent, GraficoRedComponent, CargandoComponent, ErrorComponent, VacioComponent],
  host: { class: 'pantalla' },
  template: `
    <header class="modulo-cabecera ayuda__cabecera pantalla__fijo">
      <div class="modulo-cabecera__texto">
        <p class="ceja"><app-icono nombre="ayuda" [tamano]="16" /> AYUDA Y DOCUMENTACIÓN</p>
        <h1>Su manual de trabajo</h1>
        <p>
          Lo que su rol hace en ClinicAI, paso a paso y con sus límites. Solo aparecen las tareas que
          sus permisos habilitan hoy: si la clínica los cambia, el manual cambia con ellos.
        </p>
      </div>
      <app-grafico-red class="ayuda__grafico" tono="claro" />
    </header>

    @if (cargando()) {
      <app-cargando class="pantalla__fijo" mensaje="Preparando su manual…" />
    } @else if (error(); as fallo) {
      <app-error
        class="pantalla__fijo"
        titulo="No se pudo cargar la ayuda"
        [mensaje]="fallo.message"
        [codigo]="fallo.codigo"
        [correlacion]="fallo.correlacionId ?? ''"
        (reintentar)="cargar()"
      />
    } @else if (manuales().length === 0) {
      <app-vacio
        class="pantalla__fijo"
        titulo="Su cuenta no tiene roles vigentes"
        detalle="Pida a la administración de la clínica que le asigne un rol; su manual aparecerá aquí."
      />
    } @else {
      @if (manuales().length > 1) {
        <div class="ayuda__pestanas pantalla__fijo" role="tablist" aria-label="Manuales de sus roles">
          @for (manual of manuales(); track manual.rol_codigo; let indice = $index) {
            <button
              type="button"
              role="tab"
              class="ayuda__pestana"
              [id]="'pestana-' + manual.rol_codigo"
              [attr.aria-selected]="indice === indiceActivo()"
              [attr.aria-controls]="'manual-' + manual.rol_codigo"
              [attr.tabindex]="indice === indiceActivo() ? 0 : -1"
              (click)="elegir(indice)"
              (keydown)="alTeclearPestana($event, indice)"
            >
              {{ manual.rol_nombre }}
            </button>
          }
        </div>
      }

      @if (activo(); as manual) {
        <!-- Dos columnas: el rol y sus límites a un lado, las tareas al otro.
             Cada una desplaza dentro; la pantalla no se mueve. -->
        <section
          class="ayuda__manual pantalla__columnas"
          [id]="'manual-' + manual.rol_codigo"
          [attr.role]="manuales().length > 1 ? 'tabpanel' : null"
          [attr.aria-labelledby]="manuales().length > 1 ? 'pestana-' + manual.rol_codigo : 'titulo-manual'"
        >
          <div class="ayuda__resumen desplazable" tabindex="0" role="region" aria-label="El rol y sus límites">
            <article class="tarjeta ayuda__intro">
              <p class="ceja">{{ manual.tipo === 'SISTEMA' ? 'ROL DEL SISTEMA' : 'ROL DE SU CLÍNICA' }}</p>
              <h2 id="titulo-manual">{{ manual.titulo }}</h2>
              <p>{{ manual.introduccion }}</p>
              @if (manual.responsabilidades.length) {
                <h3>De qué se ocupa</h3>
                <ul class="ayuda__lista ayuda__lista--tic">
                  @for (texto of manual.responsabilidades; track texto) {
                    <li>{{ texto }}</li>
                  }
                </ul>
              }
            </article>
            <article class="tarjeta ayuda__limites" aria-labelledby="titulo-limites">
              <p class="ceja"><app-icono nombre="escudo" [tamano]="15" /> LÍMITES</p>
              <h2 id="titulo-limites">Lo que este rol no hace</h2>
              <ul class="ayuda__lista ayuda__lista--limite">
                @for (texto of manual.limites; track texto) {
                  <li>{{ texto }}</li>
                }
              </ul>
            </article>
          </div>

          <div class="ayuda__columna-tareas">
          <div class="ayuda__barra">
            <h2 class="ayuda__subtitulo">
              Tareas <span class="ayuda__cuenta numerico">{{ seccionesVisibles().length }}</span>
            </h2>
            <label class="ayuda__buscar">
              <app-icono nombre="buscar" [tamano]="16" />
              <span class="solo-lectores">Buscar en el manual</span>
              <input
                type="search"
                placeholder="Buscar una tarea…"
                [value]="filtro()"
                (input)="filtro.set($any($event.target).value)"
              />
            </label>
          </div>

          <div class="ayuda__lista-tareas desplazable" tabindex="0" role="region" aria-label="Tareas del manual">
          @if (seccionesVisibles().length === 0) {
            <app-vacio
              titulo="Ninguna tarea coincide"
              [detalle]="manual.secciones.length ? 'Pruebe con otra palabra.' : 'Este rol no tiene tareas habilitadas todavía.'"
            />
          } @else {
            <ol class="ayuda__tareas">
              @for (seccion of seccionesVisibles(); track seccion.clave; let indice = $index) {
                <li class="tarjeta ayuda__tarea">
                  <details [open]="indice === 0 || filtro().length > 0">
                    <summary>
                      <span class="ayuda__numero numerico" aria-hidden="true">{{ indice + 1 }}</span>
                      <span class="ayuda__titulos">
                        <strong>{{ seccion.titulo }}</strong>
                        <span>{{ seccion.proposito }}</span>
                      </span>
                    </summary>
                    <div class="ayuda__cuerpo">
                      <ol class="ayuda__pasos">
                        @for (paso of seccion.pasos; track paso) {
                          <li>{{ paso }}</li>
                        }
                      </ol>
                      @if (seccion.limites.length) {
                        <ul class="ayuda__lista ayuda__lista--limite">
                          @for (texto of seccion.limites; track texto) {
                            <li>{{ texto }}</li>
                          }
                        </ul>
                      }
                      <div class="ayuda__pie">
                        @if (seccion.permisos.length) {
                          <ul class="ayuda__permisos" aria-label="Permisos que usa esta tarea">
                            @for (permiso of seccion.permisos; track permiso.codigo) {
                              <li [title]="permiso.codigo">{{ permiso.descripcion }}</li>
                            }
                          </ul>
                        }
                        @if (seccion.ruta) {
                          <a class="boton boton--pequeno boton--principal" [routerLink]="seccion.ruta">
                            Ir a {{ pantalla(seccion.ruta) }}
                          </a>
                        }
                      </div>
                    </div>
                  </details>
                </li>
              }
            </ol>
          }
          </div>
          </div>
        </section>
      }
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .ayuda__cabecera {
      gap: var(--espacio-5);
    }
    .ayuda__grafico {
      flex: 0 1 300px;
      max-width: 300px;
    }
    .ayuda__pestanas {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-bottom: var(--espacio-4);
      padding: 4px;
      border: 1px solid var(--vidrio-borde);
      border-radius: 999px;
      background: linear-gradient(180deg, rgb(255 255 255 / 70%), rgb(255 255 255 / 55%));
      box-shadow: var(--vidrio-canto), var(--vidrio-sombra);
    }
    .ayuda__pestana {
      min-height: 40px;
      padding: 0 var(--espacio-4);
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--texto-suave);
      font-weight: 650;
      cursor: pointer;
      transition: background-color 180ms ease, color 180ms ease, box-shadow 180ms ease;
    }
    .ayuda__pestana[aria-selected='true'] {
      background: linear-gradient(180deg, var(--acento), var(--acento-fuerte));
      color: var(--acento-texto);
      box-shadow: inset 0 1px 0 rgb(255 255 255 / 30%), 0 6px 16px -8px rgb(11 110 106 / 60%);
    }
    .ayuda__resumen {
      display: grid;
      gap: var(--espacio-3);
      align-content: start;
    }
    .ayuda__manual {
      --pantalla-columnas: minmax(0, 1fr) minmax(0, 1.7fr);
    }
    .ayuda__columna-tareas {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
    }
    .ayuda__barra {
      flex: none;
    }
    .ayuda__intro h2,
    .ayuda__limites h2 {
      margin-top: var(--espacio-1);
    }
    .ayuda__intro h3 {
      margin-top: var(--espacio-4);
      font-size: 0.95rem;
    }
    .ayuda__lista {
      display: grid;
      gap: var(--espacio-2);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .ayuda__lista li {
      position: relative;
      padding-left: 26px;
    }
    .ayuda__lista li::before {
      content: '';
      position: absolute;
      top: 0.45em;
      left: 4px;
      width: 12px;
      height: 12px;
      border-radius: 50%;
    }
    /* La forma distingue además del color: un círculo con tic para lo que se
       hace, un rombo para lo que no. */
    .ayuda__lista--tic li::before {
      background: var(--exito-fondo);
      box-shadow: inset 0 0 0 2px var(--exito);
    }
    .ayuda__lista--limite li::before {
      border-radius: 2px;
      transform: rotate(45deg) scale(0.8);
      background: var(--aviso-fondo);
      box-shadow: inset 0 0 0 2px var(--aviso);
    }
    .ayuda__barra {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-3);
      margin-bottom: var(--espacio-3);
    }
    .ayuda__subtitulo {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      margin: 0;
    }
    .ayuda__cuenta {
      min-width: 28px;
      padding: 0 8px;
      border-radius: 999px;
      background: var(--acento-suave);
      color: var(--acento-fuerte);
      font-size: 0.85rem;
      text-align: center;
    }
    .ayuda__buscar {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      min-height: 42px;
      padding: 0 var(--espacio-3);
      border: 1px solid var(--borde-fuerte);
      border-radius: 999px;
      background: rgb(255 255 255 / 85%);
      color: var(--texto-tenue);
    }
    .ayuda__buscar:focus-within {
      border-color: var(--acento);
      box-shadow: 0 0 0 4px rgb(95 209 196 / 26%);
    }
    .ayuda__buscar input {
      width: min(260px, 52vw);
      border: 0;
      background: transparent;
      color: var(--texto);
    }
    .ayuda__buscar input:focus {
      outline: none;
    }
    .ayuda__tareas {
      display: grid;
      gap: var(--espacio-3);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .ayuda__tarea {
      padding: 0;
    }
    .ayuda__tarea summary {
      display: flex;
      align-items: flex-start;
      gap: var(--espacio-3);
      padding: var(--espacio-4) var(--espacio-5);
      cursor: pointer;
      list-style: none;
    }
    .ayuda__tarea summary::-webkit-details-marker {
      display: none;
    }
    .ayuda__tarea summary:focus-visible {
      outline-offset: -3px;
    }
    .ayuda__numero {
      display: grid;
      flex: 0 0 32px;
      height: 32px;
      place-items: center;
      border-radius: 50%;
      background: linear-gradient(160deg, #fff, var(--acento-suave));
      box-shadow: inset 0 0 0 1px rgb(11 110 106 / 25%);
      color: var(--acento-fuerte);
      font-weight: 750;
    }
    .ayuda__titulos {
      display: grid;
      gap: 2px;
    }
    .ayuda__titulos span {
      color: var(--texto-suave);
      font-size: 0.92rem;
    }
    .ayuda__cuerpo {
      display: grid;
      gap: var(--espacio-4);
      padding: 0 var(--espacio-5) var(--espacio-5) calc(var(--espacio-5) + 44px);
    }
    .ayuda__pasos {
      display: grid;
      gap: var(--espacio-2);
      margin: 0;
      padding-left: 1.2rem;
    }
    .ayuda__pasos li::marker {
      color: var(--acento);
      font-weight: 750;
    }
    .ayuda__pie {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--espacio-3);
    }
    .ayuda__permisos {
      display: flex;
      flex-wrap: wrap;
      gap: var(--espacio-2);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .ayuda__permisos li {
      padding: 2px 10px;
      border: 1px solid rgb(11 110 106 / 22%);
      border-radius: 999px;
      background: rgb(220 240 238 / 60%);
      color: var(--acento-fuerte);
      font-size: 0.78rem;
      font-weight: 600;
    }
    @media (max-width: 720px) {
      .ayuda__grafico {
        display: none;
      }
      .ayuda__cuerpo {
        padding-left: var(--espacio-5);
      }
    }
    /* Escritorio: cabecera baja, pestañas sin margen y las listas llenan el
       alto de su columna. */
    @media (min-width: 821px) and (min-height: 600px) {
      .ayuda__cabecera p:last-child {
        font-size: 0.88rem;
      }
      /* El gráfico guarda su proporción: con 160 px de ancho mide unos 90 de
         alto y deja de ser lo que fija el alto de la cabecera. */
      .ayuda__grafico {
        flex-basis: 160px;
        max-width: 160px;
      }
      .ayuda__pestanas {
        margin-bottom: 0;
      }
      .ayuda__resumen .tarjeta {
        padding: var(--espacio-4);
      }
      .ayuda__tarea summary {
        padding: var(--espacio-3) var(--espacio-4);
      }
      .ayuda__cuerpo {
        padding: 0 var(--espacio-4) var(--espacio-4) calc(var(--espacio-4) + 44px);
      }
    }
  `,
})
export class AyudaComponent {
  private readonly ayuda = inject(AyudaService);

  protected readonly manuales = signal<readonly Manual[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<FalloApi | null>(null);
  protected readonly indiceActivo = signal(0);
  protected readonly filtro = signal('');

  protected readonly activo = computed<Manual | null>(() => this.manuales()[this.indiceActivo()] ?? null);

  protected readonly seccionesVisibles = computed<readonly SeccionManual[]>(() => {
    const manual = this.activo();
    if (!manual) {
      return [];
    }
    const terminos = normalizar(this.filtro()).split(/\s+/).filter(Boolean);
    if (terminos.length === 0) {
      return manual.secciones;
    }
    return manual.secciones.filter((seccion) => {
      const texto = normalizar(
        [seccion.titulo, seccion.proposito, ...seccion.pasos, ...seccion.limites].join(' '),
      );
      return terminos.every((termino) => texto.includes(termino));
    });
  });

  constructor() {
    this.cargar();
  }

  cargar(): void {
    this.cargando.set(true);
    this.error.set(null);
    this.ayuda.manuales().subscribe({
      next: (manuales) => {
        this.manuales.set(manuales);
        this.indiceActivo.set(0);
        this.cargando.set(false);
      },
      error: (fallo: unknown) => {
        this.error.set(
          fallo instanceof FalloApi ? fallo : new FalloApi('ERROR_DESCONOCIDO', 'No se pudo cargar la ayuda.', 0),
        );
        this.cargando.set(false);
      },
    });
  }

  protected elegir(indice: number): void {
    this.indiceActivo.set(indice);
    this.filtro.set('');
  }

  /** Flechas entre pestañas, como en cualquier lista de pestañas accesible. */
  protected alTeclearPestana(evento: KeyboardEvent, indice: number): void {
    const total = this.manuales().length;
    const destino =
      evento.key === 'ArrowRight' ? (indice + 1) % total
      : evento.key === 'ArrowLeft' ? (indice - 1 + total) % total
      : evento.key === 'Home' ? 0
      : evento.key === 'End' ? total - 1
      : null;
    if (destino === null) {
      return;
    }
    evento.preventDefault();
    this.elegir(destino);
    const lista = (evento.currentTarget as HTMLElement).parentElement;
    lista?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[destino]?.focus();
  }

  protected pantalla(ruta: string): string {
    return PANTALLAS[ruta] ?? ruta;
  }
}
