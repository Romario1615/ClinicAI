/** API local aislada obligatoria para escenarios que crean datos sintéticos. */
export function apiE2e(): string {
  const configurada = process.env.URL_API;
  if (!configurada) {
    throw new Error('URL_API es obligatoria: inicie la API con la base exclusiva de pruebas descrita en README.md.');
  }

  let destino: URL;
  try {
    destino = new URL(configurada);
  } catch {
    throw new Error('URL_API debe ser una URL absoluta de la API local aislada.');
  }

  if (!['127.0.0.1', 'localhost', '[::1]'].includes(destino.hostname) || destino.port === '8000') {
    throw new Error('URL_API debe apuntar a una API aislada local, nunca a la API compartida de desarrollo en el puerto 8000.');
  }

  if (!destino.pathname.replace(/\/$/, '').endsWith('/api/v1')) {
    throw new Error('URL_API debe terminar en /api/v1.');
  }

  return `${destino.origin}${destino.pathname.replace(/\/$/, '')}`;
}
