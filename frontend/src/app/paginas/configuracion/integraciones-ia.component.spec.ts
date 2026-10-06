/** JEV y respuestas del asistente: carga, guarda sin reenviar claves y prueba la conexión. */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { IntegracionesIaComponent } from './integraciones-ia.component';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const RUTA = `${BASE}/configuracion/integraciones`;

describe('IntegracionesIaComponent', () => {
  let fixture: ComponentFixture<IntegracionesIaComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [IntegracionesIaComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(IntegracionesIaComponent);
    c = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne(RUTA).flush([
      { codigo: 'anthropic', habilitada: false, ajustes: {}, secretos: {} },
      {
        codigo: 'typesafe',
        habilitada: true,
        ajustes: { modelo: 'jev-latest', tiempo_limite: 2, umbral_confianza: 0.7 },
        secretos: { api_key: { configurado: true } },
      },
      { codigo: 'respuestas_ia', habilitada: true, ajustes: { proveedor: 'ollama', ollama_url: 'http://127.0.0.1:11434', ollama_modelo: 'llama3' }, secretos: {} },
    ]);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('carga lo guardado sin mostrar la clave', () => {
    expect(c.jev.guardada).toBeTrue();
    expect(c.jev.umbral).toBe(0.7);
    expect(c.respuestas.proveedor).toBe('ollama');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Clave guardada (no se muestra)');
  });

  it('guarda JEV: la clave solo viaja si se escribe una nueva', () => {
    c.guardarJev();
    let peticion = http.expectOne({ method: 'PUT', url: `${RUTA}/typesafe` });
    expect(peticion.request.body.secretos).toEqual({});
    expect(peticion.request.body.ajustes.umbral_confianza).toBe(0.7);
    peticion.flush({ codigo: 'typesafe', habilitada: true, ajustes: {}, secretos: { api_key: { configurado: true } } });

    c.claveJev = '  nueva-clave  ';
    c.guardarJev();
    peticion = http.expectOne({ method: 'PUT', url: `${RUTA}/typesafe` });
    expect(peticion.request.body.secretos).toEqual({ api_key: 'nueva-clave' });
    peticion.flush({ codigo: 'typesafe', habilitada: true, ajustes: {}, secretos: { api_key: { configurado: true } } });
    expect(c.claveJev).toBe('');
    expect(c.aviso()).toBe('JEV guardado.');
  });

  it('prueba la conexión y muestra el resultado o el error', () => {
    c.probar();
    http.expectOne({ method: 'POST', url: `${RUTA}/typesafe/prueba` }).flush({
      respondio: true, mensaje: 'JEV respondio correctamente.', intencion: 'buscar_horarios',
      confianza: 0.93, pregunta_clinica: 0.01, urgencia: 0, milisegundos: 420,
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('reservar una cita (93 % de confianza)');

    c.probar();
    http.expectOne(`${RUTA}/typesafe/prueba`).flush({ codigo: 'X', mensaje: 'Guarde primero la clave API de JEV.' }, { status: 422, statusText: 'U' });
    expect(c.error()).toContain('Guarde primero');
  });

  it('guarda el proveedor de respuestas y muestra el rechazo del servidor', () => {
    c.respuestas.url = 'https://ollama.ejemplo.com';
    c.guardarRespuestas();
    const peticion = http.expectOne({ method: 'PUT', url: `${RUTA}/respuestas_ia` });
    expect(peticion.request.body.ajustes.proveedor).toBe('ollama');
    peticion.flush({ codigo: 'X', mensaje: 'Ollama solo se admite en la maquina local' }, { status: 422, statusText: 'U' });
    expect(c.error()).toContain('Ollama solo');
  });
});
