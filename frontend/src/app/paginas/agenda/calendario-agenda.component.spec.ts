/**
 * Calendario de la agenda: columnas por profesional en el día, siete días en
 * la semana, cuadrícula de seis semanas en el mes, colores por estado y
 * carriles para citas que se solapan.
 */
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import {
  CalendarioAgendaComponent,
  estadoVisual,
  lunesDe,
  partesLocales,
  rangoVista,
} from './calendario-agenda.component';
import type { Cita } from '../../nucleo/modelos/dominio';
import { PROVEEDORES_PRUEBA } from '../../nucleo/pruebas/sesion-sintetica';

const ZONA = 'America/Guayaquil';

function cita(id: string, inicio: string, fin: string, extra: Partial<Cita> = {}): Cita {
  return {
    id,
    paciente_id: `pac-${id}`,
    profesional_id: 'prof-1',
    servicio_id: 'serv-1',
    sede_id: 'sede-1',
    consultorio_id: null,
    inicio,
    fin,
    duracion_minutos: 30,
    minutos_preparacion: 0,
    estado: 'CONFIRMED',
    origen: 'RECEPCION',
    expira_en: null,
    confirmada_en: null,
    llegada_en: null,
    atencion_iniciada_en: null,
    completada_en: null,
    cancelada_en: null,
    motivo_cancelacion: null,
    ...extra,
  } as Cita;
}

describe('utilidades del calendario', () => {
  it('calcula fecha y minutos en la zona de la sede', () => {
    // 14:00 UTC son las 09:00 en Guayaquil (UTC-5).
    expect(partesLocales('2026-10-05T14:00:00Z', ZONA)).toEqual({ fecha: '2026-10-05', minutos: 540 });
    expect(partesLocales('2026-10-06T03:00:00Z', ZONA).fecha).toBe('2026-10-05');
  });

  it('calcula lunes y rangos de cada vista', () => {
    expect(lunesDe('2026-10-08')).toBe('2026-10-05');
    expect(lunesDe('2026-10-11')).toBe('2026-10-05');
    expect(rangoVista('dia', '2026-10-08')).toEqual({ desde: '2026-10-08', hasta: '2026-10-09' });
    expect(rangoVista('semana', '2026-10-08')).toEqual({ desde: '2026-10-05', hasta: '2026-10-12' });
    expect(rangoVista('mes', '2026-10-20')).toEqual({ desde: '2026-09-28', hasta: '2026-11-09' });
  });

  it('distingue sala de espera y atención', () => {
    expect(estadoVisual(cita('a', '', '', { llegada_en: 'x' }))).toBe('EN_SALA');
    expect(estadoVisual(cita('a', '', '', { llegada_en: 'x', atencion_iniciada_en: 'y' }))).toBe('EN_ATENCION');
    expect(estadoVisual(cita('a', '', '', { estado: 'NO_SHOW' }))).toBe('NO_SHOW');
  });
});

