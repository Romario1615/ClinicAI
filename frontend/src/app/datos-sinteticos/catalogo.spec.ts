import { ESPECIALIDADES, PROFESIONALES, SERVICIOS } from './catalogo';

describe('catálogo sintético dental', () => {
  it('usa las especialidades odontológicas y estética facial de la semilla', () => {
    expect(ESPECIALIDADES.map(especialidad => especialidad.nombre)).toEqual([
      'Odontología general',
      'Ortodoncia',
      'Endodoncia',
      'Periodoncia',
      'Odontopediatría',
      'Cirugía oral e implantología',
      'Rehabilitación oral y prótesis',
      'Estética facial',
    ]);
  });

  it('asigna servicios y profesionales solo a especialidades existentes', () => {
    const ids = new Set(ESPECIALIDADES.map(especialidad => especialidad.id));
    expect(SERVICIOS).toHaveLength(14);
    expect(SERVICIOS.every(servicio => ids.has(servicio.especialidad_id))).toBe(true);
    expect(PROFESIONALES.every(profesional => ids.has(profesional.especialidad_id))).toBe(true);
    expect(SERVICIOS.map(servicio => servicio.nombre)).toContain('Tratamiento facial');
    expect(SERVICIOS.map(servicio => servicio.nombre)).toContain('Endodoncia unirradicular');
  });
});
