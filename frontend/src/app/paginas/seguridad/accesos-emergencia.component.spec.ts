import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ApiService } from '../../nucleo/servicios/api.service';
import { PendientesService } from '../../nucleo/servicios/pendientes.service';
import { AccesosEmergenciaComponent } from './accesos-emergencia.component';

describe('AccesosEmergenciaComponent', () => {
    let fixture: ComponentFixture<AccesosEmergenciaComponent>;
    let api: MockedObject<ApiService>;
    let pendientes: MockedObject<Pick<PendientesService, 'cargar'>>;

    beforeEach(async () => {
        api = {
            avisosAccesoEmergencia: vi.fn().mockName("ApiService.avisosAccesoEmergencia"),
            revisarAvisoAccesoEmergencia: vi.fn().mockName("ApiService.revisarAvisoAccesoEmergencia")
        } as unknown as MockedObject<ApiService>;
        api.avisosAccesoEmergencia.mockReturnValue(of([{
                id: 'aviso-1',
                profesional: 'Profesional de prueba',
                creado_en: '2026-10-06T12:00:00Z',
                vence_en: '2026-10-06T12:30:00Z',
            }]));
        api.revisarAvisoAccesoEmergencia.mockReturnValue(of(void 0));
        pendientes = {
            cargar: vi.fn().mockName("PendientesService.cargar")
        };

        await TestBed.configureTestingModule({
            imports: [AccesosEmergenciaComponent],
            providers: [
                { provide: ApiService, useValue: api },
                { provide: PendientesService, useValue: pendientes },
            ],
        }).compileComponents();

        fixture = TestBed.createComponent(AccesosEmergenciaComponent);
        fixture.detectChanges();
    });

    it('presenta solo profesional y vigencia, sin datos del paciente', () => {
        expect(fixture.nativeElement.textContent).toContain('Profesional de prueba');
        expect(fixture.nativeElement.textContent).toContain('Vigencia hasta');
        expect(fixture.nativeElement.textContent).not.toContain('paciente_id');
        expect(fixture.nativeElement.textContent).toContain('Marcar como revisado');
    });

    it('registra la revisión y refresca la insignia', () => {
        const boton = Array.from(fixture.nativeElement.querySelectorAll('button')).find((elemento) => (elemento as HTMLButtonElement).textContent?.includes('Marcar como revisado')) as HTMLButtonElement;
        boton.click();
        fixture.detectChanges();

        expect(api.revisarAvisoAccesoEmergencia).toHaveBeenCalledWith('aviso-1');
        expect(pendientes.cargar).toHaveBeenCalled();
        expect(fixture.nativeElement.textContent).toContain('Sin avisos pendientes');
    });

    it('muestra el error si no puede cargar los avisos', () => {
        api.avisosAccesoEmergencia.mockReturnValue(throwError(() => new Error('API no disponible')));
        const segundo = TestBed.createComponent(AccesosEmergenciaComponent);
        segundo.detectChanges();
        expect(segundo.nativeElement.textContent).toContain('No se pudieron cargar los avisos.');
    });

    it('conserva el aviso si falla el registro de revisión', () => {
        api.revisarAvisoAccesoEmergencia.mockReturnValue(throwError(() => new Error('API no disponible')));
        const boton = Array.from(fixture.nativeElement.querySelectorAll('button')).find((elemento) => (elemento as HTMLButtonElement).textContent?.includes('Marcar como revisado')) as HTMLButtonElement;
        boton.click();
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('No se pudo guardar la revisión.');
        expect(fixture.nativeElement.textContent).toContain('Profesional de prueba');
    });
});
