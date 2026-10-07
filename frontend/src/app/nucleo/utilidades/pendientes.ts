/**
 * La cola de trabajo: lo que hay que hacer **ahora**, con su plazo.
 *
 * El problema que resuelve
 * -----------------------
 * El panel anterior mostraba «citas del periodo: 128». Es un dato cierto y no
 * sirve para nada a las ocho de la mañana. Lo que necesita quien abre el
 * sistema al empezar el turno es la lista de cosas que se rompen si nadie las
 * toca hoy:
 *
 * * **Un turno bloqueado que caduca.** `HELD` tiene `expira_en`. Al vencer, el
 *   hueco vuelve a la agenda y el paciente se queda sin cita sin que nadie se
 *   lo diga.
 * * **Una oferta de lista de espera sin avisar.** El paciente no tiene
 *   consentimiento para mensajes automáticos: la oferta existe pero él no sabe
 *   nada. Si nadie llama, vence sola y —lo peor— cuenta contra él.
 * * **Una cita sin confirmar.** `PENDING` es la que acaba en inasistencia.
 *   Confirmar es la medida más barata que existe contra el ausentismo.
 *
 * Esto es una función pura a propósito: recibe los datos ya cargados y devuelve
 * las tareas. Así se puede probar la regla («¿qué pasa con una oferta ya
 * vencida?») sin montar componentes, sin HTTP y sin reloj real.
 *
 * El reloj se inyecta
 * -------------------
 * `ahora` es un parámetro y no `Date.now()`, por el mismo motivo que en el
 * backend: una prueba sobre «caduca en 6 minutos» que dependiera del reloj del
 * sistema pasaría hoy y fallaría en la siguiente ejecución.
 */
import type { Cita } from '../modelos/dominio';

/** Naturaleza de la tarea. Decide el icono y el color, no el texto. */
export type ClasePendiente = 'caduca' | 'llamar' | 'confirmar';

export interface TareaPendiente {
  readonly clase: ClasePendiente;
  /** Rótulo corto de la categoría: «Caduca», «Nadie ha llamado»… */
  readonly etiqueta: string;
  /** El plazo, en palabras: «en 6 min», «vencido», «2 citas hoy». */
  readonly plazo: string;
  readonly titulo: string;
  readonly detalle: string;
  /** Texto del botón principal. */
  readonly accion: string;
  /**
   * Cierto cuando hay un plazo que corre. Gobierna el color, y el color va
   * siempre acompañado del texto de `etiqueta`: una tarea urgente no se
   * distingue solo por el tono.
   */
  readonly urgente: boolean;
  /** Identificadores sobre los que actuar. Vacío cuando la tarea agrupa. */
  readonly citas: readonly string[];
  readonly entradas: readonly string[];
}

/** Lo que la cola necesita saber de una oferta de lista de espera. */
export interface OfertaSinAvisar {
  readonly id: string;
  readonly oferta_expira_en: string | null;
}

export interface EntradaPendientes {
  readonly citas: readonly Cita[];
  readonly ofertasSinAvisar: readonly OfertaSinAvisar[];
  /** Total real del servidor si la primera página no contiene toda la cola. */
  readonly ofertasSinAvisarTotal?: number;
  readonly ahora: Date;
  /** Traduce un identificador de paciente a un nombre mostrable. */
  readonly nombrePaciente: (id: string) => string;
}

/** Minutos que quedan hasta un instante. Negativo si ya pasó. */
function minutosHasta(instante: string, ahora: Date): number {
  return Math.round((Date.parse(instante) - ahora.getTime()) / 60000);
}

/**
 * Plazo en palabras.
 *
 * Un plazo vencido se dice «vencido», no «en -3 min»: el signo negativo se lee
 * mal y de pasada se confunde con tiempo restante.
 */
function plazoLegible(minutos: number): string {
  if (minutos < 0) {
    return 'vencido';
  }
  if (minutos === 0) {
    return 'ahora';
  }
  if (minutos < 60) {
    return `en ${minutos} min`;
  }
  const horas = Math.floor(minutos / 60);
  return `en ${horas} h`;
}

/** Nombra a una persona, o cuenta cuántas son. Nunca las enumera todas. */
function sujeto(ids: readonly string[], nombre: (id: string) => string, singular: string): string {
  if (ids.length === 1) {
    return nombre(ids[0]);
  }
  return `${ids.length} ${singular}`;
}