describe('CalendarioAgendaComponent', () => {
  let fixture: ComponentFixture<CalendarioAgendaComponent>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let c: any;

  function montar(entradas: Record<string, unknown>): void {
    TestBed.configureTestingModule({ imports: [CalendarioAgendaComponent], providers: PROVEEDORES_PRUEBA });
    fixture = TestBed.createComponent(CalendarioAgendaComponent);
    c = fixture.componentInstance;
    fixture.componentRef.setInput('fecha', '2026-10-05');
    fixture.componentRef.setInput('zona', ZONA);
    for (const [clave, valor] of Object.entries(entradas)) fixture.componentRef.setInput(clave, valor);
    fixture.detectChanges();
  }

  it('día: una columna por profesional, carriles para solapes y huecos clicables', () => {
    const citas = [
      cita('1', '2026-10-05T14:00:00Z', '2026-10-05T14:45:00Z'),
      cita('2', '2026-10-05T14:30:00Z', '2026-10-05T15:30:00Z', { estado: 'HELD' }),
      cita('3', '2026-10-05T16:00:00Z', '2026-10-05T16:30:00Z', { profesional_id: 'prof-2' }),
      cita('4', '2026-10-05T17:00:00Z', '2026-10-05T17:30:00Z', { estado: 'CANCELLED' }),
    ];
    montar({
      vista: 'dia',
      citas,
      profesionalId: 'prof-1',
      profesionales: [
        { id: 'prof-1', nombre: 'Ana', apellido: 'Uno' },
        { id: 'prof-2', nombre: 'Beto', apellido: 'Dos' },
      ],
      huecos: [{ tipo: 'hueco', inicio: '2026-10-05T19:00:00Z', fin: '2026-10-05T20:00:00Z', turnos: [{}, {}] }],
      puedeReservar: true,
      etiquetaPaciente: (id: string) => `Paciente ${id}`,
    });
    const columnas = c.columnas();
    expect(columnas.map((col: { titulo: string }) => col.titulo)).toEqual(['Ana Uno', 'Beto Dos']);
    const bloques = columnas[0].bloques;
    // Cancelada oculta; las dos que se solapan van en carriles distintos; el hueco aparece.
    expect(bloques.length).toBe(3);
    expect(bloques[0].ancho).toBe(50);
    expect(bloques[1].izquierda).toBe(50);
    expect(bloques[2].estado).toBe('LIBRE');

    let elegida = '';
    let hueco = '';
    c.citaElegida.subscribe((x: Cita) => (elegida = x.id));
    c.huecoElegido.subscribe((x: { inicio: string }) => (hueco = x.inicio));
    c.elegirBloque(bloques[0]);
    c.elegirBloque(bloques[2]);
    expect(elegida).toBe('1');
    expect(hueco).toBe('2026-10-05T19:00:00Z');

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('.bloque').length).toBe(4);
    expect(el.textContent).toContain('Paciente pac-1');
    expect(el.textContent).toContain('Libre para reservar');
  });

  it('semana: siete columnas del profesional elegido y clic en el día', () => {
    montar({
      vista: 'semana',
      profesionalId: 'prof-1',
      verCanceladas: true,
      citas: [
        cita('1', '2026-10-07T14:00:00Z', '2026-10-07T14:30:00Z', { estado: 'CANCELLED' }),
        cita('2', '2026-10-07T15:00:00Z', '2026-10-07T15:30:00Z', { profesional_id: 'otro' }),
        cita('3', '2026-10-06T02:00:00Z', '2026-10-06T03:30:00Z'),
      ],
    });
    const columnas = c.columnas();
    expect(columnas.length).toBe(7);
    expect(columnas[2].bloques.length).toBe(1);
    // Una cita de 21:00 a 22:30 amplía la franja hasta las 23:00.
    expect(c.horas().at(-1).texto).toBe('22:00');
    let dia = '';
    c.diaElegido.subscribe((x: string) => (dia = x));
    (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('.tiempo__dia')[3].click();
    expect(dia).toBe('2026-10-08');
  });

  it('mes: 42 días, máximo tres citas visibles por día', () => {
    const citas = Array.from({ length: 5 }, (_, i) =>
      cita(`m${i}`, `2026-10-14T1${i}:00:00Z`, `2026-10-14T1${i}:30:00Z`),
    );
    montar({ vista: 'mes', citas });
    const dias = c.diasMes();
    expect(dias.length).toBe(42);
    const dia14 = dias.find((d: { fecha: string }) => d.fecha === '2026-10-14');
    expect(dia14.citas.length).toBe(5);
    expect(dias[0].delMes).toBeFalse();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('+2 más');
  });

  it('dice que no hay citas', () => {
    montar({ vista: 'dia', citas: [] });
    expect(c.vacio()).toBeTrue();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('No hay citas este día');
  });
});
