import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { EditorRegistroComponent } from './editor-registro.component';
import { BASE, PROVEEDORES_PRUEBA } from '../nucleo/pruebas/sesion-sintetica';

describe('EditorRegistroComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [EditorRegistroComponent], providers: PROVEEDORES_PRUEBA }));
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('carga el perfil completo de la clínica sin sobrescribir otros campos', async () => {
    const f = TestBed.createComponent(EditorRegistroComponent);
    f.componentRef.setInput('tipo', 'clinica'); f.componentRef.setInput('ruta', '/plataforma/clinicas/c-1'); f.detectChanges();
    TestBed.inject(HttpTestingController).expectOne(`${BASE}/plataforma/clinicas/c-1/datos`).flush({ nombre: 'Clínica sintética', zona_horaria: 'America/Guayaquil', moneda: 'USD', idioma: 'es', correo: null, telefono: null, identificacion_fiscal: null });
    f.detectChanges(); await f.whenStable();
    expect((f.nativeElement.querySelector('[name="moneda"]') as HTMLInputElement).value).toBe('USD');
    f.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    const solicitud = TestBed.inject(HttpTestingController).expectOne(`${BASE}/plataforma/clinicas/c-1/datos`);
    expect(solicitud.request.method).toBe('PUT'); expect(solicitud.request.body.moneda).toBe('USD'); solicitud.flush({});
  });

  it('exige motivo en la baja y usa el endpoint de estado', async () => {
    const f = TestBed.createComponent(EditorRegistroComponent);
    f.componentRef.setInput('tipo', 'usuario'); f.componentRef.setInput('ruta', '/plataforma/clinicas/usuarios/u-1'); f.componentRef.setInput('estado', false); f.detectChanges(); await f.whenStable();
    const input: HTMLTextAreaElement = f.nativeElement.querySelector('textarea'); input.value = 'Baja administrativa sintética'; input.dispatchEvent(new Event('input')); await f.whenStable();
    f.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    const solicitud = TestBed.inject(HttpTestingController).expectOne(`${BASE}/plataforma/clinicas/usuarios/u-1/estado`);
    expect(solicitud.request.body).toEqual({ activo: false, motivo: 'Baja administrativa sintética' }); solicitud.flush({});
  });
});
