/**
 * Localiza datos de partida por API, para que los escenarios sean deterministas.
 *
 * Por que se prepara por API y se actua por interfaz
 * -------------------------------------------------
 * Recorrer la pantalla haciendo clic hasta dar con un paciente que tenga
 * calendario de tomas hace la prueba lenta y, sobre todo, **dependiente de los
 * datos**: funciona mientras el sembrador no cambie, y falla mas adelante por
 * un motivo que no tiene nada que ver con lo que se esta comprobando.
 *
 * Lo que se prueba sigue siendo la interfaz. La API solo responde «sobre quien
 * hay que probarlo».
 */
import type { APIRequestContext } from '@playwright/test';

import { CONTRASENA, CUENTAS, type Rol } from './sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

export interface Paciente {
  readonly id: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly numero_documento: string | null;
}

async function token(peticion: APIRequestContext, rol: Rol): Promise<string> {
  const clinicaId = process.env.CLINICA_ID;
  if (!clinicaId) {
    throw new Error('Falta CLINICA_ID.');
  }
  const respuesta = await peticion.post(`${API}/autenticacion/sesion`, {
    data: { correo: CUENTAS[rol], contrasena: CONTRASENA, clinica_id: clinicaId },
  });
  if (!respuesta.ok()) {
    throw new Error(`No se pudo iniciar sesion como ${rol}: ${respuesta.status()}`);
  }
  return (await respuesta.json()).token_acceso;
}

/** Primer paciente del ambito que cumple el predicado sobre una ruta clinica. */
async function buscarPaciente(
  peticion: APIRequestContext,
  rol: Rol,
  ruta: (id: string) => string,
  tieneDatos: (cuerpo: unknown) => boolean,
): Promise<Paciente> {
  const acceso = await token(peticion, rol);
  const cabeceras = { Authorization: `Bearer ${acceso}` };

  const listado = await peticion.get(`${API}/pacientes/?limite=50`, { headers: cabeceras });
  const pacientes: Paciente[] = (await listado.json()).elementos;

  for (const paciente of pacientes) {
    const respuesta = await peticion.get(`${API}${ruta(paciente.id)}`, { headers: cabeceras });
    if (respuesta.ok() && tieneDatos(await respuesta.json())) {
      return paciente;
    }
  }
  throw new Error(
    'Ningun paciente del ambito tiene esos datos. ' +
      'Ejecute la carga de semillas: uv run python -m app.semillas.cargar',
  );
}

/** Paciente con historia clinica registrada. */
export function pacienteConNotas(peticion: APIRequestContext, rol: Rol = 'profesional') {
  return buscarPaciente(
    peticion,
    rol,
    (id) => `/historia/pacientes/${id}/notas?incluir_historico=true`,
    (cuerpo) => Array.isArray(cuerpo) && cuerpo.length > 0,
  );
}

/** Paciente cuya historia tiene al menos una version anterior conservada. */
export function pacienteConVersionAnterior(peticion: APIRequestContext) {
  return buscarPaciente(
    peticion,
    'profesional',
    (id) => `/historia/pacientes/${id}/notas?incluir_historico=true`,
    (cuerpo) =>
      Array.isArray(cuerpo) &&
      cuerpo.some((nota: { vigente?: boolean }) => nota.vigente === false),
  );
}

/** Paciente con calendario de tomas en la ventana por defecto. */
export function pacienteConTomas(peticion: APIRequestContext, rol: Rol = 'profesional') {
  return buscarPaciente(
    peticion,
    rol,
    (id) => `/historia/pacientes/${id}/tomas?dias=7`,
    (cuerpo) => Array.isArray(cuerpo) && cuerpo.length > 0,
  );
}
