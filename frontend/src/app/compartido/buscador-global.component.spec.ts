/**
 * Pruebas del buscador de la cabecera.
 *
 * Lo que fijan
 * ------------
 * **No busca en cada tecla.** Cada consulta de pacientes queda auditada; una
 * por pulsación llenaría la auditoría de ruido y después impediría investigar
 * un acceso de verdad.
 *
 * **Manda el filtro correcto.** Si el término son dígitos va por documento y
 * si no, por nombre; el backend ignora un término que no encaja y devolvería
 * cero resultados sin decir por qué.
 *
 * **Sin permiso no se pinta.** Un campo que siempre devuelve 403 es peor que
 * no tener campo.
 */
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { BuscadorGlobalComponent } from './buscador-global.component';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO, PERMISOS } from '../nucleo/servicios/configuracion';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { ESPECIALIDAD_SINTETICA } from '../nucleo/pruebas/sesion-sintetica';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

class SesionFalsa {
  permitido = true;
  tienePermiso(codigo: string): boolean {
    return this.permitido && codigo === PERMISOS.pacienteLeer;
  }
  tieneAlgunPermiso(...codigos: readonly string[]): boolean {
    return codigos.some((codigo) => this.tienePermiso(codigo));
  }
}

function paciente(extra: Record<string, unknown> = {}) {
  return {
    id: 'pac-1',
    tipo_documento: 'CEDULA',
    numero_documento: '9900000001',
    nombre: 'Reyna',
    apellido: 'Jurado',
    telefono_whatsapp: null,
    correo: null,
    fecha_nacimiento: null,
    nivel_verificacion: 'TELEFONO',
    ...extra,
  };
}

describe('BuscadorGlobalComponent', () => {
  let fixture: ComponentFixture<BuscadorGlobalComponent>;
  let http: HttpTestingController;
  let sesion: SesionFalsa;

  function elemento(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function escribirYBuscar(termino: string): void {
    fixture.componentInstance['termino'] = termino;
    elemento().querySelector('form')?.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
  }

  beforeEach(() => {
    sesion = new SesionFalsa();
    TestBed.configureTestingModule({
      imports: [BuscadorGlobalComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
        { provide: SesionService, useValue: sesion },
        ESPECIALIDAD_SINTETICA,
      ],
    });
    fixture = TestBed.createComponent(BuscadorGlobalComponent);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => {
    // Cada resultado pide su foto de perfil; aqui no se prueba la foto.
    http.match((peticion) => peticion.url.endsWith('/foto-perfil')).forEach((p) => p.flush(null));
    http.verify();
  });

  it('no se pinta sin permiso de ficha', () => {
    sesion.permitido = false;
    fixture = TestBed.createComponent(BuscadorGlobalComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('form')).toBeNull();
  });

  it('no pide nada mientras se escribe', () => {
    fixture.componentInstance['termino'] = 'Jur';
    fixture.componentInstance['alEscribir']();
    fixture.detectChanges();

    // `http.verify()` en afterEach falla si hubiera salido alguna peticion.
    expect(elemento().querySelector('.buscador__resultados')).toBeNull();
  });

  it('un término con letras se busca por nombre', () => {
    escribirYBuscar('Jurado');

    const peticion = http.expectOne((r) => r.url === `${BASE}/pacientes/`);
    expect(peticion.request.params.get('termino')).toBe('Jurado');
    expect(peticion.request.params.get('documento')).toBeNull();
    peticion.flush({ elementos: [paciente()], total: 1, limite: 20, desplazamiento: 0 });
    fixture.detectChanges();

    expect(elemento().textContent).toContain('Jurado, Reyna');
  });

  it('un término de solo dígitos se busca por documento', () => {
    escribirYBuscar('9900000001');

    const peticion = http.expectOne((r) => r.url === `${BASE}/pacientes/`);
    expect(peticion.request.params.get('documento')).toBe('9900000001');
    expect(peticion.request.params.get('termino')).toBeNull();
    peticion.flush({ elementos: [], total: 0, limite: 20, desplazamiento: 0 });
    fixture.detectChanges();
  });

  it('sin coincidencias dice por qué campo buscó', () => {
    escribirYBuscar('9900000001');
    http.expectOne((r) => r.url === `${BASE}/pacientes/`).flush({
      elementos: [],
      total: 0,
      limite: 20,
      desplazamiento: 0,
    });
    fixture.detectChanges();

    // Sin esto, quien busca por documento y no encuentra nada no sabe si es
    // que el paciente no existe o que se buscó por el campo equivocado.
    expect(elemento().textContent).toContain('Se buscó por número de documento');
  });

  it('un fallo se dice y no se queda buscando para siempre', () => {
    escribirYBuscar('Jurado');
    http
      .expectOne((r) => r.url === `${BASE}/pacientes/`)
      .flush({ codigo: 'ERROR', mensaje: 'No' }, { status: 500, statusText: 'Error' });
    fixture.detectChanges();

    expect(elemento().querySelector('.buscador__nota--error')).not.toBeNull();
    expect(elemento().textContent).not.toContain('Buscando…');
  });

  it('elegir un resultado abre la ficha en una ventana flotante', () => {
    escribirYBuscar('Jurado');
    http
      .expectOne((r) => r.url === `${BASE}/pacientes/`)
      .flush({ elementos: [paciente()], total: 1, limite: 20, desplazamiento: 0 });
    fixture.detectChanges();

    elemento().querySelector<HTMLButtonElement>('.buscador__lista button')?.click();
    fixture.detectChanges();

    expect(elemento().querySelector('[role="dialog"]')).not.toBeNull();
    // La ficha pide sus propios datos al montarse.
    http.expectOne(`${BASE}/pacientes/pac-1`).flush(paciente());
    fixture.detectChanges();
    http.expectOne((r) => r.url === `${BASE}/agenda/citas`).flush({
      elementos: [],
      total: 0,
      limite: 50,
      desplazamiento: 0,
    });
    fixture.detectChanges();

    // La lista de resultados se cierra: ya se eligió.
    expect(elemento().querySelector('.buscador__lista')).toBeNull();
  });

  it('vaciar el campo cierra los resultados', () => {
    escribirYBuscar('Jurado');
    http
      .expectOne((r) => r.url === `${BASE}/pacientes/`)
      .flush({ elementos: [paciente()], total: 1, limite: 20, desplazamiento: 0 });
    fixture.detectChanges();

    fixture.componentInstance['termino'] = '';
    fixture.componentInstance['alEscribir']();
    fixture.detectChanges();

    // Dejar resultados de una búsqueda anterior sobre un campo vacío se lee
    // como si fueran de la actual.
    expect(elemento().querySelector('.buscador__resultados')).toBeNull();
  });

  it('un término en blanco no dispara nada', () => {
    escribirYBuscar('   ');
    expect(elemento().querySelector('.buscador__resultados')).toBeNull();
  });
});
