/**
 * Pruebas de los guardias de ruta.
 *
 * Recordatorio, porque es fácil confundirlo: **estos guardias no protegen
 * datos**. El backend revalida el permiso y aplica el filtro de ámbito en cada
 * petición. Quitarlos no expondría nada; solo daría una experiencia peor —
 * pantallas que cargan vacías y acciones que fallan todas con 403.
 *
 * Lo que sí importa comprobar es que **no bloqueen de más**: un guardia
 * demasiado estricto deja fuera a alguien que sí puede trabajar, y eso en una
 * recepción se traduce en un paciente esperando.
 */
import { TestBed } from '@angular/core/testing';
import { Router, type ActivatedRouteSnapshot, type RouterStateSnapshot } from '@angular/router';
import { provideRouter } from '@angular/router';

import {
  guardiaAutenticacion,
  guardiaInvitado,
  guardiaPermiso,
  guardiaSegundoFactor,
} from './autenticacion.guard';
import { SesionService } from '../servicios/sesion.service';
import type { Identidad, ParTokens } from '../modelos/dominio';

const TOKENS: ParTokens = {
  token_acceso: 'a',
  token_refresco: 'r',
  tipo_token: 'Bearer',
  expira_en: new Date().toISOString(),
  requiere_segundo_factor: false,
};

function identidad(parcial: Partial<Identidad> = {}): Identidad {
  return {
    usuario_id: 'u',
    correo: 'p@example.invalid',
    nombre: 'A',
    apellido: 'B',
    clinica_id: 'c',
    roles: [],
    permisos: [],
    ambito: {
      clinica_id: 'c',
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
    ...parcial,
  };
}

const RUTA = {} as ActivatedRouteSnapshot;
const ESTADO = { url: '/agenda' } as RouterStateSnapshot;

describe('guardias de ruta', () => {
  let sesion: SesionService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    sesion = TestBed.inject(SesionService);
  });

  describe('guardiaAutenticacion', () => {
    it('deja pasar con sesión abierta', () => {
      sesion.establecerTokens(TOKENS);
      const resultado = TestBed.runInInjectionContext(() =>
        guardiaAutenticacion(RUTA, ESTADO),
      );
      expect(resultado).toBeTrue();
    });

    it('redirige al acceso y conserva el destino', () => {
      // Sin conservar el destino, un enlace compartido a una cita concreta
      // lleva al panel y hay que buscarla otra vez a mano.
      const resultado = TestBed.runInInjectionContext(() =>
        guardiaAutenticacion(RUTA, ESTADO),
      );
      const router = TestBed.inject(Router);
      expect(router.serializeUrl(resultado as never)).toContain('/acceso');
      expect(router.serializeUrl(resultado as never)).toContain('destino');
    });
  });

  describe('guardiaInvitado', () => {
    it('deja ver el formulario sin sesión', () => {
      expect(TestBed.runInInjectionContext(() => guardiaInvitado(RUTA, ESTADO))).toBeTrue();
    });

    it('con sesión abierta redirige al panel', () => {
      sesion.establecerTokens(TOKENS);
      const resultado = TestBed.runInInjectionContext(() => guardiaInvitado(RUTA, ESTADO));
      expect(resultado).not.toBeTrue();
    });
  });

  describe('guardiaPermiso', () => {
    it('exige al menos un código', () => {
      // Un guardia sin códigos dejaría la ruta abierta sin que nadie lo note.
      // Falla al construirlo, no en tiempo de navegación.
      expect(() => guardiaPermiso()).toThrowError(/al menos un codigo/);
    });

    it('deja pasar con el permiso', () => {
      sesion.establecerTokens(TOKENS);
      sesion.establecerIdentidad(identidad({ permisos: ['agenda.leer'] }));
      const guardia = guardiaPermiso('agenda.leer');
      expect(TestBed.runInInjectionContext(() => guardia(RUTA, ESTADO))).toBeTrue();
    });

    it('basta con uno de varios', () => {
      // Es el caso de una pantalla a la que llegan roles distintos por
      // caminos distintos.
      sesion.establecerTokens(TOKENS);
      sesion.establecerIdentidad(identidad({ permisos: ['paciente.leer_administrativo'] }));
      const guardia = guardiaPermiso('historia_clinica.leer', 'paciente.leer_administrativo');
      expect(TestBed.runInInjectionContext(() => guardia(RUTA, ESTADO))).toBeTrue();
    });

    it('sin el permiso redirige a la pantalla de sin acceso', () => {
      sesion.establecerTokens(TOKENS);
      sesion.establecerIdentidad(identidad({ permisos: [] }));
      const guardia = guardiaPermiso('agenda.leer');
      const resultado = TestBed.runInInjectionContext(() => guardia(RUTA, ESTADO));
      const router = TestBed.inject(Router);
      expect(router.serializeUrl(resultado as never)).toContain('/sin-permiso');
    });

    it('sin sesión redirige al acceso, no a sin-permiso', () => {
      // El orden importa: primero quién eres, después qué puedes. Enviar a
      // «sin permiso» a quien no ha entrado confundiría el diagnóstico.
      const guardia = guardiaPermiso('agenda.leer');
      const resultado = TestBed.runInInjectionContext(() => guardia(RUTA, ESTADO));
      const router = TestBed.inject(Router);
      expect(router.serializeUrl(resultado as never)).toContain('/acceso');
    });
  });

  describe('guardiaSegundoFactor', () => {
    it('deja pasar cuando no hay segundo factor pendiente', () => {
      sesion.establecerTokens(TOKENS);
      sesion.establecerIdentidad(identidad());
      expect(
        TestBed.runInInjectionContext(() => guardiaSegundoFactor(RUTA, ESTADO)),
      ).toBeTrue();
    });

    it('bloquea mientras el segundo factor esté pendiente', () => {
      // El backend emite el token para que el cliente pueda pedir el código,
      // pero rechaza toda operación. Sin este guardia el usuario vería el
      // panel completo con todas las acciones fallando.
      sesion.establecerTokens({ ...TOKENS, requiere_segundo_factor: true });
      sesion.establecerIdentidad(
        identidad({ requiere_segundo_factor: true, segundo_factor_cumplido: false }),
      );
      const resultado = TestBed.runInInjectionContext(() =>
        guardiaSegundoFactor(RUTA, ESTADO),
      );
      expect(resultado).not.toBeTrue();
    });
  });
});
