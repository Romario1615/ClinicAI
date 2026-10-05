/**
 * Caché del catálogo: una petición compartida por clave y vaciado al cerrar
 * sesión, para que la siguiente persona no vea el catálogo de la anterior.
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { CatalogoService } from './catalogo.service';
import { BASE, PROVEEDORES_PRUEBA } from '../pruebas/sesion-sintetica';

describe('CatalogoService', () => {
  let servicio: CatalogoService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: PROVEEDORES_PRUEBA });
    servicio = TestBed.inject(CatalogoService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('comparte una sola petición por clave y la repite tras limpiar', () => {
    servicio.clinica().subscribe();
    servicio.clinica().subscribe();
    http.expectOne(`${BASE}/catalogo/clinica`).flush({ id: 'c', nombre: 'C', zona_horaria: 'UTC', idioma: 'es', moneda: 'USD' });

    servicio.sedes().subscribe((sedes) => expect(sedes[0].nombre).toBe('Centro'));
    http.expectOne(`${BASE}/catalogo/sedes`).flush([
      { id: 's', nombre: 'Centro', direccion: null, telefono: null, zona_horaria: 'UTC', minutos_antelacion_minima: 60 },
    ]);
    servicio.especialidades().subscribe();
    http.expectOne(`${BASE}/catalogo/especialidades`).flush([]);

    servicio.servicios('esp-1').subscribe();
    servicio.servicios('esp-1').subscribe();
    http.expectOne(`${BASE}/catalogo/servicios?especialidad_id=esp-1`).flush([]);
    servicio.servicios().subscribe();
    http.expectOne(`${BASE}/catalogo/servicios`).flush([]);

    servicio.profesionales({ especialidadId: 'e', sedeId: 's' }).subscribe();
    http.expectOne(`${BASE}/catalogo/profesionales?especialidad_id=e&sede_id=s`).flush([]);
    servicio.profesionales().subscribe();
    http.expectOne(`${BASE}/catalogo/profesionales`).flush([]);

    servicio.consultorios('s').subscribe();
    servicio.consultorios('s').subscribe();
    http.expectOne(`${BASE}/catalogo/consultorios?sede_id=s`).flush([]);
    servicio.consultorios().subscribe();
    http.expectOne(`${BASE}/catalogo/consultorios`).flush([]);

    servicio.limpiar();
    servicio.consultorios('s').subscribe();
    http.expectOne(`${BASE}/catalogo/consultorios?sede_id=s`).flush([]);
  });
});
