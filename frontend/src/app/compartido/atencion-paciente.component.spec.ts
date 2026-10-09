import { TestBed } from '@angular/core/testing';
import { Component, input } from '@angular/core';
import { By } from '@angular/platform-browser';
import { HttpTestingController } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { AtencionPacienteComponent } from './atencion-paciente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../nucleo/pruebas/sesion-sintetica';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';
import { HistoriaClinicaComponent } from '../paginas/historia-clinica/historia-clinica.component';
import type { HerramientaHistoria } from './herramientas-paciente.component';

@Component({ selector: 'app-historia-clinica', standalone: true, template: '' })
class HistoriaEntradaPruebaComponent {
  readonly pacienteInicial = input<string | null>(null);
  readonly citaContexto = input<string | null>(null);
  readonly sedeContexto = input<string | null>(null);
  readonly moduloInicial = input<HerramientaHistoria | null>(null);
  readonly solicitudHerramienta = input(0);
  readonly embebida = input(false);
}

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

describe('AtencionPacienteComponent: herramientas y contexto asistencial', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [AtencionPacienteComponent], providers: PROVEEDORES_PRUEBA });
    TestBed.overrideComponent(AtencionPacienteComponent, {
      remove: { imports: [HistoriaClinicaComponent] }, add: { imports: [HistoriaEntradaPruebaComponent] },
    });
  });
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  for (const conCita of [false, true]) {
    it(`propaga cada apertura sin recrear la historia ni perder ${conCita ? 'la cita y la sede' : 'la atención sin cita'}`, () => {
      iniciarSesionCon(['agenda.leer', 'historia_clinica.leer', 'receta.leer']);
      const f = TestBed.createComponent(AtencionPacienteComponent);
      f.componentRef.setInput('pacienteId', 'pac-1');
      f.componentRef.setInput('citaInicial', conCita ? 'cita-1' : null);
      f.componentRef.setInput('moduloInicial', 'recetas');
      f.componentRef.setInput('solicitudHerramienta', 1);
      f.detectChanges();
      TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-1/contextos-atencion`).flush([
        { id: 'cita-1', inicio: '2026-10-09T15:00:00Z', estado: 'CONFIRMED', sede_id: 'sede-1', sede: 'Sede sintética', zona_horaria: 'America/Guayaquil', especialidad_id: 'esp-odo', especialidad: 'Odontología', profesional: 'Profesional sintético', servicio: 'Consulta sintética' },
      ]);
      f.detectChanges();
      const historia = f.debugElement.query(By.directive(HistoriaEntradaPruebaComponent)).componentInstance as HistoriaEntradaPruebaComponent;
      expect(historia.pacienteInicial()).toBe('pac-1');
      expect(historia.citaContexto()).toBe(conCita ? 'cita-1' : null);
      expect(historia.sedeContexto()).toBe(conCita ? 'sede-1' : null);
      expect(historia.moduloInicial()).toBe('recetas');
      expect(historia.solicitudHerramienta()).toBe(1);
      expect(historia.embebida()).toBe(true);
      f.componentRef.setInput('solicitudHerramienta', 2);
      f.detectChanges();
      expect(f.debugElement.query(By.directive(HistoriaEntradaPruebaComponent)).componentInstance).toBe(historia);
      expect(historia.solicitudHerramienta()).toBe(2);
      expect(historia.citaContexto()).toBe(conCita ? 'cita-1' : null);
    });
  }
});
