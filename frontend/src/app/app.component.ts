/**
 * Armazón de la aplicación.
 *
 * Decide entre dos formas: con sesión abierta muestra la navegación completa;
 * sin ella, solo el contenido, para que la pantalla de acceso no arrastre un
 * menú de secciones a las que todavía no se puede entrar.
 *
 * La navegación se construye a partir de los permisos del principal. **No es
 * un control de seguridad**: el backend revalida cada petición y aplica
 * además el filtro de ámbito. Esconder un enlace solo evita que alguien pulse
 * algo que va a recibir un 403 (CLAUDE.md, regla 7).
 */
import { DOCUMENT } from '@angular/common';
import { Component, DestroyRef, computed, effect, inject, signal, ChangeDetectionStrategy, ElementRef } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { BuscadorGlobalComponent } from './compartido/buscador-global.component';
import { FotoPersonaComponent } from './compartido/foto-persona.component';
import { FondoIAComponent } from './compartido/fondo-ia.component';
import { IconoComponent, type NombreIcono } from './compartido/icono.component';
import { MarcaComponent } from './compartido/marca.component';
import { VentanaFlotanteComponent } from './compartido/ventana-flotante.component';
import { MovimientoService } from './nucleo/movimiento/movimiento.service';
import { PERMISOS } from './nucleo/servicios/configuracion';
import { AutenticacionService } from './nucleo/servicios/autenticacion.service';
import { PendientesService } from './nucleo/servicios/pendientes.service';
import { SesionService } from './nucleo/servicios/sesion.service';
import { ModoLocalService } from './nucleo/servicios/modo-local.service';
import { especialidadDelRol } from './nucleo/utilidades/especialidad-rol';

interface EnlaceNavegacion {
  readonly ruta: string;
  readonly etiqueta: string;
  readonly icono: NombreIcono;
  /**
   * Cierto en la seccion donde se resuelven las tareas con plazo.
   *
   * Es la que lleva la insignia con el numero de pendientes: una insignia en
   * cada seccion seria decoracion, y en una sola es una instruccion.
   */
  readonly llevaInsignia?: boolean;
  /** Permisos que habilitan el enlace. Vacío significa que basta la sesión. */
  readonly permisos: readonly string[];
  /** Cierto si la sección todavía usa datos sintéticos. */
  readonly demostracion: boolean;
  readonly rol?: string;
  /** Solo se muestra cuando el propio backend confirma que está en local. */
  readonly soloLocal?: boolean;
}

