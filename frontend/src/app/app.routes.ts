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
  guardiaSegundoFactor,
} from './nucleo/guardias/autenticacion.guard';
import { PERMISOS } from './nucleo/servicios/configuracion';

export const routes: Routes = [
  {
    path: 'acceso',
    canActivate: [guardiaInvitado],
    title: 'Acceso · Gestion clinica',
    loadComponent: () =>
      import('./paginas/acceso/acceso.component').then((m) => m.AccesoComponent),
  },
  {
    path: 'panel',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor],
    title: 'Panel · Gestion clinica',
    loadComponent: () =>
      import('./paginas/panel/panel.component').then(
        (m) => m.PanelComponent,
      ),
  },
  {
    path: 'agenda',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.agendaLeer)],
    title: 'Agenda · Gestion clinica',
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
    title: 'Pacientes · Gestion clinica',
    loadComponent: () =>
      import('./paginas/pacientes/pacientes.component').then((m) => m.PacientesComponent),
  },
  {
    path: 'lista-espera',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.listaEsperaGestionar)],
    title: 'Lista de espera · Gestion clinica',
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
    title: 'Historia clinica · Gestion clinica',
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
    title: 'Medicamentos · Gestion clinica',
    loadComponent: () =>
      import('./paginas/medicamentos/medicamentos.component').then(
        (m) => m.MedicamentosComponent,
      ),
  },
  {
    path: 'conocimiento',
    canActivate: [
      guardiaAutenticacion,
      guardiaSegundoFactor,
      guardiaPermiso(PERMISOS.conocimientoLeer),
    ],
    title: 'Conocimiento · Gestion clinica',
    loadComponent: () =>
      import('./paginas/conocimiento/conocimiento.component').then((m) => m.ConocimientoComponent),
  },
  {
    path: 'catalogo',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor],
    title: 'Catalogo · Gestion clinica',
    loadComponent: () =>
      import('./paginas/catalogo/catalogo.component').then(
        (m) => m.CatalogoComponent,
      ),
  },
  {
    path: 'pagos',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso('pago.leer')],
    title: 'Pagos · Gestión clínica',
    loadComponent: () => import('./paginas/pagos/pagos.component').then(m => m.PagosComponent),
  },
  {
    path: 'agente-demo',
    canActivate: [guardiaAutenticacion, guardiaSegundoFactor, guardiaPermiso(PERMISOS.conversacionResponder)],
    title: 'Agente demo · Gestión clínica',
    loadComponent: () => import('./paginas/agente-demo/agente-demo.component').then(m => m.AgenteDemoComponent),
  },
  {
    path: 'sin-permiso',
    canActivate: [guardiaAutenticacion],
    title: 'Sin acceso · Gestion clinica',
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
