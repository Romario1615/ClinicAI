/** El rol define permisos; la especialidad procede del perfil de cada persona. */
export function areaDelRol(codigo: string): string {
  const areas: Record<string, string> = {
    superadministrador: 'Gestión global de clínicas',
    administrador_clinica: 'Administración de clínica',
    recepcion: 'Recepción y agenda',
    asistente: 'Asistencia clínica',
    auditor: 'Auditoría y cumplimiento',
    profesional: 'Atención clínica',
  };
  return areas[codigo] ?? 'Gestión según sus permisos';
}

export function especialidadDelRol(especialidad: string | null | undefined, roles: readonly string[]): string {
  if (especialidad) return `Especialidad: ${especialidad}`;
  if (roles.includes('profesional')) return 'Especialidad: Sin especialidad asignada';
  return `Área: ${[...new Set(roles.map(areaDelRol))].join(' · ') || 'Sin área asignada'}`;
}
