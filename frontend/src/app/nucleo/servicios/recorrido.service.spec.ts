import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { CONFIGURACION } from './configuracion';
import { FalloRecorrido, RecorridoService } from './recorrido.service';

describe('RecorridoService', () => {
    let servicio: RecorridoService;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: { urlApi: '/api/v1' } },
            ],
        });
        servicio = TestBed.inject(RecorridoService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('consulta el recorrido y todas las acciones de agenda en sus rutas', () => {
        servicio.recorrido('paciente-1').subscribe();
        servicio.ingresoConsultorio('cita-1', 'consultorio-1').subscribe();
        servicio.salida('cita-1').subscribe();
        servicio.opcionesDerivacion('cita-1').subscribe();
        servicio.derivar('cita-1', { profesional_id: 'prof-1', servicio_id: 'serv-1', inicio: null }).subscribe();
        servicio.pedirTiempo('cita-1', 15).subscribe();
        servicio.pendientes().subscribe();
        servicio.opcionesTiempo('cita-1').subscribe();
        servicio.resolver('cita-1', { aprobar: true }).subscribe();

        const rutas = [
            { url: '/api/v1/agenda/pacientes/paciente-1/recorrido', metodo: 'GET' },
            { url: '/api/v1/agenda/citas/cita-1/consultorio', metodo: 'POST' },
            { url: '/api/v1/agenda/citas/cita-1/salida', metodo: 'POST' },
            { url: '/api/v1/agenda/citas/cita-1/derivacion/opciones', metodo: 'GET' },
            { url: '/api/v1/agenda/citas/cita-1/derivacion', metodo: 'POST' },
            { url: '/api/v1/agenda/citas/cita-1/prolongacion', metodo: 'POST' },
            { url: '/api/v1/agenda/prolongaciones', metodo: 'GET' },
            { url: '/api/v1/agenda/citas/cita-1/prolongacion/opciones', metodo: 'GET' },
            { url: '/api/v1/agenda/citas/cita-1/prolongacion/resolucion', metodo: 'POST' },
        ];
        for (const ruta of rutas) {
            const peticion = http.expectOne(ruta.url);
            expect(peticion.request.method).toBe(ruta.metodo);
            peticion.flush({});
        }
    });

    it('traduce errores HTTP a un error de recorrido con el mensaje seguro del API', () => {
        let fallo: unknown;
        servicio.recorrido('paciente-1').subscribe({ error: (error: unknown) => (fallo = error) });

        http.expectOne('/api/v1/agenda/pacientes/paciente-1/recorrido').flush({ mensaje: 'No tiene acceso al recorrido.' }, { status: 403, statusText: 'Forbidden' });

        expect(fallo).toEqual(expect.any(FalloRecorrido));
        expect((fallo as Error).message).toBe('No tiene acceso al recorrido.');
    });
});
