/**
 * El día de la agenda como una secuencia: citas y huecos, en orden.
 *
 * Por qué no una tabla
 * --------------------
 * La pantalla anterior mostraba dos listas separadas: las citas en una tabla y
 * los turnos libres como una rejilla de botones en otra columna. Eso responde
 * bien a «quién viene» y muy mal a **«dónde queda sitio»**, que es la pregunta
 * que hace recepción con un paciente delante pidiendo cita.
 *
 * Aquí las dos cosas van en la misma columna y en orden de reloj, así que un
 * hueco de hora y media entre dos citas se ve de un vistazo en lugar de haber
 * que deducirlo comparando dos listas.
 *
 * Por qué los turnos se agrupan
 * -----------------------------
 * El motor de disponibilidad devuelve un turno por cada arranque posible según
 * la granularidad de la sede. Con granularidad de 15 minutos y un servicio de
 * 30, una hora libre son cinco turnos **solapados**: 08:00, 08:15, 08:30,
 * 08:45 y 09:00. Enumerarlos como cinco filas convierte un hueco en un muro de
 * botones y esconde lo único que importa: que hay una hora libre.
 *
 * Se agrupan por solapamiento y se conserva la lista completa, porque la
 * reserva necesita un turno concreto: el grupo es la presentación, el turno es
 * el dato.
 *
 * Por qué se comparan instantes y no cadenas
 * ------------------------------------------
 * `'2026-09-16T13:00:00Z'` y `'2026-09-16T13:00:00+00:00'` son el mismo
 * instante y ordenan distinto como texto. El backend puede devolver cualquiera
 * de las dos formas, así que se ordena por `Date.parse`.
 */
import type { Cita, EstadoCita, TurnoDisponible } from '../modelos/dominio';

/** Una fila de la secuencia del día. */
export type FilaDia =
  | { readonly tipo: 'cita'; readonly inicio: string; readonly cita: Cita }
  | {
      readonly tipo: 'hueco';
      readonly inicio: string;
      readonly fin: string;
      readonly turnos: readonly TurnoDisponible[];
    };

/**
 * Estados cuyo turno **vuelve a estar libre**.
 *
 * Una cita cancelada libera su hueco, así que el motor de disponibilidad ya
 * devuelve ese turno. Mostrar además la fila de la cita cancelada pondría dos
 * filas para la misma hora —una «cancelada» y una «libre»— y eso se lee como
 * un error de la pantalla, no como información.
 *
 * `NO_SHOW` no entra aquí: la hora ya pasó, el turno no se recupera, y saber
 * que alguien no vino es parte de la historia del día.
 */
const LIBERAN_EL_TURNO: readonly EstadoCita[] = ['CANCELLED'];

/**
 * Agrupa los turnos solapados en tramos libres continuos.
 *
 * Dos turnos pertenecen al mismo tramo cuando el siguiente empieza antes de
 * que termine el tramo acumulado —o justo cuando termina—. Así, turnos
 * solapados por granularidad y turnos consecutivos pegados caen en el mismo
 * grupo, y un corte real (un descanso, una cita en medio) abre uno nuevo.
 */
function agruparTurnos(turnos: readonly TurnoDisponible[]): FilaDia[] {
  const ordenados = [...turnos].sort((a, b) => Date.parse(a.inicio) - Date.parse(b.inicio));

  const grupos: { inicio: string; fin: string; turnos: TurnoDisponible[] }[] = [];
  for (const turno of ordenados) {
    const abierto = grupos[grupos.length - 1];
    if (abierto && Date.parse(turno.inicio) <= Date.parse(abierto.fin)) {
      abierto.turnos.push(turno);
      if (Date.parse(turno.fin_consulta) > Date.parse(abierto.fin)) {
        abierto.fin = turno.fin_consulta;
      }
      continue;
    }
    grupos.push({ inicio: turno.inicio, fin: turno.fin_consulta, turnos: [turno] });
  }

  return grupos.map((grupo) => ({
    tipo: 'hueco' as const,
    inicio: grupo.inicio,
    fin: grupo.fin,
    turnos: grupo.turnos,
  }));
}

/**
 * Mezcla las citas del día con los tramos libres en una sola secuencia.
 *
 * `incluirCanceladas` existe porque a veces hay que verlas —una reclamación,
 * una comprobación de por qué se liberó un hueco— pero no es el estado por
 * defecto: no son trabajo pendiente.
 */
export function construirSecuencia(
  citas: readonly Cita[],
  turnos: readonly TurnoDisponible[],
  incluirCanceladas = false,
): readonly FilaDia[] {
  const visibles = incluirCanceladas
    ? citas
    : citas.filter((cita) => !LIBERAN_EL_TURNO.includes(cita.estado));

  const filas: FilaDia[] = [
    ...visibles.map((cita) => ({ tipo: 'cita' as const, inicio: cita.inicio, cita })),
    ...agruparTurnos(turnos),
  ];

  // Con la misma hora, la cita va antes que el hueco: lo comprometido pesa más
  // que lo disponible.
  return filas.sort((a, b) => {
    const diferencia = Date.parse(a.inicio) - Date.parse(b.inicio);
    if (diferencia !== 0) {
      return diferencia;
    }
    return a.tipo === b.tipo ? 0 : a.tipo === 'cita' ? -1 : 1;
  });
}

/** Minutos entre dos instantes. Negativo si el segundo es anterior. */
export function minutosEntre(desde: string, hasta: string): number {
  return Math.round((Date.parse(hasta) - Date.parse(desde)) / 60000);
}

/**
 * Duración en palabras: «45 min», «1 h 30», «2 h».
 *
 * Se escribe así y no en minutos totales porque «90 min libre» obliga a
 * dividir mentalmente, y esto se lee con un paciente delante.
 */
export function duracionLegible(minutos: number): string {
  if (minutos < 60) {
    return `${minutos} min`;
  }
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  return resto === 0 ? `${horas} h` : `${horas} h ${String(resto).padStart(2, '0')}`;
}

/**
 * Minutos de consulta comprometidos por profesional en una lista de citas.
 *
 * Suma `duracion_minutos`, no citas: una primera consulta de 45 minutos y un
 * control de 15 no cargan igual la jornada, y contar «3 citas» iguala cosas
 * que no son iguales.
 *
 * Solo cuenta las que ocupan de verdad la agenda. Una cancelada no ocupa, y
 * una inasistencia ocupó el hueco aunque el paciente no viniera.
 */
export function cargaPorProfesional(citas: readonly Cita[]): ReadonlyMap<string, number> {
  const carga = new Map<string, number>();
  for (const cita of citas) {
    if (cita.estado === 'CANCELLED') {
      continue;
    }
    carga.set(cita.profesional_id, (carga.get(cita.profesional_id) ?? 0) + cita.duracion_minutos);
  }
  return carga;
}
