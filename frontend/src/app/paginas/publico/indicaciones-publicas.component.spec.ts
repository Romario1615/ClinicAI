/**
 * Página pública de indicaciones: nada se muestra sin verificar identidad,
 * los intentos restantes se informan y el bloqueo apaga el botón.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';
import { ActivatedRoute } from '@angular/router';

import { IndicacionesPublicasComponent } from './indicaciones-publicas.component';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const URL = `${BASE}/publico/indicaciones/token-sintetico-123456789/acceso`;

describe('IndicacionesPublicasComponent', () => {
    let fixture: ComponentFixture<IndicacionesPublicasComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [IndicacionesPublicasComponent],
            providers: [
                ...PROVEEDORES_PRUEBA,
                { provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => 'token-sintetico-123456789' } } } },
            ],
        });
        http = TestBed.inject(HttpTestingController);
        fixture = TestBed.createComponent(IndicacionesPublicasComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
    });

    afterEach(() => http.verify());

    it('verifica por fecha y muestra indicaciones y medicación', () => {
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('confirme que es usted');
        c.verificar();
        expect(c.error()).toContain('fecha de nacimiento');
        c.fecha = '2000-01-01';
        c.verificar();
        http.expectOne(URL).flush({ codigo: 'CREDENCIALES_INVALIDAS', mensaje: 'Los datos no coinciden con los de la ficha.', detalles: { intentos_restantes: 4 } }, { status: 401, statusText: 'U' });
        expect(c.error()).toContain('Le quedan 4 intento(s)');
        c.fecha = '1990-04-12';
        c.verificar();
        const peticion = http.expectOne(URL);
        expect(peticion.request.body).toEqual({ fecha_nacimiento: '1990-04-12' });
        peticion.flush({
            nombre_paciente: 'Ana',
            clinica: 'Clínica sintética',
            profesional: 'Pro Fe',
            fecha: '2026-10-05T10:00:00Z',
            texto: 'Reposo dos días.',
            medicamentos: [
                { nombre: 'Medicamento sintético', concentracion: '500 mg', dosis: '1 unidad', via: 'ORAL', cuando_sea_necesario: false, frecuencia_horas: 8, duracion_dias: 5, instrucciones: 'Con comida' },
                { nombre: 'Otro', concentracion: null, dosis: '1', via: 'ORAL', cuando_sea_necesario: true, frecuencia_horas: null, duracion_dias: null, instrucciones: null },
            ],
        });
        fixture.detectChanges();
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).toContain('Indicaciones para Ana');
        expect(texto).toContain('cada 8 horas');
        expect(texto).toContain('solo cuando sea necesario');
        vi.spyOn(window, 'print').mockReturnValue(undefined);
        c.imprimir();
        expect(window.print).toHaveBeenCalled();
    });

    it('verifica por documento y bloquea al agotar intentos', () => {
        c.usarDocumento.set(true);
        c.documento = '12';
        c.verificar();
        expect(c.error()).toContain('4 últimos');
        c.documento = '1234';
        c.verificar();
        const peticion = http.expectOne(URL);
        expect(peticion.request.body).toEqual({ ultimos_digitos_documento: '1234' });
        peticion.flush({ codigo: 'ENLACE_BLOQUEADO', mensaje: 'Bloqueado.' }, { status: 409, statusText: 'C' });
        fixture.detectChanges();
        expect(c.bloqueado()).toBe(true);
        c.verificar();
        expect(http.match(URL)).toHaveLength(0);
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('se bloqueó tras varios intentos');
    });

    it('explica que el enlace vencido debe renovarse y bloquea nuevos intentos', () => {
        c.fecha = '1990-04-12';
        c.verificar();
        http.expectOne(URL).flush(null, { status: 410, statusText: 'Gone' });
        fixture.detectChanges();
        expect(c.bloqueado()).toBe(true);
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('ha caducado');
        c.verificar();
        expect(http.match(URL)).toHaveLength(0);
    });
});
