import { areaDelRol, especialidadDelRol } from './especialidad-rol';

describe('Especialidad y área del rol', () => {
  it('muestra la especialidad guardada en el perfil', () => {
    expect(especialidadDelRol('Odontología', ['profesional'])).toBe('Especialidad: Odontología');
    expect(especialidadDelRol('Dermatología', ['profesional', 'administrador_clinica'])).toBe('Especialidad: Dermatología');
  });

  it('indica cuándo falta la especialidad de un profesional', () => {
    expect(especialidadDelRol(null, ['profesional'])).toContain('Sin especialidad asignada');
  });

  it('identifica las áreas de los cinco roles operativos', () => {
    for (const rol of ['superadministrador', 'administrador_clinica', 'recepcion', 'asistente', 'auditor']) {
      expect(especialidadDelRol(null, [rol])).toBe(`Área: ${areaDelRol(rol)}`);
      expect(areaDelRol(rol)).not.toBe('Gestión según sus permisos');
    }
  });

  it('maneja roles personalizados y evita repetir áreas', () => {
    expect(especialidadDelRol(undefined, ['coordinador', 'coordinador'])).toBe('Área: Gestión según sus permisos');
    expect(especialidadDelRol(null, [])).toBe('Área: Sin área asignada');
  });
});
