/**
 * Indicaciones al paciente: publicar con o sin aviso, listar el estado de
 * lectura y anular con motivo.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { IndicacionesPacienteComponent, type Indicacion } from './indicaciones-paciente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

const LISTA = `${BASE}/historia/pacientes/pac-1/indicaciones`;

function indicacion(extra: Partial<Indicacion> = {}): Indicacion {
  return {
    id: 'i1',
    texto: 'Reposo dos días.',
    receta_id: null,
    creado_en: '2026-10-05T10:00:00Z',
    expira_en: '2026-10-12T10:00:00Z',
    lecturas: 0,
    primera_lectura_en: null,
    bloqueada: false,
    anulada_en: null,
    ...extra,
  };
}

describe('IndicacionesPacienteComponent', () => {
  let fixture: ComponentFixture<IndicacionesPacienteComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [IndicacionesPacienteComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['historia_clinica.escribir']);
    fixture = TestBed.createComponent(IndicacionesPacienteComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.componentRef.setInput('puedeEscribir', true);
    fixture.componentRef.setInput('recetas', [{ id: 'r1', etiqueta: 'Receta del 05/10' }]);
    fixture.detectChanges();
    http.expectOne(LISTA).flush([
      indicacion({ lecturas: 2, primera_lectura_en: '2026-10-05T12:00:00Z', receta_id: 'r1' }),
      indicacion({ id: 'i2', bloqueada: true }),
      indicacion({ id: 'i3', anulada_en: '2026-10-05T11:00:00Z' }),
      indicacion({ id: 'i4' }),
    ]);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('lista el estado de cada indicación', () => {
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Leída 2 vez/veces');
    expect(texto).toContain('bloqueado');
    expect(texto).toContain('Anulada');
    expect(texto).toContain('Sin leer');
  });

  it('presenta la publicación y la anulación en ventanas Liquid Glass y descarta borradores al cancelar', () => {
    const elemento = fixture.nativeElement as HTMLElement;
    elemento.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!.click();
    fixture.detectChanges();
    expect(elemento.querySelector('dialog[open]')?.textContent).toContain('Redactar indicaciones');
    c.texto = 'Borrador clínico que no debe persistir.';
    c.cerrarEditor();
    fixture.detectChanges();
    expect(elemento.querySelector('dialog[open]')).toBeNull();
    expect(c.texto).toBe('');

    const botonAnular = [...elemento.querySelectorAll<HTMLButtonElement>('button')]
      .find((boton) => boton.textContent?.trim() === 'Anular');
    botonAnular!.click();
    fixture.detectChanges();
    expect(elemento.querySelector('dialog[open]')?.textContent).toContain('Anular indicación');
    c.motivoAnulacion = 'Motivo que se cancela';
    c.cerrarAnulacion();
    fixture.detectChanges();
    expect(elemento.querySelector('dialog[open]')).toBeNull();
    expect(c.motivoAnulacion).toBe('');
    expect(http.match({ method: 'POST', url: LISTA })).toHaveLength(0);
    expect(http.match({ method: 'PATCH', url: `${BASE}/historia/indicaciones/i1/anulacion` })).toHaveLength(0);
  });

  it('publica y muestra el enlace; sin aviso lo explica', () => {
    c.publicar();
    expect(c.error()).toContain('mínimo 10');
    c.texto = 'Aplicar frío local veinte minutos.';
    c.recetaId = 'r1';
    c.publicar();
    const alta = http.expectOne({ method: 'POST', url: LISTA });
    expect(alta.request.body).toEqual({ texto: 'Aplicar frío local veinte minutos.', receta_id: 'r1', dias_validez: 7 });
    alta.flush({ enlace: 'http://x/indicaciones/abc', expira_en: '2026-10-12T10:00:00Z', aviso_enviado: false, motivo_sin_aviso: 'Entregue el enlace en mano.' });
    http.expectOne(LISTA).flush([]);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Entregue el enlace en mano.');
    c.copiar('http://x/indicaciones/abc');

    c.texto = 'Otra indicación de prueba.';
    c.publicar();
    http.expectOne({ method: 'POST', url: LISTA }).flush({ codigo: 'X', mensaje: 'Sin relación' }, { status: 403, statusText: 'F' });
    expect(c.error()).toBe('Sin relación');
  });

  it('anula con motivo', () => {
    c.anulando.set('i1');
    c.motivoAnulacion = 'no';
    c.anular(indicacion());
    expect(c.error()).toContain('motivo');
    c.motivoAnulacion = 'Se corrigió el texto';
    c.anular(indicacion());
    const peticion = http.expectOne({ method: 'PATCH', url: `${BASE}/historia/indicaciones/i1/anulacion` });
    expect(peticion.request.body).toEqual({ motivo: 'Se corrigió el texto' });
    peticion.flush(indicacion({ anulada_en: '2026-10-05T12:00:00Z' }));
    http.expectOne(LISTA).flush([]);
    expect(c.anulando()).toBeNull();
    c.anulando.set('i4');
    c.motivoAnulacion = 'Motivo suficiente';
    c.anular(indicacion({ id: 'i4' }));
    http.expectOne({ method: 'PATCH', url: `${BASE}/historia/indicaciones/i4/anulacion` }).flush({ codigo: 'X', mensaje: 'Ya anulada' }, { status: 409, statusText: 'C' });
    expect(c.error()).toBe('Ya anulada');
  });
});
