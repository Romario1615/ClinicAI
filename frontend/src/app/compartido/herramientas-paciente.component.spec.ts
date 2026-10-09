import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { HerramientasPacienteComponent } from './herramientas-paciente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon, identidadCon, ODONTOLOGIA_SINTETICA } from '../nucleo/pruebas/sesion-sintetica';
import { SesionService } from '../nucleo/servicios/sesion.service';
import { EspecialidadHistoriaService } from '../nucleo/servicios/especialidad-historia.service';

const LECTURAS = ['historia_clinica.leer', 'receta.leer', 'odontograma.leer', 'imagen_clinica.leer', 'plan_tratamiento.leer'];
describe('Herramientas del paciente desde su primera atención', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [HerramientasPacienteComponent], providers: PROVEEDORES_PRUEBA }));
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  function montar(escribe = false) {
    iniciarSesionCon([...LECTURAS, ...(escribe ? ['historia_clinica.escribir', 'odontograma.escribir', 'receta.crear'] : [])]);
    const especialidades = TestBed.inject(EspecialidadHistoriaService);
    especialidades.disponibles.set([ODONTOLOGIA_SINTETICA, { id: 'est', nombre: 'Estética', propia: false, modulos: ['faciograma', 'imagenes'] }]);
    const f = TestBed.createComponent(HerramientasPacienteComponent);
    f.componentRef.setInput('pacienteId', 'pac-nuevo'); f.detectChanges();
    (f.nativeElement as HTMLElement).querySelector('button')!.click(); f.detectChanges();
    return f;
  }
  it('recepción ve las herramientas vacías en solo consulta y no pide datos clínicos al abrir el selector', () => {
    const f = montar();
    TestBed.inject(SesionService).establecerIdentidad({ ...identidadCon(LECTURAS), roles: ['recepcion'], profesional_id: null }); f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Periodontograma e índice de placa');
    expect(f.nativeElement.textContent).toContain('Faciograma');
    expect(f.componentInstance['opciones']().filter(o => o.disponible).every(o => !o.editable)).toBe(true);
    expect(f.componentInstance['puedeIniciar']()).toBe(false);
    expect(f.componentInstance['opciones']().find(o => o.clave === 'formulario033')?.disponible).toBe(false);
    TestBed.inject(HttpTestingController).expectNone(r => r.url.includes('/pacientes/'));
  });
  it('el odontólogo registra en su área y consulta la herramienta estética ajena', () => {
    const f = montar(true); const opciones = f.componentInstance['opciones']();
    expect(opciones.find(o => o.clave === 'odontograma')?.editable).toBe(true);
    expect(opciones.find(o => o.clave === 'faciograma')?.editable).toBe(false);
    const emitida = vi.fn(); f.componentInstance.elegida.subscribe(emitida);
    f.componentInstance['abrir'](opciones.find(o => o.clave === 'faciograma')!);
    expect(emitida).toHaveBeenCalledWith('faciograma');
    expect(TestBed.inject(EspecialidadHistoriaService).elegida()?.id).toBe('est');
    expect(f.componentInstance['puedeIniciar']()).toBe(false);
  });
  it('inicia la atención sin cita por petición explícita e idempotente', () => {
    const f = montar(true); const emitida = vi.fn(); f.componentInstance.elegida.subscribe(emitida);
    f.componentInstance['iniciarAtencion']();
    const r = TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-nuevo/atencion-profesional`);
    expect(r.request.method).toBe('POST'); expect(r.request.headers.get('Idempotency-Key')!.length).toBeGreaterThan(8);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.acciones button:last-child')!.disabled).toBe(true);
    r.flush(null, { status: 204, statusText: 'No Content' });
    expect(emitida).toHaveBeenCalledWith('evolucion'); expect(f.componentInstance['iniciando']()).toBe(false);
  });
  it('conserva el selector y explica un fallo al iniciar la atención', () => {
    const f = montar(true); f.componentInstance['iniciarAtencion']();
    TestBed.inject(HttpTestingController).expectOne(`${BASE}/pacientes/pac-nuevo/atencion-profesional`).flush({ mensaje: 'No disponible' }, { status: 403, statusText: 'Forbidden' });
    f.detectChanges(); expect(f.componentInstance['abierta']()).toBe(true); expect(f.componentInstance['error']()).toBeTruthy();
  });
});
