import type { MockedObject } from "vitest";
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { CatalogoService } from '../../nucleo/servicios/catalogo.service';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { AgendaConfiguracionComponent } from './agenda-configuracion.component';
import { IntegracionesService, type FeriadoAgenda, type HorarioSede } from './integraciones.service';

describe('AgendaConfiguracionComponent', () => {
    let fixture: ComponentFixture<AgendaConfiguracionComponent>;
    let api: MockedObject<IntegracionesService>;
    let ambitoCompleto: boolean;

    const horario: HorarioSede = {
        id: 'h-1', dia_semana: 1, hora_inicio: '08:00', hora_fin: '17:00',
        granularidad_minutos: 15, vigente_desde: null, vigente_hasta: null,
        descansos: [{ id: 'd-1', hora_inicio: '12:00', hora_fin: '13:00', motivo: 'Almuerzo' }],
    };
    const feriado: FeriadoAgenda = {
        id: 'f-1', sede_id: null, fecha: '2026-12-25', nombre: 'Navidad',
        recurrente_anual: true, hora_inicio: null, hora_fin: null,
    };

    beforeEach(() => {
        ambitoCompleto = true;
        api = {
            horarios: vi.fn().mockName("IntegracionesService.horarios"),
            feriados: vi.fn().mockName("IntegracionesService.feriados"),
            guardarHorario: vi.fn().mockName("IntegracionesService.guardarHorario"),
            eliminarHorario: vi.fn().mockName("IntegracionesService.eliminarHorario"),
            guardarFeriado: vi.fn().mockName("IntegracionesService.guardarFeriado"),
            eliminarFeriado: vi.fn().mockName("IntegracionesService.eliminarFeriado")
        } as unknown as MockedObject<IntegracionesService>;
        api.horarios.mockReturnValue(of([horario]));
        api.feriados.mockReturnValue(of([feriado]));
        api.guardarHorario.mockReturnValue(of(horario));
        api.eliminarHorario.mockReturnValue(of(void 0));
        api.guardarFeriado.mockReturnValue(of(feriado));
        api.eliminarFeriado.mockReturnValue(of(void 0));

        TestBed.configureTestingModule({
            imports: [AgendaConfiguracionComponent],
            providers: [
                { provide: IntegracionesService, useValue: api },
                { provide: CatalogoService, useValue: { sedes: () => of([{ id: 's-1', nombre: 'Centro', direccion: null, zona_horaria: 'America/Guayaquil' }]) } },
                { provide: SesionService, useValue: { identidad: () => ({ ambito: { todas_las_sedes: ambitoCompleto } }) } },
            ],
        });
        fixture = TestBed.createComponent(AgendaConfiguracionComponent);
        fixture.detectChanges();
    });

    function boton(texto: string): HTMLButtonElement {
        const botones = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
        const encontrado = Array.from(botones).find((elemento) => elemento.textContent?.includes(texto));
        if (!encontrado)
            throw new Error(`No se encontró el botón ${texto}.`);
        return encontrado as HTMLButtonElement;
    }

    function confirmarEliminacion(): void {
        const confirmacion = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
            'dialog[open] .ventana__pie .boton--peligro',
        );
        if (!confirmacion) throw new Error('No se encontró el botón de confirmación.');
        confirmacion.click();
        fixture.detectChanges();
    }

    it('carga la sede, presenta horarios y permite crear una franja con pausa', () => {
        expect(api.horarios).toHaveBeenCalledWith('s-1');
        expect(api.feriados).toHaveBeenCalled();
        expect(fixture.nativeElement.textContent).toContain('Lunes · 08:00–17:00');
        expect(fixture.nativeElement.textContent).toContain('Navidad');

        boton('Nuevo horario').click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open][aria-modal="true"]')).not.toBeNull();
        const componente = fixture.componentInstance as unknown as { guardarHorario(): void };
        componente.guardarHorario();
        fixture.detectChanges();
        expect(api.guardarHorario).toHaveBeenCalledWith('s-1', expect.objectContaining({ dia_semana: 1, descansos: [] }), undefined);
    });

    it('oculta cambios de feriados globales si el rol solo alcanza una sede', () => {
        ambitoCompleto = false;
        fixture.detectChanges();
        const opciones = Array.from(fixture.nativeElement.querySelectorAll('option')) as HTMLOptionElement[];
        expect(opciones.some((opcion) => opcion.value === 'clinica')).toBe(false);
        const botones = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
        expect(Array.from(botones).filter((item) => item.textContent?.includes('Editar')).length).toBe(1);
        expect(fixture.nativeElement.textContent).toContain('Toda la clínica · 2026-12-25');
    });

    it('permite editar y eliminar una franja y un feriado', () => {
        boton('Editar').click();
        fixture.detectChanges();
        boton('Guardar cambios').click();
        fixture.detectChanges();
        expect(api.guardarHorario).toHaveBeenCalledWith('s-1', expect.objectContaining({ descansos: [expect.objectContaining({ motivo: 'Almuerzo' })] }), 'h-1');

        const filas = fixture.nativeElement.querySelectorAll('.fila') as NodeListOf<HTMLElement>;
        const filaHorario = Array.from(filas).find((fila) => fila.textContent?.includes('Lunes'));
        const eliminarHorario = filaHorario?.querySelector<HTMLButtonElement>('button.peligro');
        if (!eliminarHorario) throw new Error('No se encontró la acción para eliminar el horario.');
        eliminarHorario.click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open]')?.textContent).toContain('horario del Lunes');
        confirmarEliminacion();

        const filasActualizadas = fixture.nativeElement.querySelectorAll('.fila') as NodeListOf<HTMLElement>;
        const filaFeriado = Array.from(filasActualizadas).find((fila) => fila.textContent?.includes('Navidad'));
        const eliminarFeriado = filaFeriado?.querySelector<HTMLButtonElement>('button.peligro');
        if (!eliminarFeriado) throw new Error('No se encontró la acción para eliminar el cierre.');
        eliminarFeriado.click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('dialog[open]')?.textContent).toContain('cierre «Navidad»');
        confirmarEliminacion();
        expect(api.eliminarHorario).toHaveBeenCalledWith('h-1');
        expect(api.eliminarFeriado).toHaveBeenCalledWith('f-1');
    });

    it('mantiene la lista intacta si se cancela la confirmación de borrado', () => {
        boton('Eliminar').click();
        fixture.detectChanges();
        boton('Cancelar').click();
        fixture.detectChanges();
        expect(api.eliminarHorario).not.toHaveBeenCalled();
        expect(fixture.nativeElement.querySelector('dialog[open]')).toBeNull();
    });

    it('guarda un feriado anual después de capturar el nombre', () => {
        const componente = fixture.componentInstance as unknown as {
            feriado: {
                nombre: string;
                recurrente_anual: boolean;
            };
            guardarFeriado(): void;
        };
        componente.feriado.nombre = 'Feriado local';
        componente.feriado.recurrente_anual = true;
        componente.guardarFeriado();
        fixture.detectChanges();
        expect(api.guardarFeriado).toHaveBeenCalledWith(expect.objectContaining({ sede_id: 's-1', nombre: 'Feriado local', recurrente_anual: true, hora_inicio: null }), undefined);
    });
});
