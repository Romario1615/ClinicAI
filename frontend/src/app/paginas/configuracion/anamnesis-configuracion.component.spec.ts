import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CONFIGURACION, CONFIGURACION_POR_DEFECTO } from '../../nucleo/servicios/configuracion';
import { AnamnesisConfiguracionComponent } from './anamnesis-configuracion.component';

const BASE = CONFIGURACION_POR_DEFECTO.urlApi;

describe('AnamnesisConfiguracionComponent', () => {
    let fixture: ComponentFixture<AnamnesisConfiguracionComponent>;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            imports: [AnamnesisConfiguracionComponent],
            providers: [
                provideHttpClient(withXhr()),
                provideHttpClientTesting(),
                { provide: CONFIGURACION, useValue: CONFIGURACION_POR_DEFECTO },
            ],
        });
        fixture = TestBed.createComponent(AnamnesisConfiguracionComponent);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('crea un borrador en la clínica y publica desde la pantalla de configuración', () => {
        fixture.detectChanges();
        http.expectOne(`${BASE}/historia/anamnesis/plantillas`).flush([]);
        fixture.detectChanges();

        const componente = fixture.componentInstance as unknown as {
            nuevoBorrador(): void;
            nombre: string;
            preguntas: {
                id: string;
                etiqueta: string;
                tipo: string;
                obligatoria: boolean;
                ayuda: null;
                opcionesTexto: string;
            }[];
            guardar(): void;
            publicar(): void;
        };
        componente.nuevoBorrador();
        componente.nombre = 'Primera consulta';
        componente.preguntas[0]!.etiqueta = 'Motivo de consulta';
        componente.guardar();

        const crear = http.expectOne(`${BASE}/historia/anamnesis/plantillas`);
        expect(crear.request.method).toBe('POST');
        expect(crear.request.body.nombre).toBe('Primera consulta');
        expect(crear.request.body.preguntas[0].id).toBe('pregunta_1');
        expect(crear.request.headers.has('Idempotency-Key')).toBe(true);
        crear.flush({
            id: 'plantilla-1', nombre: 'Primera consulta', version: 1, estado: 'BORRADOR',
            nivel_sensibilidad: 'N2', preguntas: [{ id: 'pregunta_1', etiqueta: 'Motivo de consulta', tipo: 'texto', obligatoria: false, ayuda: null, opciones: [] }],
            creada_en: '2026-04-15T14:00:00Z', publicada_en: null,
        });
        http.expectOne(`${BASE}/historia/anamnesis/plantillas`).flush([]);
        componente.publicar();

        const publicar = http.expectOne(`${BASE}/historia/anamnesis/plantillas/plantilla-1/publicacion`);
        expect(publicar.request.method).toBe('POST');
        publicar.flush({
            id: 'plantilla-1', nombre: 'Primera consulta', version: 1, estado: 'PUBLICADA',
            nivel_sensibilidad: 'N2', preguntas: [], creada_en: '2026-04-15T14:00:00Z', publicada_en: '2026-04-15T14:00:00Z',
        });
        http.expectOne(`${BASE}/historia/anamnesis/plantillas`).flush([]);
        fixture.detectChanges();
        expect(fixture.nativeElement.textContent).toContain('está publicada');
    });

    it('no permite guardar preguntas de selección sin opciones', () => {
        fixture.detectChanges();
        http.expectOne(`${BASE}/historia/anamnesis/plantillas`).flush([]);
        const componente = fixture.componentInstance as unknown as {
            nuevoBorrador(): void;
            nombre: string;
            preguntas: {
                id: string;
                etiqueta: string;
                tipo: string;
                opcionesTexto: string;
            }[];
            guardar(): void;
            error: () => string;
        };
        componente.nuevoBorrador();
        componente.nombre = 'Primera consulta';
        componente.preguntas[0]!.etiqueta = 'Motivo de consulta';
        componente.preguntas[0]!.tipo = 'seleccion';
        componente.guardar();
        expect(componente.error()).toContain('Agrega al menos una opción');
        http.expectNone(`${BASE}/historia/anamnesis/plantillas`);
    });

    it('etiqueta estados y permite administrar preguntas del borrador', () => {
        fixture.detectChanges();
        http.expectOne(`${BASE}/historia/anamnesis/plantillas`).flush([]);
        const componente = fixture.componentInstance as unknown as {
            estado(estado: 'BORRADOR' | 'PUBLICADA' | 'RETIRADA'): string;
            nuevoBorrador(): void;
            agregarPregunta(): void;
            quitarPregunta(indice: number): void;
            cancelarEdicion(): void;
            preguntas: unknown[];
            editando(): boolean;
        };
        expect(componente.estado('PUBLICADA')).toBe('Publicada');
        expect(componente.estado('RETIRADA')).toBe('Retirada');
        expect(componente.estado('BORRADOR')).toBe('Borrador');

        componente.nuevoBorrador();
        componente.agregarPregunta();
        expect(componente.preguntas.length).toBe(2);
        componente.quitarPregunta(1);
        expect(componente.preguntas.length).toBe(1);
        componente.cancelarEdicion();
        expect(componente.editando()).toBe(false);
    });
});
