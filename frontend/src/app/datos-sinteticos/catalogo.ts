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
  { id: 'esp-medicina-general', nombre: 'Medicina General' },
  { id: 'esp-fisioterapia', nombre: 'Fisioterapia' },
  { id: 'esp-nutricion', nombre: 'Nutricion' },
  { id: 'esp-odontologia', nombre: 'Odontologia' },
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
    id: 'srv-consulta-general',
    especialidad_id: 'esp-medicina-general',
    nombre: 'Consulta general',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 25,
  },
  {
    id: 'srv-control',
    especialidad_id: 'esp-medicina-general',
    nombre: 'Control de seguimiento',
    duracion_minutos: 15,
    minutos_preparacion: 15,
    precio: 15,
  },
  {
    id: 'srv-sesion-fisio',
    especialidad_id: 'esp-fisioterapia',
    nombre: 'Sesion de fisioterapia',
    duracion_minutos: 45,
    minutos_preparacion: 15,
    precio: 30,
  },
  {
    id: 'srv-valoracion-nutricional',
    especialidad_id: 'esp-nutricion',
    nombre: 'Valoracion nutricional',
    duracion_minutos: 45,
    minutos_preparacion: 15,
    precio: 35,
  },
  {
    id: 'srv-profilaxis',
    especialidad_id: 'esp-odontologia',
    nombre: 'Profilaxis dental',
    duracion_minutos: 30,
    minutos_preparacion: 15,
    precio: 40,
  },
];

export const PROFESIONALES: readonly Profesional[] = [
  {
    id: 'prof-1',
    especialidad_id: 'esp-medicina-general',
    nombre: 'Ana',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99001',
  },
  {
    id: 'prof-2',
    especialidad_id: 'esp-medicina-general',
    nombre: 'Bruno',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99002',
  },
  {
    id: 'prof-3',
    especialidad_id: 'esp-fisioterapia',
    nombre: 'Carla',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99003',
  },
  {
    id: 'prof-4',
    especialidad_id: 'esp-nutricion',
    nombre: 'Diego',
    apellido: `Demostracion ${MARCA_SINTETICO}`,
    numero_registro_profesional: 'REG-99004',
  },
  {
    id: 'prof-5',
    especialidad_id: 'esp-odontologia',
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
