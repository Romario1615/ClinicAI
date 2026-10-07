import { TestBed } from '@angular/core/testing';
import {
  Router,
  type ActivatedRouteSnapshot,
  type CanActivateFn,
  type RouterStateSnapshot,
} from '@angular/router';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import {
  guardiaAutenticacion,
  guardiaSegundoFactor,
  guardiaSuperadministrador,
} from './nucleo/guardias/autenticacion.guard';
import type { Identidad, ParTokens } from './nucleo/modelos/dominio';
import { PERMISOS } from './nucleo/servicios/configuracion';
import { SesionService } from './nucleo/servicios/sesion.service';

const TOKENS: ParTokens = {
  token_acceso: 'a',
  token_refresco: 'r',
  tipo_token: 'Bearer',
  expira_en: new Date().toISOString(),
  requiere_segundo_factor: false,
};

function identidad(permisos: string[] = [], roles: string[] = []): Identidad {
  return {
    usuario_id: 'usuario-prueba',
    correo: 'prueba@example.invalid',
    nombre: 'Usuario',
    apellido: 'Prueba',
    clinica_id: 'clinica-prueba',
    roles,
    permisos,
    ambito: {
      clinica_id: 'clinica-prueba',
      sedes: [],
      todas_las_sedes: true,
      especialidades: [],
      todas_las_especialidades: true,
      profesionales: [],
      todos_los_profesionales: true,
      todos_los_pacientes: true,
      nivel_maximo: 'N1',
    },
    requiere_segundo_factor: false,
    segundo_factor_cumplido: false,
    dosfa_habilitado: false,
    debe_cambiar_contrasena: false,
    ultimo_acceso_en: null,
  };
}

const RUTA = {} as ActivatedRouteSnapshot;
const ESTADO = { url: '/agenda' } as RouterStateSnapshot;

/** Cada sección de trabajo y el permiso que debe bastar para entrar. */
const MATRIZ_RUTAS: readonly (readonly [string, readonly string[]])[] = [
  ['/agenda', [PERMISOS.agendaLeer]],
  ['/pacientes', [PERMISOS.pacienteLeer]],
  ['/lista-espera', [PERMISOS.listaEsperaGestionar]],
  ['/historia-clinica', [PERMISOS.historiaLeer, PERMISOS.recetaLeer]],
  ['/medicamentos', [PERMISOS.recetaLeer]],
  ['/delegaciones', [PERMISOS.profesionalGestionar]],
  ['/promociones', [PERMISOS.promocionGestionar]],
  ['/conocimiento', [PERMISOS.conocimientoLeer]],
  ['/catalogo', [PERMISOS.agendaLeer]],
  ['/equipo', [PERMISOS.profesionalGestionar]],
  ['/pagos', [PERMISOS.pagoLeer]],
  ['/conversaciones', [PERMISOS.conversacionLeer]],
  ['/agente-demo', [PERMISOS.conversacionResponder]],
  ['/usuarios', [PERMISOS.usuarioLeer]],
  ['/seguridad', [PERMISOS.auditoriaLeer]],
  ['/asistente', [PERMISOS.agendaLeer, PERMISOS.conocimientoLeer, PERMISOS.historiaLeer]],
  ['/automatizaciones', [PERMISOS.configuracionEscribir, PERMISOS.auditoriaLeer]],
  ['/configuracion', [PERMISOS.configuracionEscribir]],
];

const PERMISOS_POR_RUTA = MATRIZ_RUTAS.flatMap(([path, permisos]) =>
  permisos.map((permiso) => [path, permiso] as const),
);

function ruta(path: string) {
  const rutaSinBarraInicial = path.replace(/^\//, '');
  const encontrada = routes.find((candidata) => candidata.path === rutaSinBarraInicial);
  if (!encontrada) throw new Error(`No existe la ruta ${path}`);
  return encontrada;
}

function guardiaDeAcceso(path: string): CanActivateFn {
  const guardia = ruta(path).canActivate?.[2];
  if (typeof guardia !== 'function') {
    throw new Error(`La ruta ${path} no declara un control de acceso`);
  }
  return guardia as CanActivateFn;
}

describe('contrato de acceso de las rutas', () => {
  let sesion: SesionService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    sesion = TestBed.inject(SesionService);
  });

  it.each(MATRIZ_RUTAS)(
    '%s exige autenticación, segundo factor y al menos un permiso válido',
    (path) => {
      const guardias = ruta(path).canActivate ?? [];
      expect(guardias).toContain(guardiaAutenticacion);
      expect(guardias).toContain(guardiaSegundoFactor);
      expect(guardias[2]).toBeDefined();
      expect(guardias[2]).not.toBe(guardiaAutenticacion);
      expect(guardias[2]).not.toBe(guardiaSegundoFactor);
    },
  );

  it.each(PERMISOS_POR_RUTA)('%s permite el permiso %s', (path, permiso) => {
    sesion.establecerTokens(TOKENS);
    sesion.establecerIdentidad(identidad([permiso]));

    const resultado = TestBed.runInInjectionContext(() =>
      guardiaDeAcceso(path)(RUTA, ESTADO),
    );

    expect(resultado).toBe(true);
  });

  it.each(MATRIZ_RUTAS)('%s rechaza la navegación sin permiso', (path) => {
    sesion.establecerTokens(TOKENS);
    sesion.establecerIdentidad(identidad());

    const resultado = TestBed.runInInjectionContext(() =>
      guardiaDeAcceso(path)(RUTA, ESTADO),
    );

    const router = TestBed.inject(Router);
    expect(router.serializeUrl(resultado as never)).toContain('/sin-permiso');
  });

  it('la consola de plataforma queda reservada al superadministrador', () => {
    sesion.establecerTokens(TOKENS);
    sesion.establecerIdentidad(identidad([], ['administrador_clinica']));
    const guardia = ruta('/plataforma/clinicas').canActivate?.[2];
    expect(guardia).toBe(guardiaSuperadministrador);
    if (typeof guardia !== 'function') throw new Error('Falta el control de superadministrador');
    const guardiaFuncion = guardia as CanActivateFn;

    const rechazado = TestBed.runInInjectionContext(() => guardiaFuncion(RUTA, ESTADO));
    expect(TestBed.inject(Router).serializeUrl(rechazado as never)).toContain('/sin-permiso');

    sesion.establecerIdentidad(identidad([], ['superadministrador']));
    expect(TestBed.runInInjectionContext(() => guardiaFuncion(RUTA, ESTADO))).toBe(true);
  });
});
