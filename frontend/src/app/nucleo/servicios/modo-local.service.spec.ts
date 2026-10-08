import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from './configuracion';
import { ModoLocalService } from './modo-local.service';

describe('ModoLocalService', () => {
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('habilita herramientas locales solo cuando el backend lo confirma', () => {
        const servicio = TestBed.inject(ModoLocalService);
        const peticion = http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`);
        expect(servicio.habilitado()).toBe(false);
        peticion.flush({ habilitado: true, roles: [] });
        expect(servicio.habilitado()).toBe(true);
    });

    it('falla cerrado si el endpoint de entorno no responde', () => {
        const servicio = TestBed.inject(ModoLocalService);
        http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`).error(new ProgressEvent('network error'));
        expect(servicio.habilitado()).toBe(false);
    });

    it('conserva la especialidad de la cuenta elegida para cada acceso', () => {
        const servicio = TestBed.inject(ModoLocalService);
        const respuesta = { habilitado: true, roles: [{ codigo: 'profesional', nombre: 'Profesional de salud', especialidad: 'Dermatología' }] };
        http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`).flush(respuesta);
        let recibido: unknown;
        servicio.accesosLocales().subscribe(datos => recibido = datos);
        http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`).flush(respuesta);
        expect(recibido).toEqual(respuesta);
        servicio.accesosLocales().subscribe(datos => recibido = datos);
        const actualizada = { ...respuesta, roles: [{ ...respuesta.roles[0], especialidad: 'Medicina estética' }] };
        http.expectOne(`${CONFIGURACION_POR_DEFECTO.urlApi}/autenticacion/accesos-locales`).flush(actualizada);
        expect(recibido).toEqual(actualizada);
    });
});
