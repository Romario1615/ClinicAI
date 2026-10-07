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
import { Component, computed, input, ChangeDetectionStrategy } from '@angular/core';

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
  | 'descargar'
  | 'archivo'
  | 'salir'
  | 'escudo'
  | 'megafono'
  | 'chispa'
  | 'metricas'
  | 'clinica'
  | 'equipo'
  | 'sedes'
  | 'notificaciones'
  | 'correo'
  | 'ia'
  | 'red-ia'
  | 'red-clinica'
  | 'diente'
  | 'diente-conectado'
  | 'corazon-clinico'
  | 'documento-verificado'
  | 'calendario-check'
  | 'ubicacion-clinica'
  | 'pulso'
  | 'persona-verificada'
  | 'historial-clinico'
  | 'sala-clinica'
  | 'conexion-segura'
  | 'llave-api'
  | 'radiografia-dental'
  | 'balance-clinico'
  | 'actividad-inteligente'
  | 'asistente-clinico'
  | 'mensajes-seguros'
  | 'revision-operativa'
  | 'analisis-ia'
  | 'menu'
  | 'tendencia-subir'
  | 'tendencia-bajar'
  | 'formulario-clinico'
  | 'revision-dental'
  | 'historial-versiones'
  | 'revision-documental'
  | 'respuesta-documentada'
  | 'automatizaciones'
  | 'conexiones'
  | 'roles'
  | 'ayuda'
  | 'gastos';

