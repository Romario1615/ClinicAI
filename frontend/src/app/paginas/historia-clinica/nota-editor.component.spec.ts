/**
 * Editor de notas: no se envía el autor, una nota vacía no se guarda, y
 * corregir exige motivo y crea versión nueva.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { NotaEditorComponent } from './nota-editor.component';
import type { Nota } from '../../nucleo/servicios/api.service';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const NOTA: Nota = {
    id: 'n-1',
    raiz_id: 'n-1',
    version: 1,
    vigente: true,
    motivo_modificacion: null,
    paciente_id: 'pac-1',
    profesional_id: 'prof-1',
    cita_id: null,
    tipo: 'EVOLUCION',
    nivel_sensibilidad: 'N2',
    motivo_consulta: 'Control [SINTETICO]',
    subjetivo: 'Refiere molestia leve',
    objetivo: null,
    analisis: null,
    plan: 'Control en 6 meses',
    signos_vitales: { temperatura: 36.5, nota: 'x' },
    creado_en: '2026-10-05T10:00:00Z',
};

describe('NotaEditorComponent', () => {
    let fixture: ComponentFixture<NotaEditorComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    function montar(base: Nota | null): void {
        fixture = TestBed.createComponent(NotaEditorComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.componentRef.setInput('base', base);
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [NotaEditorComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        c?.cerrar();
        fixture?.detectChanges();
        http.verify();
        expect(document.body.style.overflow).not.toBe('hidden');
    });

    it('presenta el editor en una ventana centrada y cancela con Escape', () => {
        montar(null);
        const cancelado = vi.fn();
        fixture.componentInstance.cancelado.subscribe(cancelado);
        const raiz = fixture.nativeElement as HTMLElement;
        const dialogo = raiz.querySelector<HTMLDialogElement>('dialog[open][aria-modal="true"]');
        expect(dialogo?.getAttribute('aria-label')).toBe('Nueva nota de evolución');
        expect(dialogo?.querySelector('form#form-nota')).not.toBeNull();
        expect(dialogo?.querySelector('.ventana__pie')).not.toBeNull();

        dialogo?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        fixture.detectChanges();
        expect(raiz.querySelector('dialog[open]')).toBeNull();
        expect(cancelado).toHaveBeenCalledOnce();
    });

    it('no guarda una nota vacía y no envía el autor', () => {
        montar(null);
        c.guardar();
        expect(c.error()).toContain('al menos una sección');
        http.expectNone(`${BASE}/historia/notas`);

        c.valores.subjetivo = ' Dolor al masticar ';
        c.vitales.temperatura = 37.2;
        c.vitales.frecuencia_cardiaca = null;
        const guardada = vi.fn().mockName('guardada');
        fixture.componentInstance.guardada.subscribe(guardada);
        c.guardar();
        const alta = http.expectOne(`${BASE}/historia/notas`);
        expect(alta.request.body.profesional_id).toBeUndefined();
        expect(alta.request.body.subjetivo).toBe('Dolor al masticar');
        expect(alta.request.body.nivel_sensibilidad).toBe('N2');
        expect(alta.request.body.objetivo).toBeNull();
        expect(alta.request.body.signos_vitales).toEqual({ temperatura: 37.2 });
        alta.flush(NOTA);
        expect(guardada).toHaveBeenCalled();
    });

    it('corregir carga la nota, exige motivo y crea versión nueva', () => {
        montar(NOTA);
        expect(c.valores.subjetivo).toBe('Refiere molestia leve');
        expect(c.vitales).toEqual({ temperatura: 36.5 });
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('versión nueva');

        c.guardar();
        expect(c.error()).toContain('motivo');

        c.motivo = 'Se completa el plan';
        c.guardar();
        const correccion = http.expectOne(`${BASE}/historia/notas/n-1/correccion`);
        expect(correccion.request.body.motivo).toBe('Se completa el plan');
        correccion.flush({ code: 'x' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBeTruthy();
        expect(c.guardando()).toBe(false);
    });
});
