import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { DocumentosPublicosComponent } from './documentos-publicos.component';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

describe('DocumentosPublicosComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [DocumentosPublicosComponent], providers: [...PROVEEDORES_PRUEBA, { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ token: 'token-sintetico-de-prueba' }) } } }] }));
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  it('envía fecha, impide doble solicitud y explica una identidad incorrecta', () => {
    const f = TestBed.createComponent(DocumentosPublicosComponent); f.detectChanges();
    f.componentInstance['fecha'] = '1990-04-12'; f.componentInstance['verificar'](); f.componentInstance['verificar']();
    const peticion = TestBed.inject(HttpTestingController).expectOne(`${BASE}/publico/documentos/token-sintetico-de-prueba/acceso`);
    expect(peticion.request.body).toEqual({ fecha_nacimiento: '1990-04-12' }); expect(peticion.request.responseType).toBe('blob');
    peticion.flush(new Blob([]), { status: 401, statusText: 'Unauthorized' }); f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Los datos no coinciden');
  });
  it('admite los cuatro caracteres cuando falta la fecha y comunica caducidad', () => {
    const f = TestBed.createComponent(DocumentosPublicosComponent); f.detectChanges();
    f.componentInstance['usarDocumento'] = true; f.componentInstance['documento'] = '1234'; f.componentInstance['verificar']();
    const peticion = TestBed.inject(HttpTestingController).expectOne(`${BASE}/publico/documentos/token-sintetico-de-prueba/acceso`);
    expect(peticion.request.body).toEqual({ ultimos_digitos_documento: '1234' }); peticion.flush(new Blob([]), { status: 404, statusText: 'Not Found' }); f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Solicite un enlace nuevo');
  });
});
