/**
 * Odontograma: carga de versiones, edición por pieza y cara, primera versión
 * sin motivo, versiones siguientes con motivo obligatorio y conflicto 409
 * cuando otra persona guardó antes.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { OdontogramaComponent } from './odontograma.component';
import type { Odontograma } from '../../nucleo/servicios/api.service';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function version(numero: number, vigente: boolean): Odontograma {
  return {
    id: `odo-${numero}`,
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    version: numero,
    vigente,
    denticion: 'PERMANENTE',
    piezas: { '36': { pieza: null, caras: { O: 'CARIES' }, nota: null } },
    motivo_modificacion: numero > 1 ? 'Control semestral' : null,
    procedimiento_id: null,
    creado_en: '2026-10-05T10:00:00Z',
  } as Odontograma;
}

describe('OdontogramaComponent', () => {
  let fixture: ComponentFixture<OdontogramaComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;
  const VERSIONES = `${BASE}/odontologia/pacientes/pac-1/odontograma/versiones`;

  function montar(permisos: readonly string[], versiones: readonly Odontograma[]): void {
    iniciarSesionCon(permisos);
    fixture = TestBed.createComponent(OdontogramaComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    http.expectOne({ method: 'GET', url: VERSIONES }).flush(versiones);
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [OdontogramaComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('crea la primera versión sin motivo', () => {
    montar(['odontograma.leer', 'odontograma.escribir'], []);
    c.cambiarDenticion('MIXTA');
    expect(c.denticion()).toBe('MIXTA');
    c.cambiarDenticion('INVENTADA');
    expect(c.denticion()).toBe('MIXTA');

    c.elegirPieza(16);
    c.cambiarHallazgoPieza('CORONA');
    c.alternarCara('O', true);
    c.cambiarHallazgoCara('O', 'OBTURACION_RESINA');
    c.cambiarNota('Control');
    expect(c.leyendaPieza(16)).toContain('Corona');
    expect(c.tieneHallazgoPieza(16)).toBeTrue();

    c.guardar();
    const alta = http.expectOne({ method: 'POST', url: `${BASE}/odontologia/pacientes/pac-1/odontograma` });
    expect(alta.request.body.piezas['16']).toEqual({
      pieza: 'CORONA',
      caras: { O: 'OBTURACION_RESINA' },
      nota: 'Control',
    });
    alta.flush(version(1, true));
    http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(1, true)]);
    expect(c.aviso()).toContain('nueva versión');
  });

  it('exige motivo para una versión nueva y muestra el conflicto 409', () => {
    montar(['odontograma.leer', 'odontograma.escribir'], [version(1, true)]);
    expect(c.leyendaPieza(36)).toContain('Caries');
    c.elegirPieza(36);
    c.alternarCara('O', false);
    c.alternarCara('M', true);
    c.cambiarHallazgoPieza('AUSENTE');
    expect(c.estadoSeleccionado().caras).toEqual({});
    c.guardar();
    expect(c.errorTexto()).toContain('motivo');

    c.motivo.set('Extraccion realizada');
    c.guardar();
    const nueva = http.expectOne(`${BASE}/odontologia/pacientes/pac-1/odontograma/versiones`);
    expect(nueva.request.method).toBe('POST');
    nueva.flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'Recargue' }, { status: 409, statusText: 'C' });
    expect(c.conflicto()).toBeTrue();
  });

  it('una versión histórica es de solo lectura', () => {
    montar(['odontograma.leer', 'odontograma.escribir'], [version(2, true), version(1, false)]);
    c.seleccionarVersion('1');
    expect(c.actual().version).toBe(1);
    expect(c.puedeGuardar()).toBeFalse();
    c.elegirPieza(36);
    c.cambiarHallazgoPieza('IMPLANTE');
    expect(c.leyendaPieza(36)).not.toContain('Implante');
    c.seleccionarVersion('99');
    expect(c.actual().version).toBe(1);
  });

  it('sin permiso de escritura no edita', () => {
    montar(['odontograma.leer'], [version(1, true)]);
    expect(c.puedeGuardar()).toBeFalse();
    expect(c.nombreHallazgo('CARIES')).toBe('Caries');
  });

  it('muestra el error de carga', () => {
    iniciarSesionCon(['odontograma.leer']);
    fixture = TestBed.createComponent(OdontogramaComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    http.expectOne(VERSIONES).flush({ codigo: 'X', mensaje: 'Sin relacion' }, { status: 403, statusText: 'F' });
    expect(c.errorTexto()).toContain('Sin relacion');
  });
});

describe('OdontogramaComponent interactivo', () => {
  let fixture: ComponentFixture<OdontogramaComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;
  const VERSIONES = `${BASE}/odontologia/pacientes/pac-1/odontograma/versiones`;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [OdontogramaComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['odontograma.leer', 'odontograma.escribir', 'plan_tratamiento.leer']);
    fixture = TestBed.createComponent(OdontogramaComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(1, true)]);
    http.expectOne(`${BASE}/odontologia/pacientes/pac-1/planes-tratamiento`).flush([]);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('pinta caras con el pincel, alterna y borra', () => {
    c.clicRegion(16, 'centro');
    expect(c.seleccionada()).toBe(16);
    expect(c.cambiadas().size).toBe(0);

    c.elegirHerramienta('CARIES');
    c.clicRegion(16, 'derecha');
    expect(c.borrador()['16'].caras).toEqual({ M: 'CARIES' });
    expect(c.claseRegion(16, 'derecha')).toBe('cara cara--caries');
    expect(c.tituloRegion(16, 'derecha')).toContain('Mesial: Caries');
    expect(c.tituloRegion(16, 'centro')).toBe('16 · Oclusal o incisal');
    expect(c.cambiadas().has(16)).toBeTrue();
    c.clicRegion(16, 'derecha');
    expect(c.borrador()['16'].caras).toEqual({});

    c.clicRegion(16, 'arriba');
    c.elegirHerramienta('BORRAR');
    c.clicRegion(16, 'arriba');
    expect(c.borrador()['16'].caras).toEqual({});
    fixture.detectChanges();
  });

  it('aplica hallazgos de pieza y bloquea caras de una ausente', () => {
    c.elegirHerramienta('AUSENTE');
    c.clicPieza(21);
    expect(c.hallazgoDePieza(21)).toBe('AUSENTE');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.marca-pieza--ausente')).not.toBeNull();

    c.elegirHerramienta('CARIES');
    c.clicRegion(21, 'centro');
    expect(c.errorTexto()).toContain('ausente');

    c.elegirHerramienta('CORONA');
    c.clicRegion(11, 'centro');
    expect(c.hallazgoDePieza(11)).toBe('CORONA');
    c.clicPieza(11);
    expect(c.hallazgoDePieza(11)).toBeNull();

    c.elegirHerramienta('BORRAR');
    c.clicPieza(21);
    expect(c.hallazgoDePieza(21)).toBeNull();

    c.elegirHerramienta('SELECCIONAR');
    c.clicPieza(12);
    expect(c.seleccionada()).toBe(12);
  });

  it('dibuja marcas y nota, deshace una pieza y guarda solo piezas con datos', () => {
    const marcas = [
      [11, 'ENDODONCIA'],
      [12, 'PROTESIS_FIJA'],
      [13, 'IMPLANTE'],
      [14, 'RESTO_RADICULAR'],
      [15, 'A_EXTRAER'],
      [17, 'CORONA'],
    ] as const;
    for (const [pieza, hallazgo] of marcas) {
      c.elegirHerramienta(hallazgo);
      c.clicPieza(pieza);
    }
    c.elegirPieza(36);
    c.cambiarNota('Sensibilidad');
    expect(c.tieneNota(36)).toBeTrue();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('.marca-pieza-texto').length).toBe(2);
    expect(el.textContent).toContain('Historial de la pieza 36');

    c.deshacerPieza();
    expect(c.borrador()['36'].nota).toBeNull();
    c.elegirPieza(17);
    c.deshacerPieza();
    expect(c.borrador()['17']).toBeUndefined();
    c.elegirHerramienta('CARIES');
    c.clicRegion(18, 'centro');
    c.clicRegion(18, 'centro');
    c.seleccionada.set(null);
    c.deshacerPieza();

    c.motivo.set('Hallazgos del control');
    c.guardar();
    const nueva = http.expectOne({ method: 'POST', url: VERSIONES });
    expect(nueva.request.body.piezas['13']).toEqual({ pieza: 'IMPLANTE', caras: {}, nota: null });
    expect(nueva.request.body.piezas['18']).toBeUndefined();
    nueva.flush(version(2, true));
    http.expectOne({ method: 'GET', url: VERSIONES }).flush([version(2, true), version(1, false)]);
  });
});
