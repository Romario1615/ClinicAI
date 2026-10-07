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

    it('carga la sede, presenta horarios y permite crear una franja con pausa', () => {
        expect(api.horarios).toHaveBeenCalledWith('s-1');
        expect(api.feriados).toHaveBeenCalled();
        expect(fixture.nativeElement.textContent).toContain('Lunes · 08:00–17:00');
        expect(fixture.nativeElement.textContent).toContain('Navidad');

        boton('Agregar horario').click();
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
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        boton('Editar').click();
        fixture.detectChanges();
        boton('Guardar cambios').click();
        fixture.detectChanges();
        expect(api.guardarHorario).toHaveBeenCalledWith('s-1', expect.objectContaining({ descansos: [expect.objectContaining({ motivo: 'Almuerzo' })] }), 'h-1');

        const botones = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;
        const eliminar = Array.from(botones).filter((elemento) => elemento.textContent?.includes('Eliminar'));
        eliminar[0].click();
        eliminar[1].click();
        fixture.detectChanges();
        expect(api.eliminarHorario).toHaveBeenCalledWith('h-1');
        expect(api.eliminarFeriado).toHaveBeenCalledWith('f-1');
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
