/**
 * Foto de una persona del equipo: iniciales sin foto, foto por usuario o por
 * profesional, y subida que muestra el rechazo del servidor.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { FotoPersonaComponent } from './foto-persona.component';
import { BASE, PROVEEDORES_PRUEBA, archivo } from '../nucleo/pruebas/sesion-sintetica';

describe('FotoPersonaComponent', () => {
    let fixture: ComponentFixture<FotoPersonaComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [FotoPersonaComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        fixture = TestBed.createComponent(FotoPersonaComponent);
        c = fixture.componentInstance;
    });

    afterEach(() => http.verify());

    function campo(file: File | null): Event {
        const input = document.createElement('input');
        Object.defineProperty(input, 'files', { value: { item: () => file } });
        return { target: input } as unknown as Event;
    }

    it('sin foto muestra iniciales; con foto la pinta; sube una nueva', () => {
        fixture.componentRef.setInput('usuarioId', 'u1');
        fixture.componentRef.setInput('nombre', 'Ana María Uno');
        fixture.componentRef.setInput('puedeEditar', true);
        fixture.detectChanges();
        http.expectOne(`${BASE}/usuarios/u1/foto`).flush(null, { status: 204, statusText: 'No Content' });
        fixture.detectChanges();
        const el = fixture.nativeElement as HTMLElement;
        expect(el.textContent).toContain('AM');
        expect(el.textContent).toContain('Subir foto');

        c.subir(campo(null));
        let avisado = false;
        c.actualizada.subscribe(() => (avisado = true));
        c.subir(campo(archivo('yo.png', 'x', 'image/png')));
        http.expectOne({ method: 'PUT', url: `${BASE}/usuarios/u1/foto` }).flush({});
        http.expectOne(`${BASE}/usuarios/u1/foto`).flush(new Blob(['x'], { type: 'image/png' }));
        expect(avisado).toBe(true);
        expect(c.url()).toMatch(/^blob:/);

        c.subir(campo(archivo('yo.png', 'x', 'image/png')));
        http
            .expectOne({ method: 'PUT', url: `${BASE}/usuarios/u1/foto` })
            .flush({ codigo: 'ARCHIVO_NO_PERMITIDO', mensaje: 'Formato no admitido.' }, { status: 415, statusText: 'U' });
        expect(c.error()).toBe('Formato no admitido.');
    });

    it('por profesional es solo lectura', () => {
        fixture.componentRef.setInput('profesionalId', 'p1');
        fixture.componentRef.setInput('puedeEditar', true);
        fixture.detectChanges();
        http.expectOne(`${BASE}/profesionales/p1/foto`).flush(null, { status: 500, statusText: 'E' });
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).textContent).not.toContain('Subir foto');
    });
});