const NAVEGACION: readonly EnlaceNavegacion[] = [
  { ruta: '/panel', etiqueta: 'Panel', icono: 'panel', permisos: [], demostracion: false },
  { ruta: '/plataforma/clinicas', etiqueta: 'Clínicas', icono: 'configuracion', permisos: [], rol: 'superadministrador', demostracion: false },
  {
    ruta: '/usuarios',
    etiqueta: 'Usuarios y roles',
    icono: 'roles',
    permisos: [PERMISOS.usuarioLeer],
    demostracion: false,
  },
  {
    ruta: '/agenda',
    etiqueta: 'Agenda',
    icono: 'agenda',
    permisos: [PERMISOS.agendaLeer],
    demostracion: false,
  },
  {
    ruta: '/pacientes',
    etiqueta: 'Pacientes',
    icono: 'pacientes',
    permisos: [PERMISOS.pacienteLeer],
    demostracion: false,
  },
  {
    ruta: '/lista-espera',
    etiqueta: 'Lista de espera',
    icono: 'espera',
    llevaInsignia: true,
    permisos: [PERMISOS.listaEsperaGestionar],
    demostracion: false,
  },
  {
    ruta: '/historia-clinica',
    etiqueta: 'Historia clínica',
    icono: 'historia',
    permisos: [PERMISOS.historiaLeer, PERMISOS.recetaLeer],
    demostracion: false,
  },
  {
    ruta: '/medicamentos',
    etiqueta: 'Medicamentos',
    icono: 'medicamentos',
    permisos: [PERMISOS.recetaLeer],
    demostracion: false,
  },
  {
    ruta: '/conocimiento',
    etiqueta: 'Conocimiento',
    icono: 'conocimiento',
    permisos: [PERMISOS.conocimientoLeer],
    demostracion: false,
  },
  {
    ruta: '/delegaciones',
    etiqueta: 'Delegaciones de firma',
    icono: 'escudo',
    permisos: [PERMISOS.profesionalGestionar],
    demostracion: false,
  },
  {
    ruta: '/equipo',
    etiqueta: 'Equipo clínico',
    icono: 'usuarios',
    permisos: [PERMISOS.profesionalGestionar],
    demostracion: false,
  },
  {
    ruta: '/promociones',
    etiqueta: 'Promociones',
    icono: 'megafono',
    permisos: [PERMISOS.promocionGestionar],
    demostracion: false,
  },
  {
    ruta: '/catalogo',
    etiqueta: 'Catálogo',
    icono: 'catalogo',
    permisos: [PERMISOS.agendaLeer],
    demostracion: false,
  },
  { ruta: '/pagos', etiqueta: 'Pagos', icono: 'pagos', permisos: ['pago.leer'], demostracion: false },
  { ruta: '/gastos', etiqueta: 'Gastos y caja', icono: 'gastos', permisos: [PERMISOS.gastoLeer], demostracion: false },
  {
    ruta: '/conversaciones',
    etiqueta: 'Atención de mensajes',
    icono: 'agente',
    llevaInsignia: true,
    permisos: [PERMISOS.conversacionLeer],
    demostracion: false,
  },
  {
    ruta: '/agente-demo',
    etiqueta: 'Agente demo',
    icono: 'agente',
    // El backend requiere este permiso y, además, limita el endpoint a local.
    permisos: [PERMISOS.conversacionResponder],
    soloLocal: true,
    demostracion: true,
  },
  {
    ruta: '/seguridad',
    etiqueta: 'Seguridad clínica',
    icono: 'escudo',
    llevaInsignia: true,
    permisos: [PERMISOS.auditoriaLeer],
    demostracion: false,
  },
  {
    ruta: '/asistente',
    etiqueta: 'Asistente',
    icono: 'agente',
    permisos: ['agenda.leer', 'conocimiento.leer', 'historia_clinica.leer'],
    demostracion: false,
  },
  {
    ruta: '/automatizaciones',
    etiqueta: 'Automatizaciones',
    icono: 'chispa',
    permisos: [PERMISOS.configuracionEscribir, 'auditoria.leer'],
    demostracion: false,
  },
  {
    ruta: '/configuracion',
    etiqueta: 'Configuración',
    icono: 'configuracion',
    permisos: [PERMISOS.configuracionEscribir],
    demostracion: false,
  },
  // Para todos: cada persona ve el manual de sus propios roles.
  { ruta: '/ayuda', etiqueta: 'Ayuda', icono: 'ayuda', permisos: [], demostracion: false },
];

@Component({
  selector: 'app-root',
  standalone: true,
  host: {
    '(document:keydown.escape)': 'cerrarCapasDesplegadas()',
    '(document:click)': 'cerrarCapasAlPulsarFuera($event)',
  },
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    IconoComponent,
    MarcaComponent,
    BuscadorGlobalComponent,
    FotoPersonaComponent,
    FondoIAComponent,
    VentanaFlotanteComponent,
  ],
  templateUrl: './app.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.component.scss',
})
export class AppComponent {
  private readonly elemento = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly autenticacion = inject(AutenticacionService);
  private readonly router = inject(Router);
  protected readonly sesion = inject(SesionService);
  private readonly modoLocal = inject(ModoLocalService);
  protected readonly pendientes = inject(PendientesService);
  private readonly movimiento = inject(MovimientoService);

  protected readonly menuAbierto = signal(false);
  protected readonly miFotoAbierta = signal(false);
  protected readonly notificacionesAbiertas = signal(false);
  /** Pantalla estrecha: el menú es un cajón que tapa el contenido. */
  private readonly pantallaEstrecha = signal(false);
  /**
   * Con el cajón abierto, el contenido de detrás no recibe foco: tabular más
   * allá del último enlace llevaría a controles tapados (WCAG 2.4.11).
   */
  protected readonly contenidoInerte = computed(() => this.menuAbierto() && this.pantallaEstrecha());

