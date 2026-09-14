/**
 * Pruebas del armazon.
 *
 * Lo que se comprueba no es cosmetico: **que la navegacion refleje los
 * permisos**. Un enlace visible a una seccion a la que el backend va a
 * responder 403 en cada llamada no es un fallo de seguridad -- el backend
 * revalida siempre --, pero si una interfaz que miente sobre lo que se puede
 * hacer.
 */
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AppComponent } from './app.component';
import {
  CONFIGURACION,
  CONFIGURACION_POR_DEFECTO,
} from './nucleo/servicios/configuracion';
import { SesionService } from './nucleo/servicios/sesion.service';
import type { Identidad } from './nucleo/modelos/dominio';

function identidadCon(permisos: readonly string[]): Identidad {
  return {
    usuario_id: 'u-1',
    correo: 'prueba@example.invalid',
    nombre: 'Persona',
    apellido: 'De Prueba',
    clinica_id: 'c-1',
    roles: ['recepcion'],
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
      nivel_maximo: 'N1',
    },
    requiere_segundo_factor: false,
    segundo_factor_cumplido: false,
    dosfa_habilitado: false,
    debe_cambiar_contrasena: false,
    ultimo_acceso_en: null,
  };
}

describe('AppComponent', () => {
  let fixture: ComponentFixture<AppComponent>;
  let sesion: SesionService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    sesion = TestBed.inject(SesionService);
  });

  it('sin sesion no muestra la navegacion', () => {
    fixture.detectChanges();
    const nav = fixture.nativeElement.querySelector('nav');
    expect(nav).toBeNull();
  });

  it('con sesion muestra el nombre del usuario', () => {
    sesion.establecerTokens({
      token_acceso: 't',
      token_refresco: 'r',
      tipo_token: 'Bearer',
      expira_en: new Date().toISOString(),
      requiere_segundo_factor: false,
    });
    sesion.establecerIdentidad(identidadCon(['agenda.leer']));
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Persona De Prueba');
  });

  it('oculta los enlaces cuyos permisos faltan', () => {
    sesion.establecerTokens({
      token_acceso: 't',
      token_refresco: 'r',
      tipo_token: 'Bearer',
      expira_en: new Date().toISOString(),
      requiere_segundo_factor: false,
    });
    // Sin `paciente.leer_administrativo` ni `historia_clinica.leer`.
    sesion.establecerIdentidad(identidadCon(['agenda.leer']));
    fixture.detectChanges();

    const enlaces = Array.from(
      fixture.nativeElement.querySelectorAll('nav a'),
    ).map((enlace) => (enlace as HTMLElement).textContent?.trim() ?? '');

    expect(enlaces.some((texto) => texto.includes('Agenda'))).toBeTrue();
    expect(enlaces.some((texto) => texto.includes('Pacientes'))).toBeFalse();
    expect(enlaces.some((texto) => texto.includes('Historia'))).toBeFalse();
  });

  it('no anuncia como demostracion ninguna seccion que ya usa datos reales', () => {
    sesion.establecerTokens({
      token_acceso: 't',
      token_refresco: 'r',
      tipo_token: 'Bearer',
      expira_en: new Date().toISOString(),
      requiere_segundo_factor: false,
    });
    sesion.establecerIdentidad(identidadCon(['agenda.leer']));
    fixture.detectChanges();

    // Todas las secciones de la navegacion estan conectadas al backend, asi
    // que no debe aparecer ninguna marca. La comprobacion no es trivial: una
    // marca olvidada en una pantalla ya real le dice a quien atiende que los
    // datos que ve son inventados, y dejaria de fiarse de ellos.
    //
    // El mecanismo de la marca sigue en la plantilla a proposito: la Fase 8 y
    // la 9 traeran pantallas nuevas, y algunas naceran con datos sinteticos.
    const marcas = fixture.nativeElement.querySelectorAll('.navegacion__demo');
    expect(marcas.length).toBe(0);
  });
});
