import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { SesionService } from '../../nucleo/servicios/sesion.service';
import { AnamnesisCapturaComponent } from './anamnesis-captura.component';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;
const PREGUNTAS = [
    { id: 'motivo', etiqueta: 'Motivo de consulta', tipo: 'texto', obligatoria: true, ayuda: null, opciones: [] },
    { id: 'medicacion', etiqueta: '¿Tiene medicación activa?', tipo: 'booleano', obligatoria: true, ayuda: null, opciones: [] },
    { id: 'habitos', etiqueta: 'Hábitos', tipo: 'seleccion_multiple', obligatoria: false, ayuda: null, opciones: ['Tabaco', 'Ninguno'] },
];

describe('AnamnesisCapturaComponent', () => {
    let fixture: ComponentFixture<AnamnesisCapturaComponent>;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [AnamnesisCapturaComponent],
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
                {
                    provide: SesionService,
                    useValue: {
                        tienePermiso: (codigo: string) => codigo === 'historia_clinica.escribir',
                        identidad: () => ({ profesional_id: 'profesional-1' }),
                    },
                },
            ],
        });
        fixture = TestBed.createComponent(AnamnesisCapturaComponent);
        fixture.componentRef.setInput('pacienteId', 'paciente-1');
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('captura respuestas tipadas y muestra la versión guardada en el historial', () => {
        fixture.detectChanges();
        http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/plantillas-activas`).flush([
            { id: 'plantilla-1', nombre: 'Primera consulta', version: 2, nivel_sensibilidad: 'N2', preguntas: PREGUNTAS },
        ]);
        http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`).flush([]);
        fixture.detectChanges();
        (fixture.nativeElement as HTMLElement)
            .querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!
            .click();
        fixture.detectChanges();
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Primera consulta · v2');

        const componente = fixture.componentInstance as unknown as {
            valores: Record<string, unknown>;
            alternarOpcion(id: string, opcion: string, marcada: boolean): void;
            establecerBooleano(id: string, valor: boolean): void;
            opcionElegida(id: string, opcion: string): boolean;
            valorLegible(valor: unknown): string;
            guardar(): void;
        };
        componente.valores = { motivo: 'Control preventivo', medicacion: false };
        componente.establecerBooleano('medicacion', true);
        expect(componente.valores['medicacion']).toBe(true);
        componente.establecerBooleano('medicacion', false);
        componente.alternarOpcion('habitos', 'Ninguno', true);
        expect(componente.opcionElegida('habitos', 'Ninguno')).toBe(true);
        expect(componente.opcionElegida('motivo', 'Ninguno')).toBe(false);
        expect(componente.valorLegible(true)).toBe('Sí');
        expect(componente.valorLegible(false)).toBe('No');
        expect(componente.valorLegible(['A', 'B'])).toBe('A, B');
        expect(componente.valorLegible('  ')).toBe('Sin respuesta');
        componente.guardar();

        const guardar = http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`);
        expect(guardar.request.method).toBe('POST');
        expect(guardar.request.body).toEqual({
            plantilla_id: 'plantilla-1',
            respuestas: { motivo: 'Control preventivo', medicacion: false, habitos: ['Ninguno'] },
        });
        guardar.flush({
            id: 'captura-1', plantilla_id: 'plantilla-1', plantilla: 'Primera consulta', version_plantilla: 2,
            nivel_sensibilidad: 'N2', preguntas: PREGUNTAS,
            respuestas: { motivo: 'Control preventivo', medicacion: false, habitos: ['Ninguno'] },
            registrada_en: '2026-04-15T14:00:00Z',
        });
        fixture.detectChanges();
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).toContain('Control preventivo');
        expect(texto).toContain('No');
        expect(texto).toContain('Ninguno');
        expect(texto).toContain('guardadas en la historia clínica');
    });

    it('abre la captura en una ventana Liquid Glass y descarta el borrador al cancelar', () => {
        fixture.detectChanges();
        http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/plantillas-activas`).flush([
            { id: 'plantilla-1', nombre: 'Primera consulta', version: 2, nivel_sensibilidad: 'N2', preguntas: PREGUNTAS },
        ]);
        http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`).flush([]);
        fixture.detectChanges();

        const elemento = fixture.nativeElement as HTMLElement;
        expect(elemento.querySelector('dialog')).toBeNull();
        elemento.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!.click();
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open]')?.textContent).toContain('Registrar anamnesis');

        const componente = fixture.componentInstance as unknown as {
            valores: Record<string, unknown>;
            cerrarEditor(): void;
        };
        componente.valores = { motivo: 'Texto que debe descartarse' };
        componente.cerrarEditor();
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open]')).toBeNull();
        expect(componente.valores).toEqual({});
        expect(http.match(`${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`).length).toBe(0);
    });
});
