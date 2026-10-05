/**
 * Fotos clínicas por pieza o procedimiento: filtra por ambos, sube con la
 * pieza y el procedimiento etiquetados, y sin permiso no pide nada.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { FotosClinicasComponent } from './fotos-clinicas.component';
import { BASE, PROVEEDORES_PRUEBA, archivo, iniciarSesionCon } from '../nucleo/pruebas/sesion-sintetica';

const IMAGEN = {
  id: 'img-1',
  paciente_id: 'pac-1',
  tipo: 'FOTO_INTRAORAL',
  piezas: [36],
  tomada_en: null,
  descripcion: 'Antes',
  procedimiento_id: 'proc-1',
  tipo_mime: 'image/png',
  tamano_bytes: 10,
  antivirus: 'NO_DISPONIBLE',
  creado_en: '2026-10-05T10:00:00Z',
  url_contenido: '/api/v1/imagenes/img-1/contenido',
};
const LISTA = `${BASE}/pacientes/pac-1/imagenes`;

function campoCon(file: File | null): Event {
  const campo = document.createElement('input');
  Object.defineProperty(campo, 'files', { value: { item: () => file } });
  return { target: campo } as unknown as Event;
}

describe('FotosClinicasComponent', () => {
  let fixture: ComponentFixture<FotosClinicasComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  function montar(permisos: readonly string[]): void {
    iniciarSesionCon(permisos);
    fixture = TestBed.createComponent(FotosClinicasComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.componentRef.setInput('pieza', 36);
    fixture.componentRef.setInput('procedimientoId', 'proc-1');
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [FotosClinicasComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('lista por pieza y procedimiento, amplía y sube etiquetada', () => {
    montar(['imagen_clinica.leer', 'imagen_clinica.cargar']);
    const lista = http.expectOne((r) => r.url === LISTA);
    expect(lista.request.params.get('pieza')).toBe('36');
    expect(lista.request.params.get('procedimiento_id')).toBe('proc-1');
    lista.flush([IMAGEN]);
    http.expectOne(`${BASE}/imagenes/img-1/contenido`).flush(new Blob(['x'], { type: 'image/png' }));
    fixture.detectChanges();
    expect(c.urls().get('img-1')).toMatch(/^blob:/);

    c.alternar('img-1');
    fixture.detectChanges();
    expect(c.descripcionAbierta()).toBe('Antes');
    expect((fixture.nativeElement as HTMLElement).querySelector('figure')).not.toBeNull();
    c.alternar('img-1');
    expect(c.abierta()).toBeNull();

    let emitida = '';
    c.cargada.subscribe((imagen: { id: string }) => (emitida = imagen.id));
    c.subir(campoCon(archivo('d.png', 'x', 'image/png')));
    const alta = http.expectOne({ method: 'POST', url: LISTA });
    const cuerpo = alta.request.body as FormData;
    expect(cuerpo.get('procedimiento_id')).toBe('proc-1');
    expect(cuerpo.getAll('piezas')).toEqual(['36']);
    alta.flush({ ...IMAGEN, id: 'img-2' });
    expect(emitida).toBe('img-2');
    http.expectOne((r) => r.url === LISTA).flush([]);
  });

  it('muestra errores de carga y de subida', () => {
    montar(['imagen_clinica.leer', 'imagen_clinica.cargar']);
    http
      .expectOne((r) => r.url === LISTA)
      .flush({ codigo: 'X', mensaje: 'Sin relacion' }, { status: 403, statusText: 'F' });
    expect(c.error()).toBe('Sin relacion');

    c.subir(campoCon(null));
    c.subir(campoCon(archivo('d.png', 'x', 'image/png')));
    http
      .expectOne({ method: 'POST', url: LISTA })
      .flush({ codigo: 'ARCHIVO_NO_PERMITIDO', mensaje: 'Formato no admitido.' }, { status: 415, statusText: 'U' });
    expect(c.subiendo()).toBeFalse();
    expect(c.error()).toBe('Formato no admitido.');
  });

  it('sin permiso de lectura no pide imágenes', () => {
    montar(['paciente.leer_administrativo']);
    expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('');
  });
});
