/**
 * La cola de trabajo: lo que hay que hacer ahora, con su plazo.
 *
 * Se usa en dos sitios a propósito
 * --------------------------------
 * En el **panel**, al empezar el turno, como primer bloque de la pantalla.
 * En la **agenda**, ocupando el panel derecho mientras no haya nada
 * seleccionado.
 *
 * Es el mismo componente porque es la misma pregunta: «¿qué se rompe hoy si
 * nadie lo toca?». Duplicarlo garantizaría que un día divergen y que quien
 * mira el panel y quien mira la agenda ven listas distintas.
 *
 * Este componente no deriva nada
 * ------------------------------
 * Recibe las tareas ya calculadas (`utilidades/pendientes.ts`) y solo las
 * pinta. La regla de negocio vive en una función pura que se prueba sin DOM;
 * aquí solo queda la presentación, y eso es lo que hace que la regla se pueda
 * cambiar sin tocar HTML.
 *
 * El color nunca informa solo
 * ---------------------------
 * Una tarea urgente lleva ámbar **y** la palabra del plazo. Aproximadamente
 * una de cada doce personas con visión cromática típica masculina no
 * distinguiría el ámbar del gris, y esta es la pantalla donde se decide a quién
 * se llama antes.
 */
import { Component, computed, input, output } from '@angular/core';

import type { TareaPendiente } from '../nucleo/utilidades/pendientes';

@Component({
  selector: 'app-cola-trabajo',
  standalone: true,
  template: `
    @if (tareas().length === 0) {
      <p class="cola__vacio" role="status">
        <span class="cola__tic" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        Nada pendiente con plazo. La jornada está al día.
      </p>
    } @else {
      <ul class="cola" [class.cola--rejilla]="rejilla()">
        @for (tarea of tareas(); track tarea.clase) {
          <li class="cola__item" [class.cola__item--urgente]="tarea.urgente">
            <p class="cola__cabecera">
              <span class="cola__icono" aria-hidden="true">
                @switch (tarea.clase) {
                  @case ('caduca') {
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
                      <circle cx="12" cy="12" r="9" /><path d="M12 7.5V12l3 2" />
                    </svg>
                  }
                  @case ('llamar') {
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
                      <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1.5 1.5 0 0 1-1.7 1.5C10.8 19.6 4.4 13.2 3.5 5.7A1.5 1.5 0 0 1 5 4z" />
                    </svg>
                  }
                  @default {
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                  }
                }
              </span>
              <span class="cola__etiqueta">{{ tarea.etiqueta }}</span>
              <span class="cola__plazo numerico">{{ tarea.plazo }}</span>
            </p>
            <p class="cola__titulo">{{ tarea.titulo }}</p>
            <p class="cola__detalle">{{ tarea.detalle }}</p>
            <div class="fila">
              <button
                type="button"
                class="boton boton--principal boton--pequeno"
                (click)="actuar.emit(tarea)"
              >
                {{ tarea.accion }}
              </button>
              <button type="button" class="boton boton--pequeno" (click)="localizar.emit(tarea)">
                Ver en la agenda
              </button>
            </div>
          </li>
        }
      </ul>
    }
  `,
  styles: `
    .cola {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: var(--espacio-3);
    }

    /* En el panel las tareas van en fila; en la agenda, apiladas en la
       columna derecha. La misma lista, dos formas. */
    .cola--rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: var(--espacio-4);
    }

    .cola__item {
      display: flex;
      flex-direction: column;
      gap: var(--espacio-1);
      padding: var(--espacio-3);
      border: 1px solid var(--borde);
      border-left-width: 4px;
      border-radius: var(--radio);
      background: var(--superficie-elevada);
    }

    /* Ámbar más la palabra del plazo. El tono acompaña; no informa solo. */
    .cola__item--urgente {
      border-color: var(--aviso);
      background: var(--aviso-fondo);
    }

    .cola__cabecera {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      margin: 0 0 var(--espacio-1);
      color: var(--texto-suave);
    }

    .cola__item--urgente .cola__cabecera {
      color: var(--aviso);
    }

    .cola__icono {
      display: inline-flex;
    }

    .cola__etiqueta {
      font-size: 0.78rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .cola__plazo {
      margin-left: auto;
      font-size: 0.82rem;
      font-weight: 650;
    }

    .cola__titulo {
      margin: 0;
      font-weight: 650;
    }

    .cola__detalle {
      margin: 0 0 var(--espacio-2);
      color: var(--texto-suave);
      font-size: 0.88rem;
    }

    .cola__vacio {
      display: flex;
      align-items: center;
      gap: var(--espacio-2);
      margin: 0;
      padding: var(--espacio-3) var(--espacio-4);
      border: 1px solid var(--exito);
      border-radius: var(--radio);
      background: var(--exito-fondo);
      color: var(--exito);
      font-weight: 550;
    }

    .cola__tic {
      display: inline-flex;
    }
  `,
})
export class ColaTrabajoComponent {
  readonly tareas = input.required<readonly TareaPendiente[]>();

  /** Cierto en el panel, donde hay ancho para ponerlas en fila. */
  readonly rejilla = input(false);

  /** El botón principal de una tarea. */
  readonly actuar = output<TareaPendiente>();

  /** Llevar la vista al sitio donde está esa tarea. */
  readonly localizar = output<TareaPendiente>();

  /** Cuántas corren contra un plazo. Lo usa la cabecera del panel. */
  readonly urgentes = computed(() => this.tareas().filter((tarea) => tarea.urgente).length);
}
