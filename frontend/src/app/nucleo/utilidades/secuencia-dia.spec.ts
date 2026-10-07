/**
 * Pruebas de la secuencia del día.
 *
 * Lo que sostienen estas pruebas es la afirmación de la pantalla: que un hueco
 * de hora y media se ve como **un** hueco de hora y media, y no como seis
 * botones. Si el agrupamiento se rompe, la agenda vuelve a ser un muro.
 */
import type { Cita, EstadoCita, TurnoDisponible } from '../modelos/dominio';
import { cargaPorProfesional, construirSecuencia, duracionLegible, minutosEntre, } from './secuencia-dia';

function cita(inicio: string, estado: EstadoCita = 'CONFIRMED', extra: Partial<Cita> = {}): Cita {
    return {
        id: `cita-${inicio}`,
        paciente_id: 'p1',
        profesional_id: 'prof1',
        servicio_id: 's1',
        sede_id: 'sede1',
        consultorio_id: null,
        inicio,
        fin: inicio,
        duracion_minutos: 30,
        minutos_preparacion: 0,
        estado,
        origen: 'PANEL',
        expira_en: null,
        confirmada_en: null,
        llegada_en: null,
        atencion_iniciada_en: null,
        completada_en: null,
        cancelada_en: null,
        motivo_cancelacion: null,
        ...extra,
    };
}

function turno(inicio: string, finConsulta: string): TurnoDisponible {
    return {
        inicio,
        fin_consulta: finConsulta,
        fin_bloque: finConsulta,
        duracion_minutos: 30,
        minutos_preparacion: 0,
    };
}

describe('construirSecuencia', () => {
    it('ordena citas y huecos por hora en una sola lista', () => {
        const filas = construirSecuencia([cita('2026-09-16T15:00:00Z'), cita('2026-09-16T13:00:00Z')], [turno('2026-09-16T14:00:00Z', '2026-09-16T14:30:00Z')]);

        expect(filas.map((f) => f.tipo)).toEqual(['cita', 'hueco', 'cita']);
        expect(filas[0].inicio).toBe('2026-09-16T13:00:00Z');
    });

    it('agrupa los turnos solapados de un mismo tramo en un solo hueco', () => {
        // Granularidad de 15 min con servicio de 30: una hora libre son cinco
        // arranques posibles solapados. La pantalla debe decir «1 h», no ofrecer
        // cinco filas.
        const turnos = [
            turno('2026-09-16T13:00:00Z', '2026-09-16T13:30:00Z'),
            turno('2026-09-16T13:15:00Z', '2026-09-16T13:45:00Z'),
            turno('2026-09-16T13:30:00Z', '2026-09-16T14:00:00Z'),
        ];

        const filas = construirSecuencia([], turnos);

        expect(filas.length).toBe(1);
        const hueco = filas[0];
        expect(hueco.tipo).toBe('hueco');
        if (hueco.tipo === 'hueco') {
            expect(hueco.inicio).toBe('2026-09-16T13:00:00Z');
            expect(hueco.fin).toBe('2026-09-16T14:00:00Z');
            // Los turnos concretos se conservan: la reserva necesita uno, no el grupo.
            expect(hueco.turnos.length).toBe(3);
        }
    });

    it('parte el hueco cuando hay un corte real entre turnos', () => {
        const turnos = [
            turno('2026-09-16T13:00:00Z', '2026-09-16T13:30:00Z'),
            // Hora y media más tarde: un descanso o una cita en medio.
            turno('2026-09-16T15:00:00Z', '2026-09-16T15:30:00Z'),
        ];

        const filas = construirSecuencia([], turnos);

        expect(filas.length).toBe(2);
    });

    it('compara instantes y no cadenas', () => {
        // El mismo instante escrito de dos formas. Ordenado como texto, 'Z' > '+'
        // y la secuencia saldría al revés.
        const filas = construirSecuencia([cita('2026-09-16T14:00:00Z')], [turno('2026-09-16T13:00:00+00:00', '2026-09-16T13:30:00+00:00')]);

        expect(filas[0].tipo).toBe('hueco');
    });

    it('oculta las canceladas porque su turno ya aparece como libre', () => {
        // Dos filas para las 13:00 —una «cancelada» y una «libre»— se leen como un
        // fallo de la pantalla, no como información.
        const filas = construirSecuencia([cita('2026-09-16T13:00:00Z', 'CANCELLED')], [turno('2026-09-16T13:00:00Z', '2026-09-16T13:30:00Z')]);

        expect(filas.length).toBe(1);
        expect(filas[0].tipo).toBe('hueco');
    });

    it('muestra las canceladas cuando se piden expresamente', () => {
        const filas = construirSecuencia([cita('2026-09-16T13:00:00Z', 'CANCELLED')], [turno('2026-09-16T13:00:00Z', '2026-09-16T13:30:00Z')], true);

        expect(filas.length).toBe(2);
        // Con la misma hora, lo comprometido va antes que lo disponible.
        expect(filas[0].tipo).toBe('cita');
    });

    it('conserva las inasistencias: la hora pasó y el turno no se recupera', () => {
        const filas = construirSecuencia([cita('2026-09-16T13:00:00Z', 'NO_SHOW')], []);

        expect(filas.length).toBe(1);
        expect(filas[0].tipo).toBe('cita');
    });
});

describe('duracionLegible', () => {
    it('escribe los minutos sueltos tal cual', () => {
        expect(duracionLegible(45)).toBe('45 min');
    });

    it('parte en horas y minutos en lugar de obligar a dividir', () => {
        expect(duracionLegible(90)).toBe('1 h 30');
    });

    it('omite los minutos cuando son cero', () => {
        expect(duracionLegible(120)).toBe('2 h');
    });

    it('rellena a dos cifras para que la columna quede alineada', () => {
        expect(duracionLegible(65)).toBe('1 h 05');
    });
});

describe('minutosEntre', () => {
    it('mide en minutos entre dos instantes', () => {
        expect(minutosEntre('2026-09-16T13:00:00Z', '2026-09-16T14:30:00Z')).toBe(90);
    });
});

describe('cargaPorProfesional', () => {
    it('suma minutos de consulta y no número de citas', () => {
        const carga = cargaPorProfesional([
            cita('2026-09-16T13:00:00Z', 'CONFIRMED', { profesional_id: 'a', duracion_minutos: 45 }),
            cita('2026-09-16T14:00:00Z', 'CONFIRMED', { profesional_id: 'a', duracion_minutos: 15 }),
            cita('2026-09-16T15:00:00Z', 'CONFIRMED', { profesional_id: 'b', duracion_minutos: 30 }),
        ]);

        expect(carga.get('a')).toBe(60);
        expect(carga.get('b')).toBe(30);
    });

    it('no cuenta las canceladas: no ocupan la agenda', () => {
        const carga = cargaPorProfesional([
            cita('2026-09-16T13:00:00Z', 'CANCELLED', { profesional_id: 'a', duracion_minutos: 45 }),
        ]);

        expect(carga.get('a')).toBeUndefined();
    });

    it('cuenta las inasistencias: el hueco se ocupó aunque el paciente no viniera', () => {
        const carga = cargaPorProfesional([
            cita('2026-09-16T13:00:00Z', 'NO_SHOW', { profesional_id: 'a', duracion_minutos: 30 }),
        ]);

        expect(carga.get('a')).toBe(30);
    });
});
