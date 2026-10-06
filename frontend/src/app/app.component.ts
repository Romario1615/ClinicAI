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
import { Component, computed, effect, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { BuscadorGlobalComponent } from './compartido/buscador-global.component';
import { FotoPersonaComponent } from './compartido/foto-persona.component';
import { IconoComponent, type NombreIcono } from './compartido/icono.component';
import { MarcaComponent } from './compartido/marca.component';
import { VentanaFlotanteComponent } from './compartido/ventana-flotante.component';
import { PERMISOS } from './nucleo/servicios/configuracion';
import { AutenticacionService } from './nucleo/servicios/autenticacion.service';
import { PendientesService } from './nucleo/servicios/pendientes.service';
import { SesionService } from './nucleo/servicios/sesion.service';

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
}

const NAVEGACION: readonly EnlaceNavegacion[] = [
  { ruta: '/panel', etiqueta: 'Panel', icono: 'panel', permisos: [], demostracion: false },
  { ruta: '/plataforma/clinicas', etiqueta: 'Clínicas', icono: 'configuracion', permisos: [], rol: 'superadministrador', demostracion: false },
  {
    ruta: '/usuarios',
    etiqueta: 'Usuarios y roles',
    icono: 'usuarios',
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
    // Simulador para probar el agente: es de administración, no del día a día
    // de recepción ni del personal clínico.
    permisos: [PERMISOS.configuracionEscribir],
    demostracion: true,
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
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    IconoComponent,
    MarcaComponent,
    BuscadorGlobalComponent,
    FotoPersonaComponent,
    VentanaFlotanteComponent,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  private readonly autenticacion = inject(AutenticacionService);
  private readonly router = inject(Router);
  protected readonly sesion = inject(SesionService);
  protected readonly pendientes = inject(PendientesService);

  protected readonly menuAbierto = signal(false);
  protected readonly miFotoAbierta = signal(false);
  protected readonly notificacionesAbiertas = signal(false);

  constructor() {
    // La cola se carga cuando hay sesion, y se vacia al cerrarla: dejar el
    // numero de la sesion anterior seria filtrar informacion de otra persona.
    effect(() => {
      if (this.sesion.autenticado()) {
        this.pendientes.cargar();
      }
    });
  }

  /** Roles del usuario, ya unidos. Cadena vacia si no hay ninguno. */
  protected readonly roles = computed(() => this.sesion.identidad()?.roles.join(' · ') ?? '');

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
        (enlace.permisos.length === 0 || this.sesion.tieneAlgunPermiso(...enlace.permisos)),
    ),
  );

  protected alternarMenu(): void {
    this.menuAbierto.update((abierto) => !abierto);
  }

  protected alternarNotificaciones(): void {
    this.notificacionesAbiertas.update((abiertas) => !abiertas);
  }

  protected cerrarNotificaciones(): void {
    this.notificacionesAbiertas.set(false);
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
