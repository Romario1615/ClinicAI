/**
 * Formato de fechas y horas, siempre con zona explícita.
 *
 * Por qué no se usa `toLocaleString()` a secas
 * --------------------------------------------
 * Sin `timeZone`, el navegador formatea en la zona del equipo. En una clínica
 * con una sola sede eso coincide con la zona de la clínica **casi siempre**:
 * falla en el portátil de alguien que viaja, en una tableta mal configurada y
 * en un servidor de capturas. El síntoma es una hora desplazada en pantalla
 * mientras la base de datos es correcta, y ese es el error más difícil de
 * detectar porque la interfaz parece coherente consigo misma.
 *
 * Toda función de este módulo exige la zona. La zona viene de la sede, que la
 * hereda de la clínica (ADR‑0010).
 */

/** Opciones base compartidas, para que el formato no varíe entre pantallas. */
const LOCALE = 'es-EC';

export function formatearHora(instanteIso: string, zona: string): string {
  return new Date(instanteIso).toLocaleTimeString(LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: zona,
  });
}

export function formatearFecha(instanteIso: string, zona: string): string {
  return new Date(instanteIso).toLocaleDateString(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    timeZone: zona,
  });
}

export function formatearFechaLarga(instanteIso: string, zona: string): string {
  return new Date(instanteIso).toLocaleDateString(LOCALE, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: zona,
  });
}

export function formatearFechaHora(instanteIso: string, zona: string): string {
  return `${formatearFecha(instanteIso, zona)} ${formatearHora(instanteIso, zona)}`;
}

/**
 * Rango de un día completo en la zona indicada, devuelto en ISO con
 * desplazamiento.
 *
 * Se construye a partir de la fecha **local de la sede**, no de la del
 * navegador. A las 02:00 UTC en Guayaquil todavía es el día anterior: usar la
 * fecha UTC desplazaría la agenda un día entero.
 */
export function rangoDelDia(fechaLocal: string, zona: string): { desde: string; hasta: string } {
  const desde = instanteLocal(fechaLocal, '00:00', zona);
  const siguiente = new Date(`${fechaLocal}T00:00:00Z`);
  siguiente.setUTCDate(siguiente.getUTCDate() + 1);
  const hasta = instanteLocal(siguiente.toISOString().slice(0, 10), '00:00', zona);
  return { desde, hasta };
}

/**
 * Convierte una fecha y hora locales de la sede en un instante ISO con
 * desplazamiento explícito.
 *
 * El desplazamiento se calcula **para esa fecha concreta** y no se fija: una
 * zona con horario de verano cambia de desplazamiento a lo largo del año, y
 * un valor fijo desplazaría media agenda seis meses al año. Ecuador no aplica
 * horario de verano, pero el sistema admite sedes en otros husos y no puede
 * asumirlo.
 */
export function instanteLocal(fechaLocal: string, horaLocal: string, zona: string): string {
  const [horas, minutos] = horaLocal.split(':').map(Number);
  const tentativo = new Date(`${fechaLocal}T${pad(horas)}:${pad(minutos)}:00Z`);
  const desplazamientoMinutos = desplazamientoZona(tentativo, zona);
  const corregido = new Date(tentativo.getTime() - desplazamientoMinutos * 60_000);
  return corregido.toISOString();
}

/** Desplazamiento de la zona, en minutos, para un instante dado. */
function desplazamientoZona(instante: Date, zona: string): number {
  // `formatToParts` con la zona da los componentes locales; la diferencia
  // entre reinterpretarlos como UTC y el instante original es el
  // desplazamiento. Es la forma de obtenerlo sin una biblioteca de zonas.
  const formateador = new Intl.DateTimeFormat('en-US', {
    timeZone: zona,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const partes = Object.fromEntries(
    formateador.formatToParts(instante).map((parte) => [parte.type, parte.value]),
  );
  // `hour` puede venir como "24" a medianoche en algunas implementaciones.
  const hora = partes['hour'] === '24' ? '00' : partes['hour'];
  const comoUtc = Date.UTC(
    Number(partes['year']),
    Number(partes['month']) - 1,
    Number(partes['day']),
    Number(hora),
    Number(partes['minute']),
    Number(partes['second']),
  );
  return (comoUtc - instante.getTime()) / 60_000;
}

/** Fecha de hoy en la zona de la sede, en formato `AAAA-MM-DD`. */
export function hoyEnZona(zona: string): string {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: zona,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
  // `en-CA` produce directamente AAAA-MM-DD.
  return partes;
}

/** Suma días a una fecha `AAAA-MM-DD` sin tocar zonas. */
export function sumarDias(fechaLocal: string, dias: number): string {
  const fecha = new Date(`${fechaLocal}T00:00:00Z`);
  fecha.setUTCDate(fecha.getUTCDate() + dias);
  return fecha.toISOString().slice(0, 10);
}

function pad(valor: number): string {
  return String(valor).padStart(2, '0');
}
