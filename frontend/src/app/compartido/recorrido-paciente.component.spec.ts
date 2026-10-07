/** Recorrido: agrupa por día, el más reciente primero, y dice cuándo no hay nada. */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { RecorridoPacienteComponent } from './recorrido-paciente.component';
import { BASE, PROVEEDORES_PRUEBA } from '../nucleo/pruebas/sesion-sintetica';

function paso(ocurrido_en: string, evento: string, titulo: string) {
    return {
        ocurrido_en,
        evento,
        titulo,
        detalle: evento === 'DERIVACION_INTERNA' ? 'Dermatología · Dra. Piel' : null,
        cita_id: 'c1',
        servicio: 'Consulta',
        profesional: 'Dra. Uno',
        consultorio: evento === 'INGRESO_CONSULTORIO' ? 'Sala 1' : null,
        sede: 'Norte',
        registrado_por: 'Recepción',
    };
}

describe('RecorridoPacienteComponent', () => {
    let fixture: ComponentFixture<RecorridoPacienteComponent>;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [RecorridoPacienteComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
        fixture = TestBed.createComponent(RecorridoPacienteComponent);
        fixture.componentRef.setInput('pacienteId', 'p1');
        fixture.detectChanges();
    });

    afterEach(() => http.verify());

    it('pinta los pasos agrupados por día, el más reciente primero', () => {
        http.expectOne(`${BASE}/agenda/pacientes/p1/recorrido`).flush([
            paso('2026-10-01T14:00:00Z', 'LLEGADA', 'Llegó a la clínica'),
            paso('2026-10-06T14:00:00Z', 'LLEGADA', 'Llegó a la clínica'),
            paso('2026-10-06T14:05:00Z', 'INGRESO_CONSULTORIO', 'Pasó a consultorio'),
            paso('2026-10-06T14:40:00Z', 'DERIVACION_INTERNA', 'Derivado a otra área'),
        ]);
        fixture.detectChanges();
        const el = fixture.nativeElement as HTMLElement;
        const dias = Array.from(el.querySelectorAll('.dia')).map((d) => d.textContent ?? '');
        expect(dias.length).toBe(2);
        expect(dias[0]).toContain('6');
        expect(el.textContent).toContain('Sala 1');
        expect(el.textContent).toContain('Dermatología · Dra. Piel');
        expect(el.querySelector('[data-tono="derivacion"]')).not.toBeNull();
    });

    it('sin pasos lo dice, y un error se muestra', () => {
        http.expectOne(`${BASE}/agenda/pacientes/p1/recorrido`).flush([]);
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Aún no hay movimientos');

        const otro = TestBed.createComponent(RecorridoPacienteComponent);
        otro.componentRef.setInput('pacienteId', 'p2');
        otro.detectChanges();
        http
            .expectOne(`${BASE}/agenda/pacientes/p2/recorrido`)
            .flush({ codigo: 'X', mensaje: 'Sin acceso' }, { status: 403, statusText: 'F' });
        otro.detectChanges();
        expect((otro.nativeElement as HTMLElement).textContent).toContain('Sin acceso');
    });
});
