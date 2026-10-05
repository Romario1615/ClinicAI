/**
 * Editor de recetas: firma propia por defecto, firma por delegación solo si
 * hay una vigente, un PRN no lleva frecuencia y una pauta fija sí.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { RecetaEditorComponent } from './receta-editor.component';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import {
  BASE,
  PROVEEDORES_PRUEBA,
  identidadCon,
  iniciarSesionCon,
} from '../../nucleo/pruebas/sesion-sintetica';

describe('RecetaEditorComponent', () => {
  let fixture: ComponentFixture<RecetaEditorComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [RecetaEditorComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['receta.crear']);
    TestBed.inject(SesionService).establecerIdentidad({
      ...identidadCon(['receta.crear']),
      profesional_id: 'prof-yo',
    });
    fixture = TestBed.createComponent(RecetaEditorComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    http.expectOne(`${BASE}/profesionales/delegaciones/mias`).flush([
      { id: 'd1', delegante_id: 'prof-adjunto', delegado_id: 'prof-yo', vigente_desde: '', vigente_hasta: '', motivo: 'Residencia', revocada_en: null, vigente: true },
      { id: 'd2', delegante_id: 'prof-otro', delegado_id: 'prof-yo', vigente_desde: '', vigente_hasta: '', motivo: 'Vencida', revocada_en: null, vigente: false },
    ]);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('ofrece firma propia y solo las delegaciones vigentes', () => {
    expect(c.firmante).toBe('prof-yo');
    expect(c.firmantes().map((f: { id: string }) => f.id)).toEqual(['prof-yo', 'prof-adjunto']);
  });

  it('valida las líneas y un PRN pierde la frecuencia', () => {
    c.crear();
    expect(c.error()).toContain('nombre y dosis');
    const linea = c.lineas()[0];
    linea.nombre = 'Medicamento sintetico';
    linea.dosis = '1 unidad';
    linea.frecuencia_horas = null;
    c.crear();
    expect(c.error()).toContain('frecuencia');
    c.alternarPrn(linea, true);
    linea.cuando_sea_necesario = true;
    expect(linea.frecuencia_horas).toBeNull();
    c.agregar();
    expect(c.lineas().length).toBe(2);
    c.quitar(1);

    c.firmante = 'prof-adjunto';
    c.crear();
    const alta = http.expectOne(`${BASE}/historia/recetas`);
    expect(alta.request.body.profesional_id).toBe('prof-adjunto');
    expect(alta.request.body.medicamentos[0].cuando_sea_necesario).toBeTrue();
    alta.flush({ id: 'r-1' });
  });

  it('muestra el rechazo del servidor', () => {
    const linea = c.lineas()[0];
    linea.nombre = 'Medicamento sintetico';
    linea.dosis = '1 unidad';
    c.crear();
    http
      .expectOne(`${BASE}/historia/recetas`)
      .flush({ codigo: 'PERMISO_DENEGADO', mensaje: 'Sin delegacion vigente.' }, { status: 403, statusText: 'F' });
    expect(c.error()).toBe('Sin delegacion vigente.');
  });
});
