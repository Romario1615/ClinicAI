/**
 * Datos sinteticos del prototipo.
 *
 * REGLA 1 de CLAUDE.md, sin excepciones: nada de aqui puede confundirse con
 * un dato real de paciente. Se aplican las mismas marcas que en las semillas
 * del backend, y por los mismos motivos:
 *
 *  * Los apellidos llevan el sufijo `[SINTETICO]`, visible en cualquier
 *    captura de pantalla y en cualquier volcado.
 *  * Los documentos empiezan por `99`, prefijo que la cedula ecuatoriana no
 *    usa (los dos primeros digitos son el codigo de provincia, 01 a 24).
 *  * Los correos terminan en `example.invalid`, un dominio reservado por el
 *    RFC 2606 que no puede existir: un envio accidental no llega a nadie.
 *  * Los telefonos empiezan por `09999`, fuera de los rangos asignados.
 *
 * Los diagnosticos y medicamentos son de libro de texto y **no describen a
 * ninguna persona**. No se usan para nada clinico: solo para que la pantalla
 * tenga la forma que tendra en produccion.
 */
import type {
  Especialidad,
  Paciente,
  Profesional,
  Sede,
  Servicio,
} from '../nucleo/modelos/dominio';

export const MARCA_SINTETICO = '[SINTETICO]';

export const SEDES: readonly Sede[] = [
  {
    id: 'sede-centro',
    nombre: 'Sede Centro',
    direccion: 'Avenida Ficticia 100 y Calle Inventada',
    zona_horaria: 'America/Guayaquil',
  },
  {
    id: 'sede-norte',
    nombre: 'Sede Norte',
    direccion: 'Calle Imaginaria 250',
    zona_horaria: 'America/Guayaquil',
  },
];

export const ESPECIALIDADES: readonly Especialidad[] = [
  { id: 'esp-odontologia-general', nombre: 'Odontología general' },
  { id: 'esp-ortodoncia', nombre: 'Ortodoncia' },
  { id: 'esp-endodoncia', nombre: 'Endodoncia' },
  { id: 'esp-periodoncia', nombre: 'Periodoncia' },
  { id: 'esp-odontopediatria', nombre: 'Odontopediatría' },
  { id: 'esp-cirugia-oral', nombre: 'Cirugía oral e implantología' },
  { id: 'esp-rehabilitacion-oral', nombre: 'Rehabilitación oral y prótesis' },
  { id: 'esp-estetica-facial', nombre: 'Estética facial' },
];

/**
 * Duraciones y preparaciones multiplos de 15 a proposito.
 *
 * Encajan con la granularidad de las franjas del motor de disponibilidad; con
 * otros valores se pierde capacidad por redondeo. Es el mismo criterio que en
 * las semillas del backend.
 */
export const SERVICIOS: readonly Servicio[] = [
  {
    id: 'srv-consulta-odontologica',
    especialidad_id: 'esp-odontologia-general',
    nombre: 'Consulta odontológica',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 30,
  },
  {
    id: 'srv-profilaxis',
    especialidad_id: 'esp-odontologia-general',
    nombre: 'Profilaxis dental',
    duracion_minutos: 45,
    minutos_preparacion: 15,
    precio: 40,
  },
  {
    id: 'srv-restauracion-resina',
    especialidad_id: 'esp-odontologia-general',
    nombre: 'Restauración con resina',
    duracion_minutos: 45,
    minutos_preparacion: 15,
    precio: 55,
  },
  {
    id: 'srv-valoracion-ortodoncia',
    especialidad_id: 'esp-ortodoncia',
    nombre: 'Valoración de ortodoncia',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 35,
  },
  {
    id: 'srv-control-ortodoncia',
    especialidad_id: 'esp-ortodoncia',
    nombre: 'Control de ortodoncia',
    duracion_minutos: 30,
    minutos_preparacion: 0,
    precio: 45,
  },
  {
    id: 'srv-endodoncia-unirradicular',
    especialidad_id: 'esp-endodoncia',
    nombre: 'Endodoncia unirradicular',
    duracion_minutos: 60,
    minutos_preparacion: 15,
    precio: 150,
  },
  {
    id: 'srv-raspado-alisado',
    especialidad_id: 'esp-periodoncia',
    nombre: 'Raspado y alisado radicular',
    duracion_minutos: 60,
    minutos_preparacion: 15,
    precio: 90,
  },
  {
    id: 'srv-consulta-odontopediatrica',
    especialidad_id: 'esp-odontopediatria',
    nombre: 'Consulta odontopediátrica',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 30,
  },
  {
    id: 'srv-sellantes',
    especialidad_id: 'esp-odontopediatria',
    nombre: 'Sellantes de fosas y fisuras',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 25,
  },
  {
    id: 'srv-extraccion-simple',
    especialidad_id: 'esp-cirugia-oral',
    nombre: 'Extracción simple',
    duracion_minutos: 45,
    minutos_preparacion: 15,
    precio: 50,
  },
  {
    id: 'srv-valoracion-implante',
    especialidad_id: 'esp-cirugia-oral',
    nombre: 'Valoración de implante',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 40,
  },
  {
    id: 'srv-valoracion-protesis',
    especialidad_id: 'esp-rehabilitacion-oral',
    nombre: 'Valoración de prótesis',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 35,
  },
  {
    id: 'srv-valoracion-estetica-facial',
    especialidad_id: 'esp-estetica-facial',
    nombre: 'Valoración estética facial',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 40,
  },
  {
    id: 'srv-tratamiento-facial',
    especialidad_id: 'esp-estetica-facial',
    nombre: 'Tratamiento facial',
    duracion_minutos: 60,
    minutos_preparacion: 15,
    precio: 80,
  },
];

