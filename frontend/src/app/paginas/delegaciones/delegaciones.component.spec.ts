/**
 * Delegaciones: validación del formulario, alta con vigencia y revocación.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { DelegacionesComponent } from './delegaciones.component';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const VIGENTE = {
    id: 'd1',
    delegante_id: 'p1',
    delegado_id: 'p2',
    vigente_desde: '2026-10-01T00:00:00Z',
    vigente_hasta: '2026-12-31T23:59:59Z',
    motivo: 'Residencia',
    revocada_en: null,
    vigente: true,
};

describe('DelegacionesComponent', () => {
    let fixture: ComponentFixture<DelegacionesComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [DelegacionesComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        fixture = TestBed.createComponent(DelegacionesComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        http.expectOne(`${BASE}/catalogo/profesionales`).flush([
            { id: 'p1', especialidad_id: 'e', nombre: 'Adjunta', apellido: 'Uno', numero_registro_profesional: 'R1' },
            { id: 'p2', especialidad_id: 'e', nombre: 'Residente', apellido: 'Dos', numero_registro_profesional: 'R2' },
        ]);
        http.expectOne(`${BASE}/profesionales/delegaciones`).flush([VIGENTE]);
        fixture.detectChanges();
    });

    afterEach(() => http.verify());

    it('lista con nombres y revoca', () => {
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).toContain('Residente Dos firma por Adjunta Uno');
        expect(c.nombre('x')).toBe('Profesional');
        c.revocar(VIGENTE);
        http
            .expectOne(`${BASE}/profesionales/delegaciones/d1/revocacion`)
            .flush({ ...VIGENTE, vigente: false, revocada_en: '2026-10-05T10:00:00Z' });
        expect(c.delegaciones()[0].vigente).toBe(false);
    });

    it('valida y registra una delegación', () => {
        c.crear();
        expect(c.error()).toContain('Complete');
        c.delegante = 'p1';
        c.delegado = 'p2';
        c.desde = '2026-10-01';
        c.hasta = '2026-12-31';
        c.motivo = 'Residencia 2026';
        c.crear();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/profesionales/delegaciones` });
        expect(alta.request.body.delegante_id).toBe('p1');
        expect(alta.request.body.vigente_hasta).toContain('T');
        alta.flush(VIGENTE);
        expect(c.exito()).toContain('registrada');

        c.motivo = 'Otra delegacion';
        c.crear();
        http
            .expectOne({ method: 'POST', url: `${BASE}/profesionales/delegaciones` })
            .flush({ codigo: 'X', mensaje: 'No existe' }, { status: 404, statusText: 'N' });
        expect(c.error()).toBe('No existe');
    });
});
