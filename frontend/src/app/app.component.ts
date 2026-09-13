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
import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { PERMISOS } from './nucleo/servicios/configuracion';
import { AutenticacionService } from './nucleo/servicios/autenticacion.service';
import { SesionService } from './nucleo/servicios/sesion.service';

interface EnlaceNavegacion {
  readonly ruta: string;
  readonly etiqueta: string;
  /** Permisos que habilitan el enlace. Vacío significa que basta la sesión. */
  readonly permisos: readonly string[];
  /** Cierto si la sección todavía usa datos sintéticos. */
  readonly demostracion: boolean;
}

const NAVEGACION: readonly EnlaceNavegacion[] = [
  { ruta: '/panel', etiqueta: 'Panel', permisos: [], demostracion: true },
  { ruta: '/agenda', etiqueta: 'Agenda', permisos: [PERMISOS.agendaLeer], demostracion: false },
  {
    ruta: '/pacientes',
    etiqueta: 'Pacientes',
    permisos: [PERMISOS.pacienteLeer],
    demostracion: false,
  },
  {
    ruta: '/lista-espera',
    etiqueta: 'Lista de espera',
    permisos: [PERMISOS.agendaLeer],
    demostracion: true,
  },
  {
    ruta: '/historia-clinica',
    etiqueta: 'Historia clínica',
    permisos: [PERMISOS.historiaLeer, PERMISOS.recetaLeer],
    demostracion: false,
  },
  {
    ruta: '/medicamentos',
    etiqueta: 'Medicamentos',
    permisos: [PERMISOS.historiaLeer, PERMISOS.pacienteLeer],
    demostracion: true,
  },
  {
    ruta: '/conocimiento',
    etiqueta: 'Conocimiento',
    permisos: [PERMISOS.conocimientoLeer],
    demostracion: false,
  },
  { ruta: '/catalogo', etiqueta: 'Catálogo', permisos: [], demostracion: true },
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  private readonly autenticacion = inject(AutenticacionService);
  private readonly router = inject(Router);
  protected readonly sesion = inject(SesionService);

  protected readonly menuAbierto = signal(false);

  /** Roles del usuario, ya unidos. Cadena vacia si no hay ninguno. */
  protected readonly roles = computed(() => this.sesion.identidad()?.roles.join(' · ') ?? '');

  protected readonly enlaces = computed(() =>
    NAVEGACION.filter(
      (enlace) => enlace.permisos.length === 0 || this.sesion.tieneAlgunPermiso(...enlace.permisos),
    ),
  );

  protected alternarMenu(): void {
    this.menuAbierto.update((abierto) => !abierto);
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
