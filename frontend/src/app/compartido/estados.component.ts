/**
 * Componentes de estado: cargando, vacio, error y aviso de demostracion.
 *
 * Existen como piezas propias porque **cada pantalla tiene que cubrir los
 * cuatro estados**, y la forma mas fiable de que ninguna los olvide es que
 * sean baratos de usar. Una tabla que solo contempla el caso con datos
 * aparece en blanco cuando falla la red, y quien la usa no sabe si no hay
 * citas o si el sistema esta roto.
 *
 * Los tres estados se anuncian a los lectores de pantalla con `role` y
 * `aria-live` adecuados: quien no ve el spinner necesita enterarse igual.
 */
import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-cargando',
  standalone: true,
  template: `
    <div class="cargando" role="status" aria-live="polite">
      <span class="cargando__rueda" aria-hidden="true"></span>
      <span>{{ mensaje() }}</span>
    </div>
  `,
  styles: `
    .cargando {
      display: flex;
      align-items: center;
      gap: var(--espacio-3);
      padding: var(--espacio-6);
      color: var(--texto-suave);
      justify-content: center;
    }
    .cargando__rueda {
      width: 20px;
      height: 20px;
      border: 2px solid var(--borde-fuerte);
      border-top-color: var(--acento);
      border-radius: 50%;
      animation: girar 700ms linear infinite;
    }
    @keyframes girar {
      to {
        transform: rotate(360deg);
      }
    }
  `,
})
export class CargandoComponent {
  readonly mensaje = input('Cargando...');
}

@Component({
  selector: 'app-vacio',
  standalone: true,
  template: `
    <div class="vacio">
      <p class="vacio__titulo">{{ titulo() }}</p>
      @if (detalle()) {
        <p class="vacio__detalle">{{ detalle() }}</p>
      }
      <ng-content />
    </div>
  `,
  styles: `
    .vacio {
      padding: var(--espacio-7) var(--espacio-5);
      text-align: center;
      color: var(--texto-suave);
    }
    .vacio__titulo {
      font-weight: 600;
      color: var(--texto);
      margin-bottom: var(--espacio-2);
    }
    .vacio__detalle {
      max-width: 46ch;
      margin: 0 auto var(--espacio-4);
    }
  `,
})
export class VacioComponent {
  readonly titulo = input.required<string>();
  readonly detalle = input<string>('');
}

@Component({
  selector: 'app-error',
  standalone: true,
  template: `
    <!-- role="alert" y no role="status": un error interrumpe, y el lector
         de pantalla debe anunciarlo sin esperar una pausa. -->
    <div class="error" role="alert">
      <p class="error__titulo">{{ titulo() }}</p>
      <p class="error__mensaje">{{ mensaje() }}</p>

      @if (codigo()) {
        <!-- El codigo se muestra porque es el discriminador estable del
             contrato: es lo que soporte necesita para saber que paso. El
             identificador de correlacion permite localizar la traza exacta
             en el registro del servidor. -->
        <p class="error__tecnico">
          <code>{{ codigo() }}</code>
          @if (correlacion()) {
            <span> · referencia {{ correlacion() }}</span>
          }
        </p>
      }

      @if (reintentable()) {
        <button type="button" class="boton boton--pequeno" (click)="reintentar.emit()">
          Reintentar
        </button>
      }
    </div>
  `,
  styles: `
    .error {
      padding: var(--espacio-5);
      border: 1px solid var(--peligro);
      border-left-width: 4px;
      border-radius: var(--radio);
      background: var(--peligro-fondo);
    }
    .error__titulo {
      font-weight: 650;
      color: var(--peligro);
      margin-bottom: var(--espacio-1);
    }
    .error__mensaje {
      margin-bottom: var(--espacio-2);
    }
    .error__tecnico {
      font-size: 0.85rem;
      color: var(--texto-suave);
      margin-bottom: var(--espacio-3);
    }
    code {
      font-family: var(--fuente-mono);
    }
  `,
})
export class ErrorComponent {
  readonly titulo = input('No se pudo completar la operacion');
  readonly mensaje = input.required<string>();
  readonly codigo = input<string>('');
  readonly correlacion = input<string>('');
  readonly reintentable = input(true);
  readonly reintentar = output<void>();
}

@Component({
  selector: 'app-aviso-demostracion',
  standalone: true,
  template: `
    <!-- Obligatorio en toda pantalla que muestre datos sinteticos.
         No es cortesia: una captura de esta pantalla sin el aviso puede
         acabar en una reunion presentada como datos de la clinica. -->
    <div class="demo" role="note">
      <strong>Datos de demostracion.</strong>
      {{ detalle() }}
      Ninguna persona, cita, diagnostico ni medicamento de esta pantalla es real.
    </div>
  `,
  styles: `
    .demo {
      padding: var(--espacio-3) var(--espacio-4);
      margin-bottom: var(--espacio-4);
      border: 1px dashed var(--aviso);
      border-radius: var(--radio);
      background: var(--aviso-fondo);
      color: var(--aviso);
      font-size: 0.92rem;
    }
  `,
})
export class AvisoDemostracionComponent {
  readonly detalle = input(
    'Esta seccion todavia no esta conectada al sistema real.',
  );
}
