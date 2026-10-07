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

    it('usa las rutas de gestión para especialidades y servicios y vacía sus cachés', () => {
        servicio.especialidades().subscribe();
        http.expectOne(`${BASE}/catalogo/especialidades`).flush([]);
        servicio.especialidadesGestion().subscribe();
        http.expectOne(`${BASE}/catalogo/especialidades/gestion`).flush([]);

        let especialidadCreada = '';
        servicio.crearEspecialidad({ nombre: 'Ortodoncia', codigo: 'ORT', descripcion: null })
            .subscribe((resultado) => especialidadCreada = resultado.nombre);
        http.expectOne({ method: 'POST', url: `${BASE}/catalogo/especialidades` }).flush({
            id: 'esp-1', nombre: 'Ortodoncia', codigo: 'ORT', descripcion: null, activa: true,
        });
        expect(especialidadCreada).toBe('Ortodoncia');
        servicio.especialidades().subscribe();
        http.expectOne(`${BASE}/catalogo/especialidades`).flush([]);
        servicio.actualizarEspecialidad('esp-1', { nombre: 'Ortodoncia clínica', codigo: 'ORT', descripcion: null }).subscribe();
        http.expectOne({ method: 'PUT', url: `${BASE}/catalogo/especialidades/esp-1` }).flush({
            id: 'esp-1', nombre: 'Ortodoncia clínica', codigo: 'ORT', descripcion: null, activa: true,
        });
        servicio.cambiarEstadoEspecialidad('esp-1', false).subscribe();
        http.expectOne({ method: 'PATCH', url: `${BASE}/catalogo/especialidades/esp-1/estado` }).flush({
            id: 'esp-1', nombre: 'Ortodoncia clínica', codigo: 'ORT', descripcion: null, activa: false,
        });

        const datos = {
            especialidad_id: 'esp-1', nombre: 'Alineadores', descripcion: null, duracion_minutos: 45,
            minutos_preparacion: 5, precio: 125, moneda: 'USD', requiere_pago_previo: false,
            instrucciones_preparacion: null, tipo_consultorio_requerido: null,
        };
        servicio.serviciosGestion().subscribe();
        http.expectOne(`${BASE}/catalogo/servicios/gestion`).flush([]);
        const respuestaServicio = {
            id: 'srv-1', especialidad_id: 'esp-1', nombre: 'Alineadores', descripcion: null,
            duracion_minutos: 45, minutos_preparacion: 5, precio: '125.00', moneda: 'USD',
            activo: true, requiere_pago_previo: false, instrucciones_preparacion: null,
            tipo_consultorio_requerido: null,
        };
        let servicioCreado = '';
        servicio.crearServicio(datos).subscribe((resultado) => servicioCreado = resultado.nombre);
        http.expectOne({ method: 'POST', url: `${BASE}/catalogo/servicios` }).flush(respuestaServicio);
        expect(servicioCreado).toBe('Alineadores');
        servicio.servicios().subscribe();
        http.expectOne(`${BASE}/catalogo/servicios`).flush([]);
        servicio.actualizarServicio('srv-1', datos).subscribe();
        http.expectOne({ method: 'PUT', url: `${BASE}/catalogo/servicios/srv-1` }).flush(respuestaServicio);
        servicio.cambiarEstadoServicio('srv-1', false).subscribe();
        http.expectOne({ method: 'PATCH', url: `${BASE}/catalogo/servicios/srv-1/estado` }).flush({
            ...respuestaServicio, activo: false,
        });
    });
});
