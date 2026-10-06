/**
 * Recepción decide qué pasa con el paciente afectado por una prolongación.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ProlongacionesPendientesComponent } from './prolongaciones-pendientes.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';
import type { PeticionTiempo } from '../../nucleo/servicios/recorrido.service';

const PETICION: PeticionTiempo = {
  cita_id: 'c1',
  paciente: 'Paciente en atención',
  profesional: 'Dra. Uno',
  minutos: 20,
  solicitada_en: '2026-10-06T14:10:00Z',
  fin_actual: '2026-10-06T14:30:00Z',
  conflictos: [
    {
      cita_id: 'c2',
      paciente: 'Siguiente',
      inicio: '2026-10-06T14:30:00Z',
      llego: true,
      alternativas: [
        { profesional_id: 'p2', profesional: 'Dr. Dos', inicio: '2026-10-06T14:30:00Z', mismo_profesional: false },
        { profesional_id: 'p1', profesional: 'Dra. Uno', inicio: '2026-10-06T15:00:00Z', mismo_profesional: true },
      ],
    },
  ],
};

describe('ProlongacionesPendientesComponent', () => {
  let fixture: ComponentFixture<ProlongacionesPendientesComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [ProlongacionesPendientesComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function montar(permisos: readonly string[]): void {
    iniciarSesionCon(permisos);
    fixture = TestBed.createComponent(ProlongacionesPendientesComponent);
    c = fixture.componentInstance;
    fixture.detectChanges();
  }

  it('sin permiso de reprogramar no pide ni muestra nada', () => {
    montar(['agenda.leer']);
    expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('');
  });

  it('aplica con la alternativa elegida y avisa a la agenda', () => {
    montar(['cita.reprogramar']);
    http.expectOne(`${BASE}/agenda/prolongaciones`).flush([PETICION]);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Dra. Uno pide +20 min');

    let resueltas = 0;
    c.resuelta.subscribe(() => resueltas++);
    c.abrir(PETICION);
    http.expectOne(`${BASE}/agenda/citas/c1/prolongacion/opciones`).flush(PETICION);
    expect(c.completa(PETICION)).toBeTrue();
    c.elegir('c2', PETICION.conflictos[0].alternativas[1]);
    c.aplicar(PETICION);
    const peticion = http.expectOne({ method: 'POST', url: `${BASE}/agenda/citas/c1/prolongacion/resolucion` });
    expect(peticion.request.body).toEqual({
      aprobar: true,
      resoluciones: [{ cita_id: 'c2', inicio: '2026-10-06T15:00:00Z', profesional_id: null }],
    });
    peticion.flush({ cita_id: 'c1', aplicada: true, minutos: 20, fin: '2026-10-06T14:50:00Z', conflictos: [] });
    http.expectOne(`${BASE}/agenda/prolongaciones`).flush([]);
    expect(resueltas).toBe(1);
    expect(c.abierta()).toBeNull();
  });

  it('no aplicar exige motivo y muestra el error del servidor', () => {
    montar(['cita.reprogramar']);
    http.expectOne(`${BASE}/agenda/prolongaciones`).flush([PETICION]);
    c.abrir(PETICION);
    http.expectOne(`${BASE}/agenda/citas/c1/prolongacion/opciones`).flush(PETICION);
    c.rechazar(PETICION);
    expect(c.error()).toContain('por qué');

    c.motivo = 'Ya está en sala';
    c.rechazar(PETICION);
    const peticion = http.expectOne({ method: 'POST', url: `${BASE}/agenda/citas/c1/prolongacion/resolucion` });
    expect(peticion.request.body).toEqual({ aprobar: false, motivo_rechazo: 'Ya está en sala' });
    peticion.flush({ codigo: 'X', mensaje: 'Sin pendiente' }, { status: 409, statusText: 'C' });
    expect(c.error()).toBe('Sin pendiente');
    c.cerrar();
    expect(c.abierta()).toBeNull();

    // Hora a mano cuando no hay hueco calculado; vaciarla quita la decisión.
    c.elegirManual('c2', '2026-10-06T16:30');
    expect(c.elegida('c2').mismo_profesional).toBeTrue();
    expect(c.elegida('c2').inicio).toBe('2026-10-06T21:30:00.000Z');
    c.elegirManual('c2', '');
    expect(c.elegida('c2')).toBeUndefined();
  });
});
