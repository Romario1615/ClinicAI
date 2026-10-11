import { rutaIconoRol } from './icono-rol';

describe('Iconos públicos de rol', () => {
  it.each(['recepcion', 'profesional', 'asistente', 'auditor', 'administradora', 'superadministrador'])('resuelve el WebP propio de %s', codigo => {
    expect(rutaIconoRol(codigo)).toBe(`/images/acceso-icono-${codigo}.webp`);
  });
  it.each(['caja_tarde', '../../otro-recurso'])('usa el recurso general para %s', codigo => {
    expect(rutaIconoRol(codigo)).toBe('/images/acceso-icono-seguridad.webp');
  });
  it('reconoce el código de administración que devuelve la API', () => {
    expect(rutaIconoRol('administrador_clinica')).toBe('/images/acceso-icono-administradora.webp');
  });
});
