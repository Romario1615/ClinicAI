/**
 * Foto de perfil: iniciales sin foto, imagen descargada por el API con foto,
 * y cambio de foto solo para quien puede editar la ficha.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { FotoPerfilComponent } from './foto-perfil.component';
import { BASE, PROVEEDORES_PRUEBA, archivo } from '../nucleo/pruebas/sesion-sintetica';

const FOTO = {
  id: 'img-1',
  paciente_id: 'pac-1',
  tipo: 'PERFIL',
  piezas: [],
  tomada_en: null,
  descripcion: null,
  tipo_mime: 'image/png',
  tamano_bytes: 10,
  antivirus: 'NO_DISPONIBLE',
  creado_en: '2026-10-05T10:00:00Z',
  url_contenido: '/api/v1/imagenes/img-1/contenido',
};

describe('FotoPerfilComponent', () => {
  let fixture: ComponentFixture<FotoPerfilComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  function montar(puedeEditar = false): void {
    fixture = TestBed.createComponent(FotoPerfilComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.componentRef.setInput('iniciales', 'PS');
    fixture.componentRef.setInput('nombre', 'Persona Sintetica');
    fixture.componentRef.setInput('puedeEditar', puedeEditar);
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [FotoPerfilComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('sin foto muestra las iniciales y no ofrece cambiarla sin permiso', () => {
    montar(false);
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('PS');
    expect(el.querySelector('input[type=file]')).toBeNull();
  });

  it('con foto la descarga por el API y la muestra', () => {
    montar(false);
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(FOTO);
    http
      .expectOne(`${BASE}/imagenes/img-1/contenido`)
      .flush(new Blob([new Uint8Array([137, 80, 78, 71])], { type: 'image/png' }));
    fixture.detectChanges();
    const imagen = (fixture.nativeElement as HTMLElement).querySelector('img');
    expect(imagen?.getAttribute('alt')).toBe('Foto de Persona Sintetica');
    expect(c.url()).toMatch(/^blob:/);
  });

  it('sube una foto nueva y la recarga; muestra el rechazo del servidor', () => {
    montar(true);
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);

    const campo = document.createElement('input');
    Object.defineProperty(campo, 'files', { value: [archivo('foto.png', 'x', 'image/png')] });
    c.subir({ target: campo } as unknown as Event);
    http.expectOne({ method: 'POST', url: `${BASE}/pacientes/pac-1/foto-perfil` }).flush(FOTO);
    http.expectOne({ method: 'GET', url: `${BASE}/pacientes/pac-1/foto-perfil` }).flush(null);

    c.subir({ target: campo } as unknown as Event);
    http
      .expectOne({ method: 'POST', url: `${BASE}/pacientes/pac-1/foto-perfil` })
      .flush({ codigo: 'ARCHIVO_NO_PERMITIDO', mensaje: 'Formato no admitido.' }, { status: 415, statusText: 'U' });
    expect(c.error()).toBe('Formato no admitido.');
    expect(c.subiendo()).toBeFalse();
  });

  it('en la ficha muestra «Subir foto» y «Tomar foto» con cámara', () => {
    fixture = TestBed.createComponent(FotoPerfilComponent);
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.componentRef.setInput('puedeEditar', true);
    fixture.componentRef.setInput('conBotones', true);
    fixture.detectChanges();
    http.expectOne(`${BASE}/pacientes/pac-1/foto-perfil`).flush(null);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Subir foto');
    expect(el.textContent).toContain('Tomar foto');
    expect(el.querySelector('input[capture=user]')).not.toBeNull();
    expect(el.querySelector('.foto__cambiar')).toBeNull();
  });
});
