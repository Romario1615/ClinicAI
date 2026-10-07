/**
 * Acciones del paciente en la clínica: solo aparecen cuando tocan y con el
 * permiso; pedir más tiempo distingue aplicada de pendiente; derivar lista
 * por especialidad y crea la atención en destino.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { HttpTestingController } from '@angular/common/http/testing';

import { AccionesRecorridoComponent } from './acciones-recorrido.component';
import { BASE, PROVEEDORES_PRUEBA, iniciarSesionCon } from '../../nucleo/pruebas/sesion-sintetica';
import type { Cita } from '../../nucleo/modelos/dominio';

function cita(extra: Partial<Cita> = {}): Cita {
    return {
        id: 'c1',
        paciente_id: 'p1',
        profesional_id: 'pr1',
        servicio_id: 's1',
        sede_id: 'se1',
        consultorio_id: null,
        inicio: '2026-10-06T14:00:00Z',
        fin: '2026-10-06T14:30:00Z',
        duracion_minutos: 30,
        minutos_preparacion: 0,
        estado: 'CONFIRMED',
        origen: 'PANEL',
        expira_en: null,
        confirmada_en: null,
        llegada_en: '2026-10-06T13:55:00Z',
        atencion_iniciada_en: '2026-10-06T14:00:00Z',
        completada_en: null,
        cancelada_en: null,
        motivo_cancelacion: null,
        ...extra,
    } as Cita;
}

describe('AccionesRecorridoComponent', () => {
    let fixture: ComponentFixture<AccionesRecorridoComponent>;
    let http: HttpTestingController;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let c: any;
    let cambios: string[];

    function montar(permisos: readonly string[], datos: Partial<Cita> = {}): void {
        iniciarSesionCon(permisos);
        fixture = TestBed.createComponent(AccionesRecorridoComponent);
        fixture.componentRef.setInput('cita', cita(datos));
        fixture.componentRef.setInput('consultorios', [{ id: 'k1', nombre: 'Sala 1', sede_id: 'se1' }]);
        c = fixture.componentInstance;
        cambios = [];
        c.cambio.subscribe((motivo: string) => cambios.push(motivo));
        fixture.detectChanges();
    }

    beforeEach(() => {
        TestBed.configureTestingModule({ imports: [AccionesRecorridoComponent], providers: PROVEEDORES_PRUEBA });
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('sin llegada no ofrece nada', () => {
        montar(['cita.registrar_llegada', 'cita.iniciar_atencion'], { llegada_en: null, atencion_iniciada_en: null });
        expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('');
    });

    it('pasa a consultorio y registra la salida', () => {
        montar(['cita.registrar_llegada']);
        const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
        expect(texto).toContain('Pasar a consultorio');
        expect(texto).not.toContain('Pedir más tiempo');
        expect(texto).not.toContain('Derivar');

        c.consultorioId = 'k1';
        c.pasarAConsultorio();
        const peticion = http.expectOne({ method: 'POST', url: `${BASE}/agenda/citas/c1/consultorio` });
        expect(peticion.request.body).toEqual({ consultorio_id: 'k1' });
        peticion.flush(cita());
        expect(c.aviso()).toBe('Paciente en Sala 1.');

        c.registrarSalida();
        http
            .expectOne(`${BASE}/agenda/citas/c1/salida`)
            .flush({ codigo: 'X', mensaje: 'La salida ya está registrada.' }, { status: 409, statusText: 'C' });
        expect(c.error()).toBe('La salida ya está registrada.');
        expect(cambios).toEqual(['Paciente en Sala 1.']);
    });

    it('pedir más tiempo: aplicada o pendiente para recepción', () => {
        montar(['cita.iniciar_atencion']);
        c.minutos = 20;
        c.pedirTiempo();
        http
            .expectOne(`${BASE}/agenda/citas/c1/prolongacion`)
            .flush({ cita_id: 'c1', aplicada: true, minutos: 20, fin: '2026-10-06T14:50:00Z', conflictos: [] });
        expect(c.aviso()).toContain('Atención alargada 20 min');

        c.pedirTiempo();
        http.expectOne(`${BASE}/agenda/citas/c1/prolongacion`).flush({
            cita_id: 'c1',
            aplicada: false,
            minutos: 20,
            fin: '2026-10-06T14:30:00Z',
            conflictos: [{ cita_id: 'c2', paciente: 'Ana Sintética', inicio: '2026-10-06T14:30:00Z', llego: true, alternativas: [] }],
        });
        fixture.detectChanges();
        expect(c.aviso()).toContain('recepción decidirá');
        expect((fixture.nativeElement as HTMLElement).textContent).toContain('Ana Sintética');
        expect(cambios.length).toBe(2);
        expect(cambios[1]).toContain('Choca con Ana Sintética');
    });

    it('deriva a otra área agrupando por especialidad', () => {
        montar(['historia_clinica.escribir', 'cita.crear']);
        c.abrirDerivacion();
        http.expectOne(`${BASE}/agenda/citas/c1/derivacion/opciones`).flush([
            { profesional_id: 'd1', profesional: 'Dra. Piel', servicio_id: 's9', servicio: 'Consulta', especialidad: 'Dermatología', libre_ahora: true, proximo_turno: '2026-10-06T14:05:00Z' },
            { profesional_id: 'd2', profesional: 'Dr. Niño', servicio_id: 's8', servicio: 'Control', especialidad: 'Pediatría', libre_ahora: false, proximo_turno: '2026-10-06T16:00:00Z' },
        ]);
        fixture.detectChanges();
        expect(c.grupos().map((g: {
            especialidad: string;
        }) => g.especialidad)).toEqual(['Dermatología', 'Pediatría']);

        c.derivar(c.opciones()[1]);
        const peticion = http.expectOne({ method: 'POST', url: `${BASE}/agenda/citas/c1/derivacion` });
        expect(peticion.request.body).toEqual({ profesional_id: 'd2', servicio_id: 's8', inicio: '2026-10-06T16:00:00Z' });
        peticion.flush(cita({ id: 'c3' }));
        expect(c.derivando()).toBe(false);
        expect(c.derivadaA()).toBe(true);
        expect(c.aviso()).toContain('Dr. Niño');
    });

    it('muestra el error al cargar opciones de derivación', () => {
        montar(['historia_clinica.escribir', 'cita.crear']);
        c.abrirDerivacion();
        http
            .expectOne(`${BASE}/agenda/citas/c1/derivacion/opciones`)
            .flush({ codigo: 'X', mensaje: 'Sin acceso' }, { status: 403, statusText: 'F' });
        expect(c.error()).toBe('Sin acceso');
        expect(c.cargandoOpciones()).toBe(false);
    });
});
