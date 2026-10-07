/**
 * Resumen para la consulta: muestra alergias graves destacadas, medicación y
 * adherencia; la redacción con IA local solo se ofrece si está configurada.
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ResumenClinicoComponent, type ResumenClinico } from './resumen-clinico.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';
import { SesionService } from '../../nucleo/servicios/sesion.service';

const URL = `${BASE}/historia/pacientes/pac-1/resumen-clinico`;

function resumen(extra: Partial<ResumenClinico> = {}): ResumenClinico {
  return {
    edad: 40,
    sexo: 'F',
    alergias: [{ id: 'al-1', sustancia: 'Sustancia sintética', reaccion: 'Urticaria', severidad: 'GRAVE' }],
    antecedentes: [{ categoria: 'PERSONAL', descripcion: 'Antecedente sintético', nivel_sensibilidad: 'N2' }],
    medicacion_activa: [
      { nombre: 'Medicamento A', concentracion: '500 mg', dosis: '1', via: 'ORAL', cuando_sea_necesario: false, frecuencia_horas: 8, duracion_dias: 7, instrucciones: null, desde: null },
      { nombre: 'Medicamento B', concentracion: null, dosis: '1', via: 'ORAL', cuando_sea_necesario: true, frecuencia_horas: null, duracion_dias: null, instrucciones: null, desde: null },
    ],
    adherencia: { dias: 14, tomadas: 10, omitidas: 2, sin_registrar: 1 },
    ultimas_notas: [{ fecha: '2026-10-01T10:00:00Z', tipo: 'EVOLUCION', nivel_sensibilidad: 'N2', motivo_consulta: 'Control', analisis: null, plan: 'Revisar' }],
    planes: [{ titulo: 'Plan sintético', estado: 'ACEPTADO', procedimientos_pendientes: 2, nivel_sensibilidad: 'N2' }],
    ultima_atencion: '2026-10-01T10:00:00Z',
    proxima_cita: null,
    redaccion_disponible: true,
    ...extra,
  };
}

describe('ResumenClinicoComponent', () => {
  let http: HttpTestingController;

  function montar(permisos: readonly string[] = ['historia_clinica.leer']) {
    TestBed.configureTestingModule({ imports: [ResumenClinicoComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(permisos);
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

  it('carga la anamnesis configurable solo cuando se abre', () => {
    const fixture = montar();
    http.expectOne(URL).flush(resumen());
    fixture.detectChanges();
    http.expectNone(`${BASE}/historia/pacientes/pac-1/anamnesis/plantillas-activas`);

    const boton = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button[aria-expanded]');
    expect(boton).not.toBeNull();
    boton!.click();
    fixture.detectChanges();
    http.expectOne(`${BASE}/historia/pacientes/pac-1/anamnesis/plantillas-activas`).flush([]);
    http.expectOne(`${BASE}/historia/pacientes/pac-1/anamnesis/respuestas`).flush([]);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Ocultar formularios de anamnesis');
  });

  it('sin IA local no ofrece redactar; el 404 no explica por qué no hay acceso', () => {
    const fixture = montar();
    http.expectOne(URL).flush(resumen({ redaccion_disponible: false, alergias: [] }));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Redactar con IA local');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Sin alergias registradas');

    fixture.componentRef.setInput('pacienteId', 'pac-2');
    fixture.detectChanges();
    http
      .expectOne(`${BASE}/historia/pacientes/pac-2/resumen-clinico`)
      .flush({ codigo: 'RECURSO_NO_ENCONTRADO', mensaje: 'El paciente solicitado no existe.' }, { status: 404, statusText: 'F' });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect((fixture.componentInstance as any).error()).toBe('La información clínica solicitada no está disponible con este acceso.');
  });

  it('registra alergias y antecedentes solo desde la identidad profesional', () => {
    const fixture = montar(['historia_clinica.leer', 'historia_clinica.escribir']);
    const sesion = TestBed.inject(SesionService);
    sesion.establecerIdentidad({ ...sesion.identidad()!, profesional_id: 'prof-1' });
    http.expectOne(URL).flush(resumen());
    fixture.detectChanges();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c = fixture.componentInstance as any;
    c.formularioAlergia.set(true);
    c.nuevaSustancia = 'Látex';
    c.nuevaReaccion = 'Dermatitis';
    c.nuevaSeveridad = 'MODERADA';
    c.registrarAlergia();
    const alergia = http.expectOne(`${BASE}/historia/pacientes/pac-1/anamnesis/alergias`);
    expect(alergia.request.body).toEqual({ sustancia: 'Látex', tipo_reaccion: 'Dermatitis', severidad: 'MODERADA' });
    alergia.flush({ id: 'al-2', sustancia: 'Látex', tipo_reaccion: 'Dermatitis', severidad: 'MODERADA', registrado_en: '2026-10-06T12:00:00Z' });
    http.expectOne(URL).flush(resumen({ alergias: [...resumen().alergias, { id: 'al-2', sustancia: 'Látex', reaccion: 'Dermatitis', severidad: 'MODERADA' }] }));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Alergia registrada.');

    c.formularioAntecedente.set(true);
    c.nuevaCategoria = 'FAMILIAR';
    c.nuevaDescripcion = 'Antecedente familiar sintético';
    c.registrarAntecedente();
    const antecedente = http.expectOne(`${BASE}/historia/pacientes/pac-1/anamnesis/antecedentes`);
    expect(antecedente.request.body).toEqual({ categoria: 'FAMILIAR', descripcion: 'Antecedente familiar sintético', nivel_sensibilidad: 'N2' });
    antecedente.flush({ id: 'ant-1', categoria: 'FAMILIAR', descripcion: 'Antecedente familiar sintético', nivel_sensibilidad: 'N2', registrado_en: '2026-10-06T12:00:00Z' });
    http.expectOne(URL).flush(resumen({ antecedentes: [...resumen().antecedentes, { categoria: 'FAMILIAR', descripcion: 'Antecedente familiar sintético', nivel_sensibilidad: 'N2' }] }));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Antecedente registrado.');
  });

  it('permite marcar y visualizar antecedentes N3 solo en el contexto con permiso sensible', () => {
    const fixture = montar([
      'historia_clinica.leer',
      'historia_clinica.escribir',
      'historia_clinica.leer_sensible',
    ]);
    const sesion = TestBed.inject(SesionService);
    sesion.establecerIdentidad({ ...sesion.identidad()!, profesional_id: 'prof-1' });
    http.expectOne(URL).flush(resumen({
      antecedentes: [{ categoria: 'PERSONAL', descripcion: 'Antecedente sensible', nivel_sensibilidad: 'N3' }],
    }));
    fixture.detectChanges();

    const elemento = fixture.nativeElement as HTMLElement;
    expect(elemento.textContent).toContain('Acceso sensible · N3');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c = fixture.componentInstance as any;
    c.formularioAntecedente.set(true);
    fixture.detectChanges();
    expect(elemento.querySelector('option[value="N3"]')).not.toBeNull();

    c.nuevaDescripcion = 'Nuevo antecedente sensible';
    c.nuevoNivelSensibilidad = 'N3';
    c.registrarAntecedente();
    const guardado = http.expectOne(`${BASE}/historia/pacientes/pac-1/anamnesis/antecedentes`);
    expect(guardado.request.body.nivel_sensibilidad).toBe('N3');
    guardado.flush({
      id: 'ant-2',
      categoria: 'PERSONAL',
      descripcion: 'Nuevo antecedente sensible',
      nivel_sensibilidad: 'N3',
      registrado_en: '2026-10-06T12:00:00Z',
    });
    http.expectOne(URL).flush(resumen());
  });
});
