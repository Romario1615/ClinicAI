/**
 * Consentimientos en la ficha: sin confirmar la lectura no se registra; con
 * permiso se registra y se revoca; sin permiso solo se ve el estado.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ConsentimientosPacienteComponent } from './consentimientos-paciente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../nucleo/pruebas/sesion-sintetica';

const ESTADOS = [
  { tipo: 'COMUNICACION_WHATSAPP', titulo: 'Avisos de citas', vigente: true, version_texto: 'v1', otorgado_en: '2026-10-01T10:00:00Z', revocado_en: null, canal: 'PRESENCIAL' },
  { tipo: 'PROMOCIONES', titulo: 'Ofertas', vigente: false, version_texto: null, otorgado_en: null, revocado_en: null, canal: null },
];
const TEXTOS = [{ tipo: 'PROMOCIONES', version: 'v1', titulo: 'Ofertas', texto: 'Acepto recibir ofertas.' }];

describe('ConsentimientosPacienteComponent', () => {
  let fixture: ComponentFixture<ConsentimientosPacienteComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;
  const RUTA = `${BASE}/pacientes/pac-1/consentimientos`;

  function montar(permisos: readonly string[]): void {
    iniciarSesionCon(permisos);
    fixture = TestBed.createComponent(ConsentimientosPacienteComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    http.expectOne(RUTA).flush(ESTADOS);
    fixture.detectChanges();
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ConsentimientosPacienteComponent],
      providers: PROVEEDORES_PRUEBA,
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('sin permiso muestra el estado y no ofrece registrar', () => {
    montar(['paciente.leer_administrativo']);
    expect(texto()).toContain('Aceptado');
    expect(texto()).not.toContain('Registrar');
  });

  it('muestra el texto, exige confirmación y registra la versión mostrada', () => {
    montar(['paciente.leer_administrativo', 'consentimiento.gestionar']);
    c.abrir('PROMOCIONES');
    http.expectOne(`${BASE}/pacientes/consentimientos/textos`).flush(TEXTOS);
    fixture.detectChanges();
    expect(texto()).toContain('Acepto recibir ofertas.');

    c.otorgar('PROMOCIONES');
    http.expectNone(RUTA);

    c.confirmado = true;
    c.otorgar('PROMOCIONES');
    const alta = http.expectOne({ method: 'POST', url: RUTA });
    expect(alta.request.body).toEqual({
      tipo: 'PROMOCIONES',
      version_texto: 'v1',
      canal: 'PRESENCIAL',
      confirmo_lectura: true,
    });
    alta.flush({ ...ESTADOS[1], vigente: true, version_texto: 'v1', otorgado_en: '2026-10-05T10:00:00Z' });
    expect(c.estados()[1].vigente).toBeTrue();

    // Segunda apertura: los textos ya están cargados.
    c.abrir('PROMOCIONES');
    http.expectNone(`${BASE}/pacientes/consentimientos/textos`);
  });

  it('registra la baja y muestra el error del servidor', () => {
    montar(['paciente.leer_administrativo', 'consentimiento.gestionar']);
    c.revocar('COMUNICACION_WHATSAPP');
    http
      .expectOne(`${RUTA}/COMUNICACION_WHATSAPP/revocacion`)
      .flush({ ...ESTADOS[0], vigente: false, revocado_en: '2026-10-05T11:00:00Z' });
    expect(c.estados()[0].vigente).toBeFalse();

    c.revocar('COMUNICACION_WHATSAPP');
    http
      .expectOne(`${RUTA}/COMUNICACION_WHATSAPP/revocacion`)
      .flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'No hay un consentimiento vigente.' }, { status: 409, statusText: 'C' });
    expect(c.error()).toContain('No hay');
  });
});
