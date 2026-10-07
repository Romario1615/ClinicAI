/**
 * Reprogramar una cita: nuevo horario del mismo profesional y, si hace falta,
 * otra sala. Solo se ofrecen salas libres a la nueva hora; mantener la actual
 * no envía cambio de sala.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { ReprogramarCitaComponent } from './reprogramar-cita.component';
import type { Cita, Consultorio } from '../../nucleo/modelos/dominio';
import { BASE, PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

function cita(extra: Partial<Cita> = {}): Cita {
    return {
        id: 'cita-1',
        paciente_id: 'pac-1',
        profesional_id: 'prof-1',
        servicio_id: 'srv-1',
        sede_id: 'sede-1',
        consultorio_id: 'sala-1',
        inicio: '2026-10-06T14:00:00Z',
        fin: '2026-10-06T14:30:00Z',
        duracion_minutos: 30,
        minutos_preparacion: 0,
        estado: 'CONFIRMED',
        origen: 'PANEL',
        expira_en: null,
        confirmada_en: null,
        llegada_en: null,
        atencion_iniciada_en: null,
        cancelada_en: null,
        motivo_cancelacion: null,
        ...extra,
    } as Cita;
}

const SALAS: readonly Consultorio[] = [
    { id: 'sala-1', sede_id: 'sede-1', nombre: 'Sillon 1', tipo: 'PROCEDIMIENTOS', capacidad: 1 },
    { id: 'sala-2', sede_id: 'sede-1', nombre: 'Sillon 2', tipo: 'PROCEDIMIENTOS', capacidad: 1 },
    { id: 'sala-3', sede_id: 'sede-1', nombre: 'Sillon 3', tipo: 'PROCEDIMIENTOS', capacidad: 1 },
];

const TURNO = {
    inicio: '2026-10-06T16:00:00Z',
    fin_consulta: '2026-10-06T16:30:00Z',
    fin_bloque: '2026-10-06T16:30:00Z',
    duracion_minutos: 30,
    minutos_preparacion: 0,
};

describe('ReprogramarCitaComponent', () => {
    let fixture: ComponentFixture<ReprogramarCitaComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [ReprogramarCitaComponent],
            providers: PROVEEDORES_PRUEBA,
        });
        http = TestBed.inject(HttpTestingController);
        fixture = TestBed.createComponent(ReprogramarCitaComponent);
        c = fixture.componentInstance;
        fixture.componentRef.setInput('cita', cita());
        fixture.componentRef.setInput('zona', 'America/Guayaquil');
        fixture.componentRef.setInput('consultorios', SALAS);
        // Otra cita ocupa el Sillon 1 a la nueva hora.
        fixture.componentRef.setInput('citasSede', [
            cita({ id: 'otra', inicio: '2026-10-06T16:00:00Z', fin: '2026-10-06T16:30:00Z' }),
            cita({ id: 'cancelada', consultorio_id: 'sala-3', estado: 'CANCELLED', inicio: TURNO.inicio, fin: TURNO.fin_bloque }),
        ]);
        fixture.detectChanges();
        http
            .expectOne((p) => p.url === `${BASE}/agenda/disponibilidad`)
            .flush({ turnos: [TURNO], motivos_sin_turno: {} });
    });

    afterEach(() => http.verify());

    it('presenta el formulario en una ventana accesible y no lo cierra al pulsar fuera', () => {
        const dialogo = fixture.nativeElement.querySelector('dialog.capa') as HTMLDialogElement | null;
        const cerrado = vi.fn();
        c.cerrar.subscribe(cerrado);

        expect(dialogo?.getAttribute('aria-modal')).toBe('true');
        expect(dialogo?.getAttribute('aria-label')).toBe('Reprogramar cita');
        expect(fixture.nativeElement.querySelector('#formulario-reprogramacion')).not.toBeNull();

        dialogo?.click();
        expect(cerrado).not.toHaveBeenCalled();
    });

    it('solo ofrece salas libres y avisa si la actual está ocupada', () => {
        c.inicio = TURNO.inicio;
        expect(c.salasLibres().map((s: Consultorio) => s.id)).toEqual(['sala-2', 'sala-3']);
        expect(c.salaActualLibre()).toBe(false);
        expect(c.nombreSala('sala-2')).toBe('Sillon 2');
        expect(c.nombreSala('x')).toBe('sala actual');
        c.inicio = 'otro';
        expect(c.salasLibres()).toEqual([]);
    });

    it('envía la sala nueva elegida', () => {
        c.inicio = TURNO.inicio;
        c.motivo = 'Pide otro horario';
        c.consultorioId = 'sala-2';
        c.guardar();
        const peticion = http.expectOne(`${BASE}/agenda/citas/cita-1/reprogramacion`);
        expect(peticion.request.body).toEqual({
            nuevo_inicio: TURNO.inicio,
            motivo: 'Pide otro horario',
            nuevo_consultorio_id: 'sala-2',
        });
        peticion.flush(cita({ consultorio_id: 'sala-2', inicio: TURNO.inicio }));
    });

    it('mantener la sala no envía cambio de sala', () => {
        c.inicio = TURNO.inicio;
        c.motivo = 'Pide otro horario';
        c.guardar();
        const peticion = http.expectOne(`${BASE}/agenda/citas/cita-1/reprogramacion`);
        expect(peticion.request.body.nuevo_consultorio_id).toBeUndefined();
        peticion.flush({ codigo: 'CONFLICTO_ESTADO', mensaje: 'El consultorio ya esta ocupado en ese horario.' }, { status: 409, statusText: 'C' });
        expect(c.error()).toContain('consultorio');
    });
});
