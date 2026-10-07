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

import { CODIGOS_ROL, type Rol } from './sesion';

const API = process.env.URL_API ?? 'http://127.0.0.1:8000/api/v1';

export interface Paciente {
  readonly id: string;
  readonly nombre: string;
  readonly apellido: string;
  readonly numero_documento: string | null;
}

export interface PacienteConAlertaAdherencia {
  readonly paciente: Paciente;
  readonly alertaId: string;
}

async function token(peticion: APIRequestContext, rol: Rol): Promise<string> {
  const respuesta = await peticion.post(`${API}/autenticacion/sesion-local`, {
    data: { codigo_rol: CODIGOS_ROL[rol] },
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

  // No basta con la primera página: los pacientes con historia clínica suelen
  // ser anteriores a los más recientes y pueden quedar fuera del límite.
  let desplazamiento = 0;
  let total = Number.POSITIVE_INFINITY;
  while (desplazamiento < total) {
    const listado = await peticion.get(
      `${API}/pacientes/?limite=100&desplazamiento=${desplazamiento}`,
      { headers: cabeceras },
    );
    if (!listado.ok()) {
      throw new Error(`No se pudo preparar la búsqueda clínica: ${listado.status()}`);
    }
    const pagina: { readonly elementos: readonly Paciente[]; readonly total: number } =
      await listado.json();
    for (const paciente of pagina.elementos) {
      const respuesta = await peticion.get(`${API}${ruta(paciente.id)}`, { headers: cabeceras });
      if (respuesta.ok() && tieneDatos(await respuesta.json())) {
        return paciente;
      }
    }
    total = pagina.total;
    desplazamiento += pagina.elementos.length;
    if (pagina.elementos.length === 0) break;
  }
  throw new Error(
    'Ningun paciente del ambito tiene esos datos. ' +
      'Prepare historia clinica sintetica: uv run python -m app.semillas.cargar --solo-historia-clinica',
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

/**
 * Encuentra una pauta sintetica con omisiones suficientes y obtiene su alerta.
 *
 * La API solo prepara el dato de partida; el escenario verifica la lista y la
 * atencion desde el navegador. No se modifica la toma ni se inventa una alerta:
 * el endpoint aplica el mismo umbral de dominio que usa el worker diario.
 */
export async function pacienteConAlertaAdherencia(
  peticion: APIRequestContext,
): Promise<PacienteConAlertaAdherencia> {
  const acceso = await token(peticion, 'profesional');
  const cabeceras = { Authorization: `Bearer ${acceso}` };
  const pacientes: Paciente[] = [];
  let desplazamiento = 0;
  let total = Number.POSITIVE_INFINITY;
  while (desplazamiento < total) {
    const listado = await peticion.get(
      `${API}/pacientes/?limite=100&desplazamiento=${desplazamiento}`,
      { headers: cabeceras },
    );
    if (!listado.ok()) {
      throw new Error(`No se pudo preparar la prueba clínica: ${listado.status()}`);
    }
    const pagina: { readonly elementos: readonly Paciente[]; readonly total: number } =
      await listado.json();
    pacientes.push(...pagina.elementos);
    total = pagina.total;
    desplazamiento += pagina.elementos.length;
    if (pagina.elementos.length === 0) break;
  }
  const respuestaAlertas = await peticion.get(`${API}/historia/adherencia/alertas`, {
    headers: cabeceras,
  });
  if (!respuestaAlertas.ok()) {
    throw new Error(`No se pudieron consultar alertas sintéticas: ${respuestaAlertas.status()}`);
  }
  const alertas: { readonly id: string; readonly receta_id: string }[] =
    await respuestaAlertas.json();

  for (const paciente of pacientes) {
    const [respuestaTomas, respuestaRecetas] = await Promise.all([
      peticion.get(`${API}/historia/pacientes/${paciente.id}/tomas?dias=7`, {
        headers: cabeceras,
      }),
      peticion.get(`${API}/historia/pacientes/${paciente.id}/recetas`, {
        headers: cabeceras,
      }),
    ]);
    if (!respuestaTomas.ok() || !respuestaRecetas.ok()) continue;

    const tomas: {
      readonly receta_medicamento_id: string;
      readonly programada_en: string;
      readonly estado: string;
    }[] = await respuestaTomas.json();
    const recetas: {
      readonly id: string;
      readonly estado: string;
      readonly medicamentos: readonly { readonly id: string }[];
    }[] = await respuestaRecetas.json();

    for (const receta of recetas) {
      if (receta.estado !== 'CONFIRMADA') continue;
      const medicamentos = new Set(receta.medicamentos.map((medicamento) => medicamento.id));
      const esperadas = tomas.filter(
        (toma) =>
          medicamentos.has(toma.receta_medicamento_id) &&
          toma.estado !== 'CANCELADA' &&
          Date.parse(toma.programada_en) <= Date.now(),
      );
      const omitidas = esperadas.filter((toma) =>
        ['PENDIENTE', 'OMITIDA'].includes(toma.estado),
      ).length;
      if (esperadas.length < 4 || omitidas / esperadas.length < 0.25) continue;

      const abierta = alertas.find((alerta) => alerta.receta_id === receta.id);
      if (abierta) return { paciente, alertaId: abierta.id };

      const evaluacion = await peticion.post(
        `${API}/historia/recetas/${receta.id}/adherencia?dias=7`,
        { headers: cabeceras },
      );
      if (!evaluacion.ok()) continue;
      const alertaId = (await evaluacion.json()).alerta?.id as string | undefined;
      if (alertaId) return { paciente, alertaId };
    }
  }

  throw new Error(
    'No hay receta sintética con al menos cuatro tomas pasadas y 25 % de omisiones. ' +
      'Cargue las semillas clínicas y ejecute la prueba cuando el calendario tenga tomas vencidas.',
  );
}
