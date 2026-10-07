import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';

import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { AgendaProfesionalesComponent } from './agenda-profesionales.component';
import { AgendaProfesionalesService, type FranjaProfesional } from './agenda-profesionales.service';

describe('AgendaProfesionalesComponent', () => {
    let fixture: ComponentFixture<AgendaProfesionalesComponent>;
    let catalogo: MockedObject<CatalogoService>;
    let agenda: MockedObject<AgendaProfesionalesService>;
    const franja: FranjaProfesional = {
        id: 'f-1', profesional_id: 'p-1', sede_id: 's-1', dia_semana: 1,
        hora_inicio: '08:00:00', hora_fin: '12:00:00', granularidad_minutos: 20,
        vigente_desde: null, vigente_hasta: null,
    };

    beforeEach(() => {
        catalogo = {
            sedes: vi.fn().mockName("CatalogoService.sedes"),
            profesionales: vi.fn().mockName("CatalogoService.profesionales")
        } as unknown as MockedObject<CatalogoService>;
        catalogo.sedes.mockReturnValue(of([{ id: 's-1', nombre: 'Centro', direccion: null, zona_horaria: 'America/Guayaquil' }]));
        catalogo.profesionales.mockReturnValue(of([{ id: 'p-1', nombre: 'Ana', apellido: 'Paz', especialidad_id: 'e-1', numero_registro_profesional: 'R-1' }]));
        agenda = {
            listar: vi.fn().mockName("AgendaProfesionalesService.listar"),
            crear: vi.fn().mockName("AgendaProfesionalesService.crear"),
            actualizar: vi.fn().mockName("AgendaProfesionalesService.actualizar"),
            eliminar: vi.fn().mockName("AgendaProfesionalesService.eliminar")
        } as unknown as MockedObject<AgendaProfesionalesService>;
        agenda.listar.mockReturnValue(of([franja]));
        agenda.crear.mockReturnValue(of(franja));
        agenda.actualizar.mockReturnValue(of(franja));
        agenda.eliminar.mockReturnValue(of(void 0));
        TestBed.configureTestingModule({
            imports: [AgendaProfesionalesComponent],
            providers: [
                { provide: CatalogoService, useValue: catalogo },
                { provide: AgendaProfesionalesService, useValue: agenda },
            ],
        });
        fixture = TestBed.createComponent(AgendaProfesionalesComponent);
        fixture.detectChanges();
    });

    interface Controles {
        cargarProfesionales(): void;
        cargarFranjas(): void;
        guardar(): void;
        editar(franja: FranjaProfesional): void;
        nueva(): void;
        eliminar(franja: FranjaProfesional): void;
        nombreDia(dia: number): string;
        etiquetaProfesional(): string;
        sedeId: string;
        profesionalId: string;
        editando: string;
        form: {
            dia_semana: number;
            hora_inicio: string;
            hora_fin: string;
            granularidad_minutos: number;
            vigente_desde: string;
            vigente_hasta: string;
        };
        mensaje(): string;
        esError(): boolean;
    }
    const controles = (): Controles => fixture.componentInstance as unknown as Controles;

    it('carga el equipo y presenta su horario guardado', () => {
        expect(catalogo.profesionales).toHaveBeenCalledWith({ sedeId: 's-1' });
        expect(agenda.listar).toHaveBeenCalledWith('p-1', 's-1');
        expect(fixture.nativeElement.textContent).toContain('Lunes · 08:00–12:00');
        expect(controles().etiquetaProfesional()).toBe('Ana Paz');
    });

    it('crea una franja y actualiza la lista', () => {
        controles().guardar();
        expect(agenda.crear).toHaveBeenCalledWith('p-1', 's-1', expect.objectContaining({
            dia_semana: 1, hora_inicio: '08:00', hora_fin: '17:00', vigente_desde: null, vigente_hasta: null,
        }));
        expect(controles().mensaje()).toBe('Disponibilidad guardada.');
        expect(controles().esError()).toBe(false);
        expect(agenda.listar).toHaveBeenCalledTimes(2);
    });

    it('edita una franja sin duplicarla', () => {
        controles().editar(franja);
        expect(controles().editando).toBe('f-1');
        expect(controles().form.hora_inicio).toBe('08:00');
        controles().form.hora_inicio = '09:00';
        controles().guardar();
        expect(agenda.actualizar).toHaveBeenCalledWith('p-1', 's-1', 'f-1', expect.objectContaining({ hora_inicio: '09:00' }));
    });

    it('conecta los botones de edición y cancelación y el envío del formulario', () => {
        const botones = (): HTMLButtonElement[] => Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
        botones().find((b) => b.textContent?.trim() === 'Editar')?.click();
        fixture.detectChanges();
        expect(controles().editando).toBe('f-1');
        botones().find((b) => b.textContent?.trim() === 'Cancelar')?.click();
        fixture.detectChanges();
        expect(controles().editando).toBe('');
        const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(agenda.crear).toHaveBeenCalled();
    });

    it('elimina tras confirmación y permite cancelar la confirmación', () => {
        const confirmacion = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
        controles().eliminar(franja);
        expect(confirmacion).toHaveBeenCalledTimes(1);
        expect(agenda.eliminar).not.toHaveBeenCalled();
        controles().eliminar(franja);
        expect(agenda.eliminar).toHaveBeenCalledWith('p-1', 's-1', 'f-1');
    });

    it('muestra el conflicto de solapamiento que devuelve la API', () => {
        agenda.crear.mockReturnValue(throwError(() => new HttpErrorResponse({ status: 409, error: { mensaje: 'La disponibilidad se solapa.' } })));
        controles().guardar();
        expect(controles().mensaje()).toBe('La disponibilidad se solapa.');
        expect(controles().esError()).toBe(true);
    });

    it('no consulta horarios cuando falta el profesional seleccionado', () => {
        const antes = vi.mocked(agenda.listar).mock.calls.length;
        controles().profesionalId = '';
        controles().cargarFranjas();
        expect(vi.mocked(agenda.listar).mock.calls.length).toBe(antes);
        expect(controles().nombreDia(9)).toBe('Día');
    });

    it('mantiene el estado vacío cuando la sede no tiene profesionales', () => {
        catalogo.profesionales.mockReturnValue(of([]));
        controles().cargarProfesionales();
        expect(controles().profesionalId).toBe('');
        expect(controles().etiquetaProfesional()).toBe('PROFESIONAL');
    });

    it('presenta errores al cargar profesionales y franjas', () => {
        catalogo.profesionales.mockReturnValue(throwError(() => new Error('fallo catálogo')));
        controles().cargarProfesionales();
        expect(controles().mensaje()).toBe('No se pudieron cargar los profesionales de la sede.');
        controles().profesionalId = 'p-1';
        agenda.listar.mockReturnValue(throwError(() => new Error('fallo agenda')));
        controles().cargarFranjas();
        expect(controles().mensaje()).toBe('No se pudo cargar la agenda individual.');
        expect(controles().esError()).toBe(true);
    });

    it('muestra errores de servicio al eliminar y omite acciones sin sede', () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        agenda.eliminar.mockReturnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
        controles().eliminar(franja);
        expect(controles().mensaje()).toBe('No se pudo eliminar la franja.');
        controles().sedeId = '';
        controles().cargarProfesionales();
        expect(vi.mocked(catalogo.profesionales).mock.calls.length).toBe(1);
    });
});
