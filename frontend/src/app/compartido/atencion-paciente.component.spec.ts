import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { AtencionPacienteComponent } from './atencion-paciente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../nucleo/pruebas/sesion-sintetica';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';

describe('AtencionPacienteComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [AtencionPacienteComponent], providers: PROVEEDORES_PRUEBA }));
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  const cita = { id: 'cita-1', inicio: '2026-10-07T15:00:00Z', estado: 'CONFIRMED', sede_id: 'sede-1', sede: 'Sede sintética', zona_horaria: 'America/Guayaquil', especialidad_id: 'esp-odo', especialidad: 'Odontología', profesional: 'Profesional sintético', servicio: 'Consulta sintética' };
  function montar(permisos: string[], inicial: string | null = 'cita-1') {
    iniciarSesionCon(permisos); const f = TestBed.createComponent(AtencionPacienteComponent);
    f.componentRef.setInput('pacienteId', 'pac-1'); f.componentRef.setInput('citaInicial', inicial); f.detectChanges(); return f;
  }
  it('selecciona la cita inicial y dirige pagos con su contexto', () => {
    const f = montar(['agenda.leer', 'pago.leer']);
    TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-1/contextos-atencion`).flush([cita]); f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Sede sintética');
    expect(TestBed.inject(EspecialidadHistoriaService).elegida()?.id).toBe('esp-odo');
    const navegar = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    f.componentInstance['abrirPagos'](); f.componentInstance['abrirAgenda']();
    expect(navegar).toHaveBeenCalledWith(['/pagos'], { queryParams: { paciente: 'pac-1', cita: 'cita-1' } });
    expect(navegar).toHaveBeenCalledWith(['/agenda'], { queryParams: { paciente: 'pac-1', cita: 'cita-1' } });
  });
  it('una cita inexistente no se interpreta como atención sin cita', () => {
    const f = montar(['agenda.leer'], 'ajena');
    TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-1/contextos-atencion`).flush([cita]); f.detectChanges();
    expect(f.nativeElement.querySelector('[role="alert"]').textContent).toContain('no está disponible');
    expect(f.nativeElement.querySelector('app-historia-clinica')).toBeNull();
    f.componentInstance['elegir']('cita-1'); f.detectChanges(); expect(f.nativeElement.querySelector('[role="alert"]')).toBeNull();
  });
  it('un fallo de carga ofrece el mensaje del servidor', () => {
    const f = montar(['agenda.leer']);
    TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-1/contextos-atencion`).flush({ mensaje: 'El contexto no está disponible' }, { status: 404, statusText: 'Not Found' }); f.detectChanges();
    expect(f.nativeElement.querySelector('[role="alert"]')).toBeTruthy();
  });

  it('comunica la cita seleccionada y no elimina el contexto ante un id no autorizado', () => {
    const f = montar(['agenda.leer']);
    const cambios: (string | null)[] = [];
    f.componentInstance.cambioCita.subscribe(c => cambios.push(c?.id ?? null));
    TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-1/contextos-atencion`).flush([cita]);
    expect(cambios).toEqual(['cita-1']);
    f.componentInstance['elegir']('ajena');
    expect(cambios).toEqual(['cita-1']);
    f.componentInstance['elegir']('');
    expect(cambios).toEqual(['cita-1', null]);
    f.componentRef.setInput('moduloInicial', 'faciograma');
    expect(f.componentInstance.moduloInicial()).toBe('faciograma');
  });
  it('sin agenda no pide citas y conserva la separación administrativa', () => {
    const f = montar(['paciente.leer_administrativo']);
    expect(f.nativeElement.textContent).toContain('datos administrativos');
  });
});