  constructor() {
    const destruccion = inject(DestroyRef);
    const vista = inject(DOCUMENT).defaultView;
    if (typeof vista?.matchMedia === 'function') {
      const consulta = vista.matchMedia('(max-width: 820px)');
      this.pantallaEstrecha.set(consulta.matches);
      const alCambiar = (evento: MediaQueryListEvent) => {
        this.pantallaEstrecha.set(evento.matches);
        // Al ensanchar la ventana el menú vuelve a ser lateral: no queda
        // ningún cajón abierto que cerrar después.
        if (!evento.matches) this.cerrarMenu();
      };
      consulta.addEventListener('change', alCambiar);
      destruccion.onDestroy(() => consulta.removeEventListener('change', alCambiar));
    }

    // La cola se carga cuando hay sesion, y se vacia al cerrarla: dejar el
    // numero de la sesion anterior seria filtrar informacion de otra persona.
    effect(() => {
      if (this.sesion.autenticado()) {
        this.pendientes.cargar();
      } else {
        this.pendientes.limpiar();
      }
    });

    // Movimiento global: presión, reflejo y entrada escalonada de lo que
    // llegue a la página (pantallas, tarjetas, filas, desplegables). Se
    // observa el cuerpo entero porque al abrir o cerrar sesión cambia el
    // `<main>`. El motor se descarga después del arranque.
    this.movimiento.iniciar(inject(DOCUMENT).body);
    destruccion.onDestroy(() => this.movimiento.detener());
  }

  /** Roles del usuario, ya unidos. Cadena vacia si no hay ninguno. */
  protected readonly roles = computed(() => this.sesion.identidad()?.roles.join(' · ') ?? '');
  protected readonly especialidad = computed(() => {
    const identidad = this.sesion.identidad();
    return identidad ? especialidadDelRol(identidad.especialidad, identidad.roles) : '';
  });

  /** Dos iniciales del nombre para el avatar de la cabecera. */
  protected readonly iniciales = computed(() =>
    this.sesion
      .nombreCompleto()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((parte) => parte[0]?.toUpperCase() ?? '')
      .join(''),
  );

  protected readonly enlaces = computed(() =>
    NAVEGACION.filter(
      (enlace) => (!enlace.rol || Boolean(this.sesion.identidad()?.roles.includes(enlace.rol))) &&
        (enlace.permisos.length === 0 || this.sesion.tieneAlgunPermiso(...enlace.permisos)) &&
        (!enlace.soloLocal || this.modoLocal.habilitado()),
    ),
  );

  protected alternarMenu(): void {
    const abrir = !this.menuAbierto();
    this.notificacionesAbiertas.set(false);
    this.menuAbierto.set(abrir);
  }

  protected alternarNotificaciones(): void {
    const abrir = !this.notificacionesAbiertas();
    this.menuAbierto.set(false);
    this.notificacionesAbiertas.update((abiertas) => {
      if (!abiertas) {
        this.pendientes.refrescarCobrosVencidos();
        this.pendientes.refrescarOfertasSinAvisar();
      }
      return abrir;
    });
  }

  protected cerrarNotificaciones(): void {
    this.notificacionesAbiertas.set(false);
  }

  /**
   * Escape cierra cualquier panel flotante del armazón, esté abierto el menú o
   * las notificaciones. Si el foco estaba dentro del panel, vuelve al botón que
   * lo abrió: al destruirse el panel caería en `<body>` y quien navega con
   * teclado tendría que empezar desde el principio de la página.
   */
  protected cerrarCapasDesplegadas(): void {
    const raiz = this.elemento.nativeElement;
    const activo = raiz.ownerDocument.activeElement;
    let devolverA: HTMLElement | null = null;
    if (this.menuAbierto() && raiz.querySelector('#navegacion-principal')?.contains(activo)) {
      devolverA = raiz.querySelector<HTMLElement>('.cabecera__menu');
    }
    if (this.notificacionesAbiertas() && raiz.querySelector('#panel-notificaciones')?.contains(activo)) {
      devolverA = raiz.querySelector<HTMLElement>('.campana');
    }
    this.cerrarMenu();
    this.cerrarNotificaciones();
    devolverA?.focus();
  }

  /** Los paneles del encabezado se descartan al pulsar fuera y nunca quedan abiertos a la vez. */
  protected cerrarCapasAlPulsarFuera(evento: MouseEvent): void {
    const objetivo = evento.target as Node;
    const raiz = this.elemento.nativeElement;
    if (this.menuAbierto()) {
      const navegacion = raiz.querySelector('#navegacion-principal');
      const botonMenu = raiz.querySelector('.cabecera__menu');
      if (!navegacion?.contains(objetivo) && !botonMenu?.contains(objetivo)) this.cerrarMenu();
    }
    if (this.notificacionesAbiertas()) {
      const ancla = raiz.querySelector('.cabecera__notificaciones');
      if (!ancla?.contains(objetivo)) this.cerrarNotificaciones();
    }
  }

  protected cerrarMenu(): void {
    this.menuAbierto.set(false);
  }

  protected cerrarSesion(): void {
    this.autenticacion.cerrarSesion().subscribe(() => {
      void this.router.navigate(['/acceso']);
    });
  }
}
