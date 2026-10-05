/**
 * Iconos de la interfaz, dibujados en SVG.
 *
 * Por qué no emoji ni una fuente de iconos
 * ----------------------------------------
 * Un emoji cambia de dibujo en cada sistema operativo: el mismo botón se ve
 * distinto en el equipo de recepción y en la tableta de consulta, y algunos
 * emoji clínicos no existen en Windows. Una fuente de iconos añade una
 * descarga y, mientras no llega, deja cuadrados en su sitio.
 *
 * Un trazo, una rejilla
 * ---------------------
 * Todos se dibujan sobre 24×24, con trazo de 1,8 y extremos redondeados, y
 * heredan el color con `currentColor`. Eso es lo que hace que un icono dentro
 * de un enlace activo se tiña solo, sin una variante por estado.
 *
 * Decorativos por defecto
 * -----------------------
 * Llevan `aria-hidden`: acompañan a un texto que ya dice lo mismo. Un icono
 * que además se anunciara haría que el lector de pantalla leyera dos veces
 * cada elemento del menú.
 */
import { Component, computed, input } from '@angular/core';

export type NombreIcono =
  | 'panel'
  | 'agenda'
  | 'espera'
  | 'pacientes'
  | 'historia'
  | 'medicamentos'
  | 'conocimiento'
  | 'catalogo'
  | 'pagos'
  | 'agente'
  | 'usuarios'
  | 'configuracion'
  | 'buscar'
  | 'reloj'
  | 'telefono'
  | 'tic'
  | 'cerrar'
  | 'mas'
  | 'aviso'
  | 'candado'
  | 'anterior'
  | 'siguiente'
  | 'subir'
  | 'archivo'
  | 'salir'
  | 'escudo'
  | 'megafono'
  | 'chispa';

/** Trazos de cada icono sobre la rejilla de 24. */
const TRAZOS: Record<NombreIcono, string> = {
  panel: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  agenda: 'M4 6h16v14H4zM4 10h16M8 4v4M16 4v4',
  espera: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7.5V12l3 2',
  pacientes: 'M9 4.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5.5a3.5 3.5 0 0 1 0 7M18 20c0-2.2-.9-4.2-2.4-5.6',
  historia: 'M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h4',
  medicamentos: 'M8.5 3.5 20.5 15.5M14 3.5a5 5 0 0 1 0 10l-4.5 4.5a5 5 0 0 1-7-7L7 6.5a5 5 0 0 1 7-3',
  conocimiento: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5zM19 18v3H6.5',
  catalogo: 'M4 6h16M4 12h16M4 18h10',
  pagos: 'M3 7h18v11H3zM3 11h18M7 15h3',
  agente: 'M5 5h14v10H9l-4 4z',
  usuarios: 'M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M20 8v6M23 11h-6',
  configuracion: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.7 2.9-.2-.1a1.7 1.7 0 0 0-1.9.1l-.1.1h-3.4l-.1-.2a1.7 1.7 0 0 0-1.6-1l-.2.1-2.9-1.7.1-.2a1.7 1.7 0 0 0-.1-1.9l-.1-.1v-3.4l.2-.1a1.7 1.7 0 0 0 1-1.6l-.1-.2 1.7-2.9.2.1a1.7 1.7 0 0 0 1.9-.1l.1-.1h3.4l.1.2a1.7 1.7 0 0 0 1.6 1l.2-.1 2.9 1.7-.1.2a1.7 1.7 0 0 0 .1 1.9l.1.1z',
  buscar: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14M16.5 16.5 21 21',
  reloj: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7.5V12l3 2',
  telefono:
    'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1.5 1.5 0 0 1-1.7 1.5C10.8 19.6 4.4 13.2 3.5 5.7A1.5 1.5 0 0 1 5 4z',
  tic: 'M20 6 9 17l-5-5',
  cerrar: 'M18 6 6 18M6 6l12 12',
  mas: 'M12 5v14M5 12h14',
  aviso: 'M12 3 2.5 20h19zM12 9v5M12 17h.01',
  candado: 'M5 10h14v11H5zM8 10V7a4 4 0 0 1 8 0v3',
  anterior: 'm14 6-6 6 6 6',
  siguiente: 'm10 6 6 6-6 6',
  subir: 'M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
  archivo: 'M6 3h8l4 4v14H6zM14 3v4h4',
  salir: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4',
  escudo: 'M12 3 4.5 6v6c0 4.4 3.2 7.9 7.5 9 4.3-1.1 7.5-4.6 7.5-9V6zM9 12l2 2 4-4',
  megafono: 'M4 10v4h3l6 4V6L7 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11',
  chispa: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6',
};

@Component({
  selector: 'app-icono',
  standalone: true,
  template: `
    <svg
      [attr.width]="tamano()"
      [attr.height]="tamano()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path [attr.d]="trazo()" />
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex: 0 0 auto;
      /* Alinea el trazo con la línea base del texto que acompaña. */
      align-items: center;
    }
  `,
})
export class IconoComponent {
  readonly nombre = input.required<NombreIcono>();
  readonly tamano = input(20);

  protected readonly trazo = computed(() => TRAZOS[this.nombre()] ?? '');
}
