/** Recursos de identidad propios; un rol personalizado usa el símbolo de acceso. */
const ROLES_CON_ICONO = new Set(['recepcion', 'profesional', 'asistente', 'auditor', 'administradora', 'superadministrador']);

export function rutaIconoRol(codigo: string): string {
  const nombre = codigo === 'administrador_clinica' ? 'administradora' : codigo;
  return `/images/acceso-icono-${ROLES_CON_ICONO.has(nombre) ? nombre : 'seguridad'}.webp`;
}
