/** Asistente: sugerencias según permisos, conversación y paciente de contexto. */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { AsistenteComponent } from './asistente.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

describe('AsistenteComponent', () => {
    let fixture: ComponentFixture<AsistenteComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [AsistenteComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        iniciarSesionCon(['agenda.leer', 'historia_clinica.leer']);
        fixture = TestBed.createComponent(AsistenteComponent);
        c = fixture.componentInstance;
        fixture.detectChanges();
        http.expectOne(`${BASE}/asistente/sugerencias`).flush(['Mi agenda de hoy', 'Agrega al conocimiento: …']);
        fixture.detectChanges();
    });

    afterEach(() => {
        // El selector de paciente busca por su cuenta; aquí no se prueba.
        http.match((p) => p.url.includes('/pacientes')).forEach((p) => p.flush({ elementos: [], total: 0 }));
        http.verify();
    });

    it('envía una sugerencia y pinta la respuesta con sus elementos y enlace', () => {
        c.usarSugerencia('Mi agenda de hoy');
        const peticion = http.expectOne({ method: 'POST', url: `${BASE}/asistente/mensajes` });
        expect(peticion.request.body).toEqual({ texto: 'Mi agenda de hoy', paciente_id: null });
        peticion.flush({
            intencion: 'AGENDA',
            texto: 'Hoy tiene 1 cita(s).',
            elementos: [{ titulo: '09:00 Ana Sintética', detalle: 'Consulta · por llegar', enlace: '/agenda' }],
            enlace: '/historia-clinica?paciente=p1',
            sugerencias: ['¿Quién sigue?'],
        });
        fixture.detectChanges();
        const el = fixture.nativeElement as HTMLElement;
        expect(el.textContent).toContain('Hoy tiene 1 cita(s).');
        expect(el.textContent).toContain('09:00 Ana Sintética');
        expect(c.sugerencias()).toEqual(['¿Quién sigue?']);
        expect(c.ruta('/historia-clinica?paciente=p1')).toBe('/historia-clinica');
        expect(c.consulta('/historia-clinica?paciente=p1')).toEqual({ paciente: 'p1' });
    });

    it('una sugerencia para completar no se envía; con paciente, va su id; un error se muestra', () => {
        c.usarSugerencia('Agrega al conocimiento: …');
        expect(c.texto).toBe('Agrega al conocimiento: ');

        c.paciente.set({ id: 'p9', nombre: 'Ana', apellido: 'Sintética' });
        c.texto = 'Resumen';
        c.alEnter(new KeyboardEvent('keydown', { key: 'Enter' }));
        const peticion = http.expectOne(`${BASE}/asistente/mensajes`);
        expect(peticion.request.body).toEqual({ texto: 'Resumen', paciente_id: 'p9' });
        peticion.flush({ codigo: 'X', mensaje: 'Sin relación asistencial' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBe('Sin relación asistencial');
        expect(c.pensando()).toBe(false);

        c.texto = '   ';
        c.enviar();
    });
});
