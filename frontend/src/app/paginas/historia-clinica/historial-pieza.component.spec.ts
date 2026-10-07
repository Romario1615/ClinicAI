/**
 * Historial de pieza: solo las versiones en que la pieza cambió, de la más
 * reciente a la más antigua, y los procedimientos del plan de esa pieza.
 */
import { TestBed } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { HistorialPiezaComponent } from './historial-pieza.component';
import type { Odontograma, PlanTratamiento } from '../../nucleo/servicios/api.service';
import { PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';

function version(numero: number, piezas: Odontograma['piezas'], procedimiento: string | null = null): Odontograma {
    return {
        id: `odo-${numero}`,
        paciente_id: 'pac-1',
        profesional_id: 'prof-1',
        version: numero,
        vigente: false,
        denticion: 'PERMANENTE',
        piezas,
        motivo_modificacion: numero > 1 ? `Motivo ${numero}` : null,
        procedimiento_id: procedimiento,
        creado_en: `2026-10-0${numero}T10:00:00Z`,
        nivel_sensibilidad: 'N2',
    };
}

describe('HistorialPiezaComponent', () => {
    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [HistorialPiezaComponent], providers: PROVEEDORES_PRUEBA });
        iniciarSesionCon([]);
    });

    afterEach(() => TestBed.inject(HttpTestingController).verify());

    it('lista cambios de la pieza y sus procedimientos', () => {
        const fixture = TestBed.createComponent(HistorialPiezaComponent);
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.componentRef.setInput('pieza', 36);
        fixture.componentRef.setInput('versiones', [
            version(1, { '36': { pieza: null, caras: { O: 'CARIES' }, nota: null } }),
            version(2, {
                '36': { pieza: null, caras: { O: 'CARIES' }, nota: null },
                '11': { pieza: 'CORONA', caras: {}, nota: null },
            }),
            version(3, { '36': { pieza: null, caras: { O: 'OBTURACION_RESINA' }, nota: 'Control' } }, 'proc-1'),
        ]);
        fixture.componentRef.setInput('planes', [
            {
                id: 'plan-1',
                titulo: 'Plan sintético',
                procedimientos: [
                    { id: 'proc-1', pieza: 36, caras: 'O', descripcion: 'Resina', estado: 'COMPLETADO', completado_en: '2026-10-03T10:00:00Z' },
                    { id: 'proc-2', pieza: 11, caras: null, descripcion: 'Corona', estado: 'PENDIENTE', completado_en: null },
                ],
            } as unknown as PlanTratamiento,
        ]);
        fixture.detectChanges();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const c = fixture.componentInstance as any;
        expect(c.cambios().map((cambio: {
            version: number;
        }) => cambio.version)).toEqual([3, 1]);
        expect(c.cambios()[0].porProcedimiento).toBe(true);
        expect(c.cambios()[0].nota).toBe('Control');
        expect(c.procedimientos().length).toBe(1);
        expect(c.estadoProcedimiento('COMPLETADO')).toBe('Completado');
        expect(c.estadoProcedimiento('OTRO')).toBe('OTRO');
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).toContain('O: Obturación de resina');
        expect(texto).toContain('Motivo 3');
        expect(texto).toContain('Plan sintético');
    });

    it('sin cambios lo dice', () => {
        const fixture = TestBed.createComponent(HistorialPiezaComponent);
        fixture.componentRef.setInput('pacienteId', 'pac-1');
        fixture.componentRef.setInput('pieza', 18);
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Sin cambios registrados');
    });
});