/**
 * Deriva la cola de trabajo.
 *
 * El orden es el de urgencia, no el de creación: primero lo que tiene un plazo
 * que corre, y dentro de eso lo que vence antes.
 */
export function derivarPendientes(entrada: EntradaPendientes): readonly TareaPendiente[] {
  const { citas, ofertasSinAvisar, ofertasSinAvisarTotal, ahora, nombrePaciente } = entrada;
  const cantidadOfertas = ofertasSinAvisarTotal ?? ofertasSinAvisar.length;
  const tareas: TareaPendiente[] = [];

  // --- 1. Turnos bloqueados que caducan -----------------------------------
  const bloqueadas = citas
    .filter((cita) => cita.estado === 'HELD' && cita.expira_en !== null)
    .sort((a, b) => Date.parse(a.expira_en as string) - Date.parse(b.expira_en as string));

  if (bloqueadas.length > 0) {
    const primera = bloqueadas[0];
    const minutos = minutosHasta(primera.expira_en as string, ahora);
    tareas.push({
      clase: 'caduca',
      etiqueta: bloqueadas.length === 1 ? 'Caduca' : 'Caduca el primero',
      plazo: plazoLegible(minutos),
      titulo:
        bloqueadas.length === 1
          ? `Turno bloqueado de ${nombrePaciente(primera.paciente_id)}`
          : `${bloqueadas.length} turnos bloqueados sin confirmar`,
      detalle:
        'Al caducar, el hueco vuelve a la agenda y el paciente se queda sin cita sin que nadie se lo diga.',
      accion: bloqueadas.length === 1 ? 'Confirmar' : 'Revisar',
      urgente: true,
      citas: bloqueadas.map((cita) => cita.id),
      entradas: [],
    });
  }

  // --- 2. Ofertas de lista de espera que nadie ha comunicado --------------
  if (cantidadOfertas > 0) {
    const conPlazo = ofertasSinAvisar
      .filter((oferta) => oferta.oferta_expira_en !== null)
      .sort(
        (a, b) =>
          Date.parse(a.oferta_expira_en as string) - Date.parse(b.oferta_expira_en as string),
      );
    const minutos = conPlazo.length > 0
      ? minutosHasta(conPlazo[0].oferta_expira_en as string, ahora)
      : null;

    tareas.push({
      clase: 'llamar',
      etiqueta: 'Nadie ha llamado',
      plazo: minutos === null ? 'sin plazo' : plazoLegible(minutos),
      titulo:
        cantidadOfertas === 1
          ? '1 oferta de lista de espera sin avisar'
          : `${cantidadOfertas} ofertas de lista de espera sin avisar`,
      detalle:
        'Estos pacientes no tienen consentimiento para mensajes automáticos: tienen un turno reservado del que no saben nada. Si nadie llama, el hueco vuelve a la cola.',
      accion: 'Abrir la cola de llamadas',
      urgente: true,
      citas: [],
      entradas: ofertasSinAvisar.map((oferta) => oferta.id),
    });
  }

  // --- 3. Citas creadas y nunca confirmadas -------------------------------
  const sinConfirmar = citas.filter((cita) => cita.estado === 'PENDING');
  if (sinConfirmar.length > 0) {
    tareas.push({
      clase: 'confirmar',
      etiqueta: 'Sin confirmar',
      plazo: sinConfirmar.length === 1 ? '1 cita' : `${sinConfirmar.length} citas`,
      titulo: sujeto(
        sinConfirmar.map((cita) => cita.paciente_id),
        nombrePaciente,
        'pacientes sin confirmar',
      ),
      detalle:
        'Creadas y nunca confirmadas. Son las que acaban en inasistencia; confirmarlas es la medida más barata que hay.',
      accion: sinConfirmar.length === 1 ? 'Confirmar' : 'Ver una a una',
      // No corre ningún plazo: es trabajo del día, no una cuenta atrás. Por eso
      // no se pinta en ámbar; si todo es urgente, nada lo es.
      urgente: false,
      citas: sinConfirmar.map((cita) => cita.id),
      entradas: [],
    });
  }

  return tareas;
}
