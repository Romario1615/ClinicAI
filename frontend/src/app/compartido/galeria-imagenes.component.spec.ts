/**
 * Galería de imágenes clínicas: lista con vistas descargadas por el API,
 * filtros por tipo y pieza, carga con piezas FDI y mensajes de antivirus.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { GaleriaImagenesComponent } from './galeria-imagenes.component';
import {
  BASE,
  PROVEEDORES_PRUEBA,
  archivo,
  iniciarSesionCon,
} from '../nucleo/pruebas/sesion-sintetica';

function imagen(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    paciente_id: 'pac-1',
    tipo: 'RADIOGRAFIA_PERIAPICAL',
    piezas: [36],
    tomada_en: '2026-10-01',
    descripcion: null,
    tipo_mime: 'image/png',
    tamano_bytes: 2048,
    antivirus: 'NO_DISPONIBLE',
    creado_en: '2026-10-05T10:00:00Z',
    url_contenido: `/api/v1/imagenes/${id}/contenido`,
    ...extra,
  };
}

describe('GaleriaImagenesComponent', () => {
  let fixture: ComponentFixture<GaleriaImagenesComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;
  const LISTA = `${BASE}/pacientes/pac-1/imagenes`;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [GaleriaImagenesComponent],
      providers: PROVEEDORES_PRUEBA,
    });
    http = TestBed.inject(HttpTestingController);
    iniciarSesionCon(['imagen_clinica.leer', 'imagen_clinica.cargar']);
    fixture = TestBed.createComponent(GaleriaImagenesComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('pacienteId', 'pac-1');
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('lista las imágenes y descarga cada vista por el API', () => {
    http.expectOne((p) => p.url === LISTA).flush([imagen('a'), imagen('b')]);
    http.expectOne(`${BASE}/imagenes/a/contenido`).flush(new Blob(['x']));
    http.expectOne(`${BASE}/imagenes/b/contenido`).flush(new Blob(['y']));
    fixture.detectChanges();
    expect(c.imagenes().length).toBe(2);
    expect(c.url('a')).toMatch(/^blob:/);
    expect(c.url('z')).toBeNull();
    expect(c.etiquetaTipo('RADIOGRAFIA_PERIAPICAL')).toBe('Radiografía periapical');
    expect(c.etiquetaTipo('DESCONOCIDO')).toBe('DESCONOCIDO');
    expect(c.puedeCargar()).toBeTrue();
  });

  it('filtra por tipo y pieza', () => {
    http.expectOne((p) => p.url === LISTA).flush([]);
    c.filtroTipo = 'FOTO_INTRAORAL';
    c.filtroPieza = '36';
    c.cargar('pac-1');
    const peticion = http.expectOne((p) => p.url === LISTA);
    expect(peticion.request.params.get('tipo')).toBe('FOTO_INTRAORAL');
    expect(peticion.request.params.get('pieza')).toBe('36');
    peticion.flush([]);
  });

  it('muestra el error de carga', () => {
    http
      .expectOne((p) => p.url === LISTA)
      .flush({ codigo: 'RELACION', mensaje: 'Sin relacion asistencial' }, { status: 403, statusText: 'F' });
    expect(c.error()).toContain('relacion');
    expect(c.cargando()).toBeFalse();
  });

  it('sube con piezas y avisa del antivirus', () => {
    http.expectOne((p) => p.url === LISTA).flush([]);
    const campo = document.createElement('input');
    Object.defineProperty(campo, 'files', {
      value: { item: () => archivo('rx.png', 'x', 'image/png') },
    });
    c.seleccionarArchivo({ target: campo } as unknown as Event);
    expect(c.archivoNombre).toBe('rx.png');
    c.piezas = '36, 37;x';
    c.descripcion = ' control ';
    c.subir();
    const subida = http.expectOne({ method: 'POST', url: LISTA });
    const cuerpo = subida.request.body as FormData;
    expect(cuerpo.getAll('piezas')).toEqual(['36', '37']);
    expect(cuerpo.get('descripcion')).toBe('control');
    subida.flush(imagen('nueva'));
    expect(c.exito()).toContain('Antivirus no disponible');
    http.expectOne((p) => p.url === LISTA).flush([]);

    c.archivo = archivo('rx2.png', 'y', 'image/png');
    c.subir();
    http.expectOne({ method: 'POST', url: LISTA }).flush(imagen('otra', { antivirus: 'LIMPIO' }));
    expect(c.exito()).toContain('revisada por antivirus');
    http.expectOne((p) => p.url === LISTA).flush([]);

    c.archivo = archivo('rx3.png', 'z', 'image/png');
    c.subir();
    http
      .expectOne({ method: 'POST', url: LISTA })
      .flush({ codigo: 'ARCHIVO_DEMASIADO_GRANDE', mensaje: 'Muy grande' }, { status: 413, statusText: 'T' });
    expect(c.error()).toBe('Muy grande');
  });

  it('formatea tamaños', () => {
    http.expectOne((p) => p.url === LISTA).flush([]);
    expect(c.formatearBytes(500)).toBe('500 B');
    expect(c.formatearBytes(2048)).toBe('2 KB');
    expect(c.formatearBytes(3 * 1024 * 1024)).toBe('3.0 MB');
  });

  it('abre el visor con zoom acotado y compara antes / después por fecha', () => {
    http
      .expectOne((p) => p.url === LISTA)
      .flush([
        imagen('nueva', { tomada_en: '2026-10-01' }),
        imagen('vieja', { tomada_en: '2026-01-15', piezas: [] }),
      ]);
    http.expectOne(`${BASE}/imagenes/nueva/contenido`).flush(new Blob(['x']));
    http.expectOne(`${BASE}/imagenes/vieja/contenido`).flush(new Blob(['y']));

    c.abrirVisor(['nueva']);
    for (let i = 0; i < 20; i++) c.cambiarZoom(0.25);
    expect(c.zoom()).toBe(4);
    for (let i = 0; i < 20; i++) c.cambiarZoom(-0.25);
    expect(c.zoom()).toBe(0.5);
    expect(c.porcentajeZoom()).toBe('50 %');
    expect(c.transformacion()).toBe('scale(0.5)');
    c.cerrarVisor();
    expect(c.visor()).toBeNull();

    c.alternarComparacion('nueva');
    c.alternarComparacion('vieja');
    expect(c.enComparacion('vieja')).toBeTrue();
    expect(c.ordenComparacion()).toEqual(['vieja', 'nueva']);
    c.abrirVisor(c.ordenComparacion());
    fixture.detectChanges();
    expect(c.leyendaVisor('vieja', true, true)).toContain('Antes');
    expect(c.leyendaVisor('nueva', true, false)).toContain('pieza(s) 36');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Antes / después');
    c.alternarComparacion('vieja');
    expect(c.comparacion()).toEqual(['nueva']);
  });
});
