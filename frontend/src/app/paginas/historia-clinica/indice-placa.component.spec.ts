/**
 * Índice de placa: vista previa del porcentaje, envío solo de superficies con
 * placa de piezas evaluadas y serie de controles.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { IndicePlacaComponent } from './indice-placa.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function registro(id: string, porcentaje: string, fecha: string) {
  return {
    id,
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    piezas_evaluadas: [16],
    superficies_con_placa: {},
    total_superficies: 4,
    total_con_placa: 0,
    porcentaje,
    observacion: null,
    creado_en: fecha,
  };
}

describe('IndicePlacaComponent', () => {
  let fixture: ComponentFixture<IndicePlacaComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;
  const RUTA = `${BASE}/odontologia/pacientes/pac-1/indice-placa`;

  function montar(permisos: readonly string[], serie: unknown[]): void {
    iniciarSesionCon(permisos);
    fixture = TestBed.createComponent(IndicePlacaComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    http.expectOne(RUTA).flush(serie);
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [IndicePlacaComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('calcula la vista previa y envía solo lo marcado', () => {
    montar(['odontograma.leer', 'odontograma.escribir'], []);
    c.alternarCara(16, 'V');
    expect(c.tienePlaca(16, 'V')).toBeFalse(); // sin evaluar no se marca
    c.alternarPieza(16);
    c.alternarPieza(36);
    c.alternarCara(16, 'V');
    c.alternarCara(16, 'M');
    c.alternarCara(36, 'D');
    c.alternarCara(36, 'D');
    expect(c.conPlaca()).toBe(2);
    expect(c.porcentajePrevio()).toBe(25);
    expect(c.nombreCara('L')).toBe('Lingual o palatina');

    c.guardar();
    const alta = http.expectOne({ method: 'POST', url: RUTA });
    expect(alta.request.body).toEqual({
      piezas_evaluadas: [16, 36],
      superficies_con_placa: { '16': ['V', 'M'] },
      observacion: null,
    });
    alta.flush(registro('r-1', '25.00', '2026-10-05T10:00:00Z'));
    expect(c.serie().length).toBe(1);
    expect(c.evaluadas().size).toBe(0);
    expect(c.exito()).toContain('25.00 %');
  });

  it('quitar una pieza borra su placa; marcar todas evalúa 32 piezas', () => {
    montar(['odontograma.leer', 'odontograma.escribir'], []);
    c.alternarPieza(16);
    c.alternarCara(16, 'V');
    c.alternarPieza(16);
    expect(c.conPlaca()).toBe(0);
    c.marcarTodas();
    expect(c.evaluadas().size).toBe(32);
    c.guardar();
    http
      .expectOne({ method: 'POST', url: RUTA })
      .flush({ codigo: 'X', mensaje: 'Sin relacion' }, { status: 403, statusText: 'F' });
    expect(c.error()).toBe('Sin relacion');
  });

  it('muestra la serie y sin permiso de escritura no ofrece registrar', () => {
    montar(['odontograma.leer'], [
      registro('r-2', '18.75', '2026-10-05T10:00:00Z'),
      registro('r-1', '42.50', '2026-07-01T10:00:00Z'),
    ]);
    expect(c.serieCronologica()[0].porcentaje).toBe('42.50');
    expect(c.resumenSerie()).toBe('42.50 %, 18.75 %');
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('18.8 %');
    expect(texto).not.toContain('Registrar control');
  });
});
