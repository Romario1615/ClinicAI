/**
 * Rutas de la aplicacion.
 *
 * Todas las secciones se cargan de forma diferida (`loadComponent`). No es
 * optimizacion prematura: el paquete inicial es lo que ve una recepcionista al
 * abrir la aplicacion por la manana con la tableta del mostrador, y no tiene
 * por que descargar la pantalla de conocimiento para poder agendar.
 *
 * Los guardias ordenan la navegacion; **no protegen datos**. El backend
 * revalida el permiso y aplica el filtro de ambito en cada peticion
 * (CLAUDE.md, regla 7). Quitar estos guardias no expondria nada: solo daria
 * una experiencia peor.
 */
import type { Routes } from '@angular/router';

import {
  guardiaAutenticacion,
  guardiaInvitado,
  guardiaPermiso,
  guardiaSuperadministrador,
  guardiaSegundoFactor,
} from './nucleo/guardias/autenticacion.guard';
import { PERMISOS } from './nucleo/servicios/configuracion';

export const routes: Routes = [
  {
    path: 'cambiar-contrasena',
    canActivate: [guardiaAutenticacion],
    title: 'Cambiar contraseña · ClinicAI',
    loadComponent: () =>
      import('./paginas/cambiar-contrasena/cambiar-contrasena.component').then(
        (m) => m.CambiarContrasenaComponent,
      ),
  },
  {
    path: 'acceso',
    canActivate: [guardiaInvitado],
    title: 'Acceso · ClinicAI',
    loadComponent: () =>
      import('./paginas/acceso/acceso.component').then((m) => m.AccesoComponent),
  },
  {
    path: 'panel',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor],
    title: 'Panel · ClinicAI',
    loadComponent: () =>
      import('./paginas/panel/panel.component').then(
        (m) => m.PanelComponent,
      ),
  },
  {
    path: 'agenda',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.agendaLeer)],
    title: 'Agenda · ClinicAI',
    loadComponent: () =>
      import('./paginas/agenda/agenda.component').then((m) => m.AgendaComponent),
  },
  {
    path: 'pacientes',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.pacienteLeer),
    ],
    title: 'Pacientes · ClinicAI',
    loadComponent: () =>
      import('./paginas/pacientes/pacientes.component').then((m) => m.PacientesComponent),
  },
  {
    path: 'lista-espera',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.listaEsperaGestionar)],
    title: 'Lista de espera · ClinicAI',
    loadComponent: () =>
      import('./paginas/lista-espera/lista-espera.component').then(
        (m) => m.ListaEsperaComponent,
      ),
  },
  {
    path: 'historia-clinica',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.historiaLeer, PERMISOS.recetaLeer),
    ],
    title: 'Historia clinica · ClinicAI',
    loadComponent: () =>
      import('./paginas/historia-clinica/historia-clinica.component').then(
        (m) => m.HistoriaClinicaComponent,
      ),
  },
  {
    path: 'medicamentos',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.recetaLeer),
    ],
    title: 'Medicamentos · ClinicAI',
    loadComponent: () =>
      import('./paginas/medicamentos/medicamentos.component').then(
        (m) => m.MedicamentosComponent,
      ),
  },
  {
    path: 'delegaciones',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.profesionalGestionar),
    ],
    title: 'Delegaciones de firma · ClinicAI',
    loadComponent: () =>
      import('./paginas/delegaciones/delegaciones.component').then((m) => m.DelegacionesComponent),
  },
  {
    path: 'promociones',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.promocionGestionar),
    ],
    title: 'Promociones · ClinicAI',
    loadComponent: () =>
      import('./paginas/promociones/promociones.component').then((m) => m.PromocionesComponent),
  },
  {
    path: 'conocimiento',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.conocimientoLeer),
    ],
    title: 'Conocimiento · ClinicAI',
    loadComponent: () =>
      import('./paginas/conocimiento/conocimiento.component').then((m) => m.ConocimientoComponent),
  },
  {
    path: 'catalogo',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.agendaLeer)],
    title: 'Catalogo · ClinicAI',
    loadComponent: () =>
      import('./paginas/catalogo/catalogo.component').then(
        (m) => m.CatalogoComponent,
      ),
  },
  {
    path: 'pagos',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso('pago.leer')],
    title: 'Pagos · ClinicAI',
    loadComponent: () => import('./paginas/pagos/pagos.component').then(m => m.PagosComponent),
  },
  {
    path: 'conversaciones',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.conversacionLeer)],
    title: 'Bandeja de atención · ClinicAI',
    loadComponent: () => import('./paginas/conversaciones/conversaciones.component').then((m) => m.ConversacionesComponent),
  },
  {
    path: 'agente-demo',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.configuracionEscribir)],
    title: 'Agente demo · ClinicAI',
    loadComponent: () => import('./paginas/agente-demo/agente-demo.component').then(m => m.AgenteDemoComponent),
  },
  {
    path: 'usuarios',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.usuarioLeer),
    ],
    title: 'Usuarios y roles · ClinicAI',
    loadComponent: () =>
      import('./paginas/usuarios/usuarios.component').then((m) => m.UsuariosComponent),
  },
  {
    path: 'automatizaciones',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.configuracionEscribir, 'auditoria.leer'),
    ],
    title: 'Automatizaciones · ClinicAI',
    loadComponent: () =>
      import('./paginas/automatizaciones/automatizaciones.component').then(
        (m) => m.AutomatizacionesComponent,
      ),
  },
  {
    path: 'configuracion',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.configuracionEscribir),
    ],
    title: 'Configuración de integraciones · ClinicAI',
    loadComponent: () =>
      import('./paginas/configuracion/configuracion.component').then(
        (modulo) => modulo.ConfiguracionComponent,
      ),
  },
  {
    path: 'plataforma/clinicas',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaSuperadministrador],
    title: 'Clínicas · Administración de plataforma · ClinicAI',
    loadComponent: () => import('./paginas/plataforma/plataforma.component').then((m) => m.PlataformaComponent),
  },
  {
    // Pública a propósito: el paciente llega desde el WhatsApp sin cuenta. La
    // página pide verificar identidad antes de mostrar nada.
    path: 'indicaciones/:token',
    title: 'Sus indicaciones · ClinicAI',
    loadComponent: () =>
      import('./paginas/publico/indicaciones-publicas.component').then(
        (m) => m.IndicacionesPublicasComponent,
      ),
  },
  {
    path: 'sin-permiso',
    canActivate: [guardiaAutenticacion],
    title: 'Sin acceso · ClinicAI',
    loadComponent: () =>
      import('./paginas/demostracion/paginas-demostracion.component').then(
        (m) => m.SinPermisoComponent,
      ),
  },
  { path: '', pathMatch: 'full', redirectTo: 'panel' },
  // Comodin al final: cualquier ruta desconocida lleva al panel en lugar de
  // dejar la pantalla en blanco, que es lo que pasa sin esta entrada.
  { path: '**', redirectTo: 'panel' },
];
