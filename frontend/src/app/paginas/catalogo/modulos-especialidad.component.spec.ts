/**
 * Módulos por especialidad: tabla de lo activo, cambio con motivo y errores
 * del servidor a la vista.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ModulosEspecialidadComponent } from './modulos-especialidad.component';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const RUTA = `${BASE}/catalogo/especialidades`;
const CATALOGO = [
    { codigo: 'odontograma', nombre: 'Odontograma', descripcion: 'Piezas' },
    { codigo: 'imagenes', nombre: 'Imágenes y radiografías', descripcion: 'Fotos' },
];

describe('ModulosEspecialidadComponent', () => {
    let fixture: ComponentFixture<ModulosEspecialidadComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [ModulosEspecialidadComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        fixture = TestBed.createComponent(ModulosEspecialidadComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
    });

    afterEach(() => http.verify());

    function cargar(): void {
        http.expectOne(`${RUTA}/modulos-historia`).flush({
            catalogo: CATALOGO,
            especialidades: [
                { id: 'odo', nombre: 'Odontología', activa: true, modulos: ['odontograma', 'imagenes'] },
                { id: 'derm', nombre: 'Dermatología', activa: false, modulos: ['imagenes'] },
            ],
        });
        fixture.detectChanges();
    }

    it('muestra qué módulo usa cada especialidad', () => {
        cargar();
        const filas = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('tbody tr'));
        expect(filas.map((f) => f.querySelectorAll('.marca--si').length)).toEqual([2, 1]);
        expect(filas[1].textContent).toContain('Inactiva');
    });

    it('cambia los módulos con motivo y conserva el orden del catálogo', () => {
        cargar();
        const derm = c.especialidades()[1];
        c.abrir(derm);
        fixture.detectChanges();
        c.alternar('odontograma');
        c.alternar('imagenes');
        c.alternar('imagenes');

        c.motivo = 'abc';
        c.guardar(derm);
        expect(c.errorCambio()).toContain('motivo');

        c.motivo = 'Empieza a registrar piezas';
        c.guardar(derm);
        const peticion = http.expectOne({ method: 'PUT', url: `${RUTA}/derm/modulos-historia` });
        expect(peticion.request.body).toEqual({ modulos: ['odontograma', 'imagenes'], motivo: 'Empieza a registrar piezas' });
        peticion.flush({ id: 'derm', nombre: 'Dermatología', activa: false, modulos: ['odontograma', 'imagenes'] });
        expect(c.especialidades()[1].modulos).toEqual(['odontograma', 'imagenes']);
        expect(c.editando()).toBeNull();
        expect(c.aviso()).toContain('Dermatología');
    });

    it('muestra el error del servidor al guardar y al cargar', () => {
        cargar();
        const odo = c.especialidades()[0];
        c.abrir(odo);
        c.motivo = 'Ajuste de prueba';
        c.guardar(odo);
        http
            .expectOne({ method: 'PUT', url: `${RUTA}/odo/modulos-historia` })
            .flush({ codigo: 'X', mensaje: 'Sin permiso' }, { status: 403, statusText: 'F' });
        expect(c.errorCambio()).toBe('Sin permiso');
        expect(c.guardando()).toBe(false);

        const otro = TestBed.createComponent(ModulosEspecialidadComponent);
        otro.detectChanges();
        http.expectOne(`${RUTA}/modulos-historia`).flush(null, { status: 500, statusText: 'F' });
        expect((otro.componentInstance as unknown as {
            error(): string;
        }).error()).toBe('No se pudieron cargar los módulos.');
    });
});
