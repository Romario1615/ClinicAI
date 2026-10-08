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

function botonConTexto(raiz: HTMLElement, texto: string): HTMLButtonElement {
    const boton = Array.from(raiz.querySelectorAll<HTMLButtonElement>('button')).find(
        (elemento) => elemento.textContent?.trim() === texto,
    );
    if (!boton) throw new Error(`No existe el botón «${texto}».`);
    return boton;
}

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
            hayCambios(): boolean;
        };
        expect(componente.hayCambios()).toBe(false);
        componente.valores = { motivo: 'Texto que debe descartarse' };
        fixture.detectChanges();
        expect(componente.hayCambios()).toBe(true);

        // Cancelar no descarta a ciegas: pregunta dentro de la ventana.
        botonConTexto(elemento, 'Cancelar').click();
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open] [role="alertdialog"]')?.textContent).toContain('Hay cambios sin guardar');
        expect(componente.valores).toEqual({ motivo: 'Texto que debe descartarse' });

        botonConTexto(elemento, 'Descartar cambios').click();
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open]')).toBeNull();
        expect(componente.valores).toEqual({});
        expect(http.match(`${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`).length).toBe(0);
    });

    it('el error del servidor se ve dentro de la ventana, no detrás del velo', () => {
        fixture.detectChanges();
        http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/plantillas-activas`).flush([
            { id: 'plantilla-1', nombre: 'Primera consulta', version: 2, nivel_sensibilidad: 'N2', preguntas: PREGUNTAS },
        ]);
        http.expectOne(`${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`).flush([]);
        fixture.detectChanges();
        const elemento = fixture.nativeElement as HTMLElement;
        elemento.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!.click();
        fixture.detectChanges();

        const componente = fixture.componentInstance as unknown as { valores: Record<string, unknown>; guardar(): void };
        componente.valores = { medicacion: false };
        componente.guardar();
        fixture.detectChanges();
        // Mientras guarda, la X está desactivada y Escape no cierra.
        expect(elemento.querySelector<HTMLButtonElement>('dialog[open] .ventana__cerrar')!.disabled).toBe(true);
        elemento
            .querySelector('dialog[open]')!
            .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
        fixture.detectChanges();
        expect(elemento.querySelector('dialog[open]')).not.toBeNull();

        http
            .expectOne((p) => p.method === 'POST' && p.url === `${BASE}/historia/pacientes/paciente-1/anamnesis/respuestas`)
            .flush(
                { codigo: 'DATOS_INVALIDOS', mensaje: 'La pregunta «Motivo de consulta» es obligatoria.' },
                { status: 422, statusText: 'Unprocessable Entity' },
            );
        fixture.detectChanges();

        const alertas = Array.from(elemento.querySelectorAll('[role="alert"]'));
        expect(alertas).toHaveLength(1);
        expect(alertas[0].closest('dialog[open]')).not.toBeNull();
        expect(alertas[0].textContent).toContain('es obligatoria');
        // Lo escrito sigue ahí para corregirlo.
        expect(componente.valores).toEqual({ medicacion: false });
    });
});