/** Trazos de cada icono sobre la rejilla de 24. */
const TRAZOS: Record<NombreIcono, string> = {
  ayuda: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01',
  gastos: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3',
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
  descargar: 'M12 4v11m-5-4 5 5 5-5M4 20h16',
  archivo: 'M6 3h8l4 4v14H6zM14 3v4h4',
  salir: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4',
  escudo: 'M12 3 4.5 6v6c0 4.4 3.2 7.9 7.5 9 4.3-1.1 7.5-4.6 7.5-9V6zM9 12l2 2 4-4',
  megafono: 'M4 10v4h3l6 4V6L7 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11',
  chispa: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6',
  metricas: 'M4 19V5M4 19h16M7 15l4-4 3 2 5-7M17 6h2v2',
  clinica: 'M3 21h18M5 21V6h9v15M14 10h5v11M8 9h3M8 13h3M8 17h3M17 14v.01M17 17v.01M9 6V3h2v3',
  equipo: 'M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M17 8v6M20 11h-6',
  sedes: 'M3 21h18M5 21V7l7-4 7 4v14M9 11h.01M15 11h.01M9 15h.01M15 15h.01M11 21v-3h2v3',
  notificaciones: 'M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  correo: 'M3 5h18v14H3zM3 6l9 7 9-7',
  ia: 'M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1M12 9v6M9 12h6',
  'red-ia': 'M12 12 6 6M12 12l6-6M12 12l-6 6M12 12l6 6M12 12V4M12 12h8M12 12H4M12 12v8M9.5 4a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M19.5 4a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M9.5 20a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M19.5 20a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M13.5 4a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M21.5 12a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M5.5 12a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0M13.5 20a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0',
  'red-clinica': 'M12 12 5 6M12 12l7-6M12 12l-7 6M12 12l7 6M12 12V4M12 12h8M12 12H4M12 12v8M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M6 4.5v3M4.5 6h3M18 4.5v3M16.5 6h3M6 16.5v3M4.5 18h3M18 16.5v3M16.5 18h3',
  diente: 'M6.8 3.5c-2.4 0-4.1 1.9-4.1 4.7 0 2.3 1 4 2 5.7.8 1.4 1.2 3.3 1.7 4.8.4 1.4 1.2 2.2 2.1 2.2 1.6 0 1.6-5 3.5-5s1.9 5 3.5 5c.9 0 1.7-.8 2.1-2.2.5-1.5.9-3.4 1.7-4.8 1-1.7 2-3.4 2-5.7 0-2.8-1.7-4.7-4.1-4.7-1.7 0-3 .8-5.2.8s-3.5-.8-5.2-.8Z',
  'diente-conectado': 'M6.8 3.5c-2.4 0-4.1 1.9-4.1 4.7 0 2.3 1 4 2 5.7.8 1.4 1.2 3.3 1.7 4.8.4 1.4 1.2 2.2 2.1 2.2 1.6 0 1.6-5 3.5-5s1.9 5 3.5 5c.9 0 1.7-.8 2.1-2.2.5-1.5.9-3.4 1.7-4.8 1-1.7 2-3.4 2-5.7 0-2.8-1.7-4.7-4.1-4.7-1.7 0-3 .8-5.2.8s-3.5-.8-5.2-.8ZM8 9h2l2 3 2-4h2M9 18h.01M15 18h.01',
  'corazon-clinico': 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 1 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8ZM5 12h3l1.6-2.5 2.2 5 1.8-3H16',
  'documento-verificado': 'M6 3h8l4 4v5M14 3v4h4M9 12h4M9 16h2M14 17l2 2 4-4M6 3v18h7',
  'calendario-check': 'M4 6h16v14H4zM4 10h16M8 4v4M16 4v4M8 15l2.5 2.5L16 12',
  'ubicacion-clinica': 'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0ZM9 10a3 3 0 1 0 6 0M10 10h4M12 8v4',
  pulso: 'M3 12h4l3-7 4 14 3-7h4',
  'persona-verificada': 'M9 4.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7M3 20c0-3.3 2.7-6 6-6 1.7 0 3.2.7 4.3 1.8M15 18l2 2 4-5',
  'historial-clinico': 'M5 3h10l4 4v7M15 3v4h4M8 12h5M8 16h3M5 3v18h7M15 18h6M18 15v6',
  'sala-clinica': 'M3 21h18M5 21V5h10v16M15 11h4v10M8 9h4M8 13h4M8 17h4M17 15v.01M17 18v.01',
  'conexion-segura': 'M12 3 5 6v5c0 4.3 2.8 7.8 7 10 4.2-2.2 7-5.7 7-10V6zM8.5 11.5l2.2 2.2 4.8-5M3 20h5M16 20h5',
  'llave-api': 'M14 7a5 5 0 1 0-1.2 3.2L21 18v3h-3v-3h-3v-3h-3.2A5 5 0 0 0 14 7ZM6.5 7h.01',
  'radiografia-dental': 'M6.8 3.5c-2.4 0-4.1 1.9-4.1 4.7 0 2.3 1 4 2 5.7.8 1.4 1.2 3.3 1.7 4.8.4 1.4 1.2 2.2 2.1 2.2 1.6 0 1.6-5 3.5-5s1.9 5 3.5 5c.9 0 1.7-.8 2.1-2.2.5-1.5.9-3.4 1.7-4.8 1-1.7 2-3.4 2-5.7 0-2.8-1.7-4.7-4.1-4.7-1.7 0-3 .8-5.2.8s-3.5-.8-5.2-.8ZM12 7v5M9.5 9.5h5M4 4 2.5 2.5M20 4l1.5-1.5',
  'balance-clinico': 'M4 5h16v15H4zM8 9h8M8 13h4M8 17h3M16 15l1.5 1.5L20 13',
  'actividad-inteligente': 'M4 18V6M4 18h16M7 14l3-4 3 2 5-6M16 6h2v2M12 3v3M12 18v3M3 12h3',
  'asistente-clinico': 'M12 3a7 7 0 0 0-7 7v2a2 2 0 0 0 2 2h1v-5H7a5 5 0 0 1 10 0h-1v5h1a2 2 0 0 0 2-2v-2a7 7 0 0 0-7-7ZM8 17h5a2 2 0 0 0 2-2M8 10v4M16 10v4M11 20h2',
  'mensajes-seguros': 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5M15 15l1.5 1.5L20 13',
  'revision-operativa': 'M4 19V5M4 19h16M7 15l3-3 3 2 5-7M17 7h2v2',
  'analisis-ia': 'M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1M8 14l2.5-2.5 2 1.5L16 9',
  menu: 'M4 6h16M4 12h16M4 18h16',
  'tendencia-subir': 'm4 16 6-6 4 4 6-7M15 7h5v5',
  'tendencia-bajar': 'm4 8 6 6 4-4 6 7M15 17h5v-5',
  'formulario-clinico': 'M6 3h8l4 4v14H6zM14 3v4h4M9 11h6M9 15h3M16 15c-1.2 1.4-1.8 2.5-1.8 3.2a1.8 1.8 0 0 0 3.6 0c0-.7-.6-1.8-1.8-3.2Z',
  'revision-dental': 'M6.8 3.5c-2.4 0-4.1 1.9-4.1 4.7 0 2.3 1 4 2 5.7.8 1.4 1.2 3.3 1.7 4.8.4 1.4 1.2 2.2 2.1 2.2 1.6 0 1.6-5 3.5-5s1.9 5 3.5 5c.9 0 1.7-.8 2.1-2.2.5-1.5.9-3.4 1.7-4.8 1-1.7 2-3.4 2-5.7 0-2.8-1.7-4.7-4.1-4.7-1.7 0-3 .8-5.2.8s-3.5-.8-5.2-.8ZM8 10h2l1.5 2.5L14 8l1.3 2H17',
  'historial-versiones': 'M4 7V3m0 4h4M4.8 7a8 8 0 1 1-1.2 7M12 7v5l3 2M8 20h8',
  'revision-documental': 'M6 3h8l4 4v5M14 3v4h4M9 12h4M9 16h2M15.5 17.5l1.5 1.5 3-3M6 3v18h7',
  'respuesta-documentada': 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5M15 15l1.5 1.5L20 13',
  automatizaciones: 'M7 6a2.5 2.5 0 1 0 0 .01M17 18a2.5 2.5 0 1 0 0 .01M17 6a2.5 2.5 0 1 0 0 .01M9.5 6H14a3 3 0 0 1 3 3v6M14.5 18H10a3 3 0 0 1-3-3V9',
  conexiones: 'M12 9v6M9.5 10.5l2.5-1.5 2.5 1.5M9.5 13.5 12 15l2.5-1.5M12 4.5l2 1.2v2.1l-2 1.2-2-1.2V5.7zM5.5 11l2 1.2v2.1l-2 1.2-2-1.2v-2.1zM18.5 11l2 1.2v2.1l-2 1.2-2-1.2v-2.1zM12 15l2 1.2v2.1l-2 1.2-2-1.2v-2.1z',
  roles: 'M12 3.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM5.5 13a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM18.5 13a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM12 9.5v3M8 14l2-1M16 13l2 1M9.5 20.5a4 4 0 0 1 5 0M2.5 21a4 4 0 0 1 6-3M15.5 18a4 4 0 0 1 6 3',
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
  changeDetection: ChangeDetectionStrategy.Eager,
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
