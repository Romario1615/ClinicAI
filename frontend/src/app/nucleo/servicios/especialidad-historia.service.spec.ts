/**
 * Especialidad desde la que se revisa: la propia por defecto, la elegida se
 * recuerda en la pestaña y una sesión de otra persona vuelve a cargar.
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';

import { EspecialidadHistoriaService, type EspecialidadHistoria } from './especialidad-historia.service';
import { BASE, iniciarSesionCon, identidadCon } from '../pruebas/sesion-sintetica';
import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from './configuracion';
import { SesionService } from './sesion.service';

const ODO: EspecialidadHistoria = {
    id: 'odo',
    nombre: 'Odontología',
    modulos: ['odontograma', 'periodoncia', 'planes', 'imagenes'],
    propia: true,
};
const DERM: EspecialidadHistoria = { id: 'derm', nombre: 'Dermatología', modulos: ['imagenes'], propia: false };

describe('EspecialidadHistoriaService', () => {
    let servicio: EspecialidadHistoriaService;
    let http: HttpTestingController;

    beforeEach(() => {
        try {
            sessionStorage.removeItem('historia.especialidad');
        }
        catch {
            // Sin almacenamiento la prueba sigue valiendo.
        }
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        iniciarSesionCon(['historia_clinica.leer']);
        servicio = TestBed.inject(EspecialidadHistoriaService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('sin permisos clínicos no la pide (el backend respondería 403)', () => {
        iniciarSesionCon(['paciente.leer']);
        servicio.cargar();
        http.expectNone(`${BASE}/historia/especialidades`);
        expect(servicio.elegida()).toBeNull();
        expect(servicio.tieneModulo('imagenes')).toBe(false);
    });

    it('revisa desde la propia y solo muestra sus módulos', () => {
        expect(servicio.tieneModulo('odontograma')).toBe(false);
        servicio.cargar();
        http.expectOne(`${BASE}/historia/especialidades`).flush([ODO, DERM]);
        expect(servicio.elegida()?.id).toBe('odo');
        expect(servicio.tieneModulo('periodoncia')).toBe(true);

        servicio.elegir('derm');
        expect(servicio.tieneModulo('odontograma')).toBe(false);
        expect(servicio.tieneModulo('imagenes')).toBe(true);

        // Ya cargada para esta persona: no vuelve a pedir.
        servicio.cargar();
    });

    it('recuerda la elegida y vuelve a cargar si cambia la persona', () => {
        servicio.cargar();
        http.expectOne(`${BASE}/historia/especialidades`).flush([ODO, DERM]);
        servicio.elegir('derm');

        TestBed.inject(SesionService).establecerIdentidad({ ...identidadCon(['historia_clinica.leer']), usuario_id: 'otra-persona' });
        servicio.cargar();
        http.expectOne(`${BASE}/historia/especialidades`).flush([ODO, DERM]);
        expect(servicio.elegida()?.id).toBe('derm');
    });

    it('sin acceso no hay especialidad ni módulos', () => {
        servicio.cargar();
        http
            .expectOne(`${BASE}/historia/especialidades`)
            .flush({ codigo: 'X', mensaje: 'x' }, { status: 403, statusText: 'F' });
        expect(servicio.cargada()).toBe(true);
        expect(servicio.elegida()).toBeNull();
        expect(servicio.tieneModulo('imagenes')).toBe(false);
    });
});
