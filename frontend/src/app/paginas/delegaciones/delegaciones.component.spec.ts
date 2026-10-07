/**
 * Delegaciones: ventana modal, validación del formulario, alta y revocación.
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

    afterEach(() => {
        c.cerrarEditor();
        fixture.detectChanges();
        http.verify();
        expect(document.body.style.overflow).not.toBe('hidden');
    });

    it('abre el alta en una ventana accesible y la cierra con Escape', () => {
        const raiz = fixture.nativeElement as HTMLElement;
        expect(raiz.querySelector('dialog[open]')).toBeNull();
        raiz.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')?.click();
        fixture.detectChanges();

        const dialogo = raiz.querySelector<HTMLDialogElement>('dialog[open][aria-modal="true"]');
        expect(dialogo?.getAttribute('aria-label')).toBe('Nueva delegación de firma');
        expect(dialogo?.querySelector('form#form-delegacion')).not.toBeNull();
        expect(dialogo?.querySelector('.ventana__pie')).not.toBeNull();

        dialogo?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();
        expect(raiz.querySelector('dialog[open]')).toBeNull();
    });

    it('cancelar cierra la ventana y limpia el borrador sin enviar datos', () => {
        const raiz = fixture.nativeElement as HTMLElement;
        raiz.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')?.click();
        fixture.detectChanges();
        c.delegante = 'p1';
        c.delegado = 'p2';
        c.motivo = 'Cobertura temporal';
        fixture.detectChanges();
        Array.from(raiz.querySelectorAll<HTMLButtonElement>('.ventana__pie button'))
            .find((boton) => boton.textContent?.includes('Cancelar'))?.click();
        fixture.detectChanges();

        expect(raiz.querySelector('dialog[open]')).toBeNull();
        expect(c.delegante).toBe('');
        expect(c.motivo).toBe('');
        http.expectNone({ method: 'POST', url: `${BASE}/profesionales/delegaciones` });
    });

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
        c.abrirEditor();
        fixture.detectChanges();
        c.crear();
        expect(c.errorEditor()).toContain('Complete');
        c.delegante = 'p1';
        c.delegado = 'p1';
        c.desde = '2026-10-01';
        c.hasta = '2026-09-30';
        c.motivo = 'Residencia 2026';
        c.crear();
        expect(c.errorEditor()).toContain('dos profesionales distintos');
        c.delegado = 'p2';
        c.crear();
        expect(c.errorEditor()).toContain('fecha de término');
        c.hasta = '2026-12-31';
        c.crear();
        const alta = http.expectOne({ method: 'POST', url: `${BASE}/profesionales/delegaciones` });
        expect(alta.request.body.delegante_id).toBe('p1');
        expect(alta.request.body.vigente_hasta).toContain('T');
        alta.flush({ ...VIGENTE, id: 'd2' });
        fixture.detectChanges();
        expect(c.exito()).toContain('registrada');
        expect((fixture.nativeElement as HTMLElement).querySelector('dialog[open]')).toBeNull();

        c.abrirEditor();
        fixture.detectChanges();
        c.delegante = 'p1';
        c.delegado = 'p2';
        c.desde = '2026-10-01';
        c.hasta = '2026-12-31';
        c.motivo = 'Otra delegacion';
        c.crear();
        http
            .expectOne({ method: 'POST', url: `${BASE}/profesionales/delegaciones` })
            .flush({ codigo: 'X', mensaje: 'No existe' }, { status: 404, statusText: 'N' });
        fixture.detectChanges();
        expect(c.errorEditor()).toBe('No existe');
        expect((fixture.nativeElement as HTMLElement).querySelector('dialog[open]')).not.toBeNull();
    });
});