export const PROFESIONALES: readonly Profesional[] = [
  {
    id: 'prof-1',
    especialidad_id: 'esp-odontologia-general',
    nombre: 'Ana',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99001',
  },
  {
    id: 'prof-2',
    especialidad_id: 'esp-ortodoncia',
    nombre: 'Bruno',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99002',
  },
  {
    id: 'prof-3',
    especialidad_id: 'esp-endodoncia',
    nombre: 'Carla',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99003',
  },
  {
    id: 'prof-4',
    especialidad_id: 'esp-periodoncia',
    nombre: 'Diego',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99004',
  },
  {
    id: 'prof-5',
    especialidad_id: 'esp-estetica-facial',
    nombre: 'Elena',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99005',
  },
];

const NOMBRES_FICTICIOS = [
  'Alba',
  'Bruno',
  'Celia',
  'Dario',
  'Elsa',
  'Fabio',
  'Gala',
  'Hugo',
  'Iria',
  'Jon',
  'Keila',
  'Lois',
  'Marta',
  'Nico',
  'Olga',
  'Pablo',
];

/** Pacientes sinteticos, generados de forma determinista. */
export const PACIENTES: readonly Paciente[] = NOMBRES_FICTICIOS.map((nombre, indice) => ({
  id: `pac-${indice + 1}`,
  tipo_documento: 'CEDULA',
  // Prefijo 99: ninguna cedula ecuatoriana empieza asi.
  numero_documento: `99${String(100000000 + indice * 137).slice(0, 7)}`,
  nombre,
  apellido: `Ejemplo ${MARCA_SINTETICO}`,
  // Prefijo 09999: fuera de los rangos asignados a operadoras.
  telefono_whatsapp: `09999${String(10000 + indice).slice(0, 5)}`,
  correo: `${nombre.toLowerCase()}.ejemplo@example.invalid`,
  nivel_verificacion: 'NO_VERIFICADO',
  fecha_nacimiento: new Date(Date.UTC(1960 + indice * 2, (indice * 3) % 12, 1 + (indice % 27)))
    .toISOString()
    .slice(0, 10),
}));

export function nombrePaciente(id: string): string {
  const paciente = PACIENTES.find((p) => p.id === id);
  return paciente ? `${paciente.nombre} ${paciente.apellido}` : 'Paciente desconocido';
}

export function nombreProfesional(id: string): string {
  const profesional = PROFESIONALES.find((p) => p.id === id);
  return profesional ? `${profesional.nombre} ${profesional.apellido}` : 'Profesional desconocido';
}

export function nombreServicio(id: string): string {
  return SERVICIOS.find((s) => s.id === id)?.nombre ?? 'Servicio desconocido';
}

export function nombreSede(id: string): string {
  return SEDES.find((s) => s.id === id)?.nombre ?? 'Sede desconocida';
}

export function nombreEspecialidad(id: string): string {
  return ESPECIALIDADES.find((e) => e.id === id)?.nombre ?? 'Especialidad desconocida';
}
