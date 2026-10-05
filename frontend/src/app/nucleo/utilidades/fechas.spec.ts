/**
 * Pruebas del formato de fechas.
 *
 * Son las pruebas más importantes de la capa de utilidades, y no por
 * casualidad: una hora mal en una agenda médica es un paciente que llega
 * cuando no le esperan, o al revés. El error no se ve — la pantalla parece
 * coherente consigo misma — y solo aparece en la sala de espera.
 *
 * Todo se comprueba con zona explícita. Ninguna prueba depende de la zona del
 * equipo que la ejecuta: si dependiera, pasaría en Guayaquil y fallaría en el
 * ejecutor de CI, que va en UTC.
 */
import {
  formatearFecha,
  formatearFechaHora,
  formatearHora,
  hoyEnZona,
  instanteLocal,
  rangoDelDia,
  sumarDias,
} from './fechas';

describe('formato de fechas', () => {
  // 2026-04-15T14:00:00Z = 09:00 en Guayaquil (UTC-5).
  const INSTANTE = '2026-04-15T14:00:00Z';

  it('formatea la hora en la zona indicada, no en la del equipo', () => {
    expect(formatearHora(INSTANTE, 'America/Guayaquil')).toBe('09:00');
    expect(formatearHora(INSTANTE, 'UTC')).toBe('14:00');
    // Madrid en abril está en horario de verano: UTC+2.
    expect(formatearHora(INSTANTE, 'Europe/Madrid')).toBe('16:00');
  });

  it('usa formato de 24 horas', () => {
    // Las 15:00 en formato de 12 horas serían «3:00», y un «3:00» sin AM/PM
    // en una agenda es ambiguo entre la madrugada y la tarde.
    expect(formatearHora('2026-04-15T20:00:00Z', 'America/Guayaquil')).toBe('15:00');
  });

  it('cambia de día según la zona', () => {
    // 02:00 UTC del día 16 todavía es el día 15 en Guayaquil. Usar la fecha
    // UTC desplazaría la agenda un día entero.
    const madrugada = '2026-04-16T02:00:00Z';
    expect(formatearFecha(madrugada, 'UTC')).toBe('16/04/2026');
    expect(formatearFecha(madrugada, 'America/Guayaquil')).toBe('15/04/2026');
  });

  it('una fecha de calendario no se mueve de día con la zona', () => {
    // La fecha de nacimiento 2012-03-01 se mostraba como 29/02/2012.
    expect(formatearFecha('2012-03-01', 'America/Guayaquil')).toBe('01/03/2012');
    expect(formatearFecha('2012-03-01', 'Asia/Tokyo')).toBe('01/03/2012');
  });

  it('combina fecha y hora de forma coherente', () => {
    expect(formatearFechaHora(INSTANTE, 'America/Guayaquil')).toBe('15/04/2026 09:00');
  });
});

describe('instanteLocal', () => {
  it('convierte una hora local de la sede al instante correcto', () => {
    // Las 09:00 en Guayaquil (UTC-5) son las 14:00 UTC.
    const resultado = instanteLocal('2026-04-15', '09:00', 'America/Guayaquil');
    expect(new Date(resultado).toISOString()).toBe('2026-04-15T14:00:00.000Z');
  });

  it('aplica el desplazamiento vigente en esa fecha, no uno fijo', () => {
    // Madrid: UTC+1 en enero, UTC+2 en julio. Un desplazamiento fijo
    // desplazaría media agenda seis meses al año.
    const invierno = instanteLocal('2026-01-15', '09:00', 'Europe/Madrid');
    const verano = instanteLocal('2026-07-15', '09:00', 'Europe/Madrid');

    expect(new Date(invierno).toISOString()).toBe('2026-01-15T08:00:00.000Z');
    expect(new Date(verano).toISOString()).toBe('2026-07-15T07:00:00.000Z');
  });

  it('maneja la medianoche local', () => {
    const resultado = instanteLocal('2026-04-15', '00:00', 'America/Guayaquil');
    expect(new Date(resultado).toISOString()).toBe('2026-04-15T05:00:00.000Z');
  });
});

describe('rangoDelDia', () => {
  it('cubre el día local completo de la sede', () => {
    const { desde, hasta } = rangoDelDia('2026-04-15', 'America/Guayaquil');

    // El día local del 15 en Guayaquil va de las 05:00 UTC del 15 a las
    // 05:00 UTC del 16.
    expect(new Date(desde).toISOString()).toBe('2026-04-15T05:00:00.000Z');
    expect(new Date(hasta).toISOString()).toBe('2026-04-16T05:00:00.000Z');
  });

  it('produce un rango de 24 horas', () => {
    const { desde, hasta } = rangoDelDia('2026-04-15', 'America/Guayaquil');
    const horas = (new Date(hasta).getTime() - new Date(desde).getTime()) / 3_600_000;
    expect(horas).toBe(24);
  });
});

describe('hoyEnZona y sumarDias', () => {
  it('devuelve la fecha en formato AAAA-MM-DD', () => {
    expect(hoyEnZona('America/Guayaquil')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('suma y resta días sin desplazarse por la zona', () => {
    expect(sumarDias('2026-04-15', 1)).toBe('2026-04-16');
    expect(sumarDias('2026-04-15', -1)).toBe('2026-04-14');
  });

  it('cruza el cambio de mes', () => {
    expect(sumarDias('2026-04-30', 1)).toBe('2026-05-01');
    expect(sumarDias('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('cruza el cambio de año', () => {
    expect(sumarDias('2026-12-31', 1)).toBe('2027-01-01');
  });

  it('maneja el 29 de febrero de un año bisiesto', () => {
    // 2028 es bisiesto. Sin esta comprobación, una implementación que
    // asumiera 28 días produciría el 1 de marzo.
    expect(sumarDias('2028-02-28', 1)).toBe('2028-02-29');
    expect(sumarDias('2028-02-29', 1)).toBe('2028-03-01');
  });
});
