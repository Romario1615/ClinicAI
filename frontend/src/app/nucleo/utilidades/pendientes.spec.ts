/**
 * Pruebas de la cola de trabajo.
 *
 * Lo que sostienen: que las tres cosas que se rompen solas si nadie las toca
 * —un bloqueo que caduca, una oferta que nadie comunicó, una cita sin
 * confirmar— aparecen, con su plazo, y en ese orden.
 */
import type { Cita, EstadoCita } from '../modelos/dominio';
import { derivarPendientes, type OfertaSinAvisar } from './pendientes';

const AHORA = new Date('2026-09-16T13:00:00Z');

function cita(estado: EstadoCita, extra: Partial<Cita> = {}): Cita {
  return {
    id: `cita-${Math.random().toString(16).slice(2)}`,
    paciente_id: 'p1',
    profesional_id: 'prof1',
    servicio_id: 's1',
    sede_id: 'sede1',
    consultorio_id: null,
    inicio: '2026-09-16T15:00:00Z',
    fin: '2026-09-16T15:30:00Z',
    duracion_minutos: 30,
    minutos_preparacion: 0,
    estado,
    origen: 'PANEL',
    expira_en: null,
    confirmada_en: null,
    cancelada_en: null,
    motivo_cancelacion: null,
    ...extra,
  };
}

function derivar(citas: readonly Cita[], ofertas: readonly OfertaSinAvisar[] = []) {
  return derivarPendientes({
    citas,
    ofertasSinAvisar: ofertas,
    ahora: AHORA,
    nombrePaciente: (id) => (id === 'p1' ? 'Reyna Jurado' : `Paciente ${id}`),
  });
}

describe('derivarPendientes', () => {
  it('no inventa trabajo cuando no hay nada pendiente', () => {
    expect(derivar([cita('CONFIRMED'), cita('COMPLETED')])).toEqual([]);
  });

  it('avisa del turno bloqueado con los minutos que quedan', () => {
    const tareas = derivar([cita('HELD', { expira_en: '2026-09-16T13:06:00Z' })]);

    expect(tareas.length).toBe(1);
    expect(tareas[0].clase).toBe('caduca');
    expect(tareas[0].plazo).toBe('en 6 min');
    // Con uno solo se nombra a la persona: es lo que permite actuar.
    expect(tareas[0].titulo).toContain('Reyna Jurado');
    expect(tareas[0].urgente).toBeTrue();
  });

  it('dice «vencido» en lugar de un plazo negativo', () => {
    // «en -3 min» se lee mal y de pasada se confunde con tiempo restante.
    const tareas = derivar([cita('HELD', { expira_en: '2026-09-16T12:57:00Z' })]);

    expect(tareas[0].plazo).toBe('vencido');
  });

  it('con varios bloqueos cuenta en lugar de enumerar, y usa el que vence antes', () => {
    const tareas = derivar([
      cita('HELD', { expira_en: '2026-09-16T14:00:00Z' }),
      cita('HELD', { expira_en: '2026-09-16T13:10:00Z' }),
    ]);

    expect(tareas[0].titulo).toContain('2 turnos bloqueados');
    expect(tareas[0].plazo).toBe('en 10 min');
  });

  it('ignora un HELD sin fecha de caducidad', () => {
    // Sin `expira_en` no hay plazo que comunicar, y anunciar una cuenta atrás
    // inexistente es peor que no decir nada.
    expect(derivar([cita('HELD')])).toEqual([]);
  });

  it('saca la oferta que nadie ha comunicado', () => {
    const tareas = derivar([], [{ id: 'e1', oferta_expira_en: '2026-09-16T13:30:00Z' }]);

    expect(tareas.length).toBe(1);
    expect(tareas[0].clase).toBe('llamar');
    expect(tareas[0].plazo).toBe('en 30 min');
    expect(tareas[0].entradas).toEqual(['e1']);
    expect(tareas[0].detalle).toContain('consentimiento');
  });

  it('una oferta sin fecha no finge tener plazo', () => {
    const tareas = derivar([], [{ id: 'e1', oferta_expira_en: null }]);

    expect(tareas[0].plazo).toBe('sin plazo');
  });

  it('saca las citas sin confirmar, pero sin marcarlas de urgentes', () => {
    // Si todo se pinta en ámbar, nada destaca. Aquí no corre ningún plazo.
    const tareas = derivar([cita('PENDING'), cita('PENDING', { paciente_id: 'p2' })]);

    expect(tareas.length).toBe(1);
    expect(tareas[0].clase).toBe('confirmar');
    expect(tareas[0].urgente).toBeFalse();
    expect(tareas[0].plazo).toBe('2 citas');
    expect(tareas[0].citas.length).toBe(2);
  });

  it('ordena por urgencia: primero lo que tiene cuenta atrás', () => {
    const tareas = derivar(
      [cita('PENDING'), cita('HELD', { expira_en: '2026-09-16T13:05:00Z' })],
      [{ id: 'e1', oferta_expira_en: '2026-09-16T13:40:00Z' }],
    );

    expect(tareas.map((t) => t.clase)).toEqual(['caduca', 'llamar', 'confirmar']);
  });

  it('el reloj es un parámetro y no el del sistema', () => {
    // La misma cita con dos relojes distintos da dos plazos distintos. Sin
    // esto, una prueba sobre «caduca en 6 minutos» pasaría hoy y fallaría en
    // la siguiente ejecución.
    const held = [cita('HELD', { expira_en: '2026-09-16T13:06:00Z' })];
    const base = { citas: held, ofertasSinAvisar: [], nombrePaciente: () => 'X' };

    expect(derivarPendientes({ ...base, ahora: new Date('2026-09-16T13:00:00Z') })[0].plazo).toBe(
      'en 6 min',
    );
    expect(derivarPendientes({ ...base, ahora: new Date('2026-09-16T13:05:00Z') })[0].plazo).toBe(
      'en 1 min',
    );
  });
});
