/**
 * Ayudantes de pruebas: identidad sintética con los permisos que pida cada
 * spec. Solo lo importan archivos `.spec.ts`; no forma parte de la aplicación.
 *
 * Los permisos se piden explícitos en cada prueba para que se lea qué
 * habilita cada botón, igual que el backend: sin permiso, no hay botón.
 */
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import type { Identidad } from '../modelos/dominio';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../servicios/configuracion';
import { SesionService } from '../servicios/sesion.service';
import { IndicadoresService } from '../servicios/indicadores.service';
import {
  EspecialidadHistoriaService,
  type EspecialidadHistoria,
} from '../servicios/especialidad-historia.service';
import { of } from 'rxjs';

export const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

export function identidadCon(permisos: readonly string[]): Identidad {
  return {
    usuario_id: 'u-prueba',
    correo: 'persona@example.invalid',
    nombre: 'Persona',
    apellido: 'Sintetica',
    clinica_id: 'c-1',
    roles: ['profesional'],
    permisos,
    ambito: {
      clinica_id: 'c-1',
      sedes: [],
      todas_las_sedes: true,
      especialidades: [],
      todas_las_especialidades: true,
      profesionales: [],
      todos_los_profesionales: true,
      todos_los_pacientes: true,
      nivel_maximo: 'N2',
    },
    requiere_segundo_factor: false,
    segundo_factor_cumplido: false,
    dosfa_habilitado: false,
    debe_cambiar_contrasena: false,
    ultimo_acceso_en: null,
  };
}

/** Proveedores comunes de un spec con HTTP simulado. */
/**
 * Indicadores vacíos: las cabeceras de resumen de cada módulo no deben añadir
 * una petición que cada spec tendría que responder. Los indicadores tienen su
 * propia prueba.
 */
export const INDICADORES_VACIOS = {
  provide: IndicadoresService,
  useValue: { obtener: () => of(null), refrescar: () => undefined },
};

export const ODONTOLOGIA_SINTETICA: EspecialidadHistoria = {
  id: 'esp-odo',
  nombre: 'Odontología',
  modulos: ['odontograma', 'periodoncia', 'planes', 'imagenes'],
  propia: true,
};

/**
 * Revisa desde una especialidad dental con todos los módulos, sin pedirla al
 * API: las pruebas de cada pantalla no prueban de dónde sale. El servicio
 * real tiene su propia prueba.
 */
export const ESPECIALIDAD_SINTETICA = {
  provide: EspecialidadHistoriaService,
  useFactory: () => {
    const servicio = new EspecialidadHistoriaService();
    servicio.disponibles.set([ODONTOLOGIA_SINTETICA]);
    servicio.cargada.set(true);
    servicio.cargar = () => undefined;
    return servicio;
  },
};

export const PROVEEDORES_PRUEBA = [
  provideHttpClient(),
  provideHttpClientTesting(),
  provideRouter([]),
  { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
  INDICADORES_VACIOS,
  ESPECIALIDAD_SINTETICA,
];

/** Abre una sesión sintética con esos permisos. Llamar tras configurar TestBed. */
export function iniciarSesionCon(permisos: readonly string[]): void {
  const sesion = TestBed.inject(SesionService);
  sesion.establecerTokens({
    token_acceso: 'acceso-sintetico',
    token_refresco: 'refresco-sintetico',
    tipo_token: 'bearer',
    expira_en: '2099-01-01T00:00:00Z',
    requiere_segundo_factor: false,
  });
  sesion.establecerIdentidad(identidadCon(permisos));
}

/** Archivo de texto sintético con la API `text()` que usa el navegador. */
export function archivo(nombre: string, contenido: string | Uint8Array, tipo = 'text/plain'): File {
  return new File([contenido], nombre, { type: tipo });
}
