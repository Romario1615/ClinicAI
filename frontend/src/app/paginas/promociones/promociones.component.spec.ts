/**
 * Promociones: la IA propone la imagen y una persona aprueba; la audiencia es
 * un recuento; sin permiso de aprobación no aparecen aprobar ni enviar.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { PromocionesComponent } from './promociones.component';
import type { Campana } from '../../nucleo/servicios/api.service';
import {
  BASE,
  PROVEEDORES_PRUEBA,
  archivo,
  iniciarSesionCon,
} from '../../nucleo/pruebas/sesion-sintetica';

function campana(extra: Partial<Campana> = {}): Campana {
  return {
    id: 'camp-1',
    nombre: 'Limpieza de octubre',
    texto: 'Este mes la limpieza tiene 20 % de descuento.',
    plantilla_meta: 'promocion_clinica',
    estado: 'BORRADOR',
    segmento: {},
    tiene_imagen: false,
    imagen_origen: null,
    imagen_proveedor: null,
    imagen_prompt: null,
    aprobada_en: null,
    programada_para: null,
    enviada_en: null,
    encolados: 0,
    omitidos: 0,
    cancelada_en: null,
    motivo_cancelacion: null,
    creado_en: '2026-10-05T10:00:00Z',
    vista_previa: 'Hola (nombre del paciente). Este mes...',
    ...extra,
  };
}

describe('PromocionesComponent', () => {
  let fixture: ComponentFixture<PromocionesComponent>;
  let http: HttpTestingController;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;
  const RUTA = `${BASE}/promociones/campanas`;

  function montar(permisos: readonly string[], campanas: readonly Campana[]): void {
    iniciarSesionCon(permisos);
    fixture = TestBed.createComponent(PromocionesComponent);
    c = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne(RUTA).flush(campanas);
    http
      .expectOne(`${BASE}/catalogo/sedes`)
      .flush([{ id: 's-1', nombre: 'Centro', direccion: null, telefono: null, zona_horaria: 'America/Guayaquil', minutos_antelacion_minima: 60 }]);
    fixture.detectChanges();
  }

  function seleccionar(elegida: Campana, audiencia = 3): void {
    c.seleccionar(elegida);
    http.expectOne(`${RUTA}/${elegida.id}/audiencia`).flush({ con_consentimiento: audiencia });
    if (elegida.tiene_imagen) {
      http.expectOne(`${RUTA}/${elegida.id}/imagen`).flush(new Blob(['png']));
    }
    fixture.detectChanges();
  }

  function texto(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [PromocionesComponent], providers: PROVEEDORES_PRUEBA });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('crea un borrador con su segmento', () => {
    montar(['promocion.gestionar'], []);
    expect(texto()).toContain('Aún no hay campañas');
    c.creando.set(true);
    c.nombre = 'Reactivacion';
    c.texto = 'Le esperamos para su control anual con descuento.';
    c.sedeId = 's-1';
    c.tipoAudiencia = 'reactivar';
    c.dias = 365;
    c.crear();
    const alta = http.expectOne(RUTA);
    expect(alta.request.body.segmento).toEqual({
      sede_id: 's-1',
      sin_visita_hace_dias: 365,
      visita_en_ultimos_dias: null,
    });
    alta.flush(campana({ segmento: { sede_id: 's-1', sin_visita_hace_dias: 365 } }));
    http.expectOne(`${RUTA}/camp-1/audiencia`).flush({ con_consentimiento: 2 });
    expect(c.creando()).toBeFalse();
    expect(c.describirSegmento(c.seleccionada())).toContain('Sede Centro');
    expect(c.describirSegmento(c.seleccionada())).toContain('365');
  });

  it('pide la imagen a la IA y la marca como propuesta', () => {
    montar(['promocion.gestionar'], [campana()]);
    seleccionar(campana());
    expect(texto()).toContain('3');
    c.descripcionImagen = 'Sonrisa luminosa en tonos verdes';
    c.generar();
    const pedido = http.expectOne(`${RUTA}/camp-1/imagen-generada`);
    expect(pedido.request.body).toEqual({ descripcion: 'Sonrisa luminosa en tonos verdes' });
    pedido.flush(
      campana({ tiene_imagen: true, imagen_origen: 'GENERADA', imagen_proveedor: 'sandbox' }),
    );
    http.expectOne(`${RUTA}/camp-1/imagen`).flush(new Blob(['png']));
    fixture.detectChanges();
    expect(texto()).toContain('Imagen propuesta por IA');
    // Sin permiso de aprobar no hay botón de aprobación.
    expect(texto()).not.toContain('Aprobar campaña');
    expect(texto()).toContain('permiso de aprobación');
  });

  it('sube una imagen propia y muestra el rechazo', () => {
    montar(['promocion.gestionar'], [campana()]);
    seleccionar(campana());
    const campo = document.createElement('input');
    Object.defineProperty(campo, 'files', { value: [archivo('oferta.png', 'x', 'image/png')] });
    c.subir({ target: campo } as unknown as Event);
    http
      .expectOne(`${RUTA}/camp-1/imagen`)
      .flush({ codigo: 'ARCHIVO_NO_PERMITIDO', mensaje: 'Formato no admitido' }, { status: 415, statusText: 'U' });
    expect(c.error()).toBe('Formato no admitido');
  });

  it('aprueba, envía y cuenta los mensajes en cola', () => {
    const conImagen = campana({ tiene_imagen: true, imagen_origen: 'SUBIDA' });
    montar(['promocion.gestionar', 'promocion.aprobar'], [conImagen]);
    seleccionar(conImagen);
    c.aprobar();
    http
      .expectOne(`${RUTA}/camp-1/aprobacion`)
      .flush({ ...conImagen, estado: 'APROBADA', aprobada_en: '2026-10-05T11:00:00Z' });
    expect(c.exito()).toContain('aprobada');

    c.enviar();
    const envio = http.expectOne(`${RUTA}/camp-1/envio`);
    expect(envio.request.body).toEqual({ programada_para: null });
    envio.flush({ ...conImagen, estado: 'ENVIADA', encolados: 4, omitidos: 1 });
    expect(c.exito()).toContain('4 mensaje(s)');
    expect(c.exito()).toContain('1 omitido(s)');
  });

  it('cancelar exige motivo', () => {
    montar(['promocion.gestionar', 'promocion.aprobar'], [campana()]);
    seleccionar(campana());
    c.motivoCancelacion = 'no';
    c.cancelar();
    expect(c.error()).toContain('motivo');
    c.motivoCancelacion = 'Se pospone la oferta';
    c.cancelar();
    http
      .expectOne(`${RUTA}/camp-1/cancelacion`)
      .flush(campana({ estado: 'CANCELADA', motivo_cancelacion: 'Se pospone la oferta' }));
    expect(c.seleccionada().estado).toBe('CANCELADA');
  });

  it('muestra el error al listar', () => {
    iniciarSesionCon(['promocion.gestionar']);
    fixture = TestBed.createComponent(PromocionesComponent);
    c = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne(RUTA).flush({ codigo: 'X', mensaje: 'Sin permiso' }, { status: 403, statusText: 'F' });
    http.expectOne(`${BASE}/catalogo/sedes`).flush([]);
    expect(c.error()).toBe('Sin permiso');
  });
});
