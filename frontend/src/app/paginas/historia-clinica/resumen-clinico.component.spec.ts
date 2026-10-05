/**
 * Resumen para la consulta: muestra alergias graves destacadas, medicación y
 * adherencia; la redacción con IA local solo se ofrece si está configurada.
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ResumenClinicoComponent, type ResumenClinico } from './resumen-clinico.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

const URL = `${BASE}/historia/pacientes/pac-1/resumen-clinico`;

function resumen(extra: Partial<ResumenClinico> = {}): ResumenClinico {
  return {
    edad: 40,
    sexo: 'F',
    alergias: [{ sustancia: 'Sustancia sintética', reaccion: 'Urticaria', severidad: 'GRAVE' }],
    antecedentes: [{ categoria: 'PERSONAL', descripcion: 'Antecedente sintético' }],
    medicacion_activa: [
      { nombre: 'Medicamento A', concentracion: '500 mg', dosis: '1', via: 'ORAL', cuando_sea_necesario: false, frecuencia_horas: 8, duracion_dias: 7, instrucciones: null, desde: null },
      { nombre: 'Medicamento B', concentracion: null, dosis: '1', via: 'ORAL', cuando_sea_necesario: true, frecuencia_horas: null, duracion_dias: null, instrucciones: null, desde: null },
    ],
    adherencia: { dias: 14, tomadas: 10, omitidas: 2, sin_registrar: 1 },
    ultimas_notas: [{ fecha: '2026-10-01T10:00:00Z', tipo: 'EVOLUCION', motivo_consulta: 'Control', analisis: null, plan: 'Revisar' }],
    planes: [{ titulo: 'Plan sintético', estado: 'ACEPTADO', procedimientos_pendientes: 2 }],
    ultima_atencion: '2026-10-01T10:00:00Z',
    proxima_cita: null,
    redaccion_disponible: true,
    ...extra,
  };
}

describe('ResumenClinicoComponent', () => {
  let http: HttpTestingController;

  function montar() {
    TestBed.configureTestingModule({ imports: [ResumenClinicoComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['historia_clinica.leer']);
    const fixture = TestBed.createComponent(ResumenClinicoComponent);
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => http.verify());

  it('muestra el resumen y redacta con IA local', () => {
    const fixture = montar();
    http.expectOne(URL).flush(resumen());
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.bloque--alerta')?.textContent).toContain('Sustancia sintética');
    expect(el.textContent).toContain('cada 8 h');
    expect(el.textContent).toContain('cuando sea necesario');
    expect(el.textContent).toContain('en curso');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c = fixture.componentInstance as any;
    expect(c.severidad('OTRA')).toBe('otra');
    expect(c.estadoPlan('OTRO')).toBe('otro');

    c.redactar();
    http.expectOne({ method: 'POST', url: `${URL}/redaccion` }).flush({ texto: 'Resumen redactado.', modelo: 'llama', aviso: 'Verifique.' });
    fixture.detectChanges();
    expect(el.textContent).toContain('Resumen redactado.');

    c.redactar();
    http.expectOne({ method: 'POST', url: `${URL}/redaccion` }).flush({ codigo: 'X', mensaje: 'IA local caída' }, { status: 503, statusText: 'E' });
    expect(c.errorRedaccion()).toBe('IA local caída');
  });

  it('sin IA local no ofrece redactar; sin relación lo explica', () => {
    const fixture = montar();
    http.expectOne(URL).flush(resumen({ redaccion_disponible: false, alergias: [] }));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Redactar con IA local');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Sin alergias registradas');

    fixture.componentRef.setInput('pacienteId', 'pac-2');
    fixture.detectChanges();
    http
      .expectOne(`${BASE}/historia/pacientes/pac-2/resumen-clinico`)
      .flush({ codigo: 'RELACION_ASISTENCIAL_REQUERIDA', mensaje: 'x' }, { status: 403, statusText: 'F' });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((fixture.componentInstance as any).error()).toContain('relación asistencial');
  });
});
